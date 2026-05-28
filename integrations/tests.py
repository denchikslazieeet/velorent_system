from datetime import timedelta
from decimal import Decimal
from unittest.mock import Mock, patch

from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import User
from catalog.models import Bike, BikeCategory, PickupLocation, Tariff
from integrations.models import SyncEvent
from integrations.services import queue_booking_sync, send_sync_event
from integrations.vk_notifications import send_vk_message
from rentals.models import Booking


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
