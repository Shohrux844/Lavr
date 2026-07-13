from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Sum, Count, Q
from django.utils import timezone
from django.http import JsonResponse
from datetime import date, timedelta
import calendar

from agent.models import AgentBalance, Agent
from client.forms import ClienteForm
from client.models import Cliente, OrderRequest
from .models import (
    Product,
    Order, OrderItem, Payment, Salary,
    PointOfInterest, Visit, StockMovement,
    OrderReturn, OrderReturnItem,
)
from .forms import (
    ProductForm,
    OrderForm, OrderUpdateForm, OrderItemFormSet, PaymentForm, SalaryForm,
    PointOfInterestForm, VisitForm,
)
from .decorators import admin_required
from .stock import record_stock_movement
from . import telegram_bot


class StockError(Exception):
    """
    Sklad yetarli emasligi haqida xato — transaction.atomic() blok ichida
    ko'tarilganda, blokdagi BARCHA o'zgarishlarni (order, itemlar, boshqa
    tovarlarning stock kamayishi) avtomatik bekor qiladi (rollback).
    """
    pass


# ════════════════════════════════════════════════
# DASHBOARD — YORDAMCHI FUNKSIYALAR
# ════════════════════════════════════════════════

def _resolve_period(request, prefix=''):
    today = date.today()
    period = request.GET.get(f'{prefix}period', 'month')
    date_from_raw = request.GET.get(f'{prefix}date_from', '')
    date_to_raw = request.GET.get(f'{prefix}date_to', '')

    if date_from_raw and date_to_raw:
        return date_from_raw, date_to_raw, 'custom'

    if period == 'today':
        return today.isoformat(), today.isoformat(), 'today'
    elif period == 'week':
        start = today - timedelta(days=today.weekday())
        return start.isoformat(), today.isoformat(), 'week'
    elif period == 'year':
        start = today.replace(month=1, day=1)
        return start.isoformat(), today.isoformat(), 'year'
    else:
        start = today.replace(day=1)
        return start.isoformat(), today.isoformat(), 'month'


def _period_stats(date_from, date_to, firma=''):
    orders = Order.objects.filter(
        date_created__date__gte=date_from,
        date_created__date__lte=date_to,
    ).exclude(status='cancelled')

    if firma:
        orders = orders.filter(cliente__firma_name=firma)

    total_sales = orders.aggregate(s=Sum('total_sum'))['s'] or 0

    total_collected = (
            Payment.objects.filter(
                order__in=orders, confirmed=True,
            ).aggregate(s=Sum('amount'))['s'] or 0
    )

    total_debt = total_sales - total_collected

    return {
        'date_from': date_from,
        'date_to': date_to,
        'orders_count': orders.count(),
        'total_sales': total_sales,
        'total_collected': total_collected,
        'total_debt': total_debt,
    }


def _agent_stats(date_from, date_to, firma=''):
    agents = Agent.objects.filter(is_active=True)
    result = []
    for agent in agents:
        orders = Order.objects.filter(
            agent=agent,
            date_created__date__gte=date_from,
            date_created__date__lte=date_to,
        ).exclude(status='cancelled')
        if firma:
            orders = orders.filter(cliente__firma_name=firma)

        sales = orders.aggregate(s=Sum('total_sum'))['s'] or 0
        commission = int(sales * float(agent.commission_rate) / 100)
        result.append({
            'agent': agent,
            'sales': sales,
            'commission_rate': agent.commission_rate,
            'commission': commission,
        })
    result.sort(key=lambda r: r['sales'], reverse=True)
    return result


def _cliente_stats(date_from, date_to, firma='', limit=8):
    clientes = Cliente.objects.filter(is_active=True)
    if firma:
        clientes = clientes.filter(firma_name=firma)

    result = []
    for cliente in clientes:
        orders = Order.objects.filter(
            cliente=cliente,
            date_created__date__gte=date_from,
            date_created__date__lte=date_to,
        ).exclude(status='cancelled')

        total_sales = orders.aggregate(s=Sum('total_sum'))['s'] or 0
        if total_sales == 0:
            continue

        total_paid = (
                Payment.objects.filter(order__in=orders, confirmed=True)
                .aggregate(s=Sum('amount'))['s'] or 0
        )
        debt = total_sales - total_paid
        result.append({
            'cliente': cliente,
            'total_sales': total_sales,
            'total_paid': total_paid,
            'debt': debt,
        })
    result.sort(key=lambda r: r['debt'], reverse=True)
    return result[:limit]


def _percent_change(old, new):
    if old == 0:
        return None
    return round(((new - old) / old) * 100, 1)


# ════════════════════════════════════════════════
# DASHBOARD
# ════════════════════════════════════════════════

@admin_required
def dashboard(request):
    today = date.today()

    firma = request.GET.get('firma', '')
    firma_list = (
        Cliente.objects.filter(is_active=True)
        .exclude(firma_name='')
        .values_list('firma_name', flat=True)
        .distinct()
        .order_by('firma_name')
    )

    date_from, date_to, period = _resolve_period(request)
    period_stats = _period_stats(date_from, date_to, firma)
    agent_stats = _agent_stats(date_from, date_to, firma)
    cliente_stats = _cliente_stats(date_from, date_to, firma)

    comparison = None
    cmp1_from = request.GET.get('cmp1_date_from', '')
    cmp1_to = request.GET.get('cmp1_date_to', '')
    cmp2_from = request.GET.get('cmp2_date_from', '')
    cmp2_to = request.GET.get('cmp2_date_to', '')

    if cmp1_from and cmp1_to and cmp2_from and cmp2_to:
        stats1 = _period_stats(cmp1_from, cmp1_to, firma)
        stats2 = _period_stats(cmp2_from, cmp2_to, firma)
        comparison = {
            'period1': stats1,
            'period2': stats2,
            'sales_change': _percent_change(stats1['total_sales'], stats2['total_sales']),
            'collected_change': _percent_change(stats1['total_collected'], stats2['total_collected']),
            'debt_change': _percent_change(stats1['total_debt'], stats2['total_debt']),
            'orders_change': _percent_change(stats1['orders_count'], stats2['orders_count']),
        }

    today_orders = Order.objects.filter(date_created__date=today)
    total_income_today = (
            Payment.objects.filter(date_created__date=today, confirmed=True)
            .aggregate(s=Sum('amount'))['s'] or 0
    )
    active_agents = Agent.objects.filter(is_active=True).count()

    low_stock_products = Product.objects.filter(is_active=True, stock__gt=0, stock__lte=10)
    out_of_stock = Product.objects.filter(is_active=True, stock=0)

    recent_orders = Order.objects.select_related('cliente', 'agent')[:10]

    agent_balances = AgentBalance.objects.filter(date=today).select_related('agent')

    context = {
        'today_orders_count': today_orders.count(),
        'total_income_today': total_income_today,
        'low_stock_count': low_stock_products.count() + out_of_stock.count(),
        'active_agents': active_agents,
        'low_stock_products': low_stock_products,
        'out_of_stock': out_of_stock,
        'recent_orders': recent_orders,
        'agent_balances': agent_balances,
        'today': today,

        'period': period,
        'date_from': date_from,
        'date_to': date_to,
        'period_stats': period_stats,
        'agent_stats': agent_stats,
        'cliente_stats': cliente_stats,
        'firma': firma,
        'firma_list': firma_list,

        'comparison': comparison,
        'cmp1_from': cmp1_from,
        'cmp1_to': cmp1_to,
        'cmp2_from': cmp2_from,
        'cmp2_to': cmp2_to,
    }
    return render(request, 'dashboard.html', context)


def models_low_threshold():
    return 10


# ════════════════════════════════════════════════
# PRODUCT (Tovar / Sklad)
# ════════════════════════════════════════════════

@admin_required
def product_list(request):
    status_filter = request.GET.get('status', '')
    q = request.GET.get('q', '')

    products = Product.objects.filter(is_active=True)
    if q:
        products = products.filter(
            Q(name__icontains=q) | Q(sku__icontains=q)
        )
    if status_filter == 'low':
        products = products.filter(stock__gt=0, stock__lte=10)
    elif status_filter == 'out':
        products = products.filter(stock=0)

    paginator = Paginator(products, 24)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {'products': page_obj, 'page_obj': page_obj, 'q': q, 'status_filter': status_filter}
    return render(request, 'products/list.html', context)


@admin_required
def product_detail(request, pk):
    product = get_object_or_404(Product, pk=pk)
    recent_items = product.order_items.select_related('order__cliente')[:10]
    recent_movements = product.stock_movements.select_related('order', 'created_by')[:15]
    return render(request, 'products/detail.html', {
        'product': product,
        'recent_items': recent_items,
        'recent_movements': recent_movements,
    })


@admin_required
def product_create(request):
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, "Tovar qo'shildi.")
            return redirect('product_list')
    else:
        form = ProductForm()
    return render(request, 'products/form.html', {'form': form, 'title': "Yangi tovar"})


@admin_required
def product_update(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        old_stock = product.stock
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            with transaction.atomic():
                updated_product = form.save()
                diff = updated_product.stock - old_stock
                if diff != 0:
                    StockMovement.objects.create(
                        product=updated_product,
                        movement_type=StockMovement.MovementType.MANUAL,
                        quantity_change=diff,
                        stock_after=updated_product.stock,
                        note="Admin tomonidan qo'lda tuzatildi",
                        created_by=request.user,
                    )
            messages.success(request, "Tovar yangilandi.")
            return redirect('product_detail', pk=pk)
    else:
        form = ProductForm(instance=product)
    return render(request, 'products/form.html', {'form': form, 'title': "Tovarni tahrirlash"})


@admin_required
def product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        product.is_active = False
        product.save()
        messages.success(request, "Tovar o'chirildi.")
        return redirect('product_list')
    return render(request, 'confirm_delete.html', {'object': product, 'type': 'Tovar'})


# ════════════════════════════════════════════════
# ORDER (Nakladnoy)
# ════════════════════════════════════════════════

@admin_required
def order_list(request):
    status_filter = request.GET.get('status', '')
    q = request.GET.get('q', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    orders = Order.objects.select_related('cliente', 'agent').all()

    if q:
        orders = orders.filter(
            Q(number__icontains=q) |
            Q(cliente__first_name__icontains=q) |
            Q(cliente__firma_name__icontains=q) |
            Q(agent__first_name__icontains=q)
        )
    if status_filter:
        orders = orders.filter(status=status_filter)
    if date_from:
        orders = orders.filter(date_created__date__gte=date_from)
    if date_to:
        orders = orders.filter(date_created__date__lte=date_to)

    paginator = Paginator(orders, 30)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'orders': page_obj,
        'page_obj': page_obj,
        'q': q,
        'status_filter': status_filter,
        'date_from': date_from,
        'date_to': date_to,
        'status_choices': Order.Status.choices,
    }
    return render(request, 'orders/list.html', context)


@admin_required
def order_detail(request, pk):
    order = get_object_or_404(
        Order.objects.select_related('cliente', 'agent').prefetch_related('items__product'),
        pk=pk
    )
    payments = order.payments.all()
    total_paid = payments.filter(confirmed=True).aggregate(s=Sum('amount'))['s'] or 0
    remaining_debt = order.total_sum - total_paid

    context = {
        'order': order,
        'payments': payments,
        'total_paid': total_paid,
        'remaining_debt': remaining_debt,
    }
    return render(request, 'orders/detail.html', context)


@admin_required
def order_create(request):
    if request.method == 'POST':
        form = OrderForm(request.POST, request.FILES)
        formset = OrderItemFormSet(request.POST, prefix='items')
        if form.is_valid() and formset.is_valid():
            real_items = [
                f for f in formset
                if not f.cleaned_data.get('DELETE') and f.cleaned_data.get('product')
            ]

            if not real_items:
                messages.error(request, "Kamida bitta tovar qo'shishingiz kerak.")
            else:
                order = None
                try:
                    with transaction.atomic():
                        order = form.save()
                        total = 0
                        for item_form in real_items:
                            product = item_form.cleaned_data.get('product')
                            quantity = item_form.cleaned_data.get('quantity')

                            # ─── Qatorni QULFLAYMIZ (select_for_update) ───
                            # Shu tovar ustida boshqa parallel so'rov ham
                            # ishlayotgan bo'lsa, u shu yerda navbatga turadi
                            # va faqat biz tranzaksiyani tugatgandan keyin
                            # eng SO'NGGI (yangilangan) stock qiymatini o'qiydi.
                            locked_product = Product.objects.select_for_update().get(pk=product.pk)

                            if quantity > locked_product.stock:
                                raise StockError(
                                    f"Skladda faqat {locked_product.stock} dona "
                                    f"'{locked_product.name}' bor (so'ralgan: {quantity})."
                                )

                            item = item_form.save(commit=False)
                            item.order = order
                            item.save()
                            total += item.subtotal

                            record_stock_movement(
                                locked_product, -quantity,
                                StockMovement.MovementType.SALE,
                                order=order, user=request.user,
                                note=f"{order.number} orqali sotildi",
                            )

                        order.total_sum = total
                        order.save()
                except StockError as e:
                    # Butun tranzaksiya (order + itemlar + stock o'zgarishlari)
                    # avtomatik bekor qilindi — hech qanday yarim-chala yozuv qolmaydi.
                    messages.error(request, str(e))
                else:
                    messages.success(request, f"{order.number} nakladnoy yaratildi.")
                    return redirect('order_detail', pk=order.pk)
        else:
            error_parts = []
            if form.errors:
                for field, errs in form.errors.items():
                    error_parts.append(f"[{field}]: {', '.join(errs)}")
            if formset.errors:
                for i, form_errors in enumerate(formset.errors):
                    if form_errors:
                        for field, errs in form_errors.items():
                            error_parts.append(f"[Tovar qator {i + 1} - {field}]: {', '.join(errs)}")
            if formset.non_form_errors():
                error_parts.append(f"[Formset]: {', '.join(formset.non_form_errors())}")

            messages.error(
                request,
                "Forma xatolari: " + " | ".join(error_parts) if error_parts else "Noma'lum xato yuz berdi."
            )
    else:
        form = OrderForm()
        formset = OrderItemFormSet(prefix='items')

    return render(request, 'orders/form.html', {
        'form': form,
        'formset': formset,
        'title': "Yangi nakladnoy",
    })


@admin_required
def order_update(request, pk):
    order = get_object_or_404(Order, pk=pk)
    if request.method == 'POST':
        form = OrderUpdateForm(request.POST, request.FILES, instance=order)
        if form.is_valid():
            form.save()
            messages.success(request, "Nakladnoy yangilandi.")
            return redirect('order_detail', pk=pk)
    else:
        form = OrderUpdateForm(instance=order)
    return render(request, 'orders/update_form.html', {'form': form, 'order': order})


@admin_required
def order_delete(request, pk):
    order = get_object_or_404(Order, pk=pk)

    if order.status == Order.Status.CANCELLED:
        messages.warning(request, "Bu nakladnoy allaqachon bekor qilingan.")
        return redirect('order_detail', pk=pk)

    if request.method == 'POST':
        with transaction.atomic():
            # ─── Sklad hisobini tiklaymiz ───
            # Nakladnoy bekor qilinganda, undagi tovarlar sklad hisobiga
            # qaytarib qo'yiladi (aks holda tovar "yo'qolib qoladi").
            # select_for_update — bir vaqtda boshqa buyurtma shu tovarni
            # sotayotgan bo'lsa ham, hisob to'g'ri qolishi uchun.
            for item in order.items.select_related('product').all():
                locked_product = Product.objects.select_for_update().get(pk=item.product_id)
                record_stock_movement(
                    locked_product, item.quantity,
                    StockMovement.MovementType.RETURN,
                    order=order, user=request.user,
                    note=f"{order.number} bekor qilingani sababli qaytarildi",
                )

            # Yozuv o'chirilmaydi — faqat holati "bekor qilingan"ga o'zgaradi.
            # Shu bilan moliyaviy tarix (audit) butunlay saqlanib qoladi.
            order.status = Order.Status.CANCELLED
            order.save()

        messages.success(request, f"{order.number} nakladnoy bekor qilindi, sklad hisobiga tovarlar qaytarildi.")
        return redirect('order_detail', pk=pk)

    return render(request, 'confirm_delete.html', {'object': order, 'type': 'Nakladnoy'})


@admin_required
def order_return_create(request, pk):
    """
    Mijoz sotib olgan tovarni (to'liq yoki qisman) qaytarganda ishlatiladi.

    MUHIM: OrderItem.quantity ning O'ZI kamaytiriladi (shunchaki alohida
    yozuv qilinmaydi) — shuning uchun admin, agent va mijoz panellaridagi
    nakladnoy sahifalari BARCHASI avtomatik yangi (qaytarilgandan keyingi)
    miqdorni ko'rsatadi, chunki ular bir xil order.items.all() dan o'qiydi.
    Har bir vozvrat, shunga qaramay, OrderReturn/OrderReturnItem orqali
    alohida audit-yozuv sifatida ham saqlanadi.
    """
    order = get_object_or_404(Order.objects.prefetch_related('items__product'), pk=pk)

    if order.status == Order.Status.CANCELLED:
        messages.error(request, "Bekor qilingan nakladnoy uchun vozvrat qilib bo'lmaydi.")
        return redirect('order_detail', pk=pk)

    # Faqat hali qoldig'i bor (quantity > 0) tovarlarni ko'rsatamiz
    items_info = [
        {'item': item, 'remaining': item.quantity}
        for item in order.items.select_related('product').all()
        if item.quantity > 0
    ]

    if request.method == 'POST':
        note = request.POST.get('note', '')
        rows_to_process = []
        has_error = False

        for info in items_info:
            item = info['item']
            try:
                qty = int(request.POST.get(f'qty_{item.pk}', '0') or 0)
            except ValueError:
                qty = 0
            if qty <= 0:
                continue
            if qty > item.quantity:
                messages.error(
                    request,
                    f"'{item.product.name}' uchun ko'pi bilan {item.quantity} dona "
                    f"qaytarish mumkin (kiritildi: {qty})."
                )
                has_error = True
            else:
                rows_to_process.append((item, qty))

        if not has_error and not rows_to_process:
            messages.error(request, "Kamida bitta tovar uchun qaytariladigan miqdorni kiriting.")
            has_error = True

        if not has_error:
            with transaction.atomic():
                order_return = OrderReturn.objects.create(order=order, note=note, created_by=request.user)
                total_returned = 0

                for item, qty in rows_to_process:
                    OrderReturnItem.objects.create(
                        order_return=order_return, product=item.product,
                        quantity=qty, price=item.price,
                    )
                    total_returned += qty * item.price

                    # ─── OrderItem.quantity ning o'zini kamaytiramiz ───
                    # Shu bilan admin/agent/mijoz panellarida nakladnoy
                    # sahifasi avtomatik yangi miqdorni ko'rsatadi.
                    item.quantity -= qty
                    item.save()

                    locked_product = Product.objects.select_for_update().get(pk=item.product_id)
                    record_stock_movement(
                        locked_product, qty,
                        StockMovement.MovementType.CLIENT_RETURN,
                        order=order, user=request.user,
                        note=f"{order.number} — mijoz qaytardi (vozvrat #{order_return.pk})",
                    )

                order.total_sum -= total_returned
                order.save()
                _update_order_status(order)

            messages.success(
                request,
                f"Vozvrat qayd etildi — {total_returned:,.0f} so'm nakladnoy summasidan ayirildi, "
                f"sklad tiklandi."
            )
            return redirect('order_detail', pk=pk)

    return render(request, 'orders/return_form.html', {
        'order': order,
        'items_info': items_info,
    })


# ════════════════════════════════════════════════
# PAYMENT (To'lov / Perechesleniye)
# ════════════════════════════════════════════════

@admin_required
def payment_list(request):
    method_filter = request.GET.get('method', '')
    confirmed_filter = request.GET.get('confirmed', '')
    q = request.GET.get('q', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    payments = Payment.objects.select_related('order__cliente', 'order__agent').all()

    if method_filter:
        payments = payments.filter(method=method_filter)
    if confirmed_filter == '1':
        payments = payments.filter(confirmed=True)
    elif confirmed_filter == '0':
        payments = payments.filter(confirmed=False)
    if q:
        payments = payments.filter(
            Q(order__number__icontains=q) |
            Q(order__cliente__first_name__icontains=q) |
            Q(order__cliente__last_name__icontains=q) |
            Q(order__cliente__firma_name__icontains=q) |
            Q(order__cliente__alternative_name__icontains=q)
        )
    if date_from:
        payments = payments.filter(date_created__date__gte=date_from)
    if date_to:
        payments = payments.filter(date_created__date__lte=date_to)

    payments = payments.order_by('-date_created')

    total_amount = payments.aggregate(s=Sum('amount'))['s'] or 0

    paginator = Paginator(payments, 30)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'payments': page_obj,
        'page_obj': page_obj,
        'total_amount': total_amount,
        'method_filter': method_filter,
        'confirmed_filter': confirmed_filter,
        'q': q,
        'date_from': date_from,
        'date_to': date_to,
        'method_choices': Payment.Method.choices,
    }
    return render(request, 'payments/list.html', context)


@admin_required
def payment_create(request, order_pk):
    order = get_object_or_404(Order, pk=order_pk)
    if request.method == 'POST':
        form = PaymentForm(request.POST, request.FILES)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.order = order
            payment.save()
            if payment.method == 'cash':
                payment.confirmed = True
                payment.save()
            _update_order_status(order)
            messages.success(request, "To'lov kiritildi.")
            return redirect('order_detail', pk=order_pk)
    else:
        form = PaymentForm()
    return render(request, 'payments/form.html', {
        'form': form,
        'order': order,
        'title': "To'lov kiritish",
    })


@admin_required
def payment_confirm(request, pk):
    payment = get_object_or_404(Payment, pk=pk)
    if request.method == 'POST':
        payment.confirmed = True
        payment.save()
        _update_order_status(payment.order)
        messages.success(request, "To'lov tasdiqlandi.")
    return redirect('order_detail', pk=payment.order.pk)


def _update_order_status(order):
    total_paid = (
            order.payments.filter(confirmed=True)
            .aggregate(s=Sum('amount'))['s'] or 0
    )
    if total_paid >= order.total_sum:
        order.status = Order.Status.PAID
    elif total_paid > 0:
        order.status = Order.Status.DEBT
    order.save()


# ════════════════════════════════════════════════
# SALARY (Maosh)
# ════════════════════════════════════════════════

@admin_required
def salary_list(request):
    month_filter = request.GET.get('month', '')
    salaries = Salary.objects.select_related('agent').all()
    if month_filter:
        salaries = salaries.filter(month__startswith=month_filter)
    return render(request, 'salaries/list.html', {
        'salaries': salaries,
        'month_filter': month_filter,
    })


@admin_required
def salary_calculate(request):
    if request.method == 'POST':
        today = date.today()
        month_start = today.replace(day=1)
        agents = Agent.objects.filter(is_active=True)
        created_count = 0

        for agent in agents:
            total_sales = (
                    Order.objects.filter(
                        agent=agent,
                        status=Order.Status.PAID,
                        date_created__year=today.year,
                        date_created__month=today.month,
                    ).aggregate(s=Sum('total_sum'))['s'] or 0
            )
            salary, created = Salary.objects.get_or_create(
                agent=agent,
                month=month_start,
                defaults={
                    'commission_rate': agent.commission_rate,
                    'total_sales': total_sales,
                    'bonus': 0,
                }
            )
            salary.total_sales = total_sales
            salary.commission_rate = agent.commission_rate
            salary.calculate()
            if created:
                created_count += 1

        messages.success(
            request,
            f"{today.strftime('%B %Y')} uchun {agents.count()} ta agent maoshi hisoblandi."
        )
        return redirect('salary_list')

    return render(request, 'salaries/calculate_confirm.html')


@admin_required
def salary_detail(request, pk):
    salary = get_object_or_404(Salary.objects.select_related('agent'), pk=pk)
    return render(request, 'salaries/detail.html', {'salary': salary})


@admin_required
def salary_update(request, pk):
    salary = get_object_or_404(Salary, pk=pk)
    if request.method == 'POST':
        form = SalaryForm(request.POST, instance=salary)
        if form.is_valid():
            s = form.save(commit=False)
            s.calculate()
            messages.success(request, "Maosh yangilandi.")
            return redirect('salary_detail', pk=pk)
    else:
        form = SalaryForm(instance=salary)
    return render(request, 'salaries/form.html', {'form': form, 'salary': salary})


@admin_required
def salary_mark_paid(request, pk):
    salary = get_object_or_404(Salary, pk=pk)
    if request.method == 'POST':
        salary.status = Salary.Status.PAID
        salary.date_paid = date.today()
        salary.save()
        messages.success(request, f"{salary.agent} maoshi to'landi deb belgilandi.")
    return redirect('salary_list')


# ════════════════════════════════════════════════
# AJAX — product narxini olish (order form uchun)
# ════════════════════════════════════════════════

@admin_required
def get_product_price(request):
    product_id = request.GET.get('product_id')
    if not product_id:
        return JsonResponse({'error': 'product_id kerak'}, status=400)
    try:
        product = Product.objects.get(pk=product_id, is_active=True)
        return JsonResponse({'price': product.price, 'stock': product.stock})
    except Product.DoesNotExist:
        return JsonResponse({'error': 'Tovar topilmadi'}, status=404)


@admin_required
def stock_movement_list(request):
    q = request.GET.get('q', '')
    movement_type = request.GET.get('movement_type', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    movements = StockMovement.objects.select_related('product', 'order', 'created_by').all()

    if q:
        movements = movements.filter(
            Q(product__name__icontains=q) |
            Q(product__sku__icontains=q) |
            Q(note__icontains=q) |
            Q(order__number__icontains=q)
        )
    if movement_type:
        movements = movements.filter(movement_type=movement_type)
    if date_from:
        movements = movements.filter(date_created__date__gte=date_from)
    if date_to:
        movements = movements.filter(date_created__date__lte=date_to)

    paginator = Paginator(movements, 40)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'movements': page_obj,
        'page_obj': page_obj,
        'q': q,
        'movement_type': movement_type,
        'date_from': date_from,
        'date_to': date_to,
        'movement_type_choices': StockMovement.MovementType.choices,
    }
    return render(request, 'stock_movements/list.html', context)


# ════════════════════════════════════════════════
# NUQTALAR (AZS / Avto-do'kon) — xarita
# ════════════════════════════════════════════════

@admin_required
def point_map(request):
    points = PointOfInterest.objects.filter(is_active=True).select_related('cliente')
    points_data = []
    for p in points:
        debt = 0
        if p.cliente:
            orders = Order.objects.filter(cliente=p.cliente).exclude(status='cancelled')
            total_sales = orders.aggregate(s=Sum('total_sum'))['s'] or 0
            total_paid = Payment.objects.filter(
                order__in=orders, confirmed=True
            ).aggregate(s=Sum('amount'))['s'] or 0
            debt = total_sales - total_paid

        points_data.append({
            'id': p.pk,
            'name': p.name,
            'kind': p.get_kind_display(),
            'lat': p.latitude,
            'lng': p.longitude,
            'has_contract': p.has_contract,
            'cliente': str(p.cliente) if p.cliente else None,
            'debt': debt,
            'address': p.address,
            'phone': p.phone,
        })

    return render(request, 'points/map.html', {
        'points': points,
        'points_json': points_data,
    })


@admin_required
def point_list(request):
    points = PointOfInterest.objects.filter(is_active=True).select_related('cliente')
    return render(request, 'points/list.html', {'points': points})


@admin_required
def point_create(request):
    if request.method == 'POST':
        form = PointOfInterestForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Nuqta qo'shildi.")
            return redirect('point_list')
    else:
        form = PointOfInterestForm()
    return render(request, 'points/form.html', {'form': form, 'title': "Yangi nuqta (AZS/Do'kon)"})


@admin_required
def point_update(request, pk):
    point = get_object_or_404(PointOfInterest, pk=pk)
    if request.method == 'POST':
        form = PointOfInterestForm(request.POST, instance=point)
        if form.is_valid():
            form.save()
            messages.success(request, "Nuqta yangilandi.")
            return redirect('point_list')
    else:
        form = PointOfInterestForm(instance=point)
    return render(request, 'points/form.html', {'form': form, 'title': "Nuqtani tahrirlash"})


@admin_required
def point_delete(request, pk):
    point = get_object_or_404(PointOfInterest, pk=pk)
    if request.method == 'POST':
        point.is_active = False
        point.save()
        messages.success(request, "Nuqta o'chirildi.")
        return redirect('point_list')
    return render(request, 'confirm_delete.html', {'object': point, 'type': 'Nuqta'})


# ════════════════════════════════════════════════
# TASHRIFLAR (Visit) — Telegram bilan
# ════════════════════════════════════════════════

@admin_required
def visit_create(request):
    """
    ⚠️ XAVFSIZLIK ESLATMASI:
    Bu — ADMIN panel funksiyasi (@admin_required bilan himoyalangan), shuning
    uchun bu yerda 'agent' ni POST'dan olish xavfli emas — chunki faqat
    ishonchli admin/xodim bu formani to'ldira oladi va u istalgan agent
    nomidan tashrif kiritishi ATAYLAB ruxsat etilgan (masalan qog'oz
    jurnaldan ma'lumot kiritish uchun).

    AGAR kelajakda agentlar o'zlari (agent panelidan) tashrif kiritadigan
    bo'lsa — bu funksiyani NUSXA olmang! Bunday holatda agentni HECH QACHON
    POST'dan olmang, faqat quyidagicha, tizimga kirgan foydalanuvchining
    o'z profilidan oling:
        visit.agent = request.user.agent_profile
    Aks holda istalgan agent boshqa agent nomidan yozib qo'yishi mumkin (IDOR).
    """
    if request.method == 'POST':
        form = VisitForm(request.POST)
        if form.is_valid():
            agent_id = request.POST.get('agent')
            agent = Agent.objects.filter(pk=agent_id, is_active=True).first() if agent_id else None

            if not agent:
                messages.error(request, "Agentni tanlashingiz shart.")
                agents = Agent.objects.filter(is_active=True)
                return render(request, 'points/visit_form.html', {'form': form, 'agents': agents})

            visit = form.save(commit=False)
            visit.agent = agent
            visit.save()

            point = visit.point
            if point.has_contract:
                orders = Order.objects.filter(cliente=point.cliente).exclude(status='cancelled')
                total_sales = orders.aggregate(s=Sum('total_sum'))['s'] or 0
                total_paid = Payment.objects.filter(
                    order__in=orders, confirmed=True
                ).aggregate(s=Sum('amount'))['s'] or 0
                debt = total_sales - total_paid
                telegram_bot.notify_visit_report(visit, debt_amount=debt)
            else:
                telegram_bot.notify_new_point(visit)

            messages.success(request, "Tashrif belgilandi va Telegramga xabar yuborildi.")
            return redirect('point_map')
    else:
        form = VisitForm()

    agents = Agent.objects.filter(is_active=True)
    return render(request, 'points/visit_form.html', {'form': form, 'agents': agents})


@admin_required
def visit_list(request):
    visits = Visit.objects.select_related('agent', 'point', 'point__cliente').all()
    return render(request, 'points/visit_list.html', {'visits': visits})


# ════════════════════════════════════════════════
# BUYURTMA SO'ROVLARI (mijozdan kelgan)
# ════════════════════════════════════════════════

@admin_required
def order_request_list(request):
    status_filter = request.GET.get('status', '')
    requests_qs = OrderRequest.objects.select_related('cliente').prefetch_related('items__product')
    if status_filter:
        requests_qs = requests_qs.filter(status=status_filter)
    pending_count = OrderRequest.objects.filter(status=OrderRequest.Status.PENDING).count()
    return render(request, 'order_requests/list.html', {
        'requests': requests_qs,
        'status_filter': status_filter,
        'pending_count': pending_count,
        'status_choices': OrderRequest.Status.choices,
    })


@admin_required
def order_request_detail(request, pk):
    req = get_object_or_404(
        OrderRequest.objects.select_related('cliente').prefetch_related('items__product'),
        pk=pk
    )
    return render(request, 'order_requests/detail.html', {'req': req})


@admin_required
def order_request_approve(request, pk):
    req = get_object_or_404(OrderRequest, pk=pk)
    if request.method != 'POST':
        return redirect('order_request_detail', pk=pk)

    if req.status != OrderRequest.Status.PENDING:
        messages.warning(request, "Bu so'rov allaqachon ko'rib chiqilgan.")
        return redirect('order_request_detail', pk=pk)

    nak_picture = request.FILES.get('nak_picture')
    if not nak_picture:
        messages.error(request, "Tasdiqlashdan oldin nakladnoy rasmini yuklashingiz shart.")
        return redirect('order_request_detail', pk=pk)

    items = list(req.items.select_related('product').all())
    if not items:
        messages.error(request, "So'rovda tovar yo'q.")
        return redirect('order_request_detail', pk=pk)

    agent = req.cliente.agent
    if not agent:
        messages.error(request, "Mijozga agent biriktirilmagan — avval mijoz profilida agent tanlang.")
        return redirect('order_request_detail', pk=pk)

    order = None
    try:
        with transaction.atomic():
            order = Order.objects.create(
                cliente=req.cliente,
                agent=agent,
                payment_type=Order.PaymentType.DEBT,
                note=req.note,
                nak_picture=nak_picture,
            )
            total = 0
            for item in items:
                # ─── Qatorni QULFLAYMIZ — parallel tasdiqlashlarda ham
                # sklad hisobi noto'g'ri bo'lib qolmasligi uchun.
                locked_product = Product.objects.select_for_update().get(pk=item.product_id)

                if item.quantity > locked_product.stock:
                    raise StockError(
                        f"Skladda faqat {locked_product.stock} dona '{locked_product.name}' bor "
                        f"(so'ralgan: {item.quantity})."
                    )

                OrderItem.objects.create(
                    order=order, product=locked_product,
                    quantity=item.quantity, price=item.price,
                )
                total += item.subtotal
                record_stock_movement(
                    locked_product, -item.quantity,
                    StockMovement.MovementType.SALE,
                    order=order, user=request.user,
                    note=f"{order.number} (mijoz so'rovi #{req.pk}) orqali sotildi",
                )

            order.total_sum = total
            order.save()

            req.status = OrderRequest.Status.APPROVED
            req.order = order
            req.date_reviewed = timezone.now()
            req.save()
    except StockError as e:
        # Butun tranzaksiya (order, itemlar, sklad, so'rov holati) bekor
        # qilindi — so'rov hali ham "kutilmoqda" holatida qoladi.
        messages.error(request, str(e))
        return redirect('order_request_detail', pk=pk)

    messages.success(request, f"So'rov tasdiqlandi — {order.number} nakladnoy yaratildi.")
    return redirect('order_detail', pk=order.pk)


@admin_required
def order_request_reject(request, pk):
    req = get_object_or_404(OrderRequest, pk=pk)
    if request.method == 'POST':
        req.admin_note = request.POST.get('admin_note', '')
        req.status = OrderRequest.Status.REJECTED
        req.date_reviewed = timezone.now()
        req.save()
        messages.success(request, "So'rov rad etildi.")
    return redirect('order_request_list')
