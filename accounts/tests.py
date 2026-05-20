from datetime import timedelta
import re

from django.core import mail
from django.db import IntegrityError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .forms import AccountClaimForm
from .models import AccountAccessCode, EmailVerificationCode, User, UserNotification
from catalog.models import Bike, BikeCategory, PickupLocation, Tariff
from integrations.vk_notifications import notify_booking_event, send_vk_message
from rentals.models import Booking


class AccountClaimFormTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="79991234567",
            phone="79991234567",
        )
        self.user.set_unusable_password()
        self.user.save(update_fields=["password"])
        self.access_code, self.raw_code = AccountAccessCode.create_for_user(self.user)

    def form_data(self, code=None):
        return {
            "phone": "+7 (999) 123-45-67",
            "code": code or self.raw_code,
            "password1": "StrongPass123",
            "password2": "StrongPass123",
            "accept_terms": "on",
            "accept_personal_data": "on",
        }

    def test_claim_sets_password_and_uses_code(self):
        form = AccountClaimForm(data=self.form_data())

        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()

        user.refresh_from_db()
        self.access_code.refresh_from_db()
        self.assertTrue(user.has_usable_password())
        self.assertTrue(user.check_password("StrongPass123"))
        self.assertTrue(user.terms_accepted)
        self.assertIsNotNone(self.access_code.used_at)

    def test_invalid_code_does_not_set_password_and_counts_attempt(self):
        form = AccountClaimForm(data=self.form_data(code="000000"))

        self.assertFalse(form.is_valid())

        self.user.refresh_from_db()
        self.access_code.refresh_from_db()
        self.assertFalse(self.user.has_usable_password())
        self.assertEqual(self.access_code.attempts, 1)


class UserLoginTests(TestCase):
    def test_non_blank_phone_is_unique_at_database_level(self):
        User.objects.create_user(
            username="customer-one",
            phone="79961543021",
            password="Mechabear1001",
            role=User.Role.CUSTOMER,
        )

        with self.assertRaises(IntegrityError):
            User.objects.create_user(
                username="customer-two",
                phone="79961543021",
                password="Mechabear1001",
                role=User.Role.CUSTOMER,
            )

    def test_customer_can_login_by_phone_even_when_username_is_not_phone(self):
        User.objects.create_user(
            username="customer01",
            phone="79961543021",
            password="Mechabear1001",
            role=User.Role.CUSTOMER,
        )

        response = self.client.post(reverse("login"), {
            "username": "8 996 154-30-21",
            "password": "Mechabear1001",
        })

        self.assertRedirects(response, reverse("user-dashboard"))


class EmailVerificationTests(TestCase):
    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_profile_email_change_sends_code_without_changing_email_immediately(self):
        user = User.objects.create_user(
            username="customer",
            phone="79960000001",
            email="old@example.com",
            email_verified_at=timezone.now(),
            password="12345678",
        )
        self.client.force_login(user)

        response = self.client.post(reverse("profile"), {
            "first_name": "Иван",
            "last_name": "Петров",
            "email": "new@example.com",
            "telegram": "",
            "edit_email": "1",
        })

        self.assertRedirects(response, reverse("profile"))
        user.refresh_from_db()
        self.assertEqual(user.email, "old@example.com")
        self.assertTrue(user.email_is_verified)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("код подтверждения email", mail.outbox[0].subject.lower())
        pending_code = EmailVerificationCode.objects.get(user=user)
        self.assertEqual(pending_code.email, "new@example.com")

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_email_confirm_sets_verified_email(self):
        user = User.objects.create_user(
            username="customer",
            phone="79960000001",
            password="12345678",
        )
        self.client.force_login(user)
        self.client.post(reverse("profile"), {
            "first_name": "",
            "last_name": "",
            "email": "new@example.com",
            "telegram": "",
        })
        raw_code = re.search(r"\b\d{6}\b", mail.outbox[0].body).group(0)

        response = self.client.post(reverse("email-confirm"), {"code": raw_code})

        self.assertRedirects(response, reverse("profile"))
        user.refresh_from_db()
        self.assertEqual(user.email, "new@example.com")
        self.assertTrue(user.email_is_verified)
        self.assertFalse(user.email_verification_codes.filter(used_at__isnull=True).exists())

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_VERIFICATION_RESEND_SECONDS=60,
    )
    def test_email_code_resend_is_available_after_one_minute(self):
        user = User.objects.create_user(
            username="customer",
            phone="79960000001",
            password="12345678",
        )
        self.client.force_login(user)
        self.client.post(reverse("profile"), {
            "first_name": "",
            "last_name": "",
            "email": "new@example.com",
            "telegram": "",
        })
        self.assertEqual(len(mail.outbox), 1)

        response = self.client.post(reverse("email-resend"))
        self.assertRedirects(response, reverse("profile"))
        self.assertEqual(len(mail.outbox), 1)

        EmailVerificationCode.objects.filter(user=user, used_at__isnull=True).update(
            created_at=timezone.now() - timedelta(seconds=61)
        )
        response = self.client.post(reverse("email-resend"))

        self.assertRedirects(response, reverse("profile"))
        self.assertEqual(len(mail.outbox), 2)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_verified_email_is_not_changed_without_edit_mode(self):
        user = User.objects.create_user(
            username="customer",
            phone="79960000001",
            email="old@example.com",
            email_verified_at=timezone.now(),
            password="12345678",
        )
        self.client.force_login(user)

        response = self.client.post(reverse("profile"), {
            "first_name": "",
            "last_name": "",
            "email": "new@example.com",
            "telegram": "",
        })

        self.assertRedirects(response, reverse("profile"))
        user.refresh_from_db()
        self.assertEqual(user.email, "old@example.com")
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_verified_email_can_be_changed_in_edit_mode(self):
        user = User.objects.create_user(
            username="customer",
            phone="79960000001",
            email="old@example.com",
            email_verified_at=timezone.now(),
            password="12345678",
        )
        self.client.force_login(user)

        response = self.client.post(reverse("profile"), {
            "first_name": "",
            "last_name": "",
            "email": "new@example.com",
            "telegram": "",
            "edit_email": "1",
        })

        self.assertRedirects(response, reverse("profile"))
        user.refresh_from_db()
        self.assertEqual(user.email, "old@example.com")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            user.email_verification_codes.filter(used_at__isnull=True).first().email,
            "new@example.com",
        )


class VKOAuthViewTests(TestCase):
    @override_settings(VK_CLIENT_ID="123", VK_CLIENT_SECRET="secret")
    def test_vk_login_redirects_to_vk_and_stores_state(self):
        response = self.client.get(reverse("vk-login"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("oauth.vk.com/authorize", response["Location"])
        self.assertIn("vk_oauth_state", self.client.session)

    def test_vk_login_without_settings_returns_to_login(self):
        response = self.client.get(reverse("vk-login"))

        self.assertRedirects(response, reverse("login"))

    def test_vk_callback_rejects_invalid_state(self):
        response = self.client.get(reverse("vk-callback"), {"state": "bad", "code": "code"})

        self.assertRedirects(response, reverse("login"))

    def test_vk_link_requires_login(self):
        response = self.client.get(reverse("vk-link"))

        self.assertEqual(response.status_code, 302)


class VKNotificationTests(TestCase):
    def test_notification_without_group_token_is_skipped(self):
        user = User.objects.create_user(
            username="vk-user",
            vk_id="12345",
            vk_notifications_enabled=True,
        )

        self.assertFalse(send_vk_message(user, "test"))


class UserNotificationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="customer",
            email="customer@example.com",
            email_verified_at=timezone.now(),
            role=User.Role.CUSTOMER,
        )
        self.location = PickupLocation.objects.create(name="ВелоРент - парк", address="Чита")
        self.category = BikeCategory.objects.create(name="Городские")
        self.tariff = Tariff.objects.create(
            name="Городской",
            hourly_rate=250,
            daily_rate=1500,
            deposit_amount=3000,
            late_fee_per_hour=350,
        )
        self.bike = Bike.objects.create(
            title="Городской Бриз",
            slug="gorodskoy-briz-test",
            category=self.category,
            tariff=self.tariff,
            current_location=self.location,
            serial_number="TEST-BIKE-001",
        )
        self.booking = Booking.objects.create(
            number="VR-1001",
            customer=self.user,
            bike=self.bike,
            pickup_location=self.location,
            tariff=self.tariff,
            start_at=timezone.now(),
            end_at=timezone.now() + timedelta(hours=2),
            quoted_price=500,
            deposit_amount=3000,
        )

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        SITE_URL="http://127.0.0.1:8000",
        VK_GROUP_TOKEN="",
    )
    def test_booking_event_creates_site_notification_and_email(self):
        result = notify_booking_event(self.booking, "confirmed")

        self.assertIsInstance(result["site_notification"], UserNotification)
        self.assertEqual(result["operator_notifications"], [])
        self.assertTrue(result["email_sent"])
        self.assertFalse(result["vk_sent"])
        self.assertEqual(self.user.notifications.filter(read_at__isnull=True).count(), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Бронь VR-1001 подтверждена", mail.outbox[0].subject)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        VK_GROUP_TOKEN="",
    )
    def test_booking_created_notifies_operators(self):
        operator = User.objects.create_user(
            username="operator",
            role=User.Role.OPERATOR,
        )

        result = notify_booking_event(self.booking, "created")

        self.assertEqual(len(result["operator_notifications"]), 1)
        self.assertEqual(result["operator_notifications"][0].user, operator)
        self.assertIn("Новая бронь VR-1001", result["operator_notifications"][0].title)
        self.assertIn("Городской Бриз", result["operator_notifications"][0].message)

    def test_notifications_page_marks_items_read(self):
        UserNotification.objects.create(
            user=self.user,
            title="Тест",
            message="Сообщение",
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("notifications"))
        self.assertContains(response, "Тест")
        self.assertEqual(self.user.notifications.filter(read_at__isnull=True).count(), 0)

        response = self.client.post(reverse("notifications-read"))
        self.assertRedirects(response, reverse("notifications"))
        self.assertEqual(self.user.notifications.filter(read_at__isnull=True).count(), 0)

    def test_authenticated_pages_are_not_cached(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("notifications"))

        self.assertIn("no-store", response.headers["Cache-Control"])
