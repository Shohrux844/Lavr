"""
apps/tests.py

Loyihaning eng xavfli joylari uchun testlar:
  1. Product.stock_status property
  2. Order raqami avtomatik generatsiyasi
  3. order_create — muvaffaqiyatli va sklad yetmagan holatlar
     (StockError → rollback: HECH NARSA yaratilmasligi kerak)
  4. order_delete — bekor qilish + sklad tiklanishi (soft-delete)
  5. admin_required — is_staff=False foydalanuvchi bloklanishi
  6. payment_confirm — to'lov tasdiqlanganda order.status yangilanishi
  7. StockMovement — har bir amalda yozuv yaratilishi

DIQQAT: Agent va Cliente modellarining TO'LIQ kodi menda yo'q edi
(faqat forms.py'da ishlatilgan maydonlar ko'rinadi). Agar sizning
haqiqiy modelingizda bu yerda ko'rsatilmagan qo'shimcha MAJBURIY
maydon bo'lsa, setUp() dagi Agent.objects.create(...) /
Cliente.objects.create(...) qatorlariga o'sha maydonni qo'shing.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from agent.models import Agent
from client.models import Cliente
from .models import Product, Order, OrderItem, Payment, StockMovement

User = get_user_model()


class ProductStockStatusTests(TestCase):
    def test_out_of_stock(self):
        p = Product.objects.create(name="Test", sku="T-001", price=1000, stock=0, low_stock_threshold=10)
        self.assertEqual(p.stock_status, 'out')

    def test_low_stock(self):
        p = Product.objects.create(name="Test", sku="T-002", price=1000, stock=5, low_stock_threshold=10)
        self.assertEqual(p.stock_status, 'low')

    def test_ok_stock(self):
        p = Product.objects.create(name="Test", sku="T-003", price=1000, stock=50, low_stock_threshold=10)
        self.assertEqual(p.stock_status, 'ok')


class OrderNumberTests(TestCase):
    def setUp(self):
        self.agent = Agent.objects.create(
            first_name="Test", last_name="Agent", phone="+998900000000",
            address="Toshkent", commission_rate=5, balance_limit=0, is_active=True,
        )
        self.cliente = Cliente.objects.create(
            first_name="Test", last_name="Cliente", agent=self.agent, is_active=True,
        )

    def test_number_auto_generated(self):
        order = Order.objects.create(cliente=self.cliente, agent=self.agent)
        self.assertTrue(order.number.startswith("NK-"))
        self.assertNotEqual(order.number, "")


class OrderCreateViewTests(TestCase):
    """
    order_create view'ining eng muhim ikkita holatini tekshiradi:
    (1) sklad yetarli bo'lsa — order va item yaratiladi, stock kamayadi;
    (2) sklad yetarli bo'lmasa — HECH NARSA yaratilmaydi (rollback).
    """

    def setUp(self):
        self.admin_user = User.objects.create_user(
            username="admin_test", password="testpass123", is_staff=True,
        )
        self.agent = Agent.objects.create(
            first_name="Test", last_name="Agent", phone="+998900000000",
            address="Toshkent", commission_rate=5, balance_limit=0, is_active=True,
        )
        self.cliente = Cliente.objects.create(
            first_name="Test", last_name="Cliente", agent=self.agent, is_active=True,
        )
        self.product = Product.objects.create(
            name="Yog'", sku="YG-001", price=15000, stock=10, low_stock_threshold=2,
        )
        self.client.login(username="admin_test", password="testpass123")

    def _post_data(self, quantity):
        return {
            'cliente': self.cliente.pk,
            'agent': self.agent.pk,
            'payment_type': 'cash',
            'note': '',
            'items-TOTAL_FORMS': '1',
            'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '0',
            'items-MAX_NUM_FORMS': '1000',
            'items-0-product': self.product.pk,
            'items-0-quantity': quantity,
            'items-0-price': self.product.price,
        }

    def test_create_success_decreases_stock_and_logs_movement(self):
        response = self.client.post(reverse('order_create'), self._post_data(quantity=3))

        self.assertEqual(Order.objects.count(), 1)
        order = Order.objects.first()
        self.assertEqual(order.items.count(), 1)
        self.assertEqual(order.total_sum, 3 * self.product.price)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 7)  # 10 - 3

        # StockMovement yozuvi ham yaratilgan bo'lishi kerak
        movement = StockMovement.objects.filter(product=self.product, order=order).first()
        self.assertIsNotNone(movement)
        self.assertEqual(movement.quantity_change, -3)
        self.assertEqual(movement.stock_after, 7)

        # Muvaffaqiyatli yaratilgandan keyin order_detail'ga redirect bo'lishi kerak
        self.assertRedirects(response, reverse('order_detail', kwargs={'pk': order.pk}))

    def test_create_fails_when_stock_insufficient_nothing_created(self):
        """
        Eng muhim test: sklad yetmasa (10 dona bor, 999 so'ralgan),
        na Order, na OrderItem, na StockMovement yaratilmasligi kerak,
        va product.stock O'ZGARMASLIGI kerak (to'liq rollback).
        """
        self.client.post(reverse('order_create'), self._post_data(quantity=999))

        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(OrderItem.objects.count(), 0)
        self.assertEqual(StockMovement.objects.count(), 0)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)  # o'zgarmagan


class OrderDeleteRestoresStockTests(TestCase):
    """order_delete endi hard-delete emas — bekor qiladi va sklad tiklaydi."""

    def setUp(self):
        self.admin_user = User.objects.create_user(
            username="admin_test2", password="testpass123", is_staff=True,
        )
        self.agent = Agent.objects.create(
            first_name="Test", last_name="Agent2", phone="+998900000001",
            address="Toshkent", commission_rate=5, balance_limit=0, is_active=True,
        )
        self.cliente = Cliente.objects.create(
            first_name="Test", last_name="Cliente2", agent=self.agent, is_active=True,
        )
        self.product = Product.objects.create(
            name="Moy", sku="MY-001", price=20000, stock=5, low_stock_threshold=2,
        )
        self.order = Order.objects.create(
            cliente=self.cliente, agent=self.agent, total_sum=3 * 20000,
        )
        OrderItem.objects.create(order=self.order, product=self.product, quantity=3, price=20000)
        # Sotuv sodir bo'lgandek, skladni oldindan kamaytirib qo'yamiz
        self.product.stock = 2  # 5 - 3
        self.product.save()

        self.client.login(username="admin_test2", password="testpass123")

    def test_delete_cancels_order_and_restores_stock(self):
        self.client.post(reverse('order_delete', kwargs={'pk': self.order.pk}))

        self.order.refresh_from_db()
        self.product.refresh_from_db()

        self.assertEqual(self.order.status, Order.Status.CANCELLED)
        self.assertEqual(self.product.stock, 5)  # 2 + 3 qaytdi

        # Yozuv O'CHMAGANLIGINI tekshiramiz (hard-delete emas)
        self.assertTrue(Order.objects.filter(pk=self.order.pk).exists())

        movement = StockMovement.objects.filter(
            product=self.product, order=self.order,
            movement_type=StockMovement.MovementType.RETURN,
        ).first()
        self.assertIsNotNone(movement)
        self.assertEqual(movement.quantity_change, 3)

    def test_cannot_cancel_twice(self):
        self.order.status = Order.Status.CANCELLED
        self.order.save()

        self.client.post(reverse('order_delete', kwargs={'pk': self.order.pk}))

        self.product.refresh_from_db()
        # Ikkinchi marta bekor qilishga urinilganda, stock QAYTA tiklanmasligi kerak
        self.assertEqual(self.product.stock, 2)


class AdminRequiredPermissionTests(TestCase):
    """Role-based ruxsat: is_staff=False foydalanuvchi admin sahifalarga kira olmasligi kerak."""

    def setUp(self):
        self.staff_user = User.objects.create_user(
            username="staff1", password="testpass123", is_staff=True,
        )
        self.regular_user = User.objects.create_user(
            username="regular1", password="testpass123", is_staff=False,
        )

    def test_staff_can_access_order_list(self):
        self.client.login(username="staff1", password="testpass123")
        response = self.client.get(reverse('order_list'))
        self.assertEqual(response.status_code, 200)

    def test_non_staff_is_redirected_away(self):
        self.client.login(username="regular1", password="testpass123")
        response = self.client.get(reverse('order_list'))
        # admin_required decoratori bloklab, boshqa panelga (yoki login'ga) redirect qiladi
        self.assertNotEqual(response.status_code, 200)
        self.assertIn(response.status_code, (302, 403))

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse('order_list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)


class PaymentConfirmTests(TestCase):
    """To'lov tasdiqlanganda order.status to'g'ri hisoblanishini tekshiradi."""

    def setUp(self):
        self.admin_user = User.objects.create_user(
            username="admin_test3", password="testpass123", is_staff=True,
        )
        self.agent = Agent.objects.create(
            first_name="Test", last_name="Agent3", phone="+998900000002",
            address="Toshkent", commission_rate=5, balance_limit=0, is_active=True,
        )
        self.cliente = Cliente.objects.create(
            first_name="Test", last_name="Cliente3", agent=self.agent, is_active=True,
        )
        self.order = Order.objects.create(
            cliente=self.cliente, agent=self.agent, total_sum=100000,
        )
        self.client.login(username="admin_test3", password="testpass123")

    def test_partial_payment_sets_debt_status(self):
        payment = Payment.objects.create(order=self.order, amount=40000, method='bank', confirmed=False)
        self.client.post(reverse('payment_confirm', kwargs={'pk': payment.pk}))

        self.order.refresh_from_db()
        payment.refresh_from_db()
        self.assertTrue(payment.confirmed)
        self.assertEqual(self.order.status, Order.Status.DEBT)

    def test_full_payment_sets_paid_status(self):
        payment = Payment.objects.create(order=self.order, amount=100000, method='bank', confirmed=False)
        self.client.post(reverse('payment_confirm', kwargs={'pk': payment.pk}))

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PAID)
