from decimal import Decimal
from datetime import timedelta
from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from catalog.models import Bike, BikeCategory, PickupLocation, Tariff
from rentals.forms import BookingForm
from rentals.models import Booking, make_booking_number
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
