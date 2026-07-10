from django import forms
from django.forms import inlineformset_factory
from django.contrib.auth import get_user_model

from apps.models import Product
from client.models import Cliente, OrderRequest, OrderRequestItem

User = get_user_model()

ATTRS = {'class': 'form-control'}
TEXTAREA = {'class': 'form-control', 'rows': 3}


class OrderRequestForm(forms.ModelForm):
    class Meta:
        model = OrderRequest
        fields = ['note']
        widgets = {'note': forms.Textarea(attrs={**TEXTAREA, 'placeholder': "Qo'shimcha izoh (ixtiyoriy)"})}


class OrderRequestItemForm(forms.ModelForm):
    class Meta:
        model = OrderRequestItem
        fields = ['product', 'quantity', 'price']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['product'].queryset = Product.objects.filter(is_active=True)
        for f in self.fields.values():
            f.widget.attrs.update(ATTRS)
        self.fields['product'].required = False
        self.fields['price'].required = False
        self.fields['quantity'].required = False

    def clean(self):
        cleaned_data = super().clean()
        product = cleaned_data.get('product')
        price = cleaned_data.get('price')
        quantity = cleaned_data.get('quantity')
        is_empty = not product and price in (None, '') and not quantity
        if is_empty:
            cleaned_data['DELETE'] = True
            return cleaned_data
        if not product:
            self.add_error('product', "Tovar tanlang.")
        if price in (None, ''):
            self.add_error('price', "Narxni kiriting.")
        if not quantity:
            self.add_error('quantity', "Miqdorni kiriting.")
        return cleaned_data


OrderRequestItemFormSet = inlineformset_factory(
    OrderRequest, OrderRequestItem,
    form=OrderRequestItemForm,
    extra=1, min_num=1, validate_min=False,
    can_delete=True,
)


class ClienteForm(forms.ModelForm):
    """
    Mijozni yaratish/tahrirlash formasi.

    'user' select maydoni o'rniga to'g'ridan-to'g'ri 'username' + 'password'
    orqali login hisobi shu formaning o'zida yaratiladi/yangilanadi.
    Login ixtiyoriy — agar mijoz mijoz-panelidan foydalanmasa, bo'sh qoldirish mumkin.
    """

    username = forms.CharField(
        label="Login (username)",
        max_length=150,
        required=False,
        help_text="Mijoz mijoz-panelga shu login bilan kiradi (ixtiyoriy).",
    )
    password = forms.CharField(
        label="Parol",
        widget=forms.PasswordInput(render_value=False),
        required=False,
        help_text="Yangi login uchun majburiy. Tahrirlashda — o'zgartirmoqchi "
                  "bo'lmasangiz bo'sh qoldiring.",
    )

    class Meta:
        model = Cliente
        fields = ['first_name', 'last_name', 'firma_name', 'alternative_name', 'phone', 'address', 'agent']
        labels = {
            'first_name': 'Ism',
            'last_name': 'Familiya',
            'firma_name': 'Firma nomi',
            'alternative_name': 'Alternativ nom',
            'phone': 'Telefon',
            'address': 'Manzil',
            'agent': 'Agent',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.user_id:
            self.fields['username'].initial = self.instance.user.username
        for f in self.fields.values():
            f.widget.attrs.update(ATTRS)

    def clean_username(self):
        username = self.cleaned_data.get('username', '').strip()
        if not username:
            return username

        qs = User.objects.filter(username=username)
        if self.instance and self.instance.pk and self.instance.user_id:
            qs = qs.exclude(pk=self.instance.user_id)
        if qs.exists():
            raise forms.ValidationError("Bu login (username) allaqachon band — boshqasini tanlang.")
        return username

    def clean(self):
        cleaned_data = super().clean()
        username = cleaned_data.get('username')
        password = cleaned_data.get('password')
        has_existing_user = bool(self.instance and self.instance.pk and self.instance.user_id)

        if username and not has_existing_user and not password:
            self.add_error('password', "Yangi login uchun parol kiritishingiz shart.")

        return cleaned_data

    def save(self, commit=True):
        cliente = super().save(commit=False)

        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')

        if username:
            if cliente.user_id:
                user = cliente.user
                user.username = username
                if password:
                    user.set_password(password)
                user.save()
            else:
                user = User.objects.create_user(username=username, password=password)
                cliente.user = user

        if commit:
            cliente.save()
        return cliente
