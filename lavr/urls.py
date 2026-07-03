"""
DIQQAT: bu fayl loyihaning ASOSIY urls.py fayli (masalan lavr/urls.py),
app/urls.py emas! Quyidagi kodni o'zingizning asosiy urls.py faylingizga
ko'chiring yoki mavjudini shu tarzda to'ldiring.
"""

from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views

from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),

    # ─── Login / Logout ───────────────────────────────
    # Bu Django'ning standart LoginView/LogoutView'idan foydalanadi
    # va templates/registration/login.html ni avtomatik ishlatadi.
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),

    # ─── Asosiy app (apps.urls — sizning app nomingiz bo'yicha o'zgartiring) ───
    path('', include('apps.urls')),
    path('agent/', include('agent.urls')),
]

# ─── Media fayllarni development rejimida ko'rsatish ───
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
