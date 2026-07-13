from django.urls import path

from client.views import cliente_list, cliente_create, cliente_detail, cliente_update, cliente_delete
from . import views
from . import exports

urlpatterns = [

    # ─── Dashboard ────────────────────────────────────
    path('', views.dashboard, name='dashboard'),

    # ─── Mijozlar ─────────────────────────────────────
    path('clients/', cliente_list, name='cliente_list'),
    path('clients/create/', cliente_create, name='cliente_create'),
    path('clients/<int:pk>/', cliente_detail, name='cliente_detail'),
    path('clients/<int:pk>/edit/', cliente_update, name='cliente_update'),
    path('clients/<int:pk>/delete/', cliente_delete, name='cliente_delete'),
    path('clients/export/excel/', exports.cliente_export_excel, name='cliente_export_excel'),
    path('clients/export/pdf/', exports.cliente_export_pdf, name='cliente_export_pdf'),

    # ─── Tovarlar (Sklad) ─────────────────────────────
    path('products/', views.product_list, name='product_list'),
    path('products/create/', views.product_create, name='product_create'),
    path('products/<int:pk>/', views.product_detail, name='product_detail'),
    path('products/<int:pk>/edit/', views.product_update, name='product_update'),
    path('products/<int:pk>/delete/', views.product_delete, name='product_delete'),
    path('products/export/excel/', exports.product_export_excel, name='product_export_excel'),
    path('products/export/pdf/', exports.product_export_pdf, name='product_export_pdf'),
    path('stock-movements/', views.stock_movement_list, name='stock_movement_list'),

    # ─── Nakladnoylar ─────────────────────────────────
    path('orders/', views.order_list, name='order_list'),
    path('orders/create/', views.order_create, name='order_create'),
    path('orders/<int:pk>/', views.order_detail, name='order_detail'),
    path('orders/<int:pk>/edit/', views.order_update, name='order_update'),
    path('orders/<int:pk>/delete/', views.order_delete, name='order_delete'),
    path('orders/<int:pk>/return/', views.order_return_create, name='order_return_create'),
    path('orders/export/excel/', exports.order_export_excel, name='order_export_excel'),
    path('orders/export/pdf/', exports.order_export_pdf, name='order_export_pdf'),

    # ─── To'lovlar (Perechesleniye) ───────────────────
    path('payments/', views.payment_list, name='payment_list'),
    path('payments/order/<int:order_pk>/create/', views.payment_create, name='payment_create'),
    path('payments/<int:pk>/confirm/', views.payment_confirm, name='payment_confirm'),
    path('payments/export/excel/', exports.payment_export_excel, name='payment_export_excel'),
    path('payments/export/pdf/', exports.payment_export_pdf, name='payment_export_pdf'),

    # ─── Maosh ────────────────────────────────────────
    path('salaries/', views.salary_list, name='salary_list'),
    path('salaries/calculate/', views.salary_calculate, name='salary_calculate'),
    path('salaries/<int:pk>/', views.salary_detail, name='salary_detail'),
    path('salaries/<int:pk>/edit/', views.salary_update, name='salary_update'),
    path('salaries/<int:pk>/paid/', views.salary_mark_paid, name='salary_mark_paid'),

    # ─── AJAX ─────────────────────────────────────────
    path('ajax/product-price/', views.get_product_price, name='get_product_price'),

    # ─── Nuqtalar (AZS / Avto-do'kon) — xarita ────────
    path('points/map/', views.point_map, name='point_map'),
    path('points/', views.point_list, name='point_list'),
    path('points/create/', views.point_create, name='point_create'),
    path('points/<int:pk>/edit/', views.point_update, name='point_update'),
    path('points/<int:pk>/delete/', views.point_delete, name='point_delete'),

    # ─── Tashriflar ────────────────────────────────────
    path('visits/', views.visit_list, name='visit_list'),
    path('visits/create/', views.visit_create, name='visit_create'),

    # ─── Buyurtma so'rovlari ───────────────────────────
    path('order-requests/', views.order_request_list, name='order_request_list'),
    path('order-requests/<int:pk>/', views.order_request_detail, name='order_request_detail'),
    path('order-requests/<int:pk>/approve/', views.order_request_approve, name='order_request_approve'),
    path('order-requests/<int:pk>/reject/', views.order_request_reject, name='order_request_reject'),

]
