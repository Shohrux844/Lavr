from django.contrib import admin
from .models import (
    User, Agent, AgentBalance, Cliente, Product,
    Order, OrderItem, Payment, Salary,
    PointOfInterest, Visit,
)


@admin.register(Agent)
class AgentAdmin(admin.ModelAdmin):
    list_display = ['first_name', 'last_name', 'phone', 'commission_rate', 'is_active']
    search_fields = ['first_name', 'last_name', 'phone']
    list_filter = ['is_active']


@admin.register(AgentBalance)
class AgentBalanceAdmin(admin.ModelAdmin):
    list_display = ['agent', 'date', 'given_amount', 'returned_amount', 'remaining']
    list_filter = ['date']


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ['first_name', 'last_name', 'firma_name', 'alternative_name', 'phone', 'agent', 'is_active']
    search_fields = ['first_name', 'last_name', 'firma_name', 'alternative_name', 'phone']
    list_filter = ['is_active', 'agent']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'sku', 'price', 'stock', 'stock_status', 'is_active']
    search_fields = ['name', 'sku']
    list_filter = ['is_active']


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['number', 'cliente', 'agent', 'total_sum', 'status', 'payment_type', 'date_created']
    list_filter = ['status', 'payment_type']
    search_fields = ['number']
    inlines = [OrderItemInline]


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['order', 'amount', 'method', 'confirmed', 'date_created']
    list_filter = ['method', 'confirmed']


@admin.register(Salary)
class SalaryAdmin(admin.ModelAdmin):
    list_display = ['agent', 'month', 'total_sales', 'commission_amount', 'bonus', 'total_salary', 'status']
    list_filter = ['status', 'month']


@admin.register(PointOfInterest)
class PointOfInterestAdmin(admin.ModelAdmin):
    list_display = ['name', 'kind', 'cliente', 'has_contract', 'is_active']
    list_filter = ['kind', 'is_active']
    search_fields = ['name', 'address']


@admin.register(Visit)
class VisitAdmin(admin.ModelAdmin):
    list_display = ['agent', 'point', 'telegram_sent', 'date_created']
    list_filter = ['telegram_sent']
    readonly_fields = ['telegram_sent']
