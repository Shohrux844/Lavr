"""
apps/management/commands/send_debt_reminders.py

Har kuni cron orqali ishga tushiriladigan buyruq — belgilangan kundan
ortiq to'lanmagan qarzi bor mijozlar haqida adminga Telegram orqali
eslatma yuboradi.

ISHLATISH:
    python manage.py send_debt_reminders
    python manage.py send_debt_reminders --days 7     (standart: 5 kun)

CRON'GA ULASH (har kuni ertalab soat 9:00 da ishga tushirish uchun):
    0 9 * * *  cd /loyiha/manzili && /loyiha/venv/bin/python manage.py send_debt_reminders

    (crontab -e buyrug'i orqali qo'shing)
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Sum
from django.utils import timezone

from client.models import Cliente
from apps.models import Order, Payment
from apps import telegram_bot


class Command(BaseCommand):
    help = "N kundan ortiq to'lanmagan qarzi bor mijozlar haqida Telegram orqali eslatma yuboradi."

    def add_arguments(self, parser):
        parser.add_argument(
            '--days', type=int, default=5,
            help="Necha kundan ortiq to'lanmagan nakladnoy 'eskirgan' deb hisoblansin (standart: 5)."
        )

    def handle(self, *args, **options):
        days_threshold = options['days']
        cutoff_date = timezone.now() - timedelta(days=days_threshold)

        clientes = Cliente.objects.filter(is_active=True).select_related('agent')
        sent_count = 0

        for cliente in clientes:
            orders = Order.objects.filter(cliente=cliente).exclude(status='cancelled')
            total_sales = orders.aggregate(s=Sum('total_sum'))['s'] or 0
            total_paid = Payment.objects.filter(
                order__in=orders, confirmed=True
            ).aggregate(s=Sum('amount'))['s'] or 0
            debt = total_sales - total_paid

            if debt <= 0:
                continue

            # Shu mijozning eng ESKI, hali to'liq to'lanmagan (qarzli/kutilmoqda)
            # nakladnoyini topamiz — shu asosida "necha kun o'tgani"ni hisoblaymiz.
            oldest_unpaid_order = (
                orders.filter(status__in=['debt', 'pending'])
                .order_by('date_created')
                .first()
            )
            if not oldest_unpaid_order:
                continue

            if oldest_unpaid_order.date_created > cutoff_date:
                continue  # hali "eskirgan" hisoblanmaydi

            days_overdue = (timezone.now() - oldest_unpaid_order.date_created).days

            sent = telegram_bot.notify_debt_reminder(
                cliente=cliente,
                debt_amount=debt,
                days_overdue=days_overdue,
                oldest_order_number=oldest_unpaid_order.number,
            )
            if sent:
                sent_count += 1
                self.stdout.write(self.style.SUCCESS(
                    f"✓ {cliente} — {debt:,.0f} so'm qarz, {days_overdue} kun — eslatma yuborildi."
                ))
            else:
                self.stdout.write(self.style.WARNING(
                    f"✗ {cliente} — eslatma yuborilmadi (Telegram xatosi, log'ni tekshiring)."
                ))

        self.stdout.write(self.style.SUCCESS(
            f"\nTugadi. Jami {sent_count} ta eslatma yuborildi "
            f"({days_threshold} kundan ortiq qarzdorlar uchun)."
        ))
