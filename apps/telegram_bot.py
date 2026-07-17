"""
Telegram xabarlarini yuborish uchun yordamchi modul.
Bu faylni apps/telegram_bot.py sifatida saqlang.

ISHLATISH UCHUN KERAK:
1. Telegram'da @BotFather orqali bot yarating, BOT_TOKEN oling.
2. Botni guruhga (yoki o'zingizning shaxsiy chatingizga) qo'shing.
3. Guruh/chat ID sini aniqlang (pastdagi "CHAT ID OLISH" bo'limiga qarang).
4. settings.py ga TELEGRAM_BOT_TOKEN va TELEGRAM_CHAT_ID qo'shing.

BACKGROUND YUBORISH:
Telegram API sekinlashsa yoki ishlamay qolsa, foydalanuvchi so'rovi
kutib qolmasligi uchun notify_* funksiyalar `run_async()` yordamida
alohida (daemon) thread'da ishga tushiriladi — natijada view darhol
javob qaytaradi, Telegram xabari esa orqa fonda yuboriladi.

Bu yechim Celery/Redis kabi qo'shimcha infratuzilma talab qilmaydi —
kichik/o'rta yuklamali loyihalar uchun yetarli. Agar kelajakda yuklama
juda oshsa (minutiga yuzlab so'rov), Celery'ga o'tish tavsiya etiladi.
"""
import logging
import threading

import requests
from django.conf import settings
from django.db import close_old_connections

logger = logging.getLogger(__name__)

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"


def run_async(func, *args, **kwargs):
    """
    Berilgan funksiyani alohida (daemon) thread'da ishga tushiradi —
    chaqiruvchi kod (masalan Django view) natijani KUTMAYDI, darhol
    davom etadi. Thread ichida ochilgan DB ulanishlari thread tugagach
    tozalanadi (aks holda ulanishlar "osilib" qolishi mumkin).
    """

    def runner():
        try:
            func(*args, **kwargs)
        except Exception:
            logger.exception("Background vazifada kutilmagan xato: %s", func.__name__)
        finally:
            close_old_connections()

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    return thread


def send_telegram_message(text, chat_id=None):
    """
    Telegramga matnli xabar yuboradi (SINXRON — to'g'ridan-to'g'ri chaqiradi).
    Xato bo'lsa, dasturni to'xtatib qo'ymaydi — faqat log yozadi
    (chunki Telegram ishlamasa ham, asosiy tizim ishlashda davom etishi kerak).

    Background (bloklamaydigan) yuborish uchun buni emas, pastdagi
    notify_*_async() funksiyalaridan foydalaning.
    """
    token = getattr(settings, 'TELEGRAM_BOT_TOKEN', None)
    target_chat_id = chat_id or getattr(settings, 'TELEGRAM_CHAT_ID', None)

    if not token or not target_chat_id:
        logger.warning("Telegram TOKEN yoki CHAT_ID sozlanmagan — xabar yuborilmadi.")
        return False

    url = TELEGRAM_API_URL.format(token=token)
    payload = {
        'chat_id': target_chat_id,
        'text': text,
        'parse_mode': 'HTML',
    }

    try:
        response = requests.post(url, json=payload, timeout=5)
        if response.status_code == 200:
            return True
        else:
            logger.error(f"Telegram xato: {response.status_code} — {response.text}")
            return False
    except requests.RequestException as e:
        logger.error(f"Telegram ulanish xatosi: {e}")
        return False


def _notify_new_point_sync(visit):
    point = visit.point
    agent = visit.agent
    kind_label = point.get_kind_display()

    text = (
        f"🆕 <b>Yangi mijoz topildi</b>\n\n"
        f"<b>Joy:</b> {point.name}\n"
        f"<b>Turi:</b> {kind_label}\n"
        f"<b>Manzil:</b> {point.address or '—'}\n"
        f"<b>Agent:</b> {agent.first_name} {agent.last_name}\n"
        f"<b>Telefon:</b> {point.phone or '—'}\n"
        f"<b>Holat:</b> Shartnoma yo'q ❌\n"
    )
    if visit.note:
        text += f"<b>Izoh:</b> {visit.note}\n"
    if point.latitude and point.longitude:
        text += f"\n📍 https://maps.google.com/?q={point.latitude},{point.longitude}"

    sent = send_telegram_message(text)
    if sent:
        visit.telegram_sent = True
        visit.save(update_fields=['telegram_sent'])
    return sent


def _notify_visit_report_sync(visit, debt_amount=0):
    point = visit.point
    agent = visit.agent
    cliente = point.cliente

    debt_line = (
        f"<b>Qarzdorlik:</b> {debt_amount:,.0f} so'm 🔴\n"
        if debt_amount > 0 else
        f"<b>Qarzdorlik:</b> yo'q ✅\n"
    )

    text = (
        f"📋 <b>Tashrif hisoboti</b>\n\n"
        f"<b>Joy:</b> {point.name}\n"
        f"<b>Mijoz:</b> {cliente.first_name} {cliente.last_name}"
        f"{' (' + cliente.firma_name + ')' if cliente.firma_name else ''}\n"
        f"<b>Agent:</b> {agent.first_name} {agent.last_name}\n"
        f"<b>Holat:</b> Shartnoma bor ✅\n"
        f"{debt_line}"
    )
    if visit.note:
        text += f"<b>Izoh:</b> {visit.note}\n"
    if point.latitude and point.longitude:
        text += f"\n📍 https://maps.google.com/?q={point.latitude},{point.longitude}"

    sent = send_telegram_message(text)
    if sent:
        visit.telegram_sent = True
        visit.save(update_fields=['telegram_sent'])
    return sent


def notify_new_point(visit):
    """SINXRON versiya — natijani darhol qaytaradi (masalan testlar uchun)."""
    return _notify_new_point_sync(visit)


def notify_visit_report(visit, debt_amount=0):
    """SINXRON versiya — natijani darhol qaytaradi (masalan testlar uchun)."""
    return _notify_visit_report_sync(visit, debt_amount=debt_amount)


def notify_new_point_async(visit):
    """
    BACKGROUND versiya — view darhol javob qaytaradi, Telegram xabari
    orqa fonda yuboriladi. Agent panelidagi GPS-kuzatuv (agent_check_nearby)
    kabi tez javob talab qiladigan joylarda shuni ishlating.
    """
    run_async(_notify_new_point_sync, visit)


def notify_visit_report_async(visit, debt_amount=0):
    """BACKGROUND versiya — izoh yuqoridagi notify_new_point_async'da."""
    run_async(_notify_visit_report_sync, visit, debt_amount=debt_amount)


def notify_debt_reminder(cliente, debt_amount, days_overdue, oldest_order_number):
    """
    Mijozning uzoq vaqtdan beri to'lanmagan qarzi haqida adminga
    Telegram orqali eslatma yuboradi.

    DIQQAT: bu funksiya SINXRON qoladi — chunki uni chaqiruvchi
    (send_debt_reminders management command) allaqachon alohida,
    cron orqali ishlaydigan background jarayon, foydalanuvchi so'rovi
    ichida emas. Shuning uchun bu yerda run_async() shart emas.
    """
    text = (
        f"⏰ <b>Qarzdorlik eslatmasi</b>\n\n"
        f"<b>Mijoz:</b> {cliente.first_name} {cliente.last_name}"
        f"{' (' + cliente.firma_name + ')' if cliente.firma_name else ''}\n"
        f"<b>Telefon:</b> {cliente.phone or '—'}\n"
        f"<b>Qarz summasi:</b> {debt_amount:,.0f} so'm 🔴\n"
        f"<b>Eng eski qarzdor nakladnoy:</b> {oldest_order_number}\n"
        f"<b>To'lanmagan kunlar:</b> {days_overdue} kun\n"
    )
    if cliente.agent:
        text += f"<b>Agent:</b> {cliente.agent.first_name} {cliente.agent.last_name}\n"

    return send_telegram_message(text)

# ════════════════════════════════════════════════════════════
# CHAT ID OLISH — bir martalik qadam
# ════════════════════════════════════════════════════════════
#
# 1. Botni Telegram guruhiga qo'shing (yoki shaxsiy xabar yuboring).
# 2. Guruhda/botga biror xabar yuboring (masalan "salom").
# 3. Brauzerda quyidagi manzilga kiring (TOKEN ni almashtiring):
#
#    https://api.telegram.org/bot<TOKEN>/getUpdates
#
# 4. JSON javobida "chat":{"id": -1001234567890, ...} kabi son ko'rinadi —
#    aynan shu son CHAT_ID. Guruhlar uchun odatda manfiy son bo'ladi.
