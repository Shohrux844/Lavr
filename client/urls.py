from django.urls import path
from client import views

urlpatterns = [
    path('panel/', views.client_dashboard, name='client_dashboard'),
    path('panel/products/', views.client_product_list, name='client_product_list'),
    path('panel/payments/', views.client_payment_list, name='client_payment_list'),
    path('panel/orders/', views.client_order_request_list, name='client_order_request_list'),
    path('panel/orders/create/', views.client_order_request_create, name='client_order_request_create'),
    path('panel/orders/<int:pk>/', views.client_order_request_detail, name='client_order_request_detail'),
    path('panel/ajax/product-price/', views.client_get_product_price, name='client_get_product_price'),

]
