"""
agent/forms.py
"""
from django import forms
from agent.models import Agent, AgentBalance

ATTRS = {'class': 'form-control'}
TEXTAREA = {'class': 'form-control', 'rows': 3}


class AgentForm(forms.ModelForm):
    class Meta:
        model = Agent
        fields = ['user', 'first_name', 'last_name', 'phone', 'address', 'commission_rate', 'balance_limit']
        labels = {
            'user': 'Login hisobi (User)',
            'first_name': 'Ism',
            'last_name': 'Familiya',
            'phone': 'Telefon',
            'address': 'Manzil',
            'commission_rate': 'Komissiya stavkasi (%)',
            'balance_limit': 'Balans limiti (so\'m)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.widget.attrs.update(ATTRS)
        self.fields['user'].required = False


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
