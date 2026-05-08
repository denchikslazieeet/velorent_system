from datetime import timedelta

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .forms import AccountClaimForm
from .models import AccountAccessCode, User, UserNotification
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
