"""
apps/stock.py

Sklad o'zgarishini BIR JOYDAN qayd qilish uchun yordamchi funksiya.
Har safar product.stock ni o'zgartirganda, to'g'ridan-to'g'ri
`product.stock -= N; product.save()` yozish o'rniga shu funksiyani
chaqiring — shunda StockMovement yozuvi ham avtomatik yaratiladi.

Diqqat: bu funksiya select_for_update() bilan OLINGAN (locked)
product obyektini kutadi — uni views.py'dagi tranzaksiya ichida
Product.objects.select_for_update().get(pk=...) orqali oling,
so'ng shu funksiyaga bering.
"""
from .models import StockMovement


def record_stock_movement(product, quantity_change, movement_type, order=None, user=None, note=''):
    """
    product.stock ni quantity_change ga o'zgartiradi (musbat=kirim, manfiy=chiqim),
    saqlaydi va StockMovement yozuvini yaratadi.

    Chaqiruvchi kod tranzaksiya (transaction.atomic()) ichida bo'lishi va
    `product` select_for_update() bilan qulflangan bo'lishi kerak.
    """
    product.stock += quantity_change
    product.save()

    StockMovement.objects.create(
        product=product,
        order=order,
        movement_type=movement_type,
        quantity_change=quantity_change,
        stock_after=product.stock,
        note=note,
        created_by=user,
    )
    return product
