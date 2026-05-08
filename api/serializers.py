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
    class Meta:
        model = Booking
        fields = ["bike", "pickup_location", "start_at", "end_at", "comment"]

class RentalSerializer(serializers.ModelSerializer):
    booking = BookingReadSerializer()

    class Meta:
        model = Rental
        fields = ["id", "status", "actual_start_at", "actual_end_at", "final_price", "damage_fee", "late_fee", "booking"]
