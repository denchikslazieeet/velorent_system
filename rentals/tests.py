from decimal import Decimal
from datetime import timedelta
from django.core import mail
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from catalog.models import Bike, BikeCategory, PickupLocation, Tariff
from rentals.forms import BookingForm, OperatorBookingForm
from rentals.models import Booking, Payment, Rental, make_booking_number
from rentals.services import bike_available_for_period, bike_next_available_at, calculate_booking_quote, compute_late_fee

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

    def test_reserved_bike_can_be_booked_for_non_overlapping_period(self):
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
        self.bike.status = Bike.Status.RESERVED
        self.bike.save(update_fields=["status"])

        self.assertTrue(
            bike_available_for_period(
                self.bike,
                end_at + timedelta(hours=1),
                end_at + timedelta(hours=3),
            )
        )

    def test_reserved_bike_stays_visible_for_new_period_selection(self):
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
        self.bike.status = Bike.Status.RESERVED
        self.bike.save(update_fields=["status"])

        response = self.client.get(reverse("catalog"))
        operator_form = OperatorBookingForm()

        self.assertContains(response, self.bike.title)
        self.assertContains(response, "Свободен после")
        self.assertEqual(bike_next_available_at(self.bike), end_at)
        self.assertIn(self.bike, operator_form.fields["bike"].queryset)

    def test_reserved_bike_without_future_booking_shows_explanation(self):
        self.bike.status = Bike.Status.RESERVED
        self.bike.save(update_fields=["status"])

        catalog_response = self.client.get(reverse("catalog"))
        detail_response = self.client.get(reverse("bike-detail", kwargs={"slug": self.bike.slug}))

        self.assertContains(catalog_response, self.bike.title)
        self.assertContains(catalog_response, "Период брони не найден")
        self.assertContains(detail_response, "Период брони не найден")
        self.assertContains(detail_response, "Выбрать время")

    def test_reserved_bike_with_stale_confirmed_booking_still_shows_end_time(self):
        start_at = timezone.now() - timedelta(hours=5)
        end_at = timezone.now() - timedelta(hours=2)
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
        self.bike.status = Bike.Status.RESERVED
        self.bike.save(update_fields=["status"])

        response = self.client.get(reverse("bike-detail", kwargs={"slug": self.bike.slug}))

        self.assertContains(response, "Свободен после")
        self.assertEqual(bike_next_available_at(self.bike), end_at)

    def test_quote_rounds_started_hour_up(self):
        start_at = timezone.now()
        end_at = start_at + timedelta(hours=1, minutes=1)

        total, _ = calculate_booking_quote(start_at, end_at, self.tariff)

        self.assertEqual(total, Decimal("400.00"))

    def test_late_fee_rounds_started_hour_up(self):
        start_at = timezone.now() - timedelta(hours=3)
        end_at = timezone.now() - timedelta(minutes=30)
        booking = Booking.objects.create(
            number=make_booking_number(),
            customer=self.user,
            bike=self.bike,
            pickup_location=self.location,
            tariff=self.tariff,
            start_at=start_at,
            end_at=end_at,
            quoted_price=Decimal("400.00"),
            deposit_amount=Decimal("3000.00"),
        )

        late_fee = compute_late_fee(booking, timezone.now())

        self.assertEqual(late_fee, Decimal("250.00"))

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

    def test_booking_form_requires_and_saves_missing_customer_name(self):
        start_at = timezone.localtime(timezone.now() + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
        form = BookingForm(
            customer=self.user,
            data={
                "first_name": "Иван",
                "last_name": "Петров",
                "start_at": start_at,
                "duration_hours": "4",
                "pickup_location": self.location.pk,
                "comment": "",
            },
        )

        self.assertTrue(form.is_valid(), form.errors)
        form.save_customer_name()
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Иван")
        self.assertEqual(self.user.last_name, "Петров")

    def test_booking_form_rejects_missing_customer_name(self):
        start_at = timezone.localtime(timezone.now() + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
        form = BookingForm(
            customer=self.user,
            data={
                "start_at": start_at,
                "duration_hours": "4",
                "pickup_location": self.location.pk,
                "comment": "",
            },
        )

        self.assertFalse(form.is_valid())
        self.assertIn("first_name", form.errors)
        self.assertIn("last_name", form.errors)

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
        self.assertNotContains(response, "Квитанция")

    def test_booking_detail_shows_receipt_after_rental_is_closed(self):
        booking = Booking.objects.create(
            number="VR-2004",
            customer=self.user,
            bike=self.bike,
            pickup_location=self.location,
            tariff=self.tariff,
            start_at=timezone.now() - timedelta(hours=3),
            end_at=timezone.now() - timedelta(hours=1),
            quoted_price=Decimal("400.00"),
            deposit_amount=Decimal("3000.00"),
            status=Booking.Status.COMPLETED,
        )
        Rental.objects.create(
            booking=booking,
            status=Rental.Status.COMPLETED,
            final_price=Decimal("400.00"),
        )
        Payment.objects.create(
            booking=booking,
            amount=Decimal("400.00"),
            kind=Payment.Kind.RENTAL,
            status=Payment.Status.PAID,
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("booking-detail", kwargs={"pk": booking.pk}))

        self.assertContains(response, "Квитанция")

    def test_booking_receipt_page_is_available_to_customer(self):
        booking = Booking.objects.create(
            number="VR-2002",
            customer=self.user,
            bike=self.bike,
            pickup_location=self.location,
            tariff=self.tariff,
            start_at=timezone.now() - timedelta(hours=3),
            end_at=timezone.now() - timedelta(hours=1),
            quoted_price=Decimal("400.00"),
            deposit_amount=Decimal("3000.00"),
            status=Booking.Status.COMPLETED,
        )
        Rental.objects.create(
            booking=booking,
            status=Rental.Status.COMPLETED,
            final_price=Decimal("400.00"),
        )
        Payment.objects.create(
            booking=booking,
            amount=Decimal("400.00"),
            kind=Payment.Kind.RENTAL,
            status=Payment.Status.PAID,
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("booking-receipt", kwargs={"pk": booking.pk}))

        self.assertContains(response, "Квитанция по аренде")
        self.assertContains(response, "Печать")

    def test_operator_can_open_filled_contract_for_verified_customer(self):
        operator = User.objects.create_user(
            username="operator-contract",
            first_name="Олег",
            last_name="Операторов",
            role=User.Role.OPERATOR,
            password="12345678",
        )
        self.user.first_name = "Иван"
        self.user.last_name = "Петров"
        self.user.phone = "79960000001"
        self.user.document_verified = True
        self.user.document_type = User.DocumentType.PASSPORT
        self.user.document_last4 = "1234"
        self.user.save(update_fields=[
            "first_name",
            "last_name",
            "phone",
            "document_verified",
            "document_type",
            "document_last4",
        ])
        booking = Booking.objects.create(
            number="VR-2020",
            customer=self.user,
            bike=self.bike,
            pickup_location=self.location,
            tariff=self.tariff,
            start_at=timezone.now() + timedelta(hours=1),
            end_at=timezone.now() + timedelta(hours=3),
            quoted_price=Decimal("400.00"),
            deposit_amount=Decimal("3000.00"),
            status=Booking.Status.CONFIRMED,
        )
        Rental.objects.create(booking=booking)
        self.client.force_login(operator)

        response = self.client.get(reverse("booking-contract", kwargs={"pk": booking.pk}))

        self.assertContains(response, "ДОГОВОР ПРОКАТА ВЕЛОСИПЕДА")
        self.assertContains(response, "Иван Петров")
        self.assertContains(response, "1234")
        self.assertContains(response, self.bike.serial_number)

    def test_contract_requires_verified_customer_document(self):
        operator = User.objects.create_user(
            username="operator-contract-blocked",
            role=User.Role.OPERATOR,
            password="12345678",
        )
        booking = Booking.objects.create(
            number="VR-2021",
            customer=self.user,
            bike=self.bike,
            pickup_location=self.location,
            tariff=self.tariff,
            start_at=timezone.now() + timedelta(hours=1),
            end_at=timezone.now() + timedelta(hours=3),
            quoted_price=Decimal("400.00"),
            deposit_amount=Decimal("3000.00"),
            status=Booking.Status.CONFIRMED,
        )
        Rental.objects.create(booking=booking)
        self.client.force_login(operator)

        response = self.client.get(reverse("booking-contract", kwargs={"pk": booking.pk}))

        self.assertRedirects(response, reverse("booking-detail", kwargs={"pk": booking.pk}))

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        OPERATOR_NOTIFICATION_EMAILS=["velo-rent.official@yandex.com"],
        VK_GROUP_TOKEN="",
    )
    def test_document_verification_notifies_customer_and_operator(self):
        operator = User.objects.create_user(
            username="operator-verification",
            role=User.Role.OPERATOR,
            password="12345678",
        )
        self.user.email = "client@example.com"
        self.user.email_verified_at = timezone.now()
        self.user.save(update_fields=["email", "email_verified_at"])
        booking = Booking.objects.create(
            number="VR-2023",
            customer=self.user,
            bike=self.bike,
            pickup_location=self.location,
            tariff=self.tariff,
            start_at=timezone.now() + timedelta(hours=1),
            end_at=timezone.now() + timedelta(hours=3),
            quoted_price=Decimal("400.00"),
            deposit_amount=Decimal("3000.00"),
            status=Booking.Status.CONFIRMED,
        )
        Rental.objects.create(booking=booking)
        self.client.force_login(operator)

        response = self.client.post(reverse("verify-customer", kwargs={"pk": booking.pk}), {
            "first_name": "Иван",
            "last_name": "Петров",
            "document_type": User.DocumentType.PASSPORT,
            "document_last4": "1234",
        })

        self.user.refresh_from_db()
        self.assertRedirects(response, reverse("booking-detail", kwargs={"pk": booking.pk}))
        self.assertTrue(self.user.document_verified)
        self.assertTrue(self.user.notifications.filter(title__contains="Документ").exists())
        self.assertEqual(len(mail.outbox), 2)

    def test_customer_cannot_open_operator_contract(self):
        self.user.first_name = "Иван"
        self.user.last_name = "Петров"
        self.user.document_verified = True
        self.user.document_type = User.DocumentType.PASSPORT
        self.user.document_last4 = "1234"
        self.user.save(update_fields=[
            "first_name",
            "last_name",
            "document_verified",
            "document_type",
            "document_last4",
        ])
        booking = Booking.objects.create(
            number="VR-2022",
            customer=self.user,
            bike=self.bike,
            pickup_location=self.location,
            tariff=self.tariff,
            start_at=timezone.now() + timedelta(hours=1),
            end_at=timezone.now() + timedelta(hours=3),
            quoted_price=Decimal("400.00"),
            deposit_amount=Decimal("3000.00"),
            status=Booking.Status.CONFIRMED,
        )
        Rental.objects.create(booking=booking)
        self.client.force_login(self.user)

        response = self.client.get(reverse("booking-contract", kwargs={"pk": booking.pk}))

        self.assertEqual(response.status_code, 403)

    @override_settings(VK_GROUP_TOKEN="")
    def test_operator_can_extend_active_rental(self):
        operator = User.objects.create_user(
            username="operator-extend",
            role=User.Role.OPERATOR,
            password="12345678",
        )
        booking = Booking.objects.create(
            number="VR-2010",
            customer=self.user,
            bike=self.bike,
            pickup_location=self.location,
            tariff=self.tariff,
            start_at=timezone.now() - timedelta(hours=1),
            end_at=timezone.now() + timedelta(hours=1),
            quoted_price=Decimal("400.00"),
            deposit_amount=Decimal("3000.00"),
            status=Booking.Status.ACTIVE,
        )
        Rental.objects.create(booking=booking, status=Rental.Status.ACTIVE)
        self.client.force_login(operator)

        response = self.client.post(reverse("rental-extend", kwargs={"pk": booking.pk}), {
            "extend_hours": "2",
        })

        booking.refresh_from_db()
        self.assertRedirects(response, reverse("booking-detail", kwargs={"pk": booking.pk}))
        self.assertGreater(booking.end_at, timezone.now() + timedelta(hours=2))
        self.assertGreater(booking.quoted_price, Decimal("400.00"))

    def test_operator_cannot_extend_active_rental_into_future_booking(self):
        operator = User.objects.create_user(
            username="operator-conflict",
            role=User.Role.OPERATOR,
            password="12345678",
        )
        booking = Booking.objects.create(
            number="VR-2011",
            customer=self.user,
            bike=self.bike,
            pickup_location=self.location,
            tariff=self.tariff,
            start_at=timezone.now() - timedelta(hours=1),
            end_at=timezone.now() + timedelta(hours=1),
            quoted_price=Decimal("400.00"),
            deposit_amount=Decimal("3000.00"),
            status=Booking.Status.ACTIVE,
        )
        Rental.objects.create(booking=booking, status=Rental.Status.ACTIVE)
        other_customer = User.objects.create_user(username="future-client", password="12345678")
        Booking.objects.create(
            number="VR-2012",
            customer=other_customer,
            bike=self.bike,
            pickup_location=self.location,
            tariff=self.tariff,
            start_at=booking.end_at + timedelta(minutes=30),
            end_at=booking.end_at + timedelta(hours=2),
            quoted_price=Decimal("400.00"),
            deposit_amount=Decimal("3000.00"),
            status=Booking.Status.CONFIRMED,
        )
        self.client.force_login(operator)

        response = self.client.post(reverse("rental-extend", kwargs={"pk": booking.pk}), {
            "extend_hours": "2",
        })

        booking.refresh_from_db()
        self.assertRedirects(response, reverse("booking-detail", kwargs={"pk": booking.pk}))
        self.assertEqual(booking.quoted_price, Decimal("400.00"))

    @override_settings(VK_GROUP_TOKEN="")
    def test_return_rental_clamps_negative_damage_fee(self):
        operator = User.objects.create_user(
            username="operator-return",
            role=User.Role.OPERATOR,
            password="12345678",
        )
        booking = Booking.objects.create(
            number="VR-2013",
            customer=self.user,
            bike=self.bike,
            pickup_location=self.location,
            tariff=self.tariff,
            start_at=timezone.now() - timedelta(hours=1),
            end_at=timezone.now() + timedelta(hours=1),
            quoted_price=Decimal("400.00"),
            deposit_amount=Decimal("3000.00"),
            status=Booking.Status.ACTIVE,
        )
        Rental.objects.create(booking=booking, status=Rental.Status.ACTIVE)
        self.bike.status = Bike.Status.IN_RENT
        self.bike.save(update_fields=["status"])
        self.client.force_login(operator)

        response = self.client.post(reverse("rental-return", kwargs={"pk": booking.pk}), {
            "damage_fee": "-1000.00",
            "end_condition": "Без повреждений",
        })

        booking.refresh_from_db()
        rental = booking.rental
        self.assertRedirects(response, reverse("booking-detail", kwargs={"pk": booking.pk}))
        self.assertEqual(rental.damage_fee, Decimal("0.00"))
        self.assertGreaterEqual(rental.final_price, Decimal("0.00"))

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
            email_verified_at=timezone.now(),
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
        self.assertEqual(len(mail.outbox), 2)
        customer_email = next(
            message for message in mail.outbox if message.to == ["customer@example.com"]
        )
        operator_email = next(
            message
            for message in mail.outbox
            if message.to == ["velo-rent.official@yandex.com"]
        )
        self.assertIn("Прокат уже закрыт", customer_email.body)
        self.assertIn("Прокат уже закрыт", operator_email.body)
