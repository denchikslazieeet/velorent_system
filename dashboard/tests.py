from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from catalog.models import Bike, BikeCategory, PickupLocation, Tariff
from rentals.models import Booking, Rental


class OperatorDashboardTests(TestCase):
    def setUp(self):
        self.operator = User.objects.create_user(
            username="operator",
            password="12345678",
            role=User.Role.OPERATOR,
        )
        self.category = BikeCategory.objects.create(name="Городские")
        self.location = PickupLocation.objects.create(name="ВелоРент - парк", address="Чита")
        self.tariff = Tariff.objects.create(
            name="Базовый",
            hourly_rate=Decimal("200.00"),
            daily_rate=Decimal("1200.00"),
            deposit_amount=Decimal("3000.00"),
            late_fee_per_hour=Decimal("250.00"),
        )
        self.bike = Bike.objects.create(
            title="Городской Бриз",
            slug="gorodskoy-briz-test",
            category=self.category,
            tariff=self.tariff,
            current_location=self.location,
            serial_number="VR-TEST-001",
        )

    def make_booking(self, number, customer_name, status):
        customer = User.objects.create_user(
            username=f"customer-{number}",
            first_name=customer_name,
            phone=f"7996{number[-4:]}000",
            password="12345678",
        )
        booking = Booking.objects.create(
            number=number,
            customer=customer,
            bike=self.bike,
            pickup_location=self.location,
            tariff=self.tariff,
            start_at=timezone.now() - timedelta(hours=3),
            end_at=timezone.now() - timedelta(hours=1),
            quoted_price=Decimal("400.00"),
            deposit_amount=Decimal("3000.00"),
            status=status,
        )
        Rental.objects.create(booking=booking)
        return booking

    def test_quick_filters_start_with_all(self):
        self.client.force_login(self.operator)

        response = self.client.get(reverse("operator-dashboard"))

        self.assertEqual(response.context["quick_filters"][0]["key"], "all")

    def test_text_filter_searches_all_bookings_even_from_work_tab(self):
        completed_booking = self.make_booking("VR-8101", "Закрытый", Booking.Status.COMPLETED)
        self.make_booking("VR-8102", "Рабочий", Booking.Status.PENDING)
        self.client.force_login(self.operator)

        response = self.client.get(
            reverse("operator-dashboard"),
            {"quick": "work", "q": "Закрытый"},
        )

        shown_numbers = [booking.number for booking in response.context["recent_bookings"]]
        self.assertEqual(response.context["current_quick"], "all")
        self.assertIn(completed_booking.number, shown_numbers)
