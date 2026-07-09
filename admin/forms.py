from django import forms
from django.forms import inlineformset_factory

from agent.models import AgentBalance
from client.models import Cliente
from .models import (
    Product, Order, OrderItem, Payment, Salary,
    PointOfInterest, Visit,
)

ATTRS = {'class': 'form-control'}
TEXTAREA = {'class': 'form-control', 'rows': 3}
DATE = {'class': 'form-control', 'type': 'date'}
FILE = {'class': 'form-control'}


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['name', 'sku', 'image', 'description', 'price', 'stock', 'low_stock_threshold']
        widgets = {
            'description': forms.Textarea(attrs=TEXTAREA),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, f in self.fields.items():
            if name == 'image':
                f.widget.attrs.update(FILE)
            elif not isinstance(f.widget, forms.Textarea):
                f.widget.attrs.update(ATTRS)


class OrderForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ['cliente', 'agent', 'payment_type', 'nak_picture', 'note']
        widgets = {'note': forms.Textarea(attrs=TEXTAREA)}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Mijozni tanlaganda uning biriktirilgan agentini JS orqali
        # avtomatik aniqlash uchun agent ma'lumotini oldindan yuklaymiz
        self.fields['cliente'].queryset = (
            Cliente.objects.filter(is_active=True).select_related('agent')
        )
        for name, f in self.fields.items():
            if name not in ('nak_picture',):
                f.widget.attrs.update(ATTRS)


class OrderUpdateForm(forms.ModelForm):
    """
    Mavjud nakladnoyni tahrirlash uchun — status maydoni bilan.
    Yangi nakladnoy yaratishda status ishlatilmaydi (avtomatik 'pending'),
    lekin tahrirlashda admin holatni qo'lda o'zgartirishi mumkin.
    """

    class Meta:
        model = Order
        fields = ['cliente', 'agent', 'payment_type', 'status', 'nak_picture', 'note']
        widgets = {'note': forms.Textarea(attrs=TEXTAREA)}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, f in self.fields.items():
            if name not in ('nak_picture',):
                f.widget.attrs.update(ATTRS)


class OrderItemForm(forms.ModelForm):
    class Meta:
        model = OrderItem
        fields = ['product', 'quantity', 'price']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.widget.attrs.update(ATTRS)
        # required=False qilamiz, chunki bo'sh "extra" qatorlarni
        # o'zimiz clean() ichida tekshiramiz va kerak bo'lsa xato chiqaramiz
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
            # Bo'sh "extra" qator — bu majburiy emas, formsetga
            # uni o'tkazib yuborishni aytamiz
            cleaned_data['DELETE'] = True
            return cleaned_data

        # Agar qatorda BIROR maydon to'ldirilgan bo'lsa, endi
        # product/price/quantity HAMMASI to'ldirilishi shart
        if not product:
            self.add_error('product', "Tovar tanlang.")
        if price in (None, ''):
            self.add_error('price', "Narxni kiriting.")
        if not quantity:
            self.add_error('quantity', "Miqdorni kiriting.")

        return cleaned_data


OrderItemFormSet = inlineformset_factory(
    Order, OrderItem,
    form=OrderItemForm,
    extra=1,
    min_num=0,
    validate_min=False,
    can_delete=True,
)


class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ['amount', 'method', 'screenshot', 'note']
        widgets = {'note': forms.Textarea(attrs=TEXTAREA)}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, f in self.fields.items():
            if name != 'screenshot':
                f.widget.attrs.update(ATTRS)


class SalaryForm(forms.ModelForm):
    class Meta:
        model = Salary
        fields = ['agent', 'month', 'total_sales', 'commission_rate', 'bonus', 'status', 'note']
        widgets = {
            'month': forms.DateInput(attrs={**ATTRS, 'type': 'date'}),
            'note': forms.Textarea(attrs=TEXTAREA),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, f in self.fields.items():
            if not isinstance(f.widget, (forms.Textarea, forms.DateInput)):
                f.widget.attrs.update(ATTRS)


class PointOfInterestForm(forms.ModelForm):
    """
    AZS/avto-do'kon yaratish/tahrirlash. Koordinatalar yashirin maydon
    sifatida xaritadan tanlash orqali to'ladi (JS), lekin qo'lda ham
    kiritish mumkin.
    """

    class Meta:
        model = PointOfInterest
        fields = ['name', 'kind', 'latitude', 'longitude', 'address', 'phone', 'cliente']
        labels = {
            'name': 'Nomi',
            'kind': 'Turi',
            'latitude': 'Kenglik (latitude)',
            'longitude': "Uzunlik (longitude)",
            'address': 'Manzil',
            'phone': 'Telefon',
            'cliente': "Bog'langan mijoz (agar shartnoma bo'lsa)",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['cliente'].required = False
        self.fields['cliente'].queryset = Cliente.objects.filter(is_active=True)
        for f in self.fields.values():
            f.widget.attrs.update(ATTRS)
        self.fields['latitude'].widget.attrs['readonly'] = True
        self.fields['longitude'].widget.attrs['readonly'] = True


class VisitForm(forms.ModelForm):
    """Agent tashrifni belgilash formasi."""

    class Meta:
        model = Visit
        fields = ['point', 'latitude', 'longitude', 'note']
        labels = {
            'point': 'Joy (AZS/Do\'kon)',
            'note': 'Izoh',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['point'].queryset = PointOfInterest.objects.filter(is_active=True)
        self.fields['latitude'].required = False
        self.fields['longitude'].required = False
        self.fields['latitude'].widget = forms.HiddenInput()
        self.fields['longitude'].widget = forms.HiddenInput()
        self.fields['point'].widget.attrs.update(ATTRS)
        self.fields['note'].widget = forms.Textarea(attrs=TEXTAREA)
