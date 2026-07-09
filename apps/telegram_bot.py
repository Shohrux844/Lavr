"""
Telegram xabarlarini yuborish uchun yordamchi modul.
Bu faylni apps/telegram_bot.py sifatida saqlang.

ISHLATISH UCHUN KERAK:
1. Telegram'da @BotFather orqali bot yarating, BOT_TOKEN oling.
2. Botni guruhga (yoki o'zingizning shaxsiy chatingizga) qo'shing.
3. Guruh/chat ID sini aniqlang (pastdagi "CHAT ID OLISH" bo'limiga qarang).
4. settings.py ga TELEGRAM_BOT_TOKEN va TELEGRAM_CHAT_ID qo'shing.
"""
import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"


def send_telegram_message(text, chat_id=None):
    """
    Telegramga matnli xabar yuboradi.
    Xato bo'lsa, dasturni to'xtatib qo'ymaydi — faqat log yozadi
    (chunki Telegram ishlamasa ham, asosiy tizim ishlashda davom etishi kerak).
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


def notify_new_point(visit):
    """
    Agent shartnomasiz (yangi) nuqtaga tashrif qilganda yuboriladigan xabar.
    """
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


def notify_visit_report(visit, debt_amount=0):
    """
    Agent shartnoma qilingan (mijoz bog'langan) nuqtaga tashrif qilganda
    yuboriladigan xabar — qarzdorlik ma'lumoti bilan.
    """
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
