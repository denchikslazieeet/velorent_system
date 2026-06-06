from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from catalog.models import Bike, Tariff, PickupLocation
from rentals.models import Booking, Rental, Payment, make_booking_number
from rentals.services import bike_available_for_period, calculate_booking_quote, compute_late_fee
from integrations.services import queue_booking_sync
from integrations.vk_notifications import notify_booking_event
from .permissions import IsOperator
from .serializers import (
    BikeSerializer,
    BookingCreateSerializer,
    BookingReadSerializer,
    TariffSerializer,
    PickupLocationSerializer,
    RentalSerializer,
)


def error_response(message, response_status=status.HTTP_400_BAD_REQUEST):
    return Response({"detail": message}, status=response_status)


def parse_money(value, default="0"):
    try:
        amount = Decimal(str(value if value not in (None, "") else default))
    except (InvalidOperation, TypeError):
        amount = Decimal(default)
    return max(amount, Decimal("0"))


def normalize_payment_method(value):
    if value in {Payment.Method.CASH, Payment.Method.CARD, Payment.Method.ONLINE}:
        return value
    return Payment.Method.CARD


class BikeViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Bike.objects.select_related("tariff", "current_location").all()
    serializer_class = BikeSerializer
    permission_classes = [AllowAny]
    lookup_field = "slug"

    def get_queryset(self):
        qs = super().get_queryset()
        status_filter = self.request.query_params.get("status")
        location = self.request.query_params.get("location")
        if status_filter:
            qs = qs.filter(status=status_filter)
        if location:
            qs = qs.filter(current_location__id=location)
        return qs

class BookingViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Booking.objects.filter(customer=self.request.user).select_related("bike", "pickup_location", "tariff")

    def list(self, request):
        serializer = BookingReadSerializer(self.get_queryset(), many=True)
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        booking = self.get_queryset().filter(pk=pk).first()
        if not booking:
            return Response({"detail": "Бронирование не найдено."}, status=status.HTTP_404_NOT_FOUND)
        serializer = BookingReadSerializer(booking)
        return Response(serializer.data)

    def create(self, request):
        serializer = BookingCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        start_at = serializer.validated_data["start_at"]
        end_at = serializer.validated_data["end_at"]

        with transaction.atomic():
            user_name_fields = []
            if not (request.user.first_name or "").strip():
                request.user.first_name = serializer.validated_data["first_name"].strip()
                user_name_fields.append("first_name")
            if not (request.user.last_name or "").strip():
                request.user.last_name = serializer.validated_data["last_name"].strip()
                user_name_fields.append("last_name")
            if user_name_fields:
                request.user.save(update_fields=user_name_fields)

            bike = Bike.objects.select_for_update().select_related("tariff").get(
                pk=serializer.validated_data["bike"].pk
            )
            if not bike_available_for_period(bike, start_at, end_at):
                return Response({"detail": "Велосипед недоступен в выбранный период."}, status=status.HTTP_400_BAD_REQUEST)

            quoted_price, deposit_amount = calculate_booking_quote(
                start_at,
                end_at,
                bike.tariff,
                customer=request.user,
            )
            booking = Booking.objects.create(
                number=make_booking_number(),
                customer=request.user,
                bike=bike,
                pickup_location=serializer.validated_data["pickup_location"],
                tariff=bike.tariff,
                start_at=start_at,
                end_at=end_at,
                comment=serializer.validated_data.get("comment", ""),
                quoted_price=quoted_price,
                deposit_amount=deposit_amount,
            )
            Rental.objects.create(booking=booking)

            if request.user.next_booking_hourly_surcharge > 0:
                request.user.next_booking_hourly_surcharge = Decimal("0")
                request.user.next_booking_penalty_reason = ""
                request.user.save(update_fields=[
                    "next_booking_hourly_surcharge",
                    "next_booking_penalty_reason",
                ])

        queue_booking_sync(booking)
        notify_booking_event(booking, "created")
        return Response(BookingReadSerializer(booking).data, status=status.HTTP_201_CREATED)

class OperatorActionViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, IsOperator]
    queryset = Booking.objects.select_related("bike", "customer", "pickup_location", "tariff", "rental").all()

    def get_locked_booking(self, pk):
        return get_object_or_404(
            Booking.objects.select_for_update().select_related(
                "bike",
                "customer",
                "pickup_location",
                "tariff",
            ),
            pk=pk,
        )

    @action(detail=False, methods=["get"])
    def dashboard(self, request):
        data = {
            "pending_bookings": Booking.objects.filter(status=Booking.Status.PENDING).count(),
            "confirmed_bookings": Booking.objects.filter(status=Booking.Status.CONFIRMED).count(),
            "active_rentals": Rental.objects.filter(status=Rental.Status.ACTIVE).count(),
        }
        return Response(data)

    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        with transaction.atomic():
            booking = self.get_locked_booking(pk)
            booking.bike = Bike.objects.select_for_update().get(pk=booking.bike_id)

            if booking.status != Booking.Status.PENDING:
                return error_response("Подтвердить можно только новую бронь.")

            if booking.bike.status in {Bike.Status.SERVICE, Bike.Status.RETIRED, Bike.Status.IN_RENT}:
                return error_response("Велосипед сейчас недоступен для подтверждения брони.")

            conflict_exists = Booking.objects.filter(
                bike=booking.bike,
                status__in=[
                    Booking.Status.PENDING,
                    Booking.Status.CONFIRMED,
                    Booking.Status.ACTIVE,
                ],
                start_at__lt=booking.end_at,
                end_at__gt=booking.start_at,
            ).exclude(pk=booking.pk).exists()
            if conflict_exists:
                return error_response("На этот период уже есть другая бронь.")

            booking.status = Booking.Status.CONFIRMED
            booking.save(update_fields=["status", "updated_at"])
            booking.bike.status = booking.bike.Status.RESERVED
            booking.bike.save(update_fields=["status"])

        queue_booking_sync(booking)
        notify_booking_event(booking, "confirmed")
        return Response({"detail": f"Бронь {booking.number} подтверждена."})

    @action(detail=True, methods=["post"])
    def issue(self, request, pk=None):
        with transaction.atomic():
            booking = self.get_locked_booking(pk)
            booking.bike = Bike.objects.select_for_update().get(pk=booking.bike_id)

            if booking.status != Booking.Status.CONFIRMED:
                return error_response("Выдать можно только подтверждённую бронь.")

            if not booking.customer.document_verified:
                return error_response("Перед выдачей нужно проверить документ клиента.")

            rental = Rental.objects.select_for_update().get(booking=booking)
            if rental.status != Rental.Status.READY:
                return error_response("Аренда уже была выдана или закрыта.")

            rental.status = Rental.Status.ACTIVE
            rental.actual_start_at = timezone.now()
            rental.issued_by = request.user
            rental.start_condition = request.data.get("start_condition", "")
            rental.save()
            booking.status = Booking.Status.ACTIVE
            booking.save(update_fields=["status", "updated_at"])
            booking.bike.status = booking.bike.Status.IN_RENT
            booking.bike.save(update_fields=["status"])
            if booking.deposit_amount:
                Payment.objects.create(
                    booking=booking,
                    amount=booking.deposit_amount,
                    kind=Payment.Kind.DEPOSIT,
                    method=normalize_payment_method(request.data.get("method")),
                    status=Payment.Status.PAID,
                )

        queue_booking_sync(booking)
        notify_booking_event(booking, "issued")
        return Response({"detail": f"Велосипед по брони {booking.number} выдан."})

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        with transaction.atomic():
            booking = self.get_locked_booking(pk)
            booking.bike = Bike.objects.select_for_update().get(pk=booking.bike_id)
            rental = Rental.objects.select_for_update().get(booking=booking)

            if booking.status != Booking.Status.ACTIVE or rental.status != Rental.Status.ACTIVE:
                return error_response("Завершить можно только активную аренду.")

            actual_end_at = timezone.now()
            damage_fee = parse_money(request.data.get("damage_fee"))
            extra_time_fee = parse_money(request.data.get("extra_time_fee"))

            rental.status = Rental.Status.COMPLETED
            rental.actual_end_at = actual_end_at
            rental.received_by = request.user
            rental.end_condition = request.data.get("end_condition", "")
            rental.damage_fee = damage_fee
            rental.late_fee = compute_late_fee(booking, actual_end_at)
            rental.extra_time_fee = extra_time_fee
            rental.final_price = booking.quoted_price + rental.late_fee + rental.damage_fee + rental.extra_time_fee
            rental.save()
            booking.status = Booking.Status.COMPLETED
            booking.save(update_fields=["status", "updated_at"])
            booking.bike.status = booking.bike.Status.AVAILABLE
            booking.bike.save(update_fields=["status"])

            existing_pending = booking.payments.filter(
                kind=Payment.Kind.RENTAL,
                status=Payment.Status.PENDING,
            ).exists()
            if not existing_pending:
                Payment.objects.create(
                    booking=booking,
                    amount=rental.final_price,
                    kind=Payment.Kind.RENTAL,
                    method=normalize_payment_method(request.data.get("method")),
                    status=Payment.Status.PENDING,
                )

        queue_booking_sync(booking)
        notify_booking_event(booking, "completed")
        return Response({"detail": f"Аренда {booking.number} завершена."})

class ReferenceViewSet(viewsets.GenericViewSet):
    permission_classes = [AllowAny]

    @action(detail=False, methods=["get"])
    def tariffs(self, request):
        return Response(TariffSerializer(Tariff.objects.filter(is_active=True), many=True).data)

    @action(detail=False, methods=["get"])
    def pickup_locations(self, request):
        return Response(PickupLocationSerializer(PickupLocation.objects.filter(is_active=True), many=True).data)
