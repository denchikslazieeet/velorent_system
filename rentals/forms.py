from datetime import timedelta

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from accounts.forms import normalize_phone
from accounts.models import AccountAccessCode, User
from catalog.models import Bike, PickupLocation
from .models import Booking


class BookingForm(forms.ModelForm):
    duration_hours = forms.IntegerField(
        label="На сколько часов хотите арендовать",
        min_value=1,
        max_value=24 * 30,
        initial=1,
        widget=forms.NumberInput(attrs={
            "min": "1",
            "step": "1",
            "placeholder": "Например, 3",
        }),
    )

    class Meta:
        model = Booking
        fields = ["start_at", "duration_hours", "pickup_location", "comment"]
        labels = {
            "start_at": "Начало аренды",
            "pickup_location": "Точка выдачи",
            "comment": "Комментарий",
        }
        widgets = {
            "start_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "comment": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["pickup_location"].queryset = PickupLocation.objects.filter(is_active=True)

    def clean(self):
        cleaned_data = super().clean()
        start_at = cleaned_data.get("start_at")
        duration_hours = cleaned_data.get("duration_hours")

        if start_at and timezone.is_naive(start_at):
            start_at = timezone.make_aware(start_at)
            cleaned_data["start_at"] = start_at

        if start_at and duration_hours:
            cleaned_data["end_at"] = start_at + timedelta(hours=duration_hours)
            if start_at < timezone.now():
                self.add_error("start_at", "Нельзя бронировать на прошедшее время.")

        return cleaned_data

    def save(self, commit=True):
        booking = super().save(commit=False)
        booking.end_at = self.cleaned_data["end_at"]
        if commit:
            booking.save()
        return booking


class OperatorBookingForm(BookingForm):
    customer_phone = forms.CharField(label="Телефон клиента", max_length=20)
    customer_full_name = forms.CharField(label="ФИО клиента", max_length=255)
    bike = forms.ModelChoiceField(label="Велосипед", queryset=Bike.objects.filter(status=Bike.Status.AVAILABLE))

    class Meta(BookingForm.Meta):
        fields = [
            "customer_full_name",
            "customer_phone",
            "bike",
            "start_at",
            "duration_hours",
            "pickup_location",
            "comment",
        ]

    def clean_customer_phone(self):
        phone = normalize_phone(self.cleaned_data["customer_phone"])
        if len(phone) != 11 or not phone.startswith("7"):
            raise ValidationError("Введите корректный номер телефона.")
        return phone

    def resolve_customer(self, created_by=None):
        phone = self.cleaned_data["customer_phone"]
        full_name = self.cleaned_data["customer_full_name"].strip()
        first_name = full_name.split()[1] if len(full_name.split()) > 1 else full_name
        last_name = full_name.split()[0] if len(full_name.split()) > 1 else ""
        customer, created = User.objects.get_or_create(
            phone=phone,
            defaults={
                "username": phone,
                "first_name": first_name[:150],
                "last_name": last_name[:150],
                "role": User.Role.CUSTOMER,
            },
        )
        if created:
            customer.set_unusable_password()
            customer.save(update_fields=["password"])

        self.account_access_code = None
        if not customer.has_usable_password():
            _, self.account_access_code = AccountAccessCode.create_for_user(
                customer,
                created_by=created_by,
            )
        return customer
