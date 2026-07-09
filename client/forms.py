from django import forms
from django.forms import inlineformset_factory

from apps.models import Product
from client.models import Cliente, OrderRequest, OrderRequestItem

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
    class Meta:
        model = Cliente
        fields = ['first_name', 'last_name', 'firma_name', 'alternative_name', 'phone', 'address', 'agent', 'user']
        labels = {
            'first_name': 'Ism',
            'last_name': 'Familiya',
            'firma_name': 'Firma nomi',
            'alternative_name': 'Alternativ nom',
            'phone': 'Telefon',
            'address': 'Manzil',
            'agent': 'Agent',
            'user': 'Login hisobi (User)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['user'].required = False
        for f in self.fields.values():
            f.widget.attrs.update(ATTRS)
