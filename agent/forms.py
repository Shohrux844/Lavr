"""
agent/forms.py
"""
from django import forms
from django.contrib.auth import get_user_model

from agent.models import Agent, AgentBalance

User = get_user_model()

ATTRS = {'class': 'form-control'}
TEXTAREA = {'class': 'form-control', 'rows': 3}


class AgentForm(forms.ModelForm):
    """
    Agentni yaratish/tahrirlash formasi.

    Endi 'user' maydoni (select) o'rniga to'g'ridan-to'g'ri
    'username' + 'password' maydonlari orqali login hisobi
    shu formaning o'zida yaratiladi yoki yangilanadi — Django
    admin panelga alohida kirish shart emas.
    """

    username = forms.CharField(
        label="Login (username)",
        max_length=150,
        required=False,
        help_text="Agent tizimga shu login bilan kiradi.",
    )
    password = forms.CharField(
        label="Parol",
        widget=forms.PasswordInput(render_value=False),
        required=False,
        help_text="Yangi agent uchun majburiy. Tahrirlashda — o'zgartirmoqchi "
                  "bo'lmasangiz bo'sh qoldiring.",
    )

    class Meta:
        model = Agent
        fields = ['first_name', 'last_name', 'phone', 'address', 'commission_rate', 'balance_limit']
        labels = {
            'first_name': 'Ism',
            'last_name': 'Familiya',
            'phone': 'Telefon',
            'address': 'Manzil',
            'commission_rate': 'Komissiya stavkasi (%)',
            'balance_limit': 'Balans limiti (so\'m)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Tahrirlashda mavjud loginni maydonga oldindan to'ldirib qo'yamiz
        if self.instance and self.instance.pk and self.instance.user_id:
            self.fields['username'].initial = self.instance.user.username

        for f in self.fields.values():
            f.widget.attrs.update(ATTRS)

    def clean_username(self):
        username = self.cleaned_data.get('username', '').strip()
        if not username:
            return username

        qs = User.objects.filter(username=username)
        # Tahrirlashda o'zining joriy userini bandlik tekshiruvidan chiqarib tashlaymiz
        if self.instance and self.instance.pk and self.instance.user_id:
            qs = qs.exclude(pk=self.instance.user_id)
        if qs.exists():
            raise forms.ValidationError("Bu login (username) allaqachon band — boshqasini tanlang.")
        return username

    def clean(self):
        cleaned_data = super().clean()
        username = cleaned_data.get('username')
        password = cleaned_data.get('password')
        is_new_agent = not (self.instance and self.instance.pk)
        has_existing_user = bool(self.instance and self.instance.pk and self.instance.user_id)

        # Yangi login yaratilayotgan bo'lsa (hali user bog'lanmagan), parol majburiy
        if username and not has_existing_user and not password:
            self.add_error('password', "Yangi login uchun parol kiritishingiz shart.")

        return cleaned_data

    def save(self, commit=True):
        agent = super().save(commit=False)

        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')

        if username:
            if agent.user_id:
                # Mavjud login — username yangilanadi, parol faqat kiritilgan bo'lsa o'zgaradi
                user = agent.user
                user.username = username
                if password:
                    user.set_password(password)
                user.save()
            else:
                # Yangi login yaratamiz va agentga bog'laymiz
                user = User.objects.create_user(username=username, password=password)
                agent.user = user

        if commit:
            agent.save()
        return agent


class AgentBalanceForm(forms.ModelForm):
    class Meta:
        model = AgentBalance
        fields = ['agent', 'date', 'given_amount', 'returned_amount', 'note']
        widgets = {
            'date': forms.DateInput(attrs={**ATTRS, 'type': 'date'}),
            'note': forms.Textarea(attrs=TEXTAREA),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, f in self.fields.items():
            if not isinstance(f.widget, (forms.Textarea, forms.DateInput)):
                f.widget.attrs.update(ATTRS)
