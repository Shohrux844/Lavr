"""
apps/auth_views.py

Standart Django LoginView'ni kengaytiradi — foydalanuvchi turiga qarab
(admin / agent / mijoz) to'g'ri dashboard'ga yo'naltirish uchun.
"""
from django.contrib.auth.views import LoginView
from django.urls import reverse


class RoleBasedLoginView(LoginView):
    template_name = 'registration/login.html'

    def get_success_url(self):
        user = self.request.user
        if user.is_staff:
            return reverse('dashboard')
        if hasattr(user, 'agent_profile'):
            return reverse('agent_dashboard')
        if hasattr(user, 'cliente_profile'):
            return reverse('client_dashboard')
        # Hech qanday profilga bog'lanmagan foydalanuvchi (masalan yangi
        # yaratilgan, lekin agent/cliente profiliga ulanmagan) — xavfsiz holat
        return reverse('login')
