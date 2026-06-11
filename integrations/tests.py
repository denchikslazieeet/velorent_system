from datetime import timedelta
from decimal import Decimal
from unittest.mock import Mock, patch

from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import User, UserNotification
from catalog.models import Bike, BikeCategory, PickupLocation, Tariff
from integrations.email_delivery import send_email_reliably
from integrations.models import BookingNotificationEvent, EmailDelivery, SyncEvent
from integrations.services import queue_booking_sync, send_sync_event
from integrations.vk_notifications import build_booking_message, notify_booking_event, send_vk_message
from rentals.models import Booking, Rental


class OneCSyncTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(username="customer", phone="79960000001")
        self.location = PickupLocation.objects.create(name="Парк", address="Чита")
        self.category = BikeCategory.objects.create(name="Городские")
        self.tariff = Tariff.objects.create(
            name="Городской",
            hourly_rate=Decimal("200.00"),
            deposit_amount=Decimal("3000.00"),
        )
        self.bike = Bike.objects.create(
            title="Городской",
            slug="city-bike",
            category=self.category,
            tariff=self.tariff,
            current_location=self.location,
            serial_number="SYNC-001",
        )
        self.booking = Booking.objects.create(
            number="VR-3001",
            customer=self.customer,
            bike=self.bike,
            pickup_location=self.location,
            tariff=self.tariff,
            start_at=timezone.now() + timedelta(hours=1),
            end_at=timezone.now() + timedelta(hours=2),
            quoted_price=Decimal("200.00"),
            deposit_amount=Decimal("3000.00"),
        )

    def test_queue_booking_sync_keeps_pending_when_immediate_disabled(self):
        event = queue_booking_sync(self.booking)

        self.assertEqual(event.status, SyncEvent.Status.PENDING)

    @override_settings(ONEC_API_URL="http://onec.local/sync", ONEC_API_TOKEN="secret", ONEC_API_TIMEOUT_SECONDS=3)
    @patch("integrations.services.urlopen")
    def test_send_sync_event_uses_bearer_token(self, mocked_urlopen):
        response = Mock()
        response.read.return_value = b'{"ok": true}'
        mocked_urlopen.return_value.__enter__.return_value = response
        event = queue_booking_sync(self.booking)

        sent = send_sync_event(event)

        self.assertTrue(sent)
        event.refresh_from_db()
        self.assertEqual(event.status, SyncEvent.Status.SENT)
        request = mocked_urlopen.call_args.args[0]
        self.assertEqual(request.headers["Authorization"], "Bearer secret")


@override_settings(VK_GROUP_TOKEN="token", VK_API_VERSION="5.199")
class VKNotificationParsingTests(TestCase):
    @patch("integrations.vk_notifications.urlopen")
    def test_vk_error_json_returns_false(self, mocked_urlopen):
        response = Mock()
        response.read.return_value = b'{"error": {"error_code": 901}}'
        mocked_urlopen.return_value.__enter__.return_value = response
        user = User.objects.create_user(username="vk", vk_id="123", vk_notifications_enabled=True)

        self.assertFalse(send_vk_message(user, "test"))

    @patch("integrations.vk_notifications.urlopen")
    def test_vk_response_json_returns_true(self, mocked_urlopen):
        response = Mock()
        response.read.return_value = b'{"response": 1}'
        mocked_urlopen.return_value.__enter__.return_value = response
        user = User.objects.create_user(username="vk-ok", vk_id="456", vk_notifications_enabled=True)

        self.assertTrue(send_vk_message(user, "test"))


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    OPERATOR_NOTIFICATION_EMAILS=["velo-rent.official@yandex.com"],
    SITE_URL="https://velo-rent-chita.ru",
    VK_GROUP_TOKEN="",
)
class BookingNotificationTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            username="notification-customer",
            phone="79960000001",
            email="customer@example.com",
            email_verified_at=timezone.now(),
            next_booking_hourly_surcharge=Decimal("150.00"),
        )
        self.operator = User.objects.create_user(
            username="notification-operator",
            role=User.Role.OPERATOR,
        )
        self.location = PickupLocation.objects.create(name="Парк", address="Чита")
        self.category = BikeCategory.objects.create(name="Городские")
        self.tariff = Tariff.objects.create(
            name="Городской",
            hourly_rate=Decimal("200.00"),
            deposit_amount=Decimal("3000.00"),
        )
        self.bike = Bike.objects.create(
            title="Городской",
            slug="notification-city-bike",
            category=self.category,
            tariff=self.tariff,
            current_location=self.location,
            serial_number="NOTIFY-001",
        )
        self.booking = Booking.objects.create(
            number="VR-4001",
            customer=self.customer,
            bike=self.bike,
            pickup_location=self.location,
            tariff=self.tariff,
            start_at=timezone.now() + timedelta(hours=1),
            end_at=timezone.now() + timedelta(hours=2),
            quoted_price=Decimal("400.00"),
            deposit_amount=Decimal("3000.00"),
            status=Booking.Status.CONFIRMED,
        )

    def test_important_event_emails_customer_and_operator(self):
        result = notify_booking_event(self.booking, "confirmed")

        self.assertTrue(result["email_sent"])
        self.assertTrue(result["operator_email_sent"])
        self.assertEqual(len(result["operator_notifications"]), 1)
        self.assertEqual(len(mail.outbox), 2)
        self.assertTrue(
            UserNotification.objects.filter(user=self.operator, title__contains="VR-4001").exists()
        )

    def test_no_show_message_contains_next_booking_surcharge(self):
        message = build_booking_message(self.booking, "no_show")

        self.assertIn("150.00 ₽ за час", message)

    def test_completed_message_contains_fines(self):
        Rental.objects.create(
            booking=self.booking,
            damage_fee=Decimal("700.00"),
            late_fee=Decimal("250.00"),
            final_price=Decimal("1350.00"),
            status=Rental.Status.COMPLETED,
        )

        message = build_booking_message(self.booking, "completed")

        self.assertIn("Штраф за просрочку: 250.00 ₽", message)
        self.assertIn("Штраф за повреждение: 700.00 ₽", message)
        self.assertIn("Итого к оплате: 1350.00 ₽", message)

    def test_reminder_command_sends_each_reminder_once(self):
        call_command("send_booking_reminders")
        call_command("send_booking_reminders")

        self.assertEqual(
            BookingNotificationEvent.objects.filter(
                booking=self.booking,
                event__startswith="pickup_reminder:",
                audience=BookingNotificationEvent.Audience.CUSTOMER,
            ).count(),
            1,
        )
        self.assertEqual(
            self.customer.notifications.filter(title__contains="Напоминание о выдаче").count(),
            1,
        )
        self.assertEqual(len(mail.outbox), 1)

    def test_overdue_command_warns_operator_once(self):
        self.booking.status = Booking.Status.ACTIVE
        self.booking.end_at = timezone.now() - timedelta(hours=1)
        self.booking.save(update_fields=["status", "end_at", "updated_at"])

        call_command("send_booking_reminders")
        call_command("send_booking_reminders")

        self.assertEqual(
            self.operator.notifications.filter(title__contains="Просрочен возврат").count(),
            1,
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["velo-rent.official@yandex.com"])


class EmailDeliveryRetryTests(TestCase):
    @override_settings(EMAIL_RETRY_DELAY_MINUTES=0)
    @patch("integrations.email_delivery.send_mail", side_effect=RuntimeError("SMTP unavailable"))
    def test_failed_email_is_saved_for_retry(self, mocked_send_mail):
        sent = send_email_reliably(
            "customer@example.com",
            "Тест",
            "Сообщение",
            kind="test",
        )

        self.assertFalse(sent)
        delivery = EmailDelivery.objects.get()
        self.assertEqual(delivery.status, EmailDelivery.Status.FAILED)
        self.assertEqual(delivery.attempts, 1)
        self.assertIn("SMTP unavailable", delivery.last_error)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_RETRY_DELAY_MINUTES=0,
    )
    def test_pending_email_command_retries_delivery(self):
        delivery = EmailDelivery.objects.create(
            recipient="customer@example.com",
            subject="Повтор",
            body="Сообщение",
            status=EmailDelivery.Status.FAILED,
        )

        call_command("send_pending_emails")

        delivery.refresh_from_db()
        self.assertEqual(delivery.status, EmailDelivery.Status.SENT)
        self.assertEqual(len(mail.outbox), 1)
