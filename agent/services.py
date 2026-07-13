"""
agent/services.py

Agent uchun avtomatik hisob-kitob funksiyalari.
"""
from django.db.models import Sum
from apps.models import Payment


def calculate_daily_cash_collected(agent, target_date):
    """
    Berilgan sana uchun shu agentga tegishli nakladnoylar bo'yicha
    TASDIQLANGAN (confirmed=True) naqd to'lovlar yig'indisini hisoblaydi.

    Bu — agent o'sha kuni mijozlardan naqd pul sifatida yig'gan summa
    (ya'ni "Berildi" / "ostatka" maydoni uchun taklif qilinadigan qiymat).
    """
    return (
            Payment.objects
            .filter(
                order__agent=agent,
                method='cash',
                confirmed=True,
                date_created__date=target_date,
            )
            .aggregate(s=Sum('amount'))['s'] or 0
    )
