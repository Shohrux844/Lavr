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

from apps.auth_views import RoleBasedLoginView

urlpatterns = [
    path('apps/', admin.site.urls),

    # ─── Login / Logout ───────────────────────────────
    # Endi RoleBasedLoginView ishlatiladi — login qilgandan keyin
    # foydalanuvchi turiga (admin/agent/mijoz) qarab to'g'ri panelga yo'naltiradi.
    path('login/', RoleBasedLoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),

    # ─── Parolni tiklash (email orqali) ────────────────
    path('password-reset/',
         auth_views.PasswordResetView.as_view(
             template_name='registration/password_reset_form.html',
             email_template_name='registration/password_reset_email.html',
             subject_template_name='registration/password_reset_subject.txt',
         ),
         name='password_reset'),
    path('password-reset/done/',
         auth_views.PasswordResetDoneView.as_view(
             template_name='registration/password_reset_done.html'),
         name='password_reset_done'),
    path('password-reset/confirm/<uidb64>/<token>/',
         auth_views.PasswordResetConfirmView.as_view(
             template_name='registration/password_reset_confirm.html'),
         name='password_reset_confirm'),
    path('password-reset/complete/',
         auth_views.PasswordResetCompleteView.as_view(
             template_name='registration/password_reset_complete.html'),
         name='password_reset_complete'),

    # ─── Asosiy app (apps.urls — sizning app nomingiz bo'yicha o'zgartiring) ───
    path('admin/', admin.site.urls),
    path('', include('apps.urls')),
    path('agent/', include('agent.urls')),
    path('client/', include('client.urls')),
]

# ─── Media fayllarni development rejimida ko'rsatish ───
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
