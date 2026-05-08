from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from catalog.models import Bike, Tariff, PickupLocation
from rentals.models import Booking, Rental, Payment, make_booking_number
from rentals.services import bike_available_for_period, calculate_booking_quote
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
        serializer = BookingCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        bike = serializer.validated_data["bike"]
        start_at = serializer.validated_data["start_at"]
        end_at = serializer.validated_data["end_at"]
        if not bike_available_for_period(bike, start_at, end_at):
            return Response({"detail": "Велосипед недоступен в выбранный период."}, status=status.HTTP_400_BAD_REQUEST)
        quoted_price, deposit_amount = calculate_booking_quote(start_at, end_at, bike.tariff)
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
        queue_booking_sync(booking)
        notify_booking_event(booking, "created")
        return Response(BookingReadSerializer(booking).data, status=status.HTTP_201_CREATED)

class OperatorActionViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, IsOperator]
    queryset = Booking.objects.select_related("bike", "customer", "pickup_location", "tariff", "rental").all()

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
        booking = self.get_object()
        booking.status = Booking.Status.CONFIRMED
        booking.save(update_fields=["status", "updated_at"])
        booking.bike.status = booking.bike.Status.RESERVED
        booking.bike.save(update_fields=["status"])
        queue_booking_sync(booking)
        notify_booking_event(booking, "confirmed")
        return Response({"detail": f"Бронь {booking.number} подтверждена."})

    @action(detail=True, methods=["post"])
    def issue(self, request, pk=None):
        booking = self.get_object()
        rental = booking.rental
        rental.status = Rental.Status.ACTIVE
        rental.actual_start_at = booking.start_at
        rental.issued_by = request.user
        rental.start_condition = request.data.get("start_condition", "")
        rental.save()
        booking.status = Booking.Status.ACTIVE
        booking.save(update_fields=["status", "updated_at"])
        booking.bike.status = booking.bike.Status.IN_RENT
        booking.bike.save(update_fields=["status"])
        Payment.objects.create(
            booking=booking,
            amount=booking.deposit_amount,
            kind=Payment.Kind.DEPOSIT,
            method=request.data.get("method", Payment.Method.CARD),
            status=Payment.Status.PAID,
        )
        queue_booking_sync(booking)
        notify_booking_event(booking, "issued")
        return Response({"detail": f"Велосипед по брони {booking.number} выдан."})

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        booking = self.get_object()
        rental = booking.rental
        rental.status = Rental.Status.COMPLETED
        rental.actual_end_at = booking.end_at
        rental.received_by = request.user
        rental.end_condition = request.data.get("end_condition", "")
        rental.damage_fee = request.data.get("damage_fee", 0)
        rental.final_price = booking.quoted_price
        rental.save()
        booking.status = Booking.Status.COMPLETED
        booking.save(update_fields=["status", "updated_at"])
        booking.bike.status = booking.bike.Status.AVAILABLE
        booking.bike.save(update_fields=["status"])
        Payment.objects.create(
            booking=booking,
            amount=rental.final_price,
            kind=Payment.Kind.RENTAL,
            method=request.data.get("method", Payment.Method.CARD),
            status=Payment.Status.PAID,
        )
        if booking.deposit_amount:
            Payment.objects.create(
                booking=booking,
                amount=booking.deposit_amount,
                kind=Payment.Kind.REFUND,
                method=request.data.get("method", Payment.Method.CARD),
                status=Payment.Status.PAID,
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
