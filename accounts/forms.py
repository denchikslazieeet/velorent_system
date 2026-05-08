import re

from django.conf import settings
from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import AccountAccessCode, User


def normalize_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith("8") and len(digits) == 11:
        digits = "7" + digits[1:]
    if len(digits) == 10:
        digits = "7" + digits
    return digits


def format_phone(value: str) -> str:
    digits = normalize_phone(value)
    if len(digits) == 11 and digits.startswith("7"):
        return f"+7 ({digits[1:4]}) {digits[4:7]}-{digits[7:9]}-{digits[9:11]}"
    return value or ""


class UserRegisterForm(forms.ModelForm):
    phone = forms.CharField(
        label="Телефон",
        max_length=20,
        widget=forms.TextInput(attrs={
            "placeholder": "+7 (999) 123-45-67",
            "inputmode": "numeric",
            "autocomplete": "tel",
        })
    )
    password1 = forms.CharField(
        label="Пароль",
        widget=forms.PasswordInput(attrs={
            "placeholder": "Минимум 8 символов",
            "autocomplete": "new-password",
        }),
        help_text="Минимум 8 символов."
    )
    password2 = forms.CharField(
        label="Повторите пароль",
        widget=forms.PasswordInput(attrs={
            "placeholder": "Повторите пароль",
            "autocomplete": "new-password",
        })
    )
    accept_terms = forms.BooleanField(
        label="Я принимаю условия аренды",
        required=True
    )
    accept_personal_data = forms.BooleanField(
        label="Я даю согласие на обработку персональных данных",
        required=True
    )

    class Meta:
        model = User
        fields = ("phone",)

    def clean_phone(self):
        phone = normalize_phone(self.cleaned_data["phone"])
        if len(phone) != 11 or not phone.startswith("7"):
            raise ValidationError("Введите корректный номер телефона.")
        if User.objects.filter(phone=phone).exists():
            raise ValidationError("Пользователь с таким номером уже зарегистрирован.")
        return phone

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")

        if password1 and password2 and password1 != password2:
            self.add_error("password2", "Пароли не совпадают.")

        if password1:
            try:
                validate_password(password1)
            except ValidationError as exc:
                self.add_error("password1", exc)

        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        phone = self.cleaned_data["phone"]

        user.phone = phone
        user.username = phone
        user.role = User.Role.CUSTOMER
        user.mark_consents_accepted()
        user.set_password(self.cleaned_data["password1"])

        if commit:
            user.save()
        return user


class UserLoginForm(AuthenticationForm):
    username = forms.CharField(
        label="Телефон",
        widget=forms.TextInput(attrs={
            "placeholder": "+7 (999) 123-45-67",
            "inputmode": "numeric",
            "autocomplete": "tel",
        })
    )
    password = forms.CharField(
        label="Пароль",
        widget=forms.PasswordInput(attrs={
            "placeholder": "Введите пароль",
            "autocomplete": "current-password",
        })
    )

    def clean_username(self):
        return normalize_phone(self.cleaned_data["username"])


class ProfileForm(forms.ModelForm):
    phone = forms.CharField(label="Телефон", disabled=True, required=False)

    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "telegram", "phone")
        labels = {
            "first_name": "Имя",
            "last_name": "Фамилия",
            "email": "Email",
            "telegram": "Telegram",
        }
        widgets = {
            "first_name": forms.TextInput(attrs={"placeholder": "Введите имя"}),
            "last_name": forms.TextInput(attrs={"placeholder": "Введите фамилию"}),
            "email": forms.EmailInput(attrs={"placeholder": "Введите email"}),
            "telegram": forms.TextInput(attrs={"placeholder": "@username"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["phone"].initial = format_phone(self.instance.phone)


class AccountClaimForm(forms.Form):
    phone = forms.CharField(
        label="Телефон",
        max_length=20,
        widget=forms.TextInput(attrs={
            "placeholder": "+7 (999) 123-45-67",
            "inputmode": "numeric",
            "autocomplete": "tel",
        })
    )
    code = forms.CharField(
        label="Код от оператора",
        max_length=6,
        widget=forms.TextInput(attrs={
            "placeholder": "123456",
            "inputmode": "numeric",
            "autocomplete": "one-time-code",
        })
    )
    password1 = forms.CharField(
        label="Пароль",
        widget=forms.PasswordInput(attrs={
            "placeholder": "Минимум 8 символов",
            "autocomplete": "new-password",
        }),
        help_text="Минимум 8 символов."
    )
    password2 = forms.CharField(
        label="Повторите пароль",
        widget=forms.PasswordInput(attrs={
            "placeholder": "Повторите пароль",
            "autocomplete": "new-password",
        })
    )
    accept_terms = forms.BooleanField(
        label="Я принимаю условия аренды",
        required=True
    )
    accept_personal_data = forms.BooleanField(
        label="Я даю согласие на обработку персональных данных",
        required=True
    )

    error_messages = {
        "invalid_claim": "Телефон или код указан неверно. Проверьте данные или попросите оператора выдать новый код.",
        "password_exists": "Для этого аккаунта уже задан пароль. Войдите по телефону и паролю.",
    }

    def clean_phone(self):
        phone = normalize_phone(self.cleaned_data["phone"])
        if len(phone) != 11 or not phone.startswith("7"):
            raise ValidationError("Введите корректный номер телефона.")
        return phone

    def clean_code(self):
        code = ''.join(ch for ch in self.cleaned_data["code"] if ch.isdigit())
        if len(code) != 6:
            raise ValidationError("Введите 6 цифр кода.")
        return code

    def clean(self):
        cleaned_data = super().clean()
        phone = cleaned_data.get("phone")
        code = cleaned_data.get("code")
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")

        if password1 and password2 and password1 != password2:
            self.add_error("password2", "Пароли не совпадают.")

        self.user = None
        self.access_code = None

        if not phone or not code:
            return cleaned_data

        try:
            user = User.objects.get(phone=phone)
        except User.DoesNotExist:
            raise ValidationError(self.error_messages["invalid_claim"])

        if user.has_usable_password():
            raise ValidationError(self.error_messages["password_exists"])

        active_codes = user.account_access_codes.filter(
            used_at__isnull=True,
            expires_at__gte=timezone.now(),
            attempts__lt=settings.ACCOUNT_ACCESS_CODE_MAX_ATTEMPTS,
        )

        for access_code in active_codes:
            if access_code.check_code(code):
                self.user = user
                self.access_code = access_code
                break

        if self.access_code is None:
            latest_code = active_codes.first()
            if latest_code:
                latest_code.attempts += 1
                latest_code.save(update_fields=["attempts"])
            raise ValidationError(self.error_messages["invalid_claim"])

        if password1:
            try:
                validate_password(password1, user)
            except ValidationError as exc:
                self.add_error("password1", exc)

        return cleaned_data

    def save(self):
        self.user.set_password(self.cleaned_data["password1"])
        self.user.mark_consents_accepted()
        self.user.save(update_fields=[
            "password",
            "terms_accepted",
            "personal_data_consent",
            "terms_accepted_at",
            "personal_data_consent_at",
        ])
        self.access_code.mark_used()
        return self.user
