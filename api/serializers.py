from django.utils import timezone
from rest_framework import serializers
from catalog.models import Bike, Tariff, PickupLocation
from rentals.models import Booking, Rental

class TariffSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tariff
        fields = ["id", "name", "hourly_rate", "daily_rate", "deposit_amount", "late_fee_per_hour"]

class PickupLocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = PickupLocation
        fields = ["id", "name", "address", "opening_hours", "phone"]

class BikeSerializer(serializers.ModelSerializer):
    tariff = TariffSerializer()
    current_location = PickupLocationSerializer()

    class Meta:
        model = Bike
        fields = [
            "id", "title", "slug", "description", "frame_size", "wheel_size",
            "color", "status", "tariff", "current_location",
        ]

class BookingReadSerializer(serializers.ModelSerializer):
    bike = BikeSerializer()
    pickup_location = PickupLocationSerializer()

    class Meta:
        model = Booking
        fields = [
            "id", "number", "status", "start_at", "end_at", "quoted_price",
            "deposit_amount", "comment", "bike", "pickup_location",
        ]

class BookingCreateSerializer(serializers.ModelSerializer):
    bike = serializers.PrimaryKeyRelatedField(
        queryset=Bike.objects.select_related("tariff").filter(
            status__in=[Bike.Status.AVAILABLE, Bike.Status.RESERVED],
            tariff__is_active=True,
        )
    )
    pickup_location = serializers.PrimaryKeyRelatedField(
        queryset=PickupLocation.objects.filter(is_active=True)
    )

    class Meta:
        model = Booking
        fields = ["bike", "pickup_location", "start_at", "end_at", "comment"]

    def validate(self, attrs):
        start_at = attrs.get("start_at")
        end_at = attrs.get("end_at")

        if start_at and timezone.is_naive(start_at):
            start_at = timezone.make_aware(start_at)
            attrs["start_at"] = start_at

        if end_at and timezone.is_naive(end_at):
            end_at = timezone.make_aware(end_at)
            attrs["end_at"] = end_at

        if start_at and start_at < timezone.now():
            raise serializers.ValidationError({"start_at": "Нельзя бронировать на прошедшее время."})

        if start_at and end_at and end_at <= start_at:
            raise serializers.ValidationError({"end_at": "Время возврата должно быть позже начала аренды."})

        return attrs

class RentalSerializer(serializers.ModelSerializer):
    booking = BookingReadSerializer()

    class Meta:
        model = Rental
        fields = ["id", "status", "actual_start_at", "actual_end_at", "final_price", "damage_fee", "late_fee", "booking"]
