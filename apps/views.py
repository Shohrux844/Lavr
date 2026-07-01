from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Count, Q
from django.utils import timezone
from django.http import JsonResponse
from datetime import date, timedelta
import calendar

from .models import (
    Agent, AgentBalance, Cliente, Product,
    Order, OrderItem, Payment, Salary,
    PointOfInterest, Visit,
)
from .forms import (
    AgentForm, AgentBalanceForm, ClienteForm, ProductForm,
    OrderForm, OrderUpdateForm, OrderItemFormSet, PaymentForm, SalaryForm,
    PointOfInterestForm, VisitForm,
)
from . import telegram_bot


# ════════════════════════════════════════════════
# DASHBOARD — YORDAMCHI FUNKSIYALAR
# ════════════════════════════════════════════════

def _resolve_period(request, prefix=''):
    """
    Tezkor tugma (today/week/month/year) yoki qo'lda sana oralig'idan
    boshlanish/tugash sanalarini hisoblab beradi.

    prefix — bir nechta davr (masalan solishtirish uchun 2 ta) bo'lganda
    GET parametr nomlarini ajratish uchun, masalan 'cmp1_', 'cmp2_'.
    """
    today = date.today()
    period = request.GET.get(f'{prefix}period', 'month')
    date_from_raw = request.GET.get(f'{prefix}date_from', '')
    date_to_raw = request.GET.get(f'{prefix}date_to', '')

    # Qo'lda sana kiritilgan bo'lsa, u ustun turadi
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
    else:  # month — default
        start = today.replace(day=1)
        return start.isoformat(), today.isoformat(), 'month'


def _period_stats(date_from, date_to, firma=''):
    """
    Berilgan sana oralig'i (va ixtiyoriy firma) uchun umumiy statistika:
    umumiy savdo, yig'ilgan pul, qolgan qarz.
    """
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
    """Har bir agent uchun: savdo summasi va komissiya summasi (tanlangan davrda)."""
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
    # Eng ko'p sotgan agent yuqorida
    result.sort(key=lambda r: r['sales'], reverse=True)
    return result


def _cliente_stats(date_from, date_to, firma='', limit=8):
    """Har bir mijoz uchun: to'lagan pul va qolgan qarz (tanlangan davrda)."""
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
    # Eng katta qarzi bor mijozlar yuqorida
    result.sort(key=lambda r: r['debt'], reverse=True)
    return result[:limit]


def _percent_change(old, new):
    """Eski va yangi qiymat orasidagi foiz o'zgarish. Eski 0 bo'lsa None qaytaradi."""
    if old == 0:
        return None
    return round(((new - old) / old) * 100, 1)


# ════════════════════════════════════════════════
# DASHBOARD
# ════════════════════════════════════════════════

@login_required
def dashboard(request):
    today = date.today()

    # ─── 0. Firma filtri (ixtiyoriy) ───
    firma = request.GET.get('firma', '')
    firma_list = (
        Cliente.objects.filter(is_active=True)
        .exclude(firma_name='')
        .values_list('firma_name', flat=True)
        .distinct()
        .order_by('firma_name')
    )

    # ─── 1. Joriy davr (tezkor tugma yoki qo'lda sana) ───
    date_from, date_to, period = _resolve_period(request)
    period_stats = _period_stats(date_from, date_to, firma)
    agent_stats = _agent_stats(date_from, date_to, firma)
    cliente_stats = _cliente_stats(date_from, date_to, firma)

    # ─── 2. Solishtirish bloki (ixtiyoriy, ikki davr) ───
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

    # ─── 3. Eski statistikalar (bugungi kun uchun, o'zgarmagan) ───
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

        # Davr filtri va statistika
        'period': period,
        'date_from': date_from,
        'date_to': date_to,
        'period_stats': period_stats,
        'agent_stats': agent_stats,
        'cliente_stats': cliente_stats,
        'firma': firma,
        'firma_list': firma_list,

        # Solishtirish
        'comparison': comparison,
        'cmp1_from': cmp1_from,
        'cmp1_to': cmp1_to,
        'cmp2_from': cmp2_from,
        'cmp2_to': cmp2_to,
    }
    return render(request, 'dashboard.html', context)


def models_low_threshold():
    """Yordamchi: stock_threshold uchun."""
    return 10


# ════════════════════════════════════════════════
# AGENT
# ════════════════════════════════════════════════

@login_required
def agent_list(request):
    agents = Agent.objects.filter(is_active=True).annotate(
        order_count=Count('orders'),
        total_sales=Sum('orders__total_sum'),
    )
    return render(request, 'agents/list.html', {'agents': agents})


@login_required
def agent_detail(request, pk):
    agent = get_object_or_404(Agent, pk=pk)
    orders = agent.orders.all()[:20]
    balances = agent.balances.all()[:10]
    salaries = agent.salaries.all()[:6]
    today_balance = agent.balances.filter(date=date.today()).first()

    context = {
        'agent': agent,
        'orders': orders,
        'balances': balances,
        'salaries': salaries,
        'today_balance': today_balance,
    }
    return render(request, 'agents/detail.html', context)


@login_required
def agent_create(request):
    if request.method == 'POST':
        form = AgentForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Agent muvaffaqiyatli qo'shildi.")
            return redirect('agent_list')
    else:
        form = AgentForm()
    return render(request, 'agents/form.html', {'form': form, 'title': "Yangi agent"})


@login_required
def agent_update(request, pk):
    agent = get_object_or_404(Agent, pk=pk)
    if request.method == 'POST':
        form = AgentForm(request.POST, instance=agent)
        if form.is_valid():
            form.save()
            messages.success(request, "Agent ma'lumotlari yangilandi.")
            return redirect('agent_detail', pk=pk)
    else:
        form = AgentForm(instance=agent)
    return render(request, 'agents/form.html', {'form': form, 'title': "Agentni tahrirlash"})


@login_required
def agent_delete(request, pk):
    agent = get_object_or_404(Agent, pk=pk)
    if request.method == 'POST':
        agent.is_active = False
        agent.save()
        messages.success(request, "Agent o'chirildi.")
        return redirect('agent_list')
    return render(request, 'confirm_delete.html', {'object': agent, 'type': 'Agent'})


# ════════════════════════════════════════════════
# AGENT BALANCE (Ostatka)
# ════════════════════════════════════════════════

@login_required
def agent_balance_list(request):
    today = date.today()
    balances = (
        AgentBalance.objects.filter(date=today)
        .select_related('agent')
        .order_by('-given_amount')
    )
    return render(request, 'balances/list.html', {
        'balances': balances,
        'today': today,
    })


@login_required
def agent_balance_create(request):
    if request.method == 'POST':
        form = AgentBalanceForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Ostatka kiritildi.")
            return redirect('agent_balance_list')
    else:
        form = AgentBalanceForm()
    return render(request, 'balances/form.html', {'form': form, 'title': "Ostatka kiritish"})


@login_required
def agent_balance_update(request, pk):
    balance = get_object_or_404(AgentBalance, pk=pk)
    if request.method == 'POST':
        form = AgentBalanceForm(request.POST, instance=balance)
        if form.is_valid():
            form.save()
            messages.success(request, "Ostatka yangilandi.")
            return redirect('agent_balance_list')
    else:
        form = AgentBalanceForm(instance=balance)
    return render(request, 'balances/form.html', {'form': form, 'title': "Ostatkani tahrirlash"})


# ════════════════════════════════════════════════
# CLIENTE (Mijoz)
# ════════════════════════════════════════════════

@login_required
def cliente_list(request):
    q = request.GET.get('q', '')
    clientes = Cliente.objects.filter(is_active=True).select_related('agent')
    if q:
        clientes = clientes.filter(
            Q(first_name__icontains=q) |
            Q(last_name__icontains=q) |
            Q(firma_name__icontains=q) |
            Q(alternative_name__icontains=q) |
            Q(phone__icontains=q)
        )
    return render(request, 'clientes/list.html', {'clientes': clientes, 'q': q})


@login_required
def cliente_detail(request, pk):
    cliente = get_object_or_404(Cliente, pk=pk)
    orders = cliente.orders.all()[:20]
    total_debt = (
            cliente.orders.filter(status='debt')
            .aggregate(s=Sum('total_sum'))['s'] or 0
    )
    context = {'cliente': cliente, 'orders': orders, 'total_debt': total_debt}
    return render(request, 'clientes/detail.html', context)


@login_required
def cliente_create(request):
    if request.method == 'POST':
        form = ClienteForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Mijoz qo'shildi.")
            return redirect('cliente_list')
    else:
        form = ClienteForm()
    return render(request, 'clientes/form.html', {'form': form, 'title': "Yangi mijoz"})


@login_required
def cliente_update(request, pk):
    cliente = get_object_or_404(Cliente, pk=pk)
    if request.method == 'POST':
        form = ClienteForm(request.POST, instance=cliente)
        if form.is_valid():
            form.save()
            messages.success(request, "Mijoz yangilandi.")
            return redirect('cliente_detail', pk=pk)
    else:
        form = ClienteForm(instance=cliente)
    return render(request, 'clientes/form.html', {'form': form, 'title': "Mijozni tahrirlash"})


@login_required
def cliente_delete(request, pk):
    cliente = get_object_or_404(Cliente, pk=pk)
    if request.method == 'POST':
        cliente.is_active = False
        cliente.save()
        messages.success(request, "Mijoz o'chirildi.")
        return redirect('cliente_list')
    return render(request, 'confirm_delete.html', {'object': cliente, 'type': 'Mijoz'})


# ════════════════════════════════════════════════
# PRODUCT (Tovar / Sklad)
# ════════════════════════════════════════════════

@login_required
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

    context = {'products': products, 'q': q, 'status_filter': status_filter}
    return render(request, 'products/list.html', context)


@login_required
def product_detail(request, pk):
    product = get_object_or_404(Product, pk=pk)
    recent_items = product.order_items.select_related('order__cliente')[:10]
    return render(request, 'products/detail.html', {
        'product': product,
        'recent_items': recent_items,
    })


@login_required
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


@login_required
def product_update(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            form.save()
            messages.success(request, "Tovar yangilandi.")
            return redirect('product_detail', pk=pk)
    else:
        form = ProductForm(instance=product)
    return render(request, 'products/form.html', {'form': form, 'title': "Tovarni tahrirlash"})


@login_required
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

@login_required
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

    context = {
        'orders': orders,
        'q': q,
        'status_filter': status_filter,
        'date_from': date_from,
        'date_to': date_to,
        'status_choices': Order.Status.choices,
    }
    return render(request, 'orders/list.html', context)


@login_required
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


@login_required
def order_create(request):
    if request.method == 'POST':
        form = OrderForm(request.POST, request.FILES)
        formset = OrderItemFormSet(request.POST, prefix='items')
        if form.is_valid() and formset.is_valid():
            # Bo'sh (DELETE=True belgilangan) qatorlarni chiqarib,
            # haqiqiy tovar qatorlari borligini tekshirish
            real_items = [
                f for f in formset
                if not f.cleaned_data.get('DELETE') and f.cleaned_data.get('product')
            ]

            if not real_items:
                messages.error(request, "Kamida bitta tovar qo'shishingiz kerak.")
            else:
                # Skladda yetarli miqdor borligini oldindan tekshirish
                stock_error = False
                for item_form in real_items:
                    product = item_form.cleaned_data.get('product')
                    quantity = item_form.cleaned_data.get('quantity')
                    if product and quantity and quantity > product.stock:
                        item_form.add_error(
                            'quantity',
                            f"Skladda faqat {product.stock} dona '{product.name}' bor."
                        )
                        stock_error = True

                if not stock_error:
                    order = form.save()
                    total = 0
                    for item_form in real_items:
                        item = item_form.save(commit=False)
                        item.order = order
                        item.save()
                        total += item.subtotal
                        # Skladdan ayirish
                        item.product.stock -= item.quantity
                        item.product.save()
                    # Jami summani hisoblash
                    order.total_sum = total
                    order.save()
                    messages.success(request, f"{order.number} nakladnoy yaratildi.")
                    return redirect('order_detail', pk=order.pk)
        else:
            # Aniq qaysi maydonda xato borligini ko'rsatish
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


@login_required
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


@login_required
def order_delete(request, pk):
    order = get_object_or_404(Order, pk=pk)
    if request.method == 'POST':
        order.delete()
        messages.success(request, "Nakladnoy o'chirildi.")
        return redirect('order_list')
    return render(request, 'confirm_delete.html', {'object': order, 'type': 'Nakladnoy'})


# ════════════════════════════════════════════════
# PAYMENT (To'lov / Perechesleniye)
# ════════════════════════════════════════════════

@login_required
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

    context = {
        'payments': payments,
        'total_amount': total_amount,
        'method_filter': method_filter,
        'confirmed_filter': confirmed_filter,
        'q': q,
        'date_from': date_from,
        'date_to': date_to,
        'method_choices': Payment.Method.choices,
    }
    return render(request, 'payments/list.html', context)


@login_required
def payment_create(request, order_pk):
    order = get_object_or_404(Order, pk=order_pk)
    if request.method == 'POST':
        form = PaymentForm(request.POST, request.FILES)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.order = order
            payment.save()
            # Agar naqd bo'lsa, avtomatik tasdiqlash
            if payment.method == 'cash':
                payment.confirmed = True
                payment.save()
            # Order statusini yangilash
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


@login_required
def payment_confirm(request, pk):
    """Bank to'lovini tasdiqlash."""
    payment = get_object_or_404(Payment, pk=pk)
    if request.method == 'POST':
        payment.confirmed = True
        payment.save()
        _update_order_status(payment.order)
        messages.success(request, "To'lov tasdiqlandi.")
    return redirect('order_detail', pk=payment.order.pk)


def _update_order_status(order):
    """To'lovlar asosida order statusini avtomatik yangilash."""
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

@login_required
def salary_list(request):
    month_filter = request.GET.get('month', '')
    salaries = Salary.objects.select_related('agent').all()
    if month_filter:
        salaries = salaries.filter(month__startswith=month_filter)
    return render(request, 'salaries/list.html', {
        'salaries': salaries,
        'month_filter': month_filter,
    })


@login_required
def salary_calculate(request):
    """
    Joriy oy uchun barcha agentlarning maoshini avtomatik hisoblash.
    POST so'rov bilan ishlaydi.
    """
    if request.method == 'POST':
        today = date.today()
        month_start = today.replace(day=1)
        agents = Agent.objects.filter(is_active=True)
        created_count = 0

        for agent in agents:
            # O'sha oy sotuvi
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
            salary.calculate()  # commission_amount va total_salary ni hisoblaydi
            if created:
                created_count += 1

        messages.success(
            request,
            f"{today.strftime('%B %Y')} uchun {agents.count()} ta agent maoshi hisoblandi."
        )
        return redirect('salary_list')

    return render(request, 'salaries/calculate_confirm.html')


@login_required
def salary_detail(request, pk):
    salary = get_object_or_404(Salary.objects.select_related('agent'), pk=pk)
    return render(request, 'salaries/detail.html', {'salary': salary})


@login_required
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


@login_required
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

@login_required
def get_product_price(request):
    """
    AJAX: ?product_id=5 → {"price": 48000, "stock": 23}
    Nakladnoy formida tovar tanlanganda narxni avtomatik to'ldirish uchun.
    """
    product_id = request.GET.get('product_id')
    if not product_id:
        return JsonResponse({'error': 'product_id kerak'}, status=400)
    try:
        product = Product.objects.get(pk=product_id, is_active=True)
        return JsonResponse({'price': product.price, 'stock': product.stock})
    except Product.DoesNotExist:
        return JsonResponse({'error': 'Tovar topilmadi'}, status=404)


# ════════════════════════════════════════════════
# NUQTALAR (AZS / Avto-do'kon) — xarita
# ════════════════════════════════════════════════

@login_required
def point_map(request):
    """
    Xarita sahifasi: barcha AZS/do'konlarni ko'rsatadi.
    Shartnomasi bor (yashil) / yo'q (qizil) rang bilan ajraladi.
    """
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


@login_required
def point_list(request):
    points = PointOfInterest.objects.filter(is_active=True).select_related('cliente')
    return render(request, 'points/list.html', {'points': points})


@login_required
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


@login_required
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


@login_required
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

@login_required
def visit_create(request):
    """
    Agent tashrifni belgilash sahifasi. Saqlangandan keyin
    avtomatik ravishda Telegramga mos xabar yuboriladi:
    - Agar nuqtada shartnoma (cliente) bo'lmasa → "yangi mijoz" xabari
    - Agar shartnoma bor bo'lsa → qarzdorlik bilan tashrif hisoboti
    """
    if request.method == 'POST':
        form = VisitForm(request.POST)
        if form.is_valid():
            visit = form.save(commit=False)
            # Hozircha agentni so'rovdan emas, formdan yoki
            # tizimga kirgan foydalanuvchiga bog'liq agentdan olamiz.
            # Oddiy holatda: ro'yxatdan agentni alohida tanlash maydoni qo'shilgan.
            agent_id = request.POST.get('agent')
            if agent_id:
                visit.agent = get_object_or_404(Agent, pk=agent_id)
            visit.save()

            point = visit.point
            if point.has_contract:
                # Qarzdorlikni hisoblash
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


@login_required
def visit_list(request):
    visits = Visit.objects.select_related('agent', 'point', 'point__cliente').all()
    return render(request, 'points/visit_list.html', {'visits': visits})
