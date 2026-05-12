from decimal import Decimal
from datetime import timedelta
from django.core import mail
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from catalog.models import Bike, BikeCategory, PickupLocation, Tariff
from rentals.forms import BookingForm
from rentals.models import Booking, Rental, make_booking_number
from rentals.services import bike_available_for_period, calculate_booking_quote

class BookingServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="client", password="12345678")
        self.category = BikeCategory.objects.create(name="Горный")
        self.location = PickupLocation.objects.create(name="Центр", address="Чита")
        self.tariff = Tariff.objects.create(
            name="Базовый",
            hourly_rate=Decimal("200.00"),
            daily_rate=Decimal("1200.00"),
            deposit_amount=Decimal("3000.00"),
            late_fee_per_hour=Decimal("250.00"),
        )
        self.bike = Bike.objects.create(
            title="Stels Navigator",
            slug="stels-navigator",
            category=self.category,
            tariff=self.tariff,
            current_location=self.location,
            serial_number="SN-001",
        )

    def test_quote_is_calculated(self):
        start_at = timezone.now()
        end_at = start_at + timedelta(hours=3)
        total, deposit = calculate_booking_quote(start_at, end_at, self.tariff)
        self.assertEqual(total, Decimal("600.00"))
        self.assertEqual(deposit, Decimal("3000.00"))

    def test_bike_unavailable_when_conflict_exists(self):
        start_at = timezone.now() + timedelta(hours=1)
        end_at = start_at + timedelta(hours=2)
        Booking.objects.create(
            number=make_booking_number(),
            customer=self.user,
            bike=self.bike,
            pickup_location=self.location,
            tariff=self.tariff,
            start_at=start_at,
            end_at=end_at,
            status=Booking.Status.CONFIRMED,
        )
        self.assertFalse(bike_available_for_period(self.bike, start_at + timedelta(minutes=30), end_at + timedelta(minutes=30)))

    def test_booking_form_calculates_planned_return_from_hours(self):
        start_at = timezone.localtime(timezone.now() + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
        form = BookingForm(data={
            "start_at": start_at,
            "duration_hours": "4",
            "pickup_location": self.location.pk,
            "comment": "",
        })

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(
            form.cleaned_data["end_at"],
            form.cleaned_data["start_at"] + timedelta(hours=4),
        )

    def test_booking_number_is_short_and_readable(self):
        number = make_booking_number()

        self.assertRegex(number, r"^VR-\d{4}$")

    def test_booking_detail_shows_next_step_and_timeline(self):
        booking = Booking.objects.create(
            number="VR-2001",
            customer=self.user,
            bike=self.bike,
            pickup_location=self.location,
            tariff=self.tariff,
            start_at=timezone.now() + timedelta(hours=1),
            end_at=timezone.now() + timedelta(hours=3),
            quoted_price=Decimal("400.00"),
            deposit_amount=Decimal("3000.00"),
        )
        Rental.objects.create(booking=booking)
        self.client.force_login(self.user)

        response = self.client.get(reverse("booking-detail", kwargs={"pk": booking.pk}))

        self.assertContains(response, "Что дальше?")
        self.assertContains(response, "История брони")
        self.assertContains(response, "Квитанция")

    def test_booking_receipt_page_is_available_to_customer(self):
        booking = Booking.objects.create(
            number="VR-2002",
            customer=self.user,
            bike=self.bike,
            pickup_location=self.location,
            tariff=self.tariff,
            start_at=timezone.now() + timedelta(hours=1),
            end_at=timezone.now() + timedelta(hours=3),
            quoted_price=Decimal("400.00"),
            deposit_amount=Decimal("3000.00"),
        )
        Rental.objects.create(booking=booking)
        self.client.force_login(self.user)

        response = self.client.get(reverse("booking-receipt", kwargs={"pk": booking.pk}))

        self.assertContains(response, "Квитанция по аренде")
        self.assertContains(response, "Печать")

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        SITE_URL="http://127.0.0.1:8000",
        VK_GROUP_TOKEN="",
    )
    def test_operator_cancel_reason_is_saved_and_emailed(self):
        customer = User.objects.create_user(
            username="customer",
            phone="79960000002",
            email="customer@example.com",
            password="12345678",
        )
        operator = User.objects.create_user(
            username="operator",
            role=User.Role.OPERATOR,
            password="12345678",
        )
        booking = Booking.objects.create(
            number="VR-2003",
            customer=customer,
            bike=self.bike,
            pickup_location=self.location,
            tariff=self.tariff,
            start_at=timezone.now() + timedelta(hours=1),
            end_at=timezone.now() + timedelta(hours=3),
            quoted_price=Decimal("400.00"),
            deposit_amount=Decimal("3000.00"),
        )
        Rental.objects.create(booking=booking)
        self.client.force_login(operator)

        response = self.client.post(reverse("booking-cancel", kwargs={"pk": booking.pk}), {
            "reason": "closed",
            "custom_reason": "",
        })

        booking.refresh_from_db()
        self.assertRedirects(response, reverse("operator-dashboard"))
        self.assertEqual(booking.status, Booking.Status.CANCELLED)
        self.assertIn("Прокат уже закрыт", booking.cancellation_reason)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Прокат уже закрыт", mail.outbox[0].body)
