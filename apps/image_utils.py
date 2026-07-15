"""
apps/image_utils.py

Rasmlarni avtomatik siqish uchun yordamchi funksiyalar.
Product.image, Order.nak_picture, Payment.screenshot kabi ImageField'lar
saqlanishidan oldin shu funksiya orqali o'tkaziladi — natijada disk joyi
va sahifa yuklash tezligi sezilarli yaxshilanadi (masalan telefon
kamerasidan 4-5 MB rasm ~200-400 KB gacha tushishi mumkin).
"""
import io
import logging

from PIL import Image
from django.core.files.base import ContentFile

logger = logging.getLogger(__name__)

MAX_DIMENSION = 1600  # piksel — bundan katta rasm shu o'lchamgacha kichrayadi
JPEG_QUALITY = 82  # 0-100, qanchalik yuqori — sifat yaxshi, hajm katta


def compress_image(image_field, max_dimension=MAX_DIMENSION, quality=JPEG_QUALITY):
    """
    ImageFieldFile obyektini (masalan `product.image`) siqadi:
    - eni yoki bo'yi max_dimension'dan katta bo'lsa, aspekt nisbatini
      saqlagan holda kichraytiradi;
    - JPEG uchun quality parametri bilan qayta saqlaydi (PNG uchun
      optimize=True yetarli, sifat yo'qotilmaydi).

    Xato yuz bersa (masalan fayl buzilgan), original rasmni saqlab
    qoladi — foydalanuvchi tajribasini buzmaydi, faqat log yozadi.
    """
    if not image_field:
        return image_field

    try:
        image_field.seek(0)
        img = Image.open(image_field)
        img_format = (img.format or 'JPEG').upper()

        # RGBA/P (masalan PNG/GIF) rejimini JPEG uchun RGB'ga o'tkazamiz
        if img_format == 'JPEG' and img.mode in ('RGBA', 'P', 'LA'):
            img = img.convert('RGB')

        img.thumbnail((max_dimension, max_dimension), Image.LANCZOS)

        buffer = io.BytesIO()
        save_kwargs = {'optimize': True}
        if img_format in ('JPEG', 'JPG'):
            save_kwargs['quality'] = quality
            img_format = 'JPEG'
        img.save(buffer, format=img_format, **save_kwargs)
        buffer.seek(0)

        image_field.save(image_field.name, ContentFile(buffer.read()), save=False)
    except Exception as e:
        logger.warning("Rasmni siqib bo'lmadi (%s) — original saqlanadi: %s", image_field.name, e)

    return image_field


def image_field_changed(model_cls, pk, field_name, current_file):
    """
    Berilgan model/maydon uchun joriy fayl DB'dagi eskisidan farq
    qilishini tekshiradi — rasm o'zgarmagan bo'lsa (masalan admin
    faqat narxni tahrirlagan bo'lsa), qayta siqishning hojati yo'q.
    """
    if not pk:
        return bool(current_file)
    old_name = model_cls.objects.filter(pk=pk).values_list(field_name, flat=True).first()
    new_name = current_file.name if current_file else None
    return old_name != new_name
