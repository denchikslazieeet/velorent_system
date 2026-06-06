from datetime import timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from catalog.models import Bike, BikeCategory, PickupLocation, Tariff
from rentals.models import Booking, Rental, Payment


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    VK_GROUP_TOKEN="",
)
class OperatorActionApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.operator = User.objects.create_user(
            username="operator",
            password="Mechabear1001",
            role=User.Role.OPERATOR,
        )
        self.customer = User.objects.create_user(
            username="customer",
            phone="79960000001",
            password="Mechabear1001",
            role=User.Role.CUSTOMER,
        )
        self.location = PickupLocation.objects.create(name="ВелоРент - парк", address="Чита")
        self.category = BikeCategory.objects.create(name="Городские")
        self.tariff = Tariff.objects.create(
            name="Городской",
            hourly_rate=Decimal("200.00"),
            daily_rate=Decimal("1200.00"),
            deposit_amount=Decimal("3000.00"),
            late_fee_per_hour=Decimal("250.00"),
        )
        self.bike = Bike.objects.create(
            title="Городской Бриз",
            slug="gorodskoy-briz-api",
            category=self.category,
            tariff=self.tariff,
            current_location=self.location,
            serial_number="API-BIKE-001",
        )
        self.client.force_authenticate(self.operator)

    def create_booking(self, status=Booking.Status.PENDING):
        booking = Booking.objects.create(
            number="VR-9001",
            customer=self.customer,
            bike=self.bike,
            pickup_location=self.location,
            tariff=self.tariff,
            start_at=timezone.now() - timedelta(hours=2),
            end_at=timezone.now() - timedelta(minutes=30),
            quoted_price=Decimal("400.00"),
            deposit_amount=Decimal("3000.00"),
            status=status,
        )
        Rental.objects.create(
            booking=booking,
            status=Rental.Status.ACTIVE if status == Booking.Status.ACTIVE else Rental.Status.READY,
        )
        return booking

    def test_confirm_rejects_non_pending_booking(self):
        booking = self.create_booking(status=Booking.Status.CONFIRMED)

        response = self.client.post(reverse("api-operator-confirm", kwargs={"pk": booking.pk}))

        self.assertEqual(response.status_code, 400)
        self.assertIn("Подтвердить можно только новую бронь", response.data["detail"])

    def test_issue_requires_verified_customer_document(self):
        booking = self.create_booking(status=Booking.Status.CONFIRMED)

        response = self.client.post(reverse("api-operator-issue", kwargs={"pk": booking.pk}))

        self.assertEqual(response.status_code, 400)
        self.assertIn("проверить документ", response.data["detail"])

    def test_complete_calculates_late_damage_and_extra_fees(self):
        self.customer.document_verified = True
        self.customer.save(update_fields=["document_verified"])
        booking = self.create_booking(status=Booking.Status.ACTIVE)
        self.bike.status = Bike.Status.IN_RENT
        self.bike.save(update_fields=["status"])

        response = self.client.post(
            reverse("api-operator-complete", kwargs={"pk": booking.pk}),
            {
                "damage_fee": "100.00",
                "extra_time_fee": "50.00",
                "method": Payment.Method.CASH,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        booking.refresh_from_db()
        rental = booking.rental
        self.assertEqual(booking.status, Booking.Status.COMPLETED)
        self.assertEqual(rental.late_fee, Decimal("250.00"))
        self.assertEqual(rental.damage_fee, Decimal("100.00"))
        self.assertEqual(rental.extra_time_fee, Decimal("50.00"))
        self.assertEqual(rental.final_price, Decimal("800.00"))
        payment = booking.payments.get(kind=Payment.Kind.RENTAL)
        self.assertEqual(payment.status, Payment.Status.PENDING)


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    VK_GROUP_TOKEN="",
)
class BookingApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.customer = User.objects.create_user(
            username="api-customer",
            first_name="Иван",
            last_name="Петров",
            phone="79960000011",
            password="Mechabear1001",
            role=User.Role.CUSTOMER,
        )
        self.location = PickupLocation.objects.create(name="ВелоРент - парк", address="Чита")
        self.category = BikeCategory.objects.create(name="Городские")
        self.tariff = Tariff.objects.create(
            name="Городской",
            hourly_rate=Decimal("200.00"),
            daily_rate=Decimal("1200.00"),
            deposit_amount=Decimal("3000.00"),
            late_fee_per_hour=Decimal("250.00"),
        )
        self.bike = Bike.objects.create(
            title="API Bike",
            slug="api-bike",
            category=self.category,
            tariff=self.tariff,
            current_location=self.location,
            serial_number="API-BIKE-BOOKING",
        )
        self.client.force_authenticate(self.customer)

    def test_create_rejects_past_start(self):
        response = self.client.post(
            reverse("api-bookings-list"),
            {
                "bike": self.bike.pk,
                "pickup_location": self.location.pk,
                "start_at": timezone.now() - timedelta(hours=1),
                "end_at": timezone.now() + timedelta(hours=1),
                "comment": "",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("start_at", response.data)

    def test_create_applies_and_clears_no_show_surcharge(self):
        self.customer.next_booking_hourly_surcharge = Decimal("50.00")
        self.customer.next_booking_penalty_reason = "Неявка"
        self.customer.save(update_fields=["next_booking_hourly_surcharge", "next_booking_penalty_reason"])
        start_at = timezone.now() + timedelta(hours=1)

        response = self.client.post(
            reverse("api-bookings-list"),
            {
                "bike": self.bike.pk,
                "pickup_location": self.location.pk,
                "start_at": start_at,
                "end_at": start_at + timedelta(hours=2),
                "comment": "",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        booking = Booking.objects.get(pk=response.data["id"])
        self.assertEqual(booking.quoted_price, Decimal("500.00"))
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.next_booking_hourly_surcharge, Decimal("0.00"))

    def test_create_requires_and_saves_missing_customer_name(self):
        self.customer.first_name = ""
        self.customer.last_name = ""
        self.customer.save(update_fields=["first_name", "last_name"])
        start_at = timezone.now() + timedelta(hours=1)

        response = self.client.post(
            reverse("api-bookings-list"),
            {
                "first_name": "Иван",
                "last_name": "Петров",
                "bike": self.bike.pk,
                "pickup_location": self.location.pk,
                "start_at": start_at,
                "end_at": start_at + timedelta(hours=2),
                "comment": "",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.first_name, "Иван")
        self.assertEqual(self.customer.last_name, "Петров")
