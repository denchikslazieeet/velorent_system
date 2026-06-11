from datetime import timedelta
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import AccountAccessCode, User
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

    def test_operator_can_generate_account_code_from_customer_card(self):
        customer = User.objects.create_user(
            username="phone-customer",
            phone="79960000001",
            role=User.Role.CUSTOMER,
        )
        customer.set_unusable_password()
        customer.save(update_fields=["password"])
        self.client.force_login(self.operator)

        response = self.client.post(
            reverse("operator-customer-access-code", kwargs={"pk": customer.pk}),
            follow=True,
        )

        self.assertEqual(AccountAccessCode.objects.filter(user=customer, used_at__isnull=True).count(), 1)
        self.assertContains(response, "Код для задания пароля")

    def test_operator_cannot_generate_account_code_for_activated_customer(self):
        customer = User.objects.create_user(
            username="active-customer",
            phone="79960000002",
            role=User.Role.CUSTOMER,
            password="12345678",
        )
        self.client.force_login(self.operator)

        response = self.client.post(reverse("operator-customer-access-code", kwargs={"pk": customer.pk}))

        self.assertRedirects(response, reverse("operator-customer-detail", kwargs={"pk": customer.pk}))
        self.assertFalse(AccountAccessCode.objects.filter(user=customer).exists())

    @override_settings(
        RENTAL_PROVIDER_NAME="ИП Ким Юрий Брониславович",
        RENTAL_PROVIDER_OGRNIP="323750000053480",
    )
    def test_public_legal_documents_are_available(self):
        privacy_response = self.client.get(reverse("privacy-policy"))
        contract_response = self.client.get(reverse("contract-template"))
        terms_response = self.client.get(reverse("terms"))

        self.assertContains(privacy_response, "Как отозвать согласие")
        self.assertContains(privacy_response, "323750000053480")
        self.assertContains(contract_response, "ДОГОВОР ПРОКАТА ВЕЛОСИПЕДА")
        self.assertContains(contract_response, "ИП Ким Юрий Брониславович")
        self.assertContains(terms_response, "Клиенты от 14 до 17 лет")
        self.assertContains(terms_response, "Кассовый чек предоставляется")

    @override_settings(
        RENTAL_PROVIDER_NAME="ИП Ким Юрий Брониславович",
        RENTAL_PROVIDER_INN="750536889872",
        RENTAL_PROVIDER_OGRNIP="323750000053480",
        RENTAL_PROVIDER_ADDRESS="г. Чита, ул. Бутина, д. 50",
    )
    def test_footer_contains_public_business_details(self):
        response = self.client.get(reverse("home"))

        self.assertContains(response, "ИП Ким Юрий Брониславович")
        self.assertContains(response, "ИНН 750536889872")
        self.assertContains(response, "ОГРНИП 323750000053480")
        self.assertContains(response, "г. Чита, ул. Бутина, д. 50")

    @override_settings(
        RENTAL_PROVIDER_ADDRESS="г. Чита, ул. Бутина, д. 50",
        RENTAL_PROVIDER_PHONE="+7 914 123-23-33",
    )
    def test_configure_business_location_preserves_opening_hours(self):
        self.location.opening_hours = "10:00-22:00"
        self.location.save(update_fields=["opening_hours"])

        call_command("configure_business_location")

        self.location.refresh_from_db()
        self.assertEqual(self.location.address, "г. Чита, ул. Бутина, д. 50")
        self.assertEqual(self.location.phone, "+7 914 123-23-33")
        self.assertEqual(self.location.opening_hours, "10:00-22:00")
