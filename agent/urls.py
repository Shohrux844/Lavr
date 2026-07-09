"""
agent/urls.py

DIQQAT: bu fayl ikkita guruh URL ni birlashtiradi:
  1. Admin uchun: agentlar boshqaruvi (/agents/...)
     Ular asosiy apps/urls.py dagi URL'larni shu app'ga ko'chirildi.
  2. Agent panel uchun: /agent/... prefix bilan project urls.py da include qilinadi.
"""
from django.urls import path
from agent import views

urlpatterns = [

    # ── ADMIN: Agentlar boshqaruvi (/agents/ prefix bilan chaqiriladi) ──
    path('',                    views.agent_list,          name='agent_list'),
    path('create/',             views.agent_create,        name='agent_create'),
    path('<int:pk>/',           views.agent_detail,        name='agent_detail'),
    path('<int:pk>/edit/',      views.agent_update,        name='agent_update'),
    path('<int:pk>/delete/',    views.agent_delete,        name='agent_delete'),

    # ── ADMIN: Ostatka (Balans) ──
    path('balances/',              views.agent_balance_list,   name='agent_balance_list'),
    path('balances/create/',       views.agent_balance_create, name='agent_balance_create'),
    path('balances/<int:pk>/edit/',views.agent_balance_update, name='agent_balance_update'),

    # ── AGENT PANEL (/agent/ prefix bilan chaqiriladi) ──
    path('panel/',                   views.agent_dashboard,      name='agent_dashboard'),
    path('panel/orders/',            views.agent_order_list,     name='agent_order_list'),
    path('panel/orders/<int:pk>/',   views.agent_order_detail,   name='agent_order_detail'),
    path('panel/products/',          views.agent_product_list,   name='agent_product_list'),
    path('panel/products/<int:pk>/', views.agent_product_detail, name='agent_product_detail'),
    path('panel/clients/',          views.agent_cliente_list,   name='agent_cliente_list'),
    path('panel/clients/create/',   views.agent_cliente_create, name='agent_cliente_create'),
    path('panel/salary/',            views.agent_salary_list,    name='agent_salary_list'),
    path('panel/road/',              views.agent_road_tracking,  name='agent_road_tracking'),
    path('panel/ajax/nearby/',       views.agent_check_nearby,   name='agent_check_nearby'),
]