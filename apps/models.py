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
from django.utils import timezone


# ──────────────────────────────────────────────
# 1. Foydalanuvchi
# ──────────────────────────────────────────────
class User(AbstractUser):
    pass


# ──────────────────────────────────────────────
# 2. Agent
# ──────────────────────────────────────────────
class Agent(Model):
    first_name = CharField(max_length=120)
    last_name = CharField(max_length=120)
    phone = CharField(max_length=20)
    address = CharField(max_length=255, blank=True)

    # Maosh hisoblash uchun stavka (foiz, masalan 3.5 = 3.5%)
    commission_rate = DecimalField(
        max_digits=5, decimal_places=2, default=3.0,
        help_text="Foiz stavkasi, masalan 3.5"
    )
    # Agentga berilgan pul limiti
    balance_limit = IntegerField(
        default=0,
        help_text="Agentga berilishi mumkin bo'lgan maksimal naqd pul"
    )
    is_active = BooleanField(default=True)
    date_created = DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    class Meta:
        verbose_name = "Agent"
        verbose_name_plural = "Agentlar"


# ──────────────────────────────────────────────
# 3. Agent qo'lidagi naqd pul (Ostatka)
# ──────────────────────────────────────────────
class AgentBalance(Model):
    """
    Agentga kun boshida berilgan pul va qaytargan pulini kuzatish.
    Har kun yangi yozuv yaratiladi.
    """
    agent = ForeignKey(Agent, on_delete=CASCADE, related_name='balances')
    date = DateField(default=timezone.now)
    given_amount = IntegerField(default=0, help_text="Agentga berilgan pul")
    returned_amount = IntegerField(default=0, help_text="Agent qaytargan pul")
    note = TextField(blank=True)

    @property
    def remaining(self):
        return self.given_amount - self.returned_amount

    def __str__(self):
        return f"{self.agent} — {self.date} | Qoldi: {self.remaining}"

    class Meta:
        verbose_name = "Agent balansi"
        verbose_name_plural = "Agent balanslari"
        ordering = ['-date']


# ──────────────────────────────────────────────
# 4. Mijoz (Cliente)
# ──────────────────────────────────────────────
class Cliente(Model):
    first_name = CharField(max_length=120)
    last_name = CharField(max_length=120)
    firma_name = CharField(max_length=120, blank=True)
    alternative_name = CharField(max_length=120, blank=True)
    phone = CharField(max_length=20, blank=True)
    address = CharField(max_length=255, blank=True)
    agent = ForeignKey(Agent, on_delete=SET_NULL, null=True, related_name='clientes')
    is_active = BooleanField(default=True)
    date_created = DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.firma_name or f"{self.first_name} {self.last_name}"

    class Meta:
        verbose_name = "Mijoz"
        verbose_name_plural = "Mijozlar"


# ──────────────────────────────────────────────
# 5. Tovar (Mahsulot) — Sklad
# ──────────────────────────────────────────────
class Product(Model):
    name = CharField(max_length=255)
    sku = CharField(max_length=50, unique=True, help_text="Tovar kodi, masalan: YG-001")
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
    cliente = ForeignKey(Cliente, on_delete=CASCADE, related_name='orders')
    agent = ForeignKey(Agent, on_delete=CASCADE, related_name='orders')
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
    order = ForeignKey(Order, on_delete=CASCADE, related_name='items')
    product = ForeignKey(Product, on_delete=CASCADE, related_name='order_items')
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

    order = ForeignKey(Order, on_delete=CASCADE, related_name='payments')
    amount = IntegerField()
    method = CharField(max_length=20, choices=Method.choices, default=Method.CASH)
    screenshot = ImageField(
        upload_to='payments/', null=True, blank=True,
        help_text="Bank to'lovi skrinshotini yuklash"
    )
    confirmed = BooleanField(default=False, help_text="Admin tasdiqladi")
    note = TextField(blank=True)
    date_created = DateTimeField(auto_now_add=True)

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

    agent = ForeignKey(Agent, on_delete=CASCADE, related_name='salaries')
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
        'Cliente', on_delete=SET_NULL, null=True, blank=True,
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
    agent = ForeignKey(Agent, on_delete=CASCADE, related_name='visits')
    point = ForeignKey(PointOfInterest, on_delete=CASCADE, related_name='visits')
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
