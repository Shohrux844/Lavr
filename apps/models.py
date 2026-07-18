from django.contrib.auth.models import AbstractUser
from django.db.models import (
    Model,
    CharField,
    TextField,
    ForeignKey,
    CASCADE,
    SET_NULL,
    IntegerField,
    DecimalField,
    PositiveIntegerField,
    FloatField,
    ImageField,
    DateTimeField,
    DateField,
    BooleanField,
    TextChoices,
)
from django.utils.text import slugify
from django.db.models import SlugField, PositiveIntegerField

from .image_utils import compress_image, image_field_changed


# ──────────────────────────────────────────────
# 1. Foydalanuvchi
# ──────────────────────────────────────────────
class User(AbstractUser):
    pass


# ──────────────────────────────────────────────
# 5. Tovar (Mahsulot) — Sklad
# ──────────────────────────────────────────────

class Category(Model):
    name = CharField(max_length=100)
    slug = SlugField(max_length=100, unique=True, blank=True)
    icon = CharField(max_length=50, default='ti-package',
                      help_text="Agar rasm yuklanmasa, shu icon ko'rsatiladi")
    image = ImageField(upload_to='categories/', null=True, blank=True)
    order = PositiveIntegerField(default=0)
    is_active = BooleanField(default=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        if self.image and image_field_changed(Category, self.pk, 'image', self.image):
            compress_image(self.image, max_dimension=600)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Kategoriya"
        verbose_name_plural = "Kategoriyalar"
        ordering = ['order', 'name']


class Product(Model):
    name = CharField(max_length=255)
    sku = CharField(max_length=50, unique=True, help_text="Tovar kodi, masalan: YG-001")
    category = ForeignKey(
        "apps.Category", on_delete=SET_NULL, null=True, blank=True, related_name='products'
    )
    image = ImageField(upload_to='products/', null=True, blank=True)
    description = TextField(blank=True)
    price = IntegerField(default=0, help_text="So'mda narx")
    stock = PositiveIntegerField(default=0, help_text="Skladda mavjud miqdor")
    low_stock_threshold = PositiveIntegerField(
        default=10,
        help_text="Shu miqdordan kam bo'lsa ogohlantirish chiqadi"
    )
    is_active = BooleanField(default=True)
    date_created = DateTimeField(auto_now_add=True)

    @property
    def stock_status(self):
        if self.stock == 0:
            return 'out'  # Tugagan
        elif self.stock <= self.low_stock_threshold:
            return 'low'  # Kam qolgan
        return 'ok'  # Yetarli

    def save(self, *args, **kwargs):
        # Rasm yangi yuklangan/o'zgargan bo'lsagina siqamiz — tahrirlashda
        # boshqa maydon (masalan narx) o'zgarganda qayta siqmaymiz.
        if self.image and image_field_changed(Product, self.pk, 'image', self.image):
            compress_image(self.image)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.sku})"

    class Meta:
        verbose_name = "Tovar"
        verbose_name_plural = "Tovarlar"


# ──────────────────────────────────────────────
# 6. Nakladnoy (Order)
# ──────────────────────────────────────────────
class Order(Model):
    class Status(TextChoices):
        PENDING = 'pending', "Kutilmoqda"
        PAID = 'paid', "To'langan"
        DEBT = 'debt', "Qarz"
        CANCELLED = 'cancelled', "Bekor qilingan"

    class PaymentType(TextChoices):
        CASH = 'cash', "Naqd"
        TRANSFER = 'transfer', "Perechesleniye"
        DEBT = 'debt', "Qarz (keyinroq)"

    # Nakladnoy raqami (NK-1041 formatida)
    number = CharField(max_length=20, unique=True, blank=True)
    cliente = ForeignKey("client.Cliente", on_delete=CASCADE, related_name='orders')
    agent = ForeignKey("agent.Agent", on_delete=CASCADE, related_name='orders')
    status = CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    payment_type = CharField(
        max_length=20, choices=PaymentType.choices, default=PaymentType.CASH
    )
    total_sum = IntegerField(default=0)
    nak_picture = ImageField(upload_to='orders/', null=True, blank=True)
    note = TextField(blank=True)
    date_created = DateTimeField(auto_now_add=True)
    date_updated = DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        # Rasm yangi yuklangan/o'zgargan bo'lsagina siqamiz
        if self.nak_picture and image_field_changed(Order, self.pk, 'nak_picture', self.nak_picture):
            compress_image(self.nak_picture)

        # Nakladnoy raqamini avtomatik yaratish: NK-0001
        if not self.number:
            super().save(*args, **kwargs)
            self.number = f"NK-{self.id:04d}"
            Order.objects.filter(pk=self.pk).update(number=self.number)
        else:
            super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.number} — {self.cliente}"

    class Meta:
        verbose_name = "Nakladnoy"
        verbose_name_plural = "Nakladnoylar"
        ordering = ['-date_created']


# ──────────────────────────────────────────────
# 7. Nakladnoy satrlari (OrderItem)
# ──────────────────────────────────────────────
class OrderItem(Model):
    order = ForeignKey("apps.Order", on_delete=CASCADE, related_name='items')
    product = ForeignKey("apps.Product", on_delete=CASCADE, related_name='order_items')
    quantity = PositiveIntegerField(default=1)
    price = IntegerField(help_text="Sotish paytidagi narx (o'zgarmasligi uchun saqlanadi)")

    @property
    def subtotal(self):
        return self.quantity * self.price

    def __str__(self):
        return f"{self.order.number} | {self.product.name} x{self.quantity}"

    class Meta:
        verbose_name = "Nakladnoy satri"
        verbose_name_plural = "Nakladnoy satrlari"


# ──────────────────────────────────────────────
# 8. To'lov (Perechesleniye / Naqd)
# ──────────────────────────────────────────────
class Payment(Model):
    class Method(TextChoices):
        CASH = 'cash', "Naqd"
        BANK = 'bank', "Bank o'tkazmasi"

    order = ForeignKey("apps.Order", on_delete=CASCADE, related_name='payments')
    amount = IntegerField()
    method = CharField(max_length=20, choices=Method.choices, default=Method.CASH)
    screenshot = ImageField(
        upload_to='payments/', null=True, blank=True,
        help_text="Bank to'lovi skrinshotini yuklash"
    )
    confirmed = BooleanField(default=False, help_text="Admin tasdiqladi")
    note = TextField(blank=True)
    date_created = DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.screenshot and image_field_changed(Payment, self.pk, 'screenshot', self.screenshot):
            compress_image(self.screenshot)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.order.number} | {self.amount} so'm | {self.get_method_display()}"

    class Meta:
        verbose_name = "To'lov"
        verbose_name_plural = "To'lovlar"
        ordering = ['-date_created']


# ──────────────────────────────────────────────
# 9. Maosh (Salary)
# ──────────────────────────────────────────────
class Salary(Model):
    class Status(TextChoices):
        CALCULATED = 'calculated', "Hisoblandi"
        PAID = 'paid', "To'landi"

    agent = ForeignKey("agent.Agent", on_delete=CASCADE, related_name='salaries')
    month = DateField(help_text="Oy boshi sanasi, masalan: 2026-06-01")
    total_sales = IntegerField(default=0, help_text="O'sha oyda jami sotilgan summa")
    commission_rate = DecimalField(max_digits=5, decimal_places=2)
    commission_amount = IntegerField(default=0, help_text="Foiz bo'yicha hisoblangan summa")
    bonus = IntegerField(default=0)
    total_salary = IntegerField(default=0, help_text="commission_amount + bonus")
    status = CharField(max_length=20, choices=Status.choices, default=Status.CALCULATED)
    date_paid = DateField(null=True, blank=True)
    note = TextField(blank=True)

    def calculate(self):
        """Maoshni avtomatik hisoblash."""
        self.commission_amount = int(self.total_sales * float(self.commission_rate) / 100)
        self.total_salary = self.commission_amount + self.bonus
        self.save()

    def __str__(self):
        return f"{self.agent} — {self.month.strftime('%B %Y')} | {self.total_salary} so'm"

    class Meta:
        verbose_name = "Maosh"
        verbose_name_plural = "Maoshlar"
        unique_together = ('agent', 'month')
        ordering = ['-month']


# ──────────────────────────────────────────────
# 10. Diqqatga sazovor nuqta (AZS / Avto-do'kon)
# ──────────────────────────────────────────────
class PointOfInterest(Model):
    """
    Agent yo'nalishga chiqganda xaritada ko'radigan yoki ro'yxatdan
    tanlaydigan AZS/avto-do'kon. Shartnoma holati bilan bog'liq.
    """

    class Kind(TextChoices):
        AZS = 'azs', "AZS (yoqilg'i shaxobchasi)"
        AVTO_DUKON = 'avto_dukon', "Avto-do'kon"

    name = CharField(max_length=255, help_text="Masalan: 'Quvonchli AZS-4'")
    kind = CharField(max_length=20, choices=Kind.choices, default=Kind.AZS)
    latitude = FloatField()
    longitude = FloatField()
    address = CharField(max_length=255, blank=True)
    phone = CharField(max_length=20, blank=True)

    # Shartnoma holati — bog'langan Cliente orqali aniqlanadi.
    # Agar cliente bo'lmasa — bu joy hali shartnomasiz (yangi).
    cliente = ForeignKey(
        'client.Cliente', on_delete=SET_NULL, null=True, blank=True,
        related_name='points_of_interest',
        help_text="Agar shartnoma qilingan bo'lsa, mos mijoz yozuvi"
    )

    is_active = BooleanField(default=True)
    date_created = DateTimeField(auto_now_add=True)

    @property
    def has_contract(self):
        return self.cliente is not None

    def __str__(self):
        return f"{self.name} ({self.get_kind_display()})"

    class Meta:
        verbose_name = "Nuqta (AZS/Do'kon)"
        verbose_name_plural = "Nuqtalar (AZS/Do'konlar)"
        ordering = ['name']


# ──────────────────────────────────────────────
# 11. Tashrif (Visit)
# ──────────────────────────────────────────────
class Visit(Model):
    """
    Agent biror nuqtaga (AZS/do'kon) tashrif qilganda yaratiladigan yozuv.
    Telegramga xabar yuborish shu yozuv asosida ishlaydi.
    """
    agent = ForeignKey("agent.Agent", on_delete=CASCADE, related_name='visits')
    point = ForeignKey("apps.PointOfInterest", on_delete=CASCADE, related_name='visits')
    latitude = FloatField(null=True, blank=True, help_text="Agent tashrif paytidagi GPS")
    longitude = FloatField(null=True, blank=True)
    note = TextField(blank=True)
    telegram_sent = BooleanField(default=False)
    date_created = DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.agent} → {self.point} | {self.date_created.strftime('%d.%m.%Y %H:%M')}"

    class Meta:
        verbose_name = "Tashrif"
        verbose_name_plural = "Tashriflar"
        ordering = ['-date_created']


# ──────────────────────────────────────────────
# 12. Sklad harakati tarixi (Stock Ledger)
# ──────────────────────────────────────────────
class StockMovement(Model):
    """
    Har bir sklad o'zgarishini (kirim/chiqim) qayd qiladi — audit uchun.
    product.stock ustidagi HAR bir += yoki -= amali shu yerda ham
    yozib qo'yilishi kerak (order_create, order_request_approve,
    order_delete/cancel, va h.k.).
    """

    class MovementType(TextChoices):
        SALE = 'sale', "Sotildi (nakladnoy)"
        RETURN = 'return', "Qaytarildi (nakladnoy bekor qilindi)"
        CLIENT_RETURN = 'client_return', "Mijoz tovarni qaytardi"
        MANUAL = 'manual', "Qo'lda tuzatish"

    product = ForeignKey("apps.Product", on_delete=CASCADE, related_name='stock_movements')
    order = ForeignKey(
        "apps.Order", on_delete=SET_NULL, null=True, blank=True,
        related_name='stock_movements',
        help_text="Agar shu nakladnoy sababli bo'lsa"
    )
    movement_type = CharField(max_length=20, choices=MovementType.choices)
    # Musbat son = kirim (skladga qo'shildi), manfiy son = chiqim (skladdan ayirildi)
    quantity_change = IntegerField(help_text="Musbat = kirim, manfiy = chiqim")
    stock_after = PositiveIntegerField(help_text="Amaldan keyingi qoldiq (tekshirish uchun)")
    note = CharField(max_length=255, blank=True)
    created_by = ForeignKey(
        "apps.User", on_delete=SET_NULL, null=True, blank=True,
        related_name='stock_movements'
    )
    date_created = DateTimeField(auto_now_add=True)

    def __str__(self):
        sign = '+' if self.quantity_change >= 0 else ''
        return f"{self.product.name}: {sign}{self.quantity_change} ({self.get_movement_type_display()})"

    class Meta:
        verbose_name = "Sklad harakati"
        verbose_name_plural = "Sklad harakatlari"
        ordering = ['-date_created']


# ──────────────────────────────────────────────
# 13. Vozvrat (mijoz tovarni qaytarganda)
# ──────────────────────────────────────────────
class OrderReturn(Model):
    """
    Bitta nakladnoy bo'yicha mijoz qaytargan tovarlarni qayd qiluvchi hujjat.
    Bir nakladnoy uchun bir necha marta (qisman) vozvrat bo'lishi mumkin —
    shuning uchun har bir vozvrat alohida yozuv sifatida saqlanadi.
    """
    order = ForeignKey("apps.Order", on_delete=CASCADE, related_name='returns')
    note = TextField(blank=True, help_text="Qaytarish sababi (ixtiyoriy)")
    created_by = ForeignKey(
        "apps.User", on_delete=SET_NULL, null=True, blank=True,
        related_name='order_returns'
    )
    date_created = DateTimeField(auto_now_add=True)

    @property
    def total_amount(self):
        return sum(i.subtotal for i in self.items.all())

    def __str__(self):
        return f"Vozvrat #{self.pk} — {self.order.number}"

    class Meta:
        verbose_name = "Vozvrat"
        verbose_name_plural = "Vozvratlar"
        ordering = ['-date_created']


class OrderReturnItem(Model):
    order_return = ForeignKey("apps.OrderReturn", on_delete=CASCADE, related_name='items')
    product = ForeignKey("apps.Product", on_delete=CASCADE, related_name='return_items')
    quantity = PositiveIntegerField()
    price = IntegerField(help_text="Sotilgan paytdagi narx (nakladnoydan olinadi)")

    @property
    def subtotal(self):
        return self.quantity * self.price

    def __str__(self):
        return f"{self.product.name} x{self.quantity}"

    class Meta:
        verbose_name = "Vozvrat qatori"
        verbose_name_plural = "Vozvrat qatorlari"
