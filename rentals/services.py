from decimal import Decimal, ROUND_HALF_UP
from catalog.models import Bike
from .models import Booking


def calculate_booking_quote(start_at, end_at, tariff, customer=None):
    seconds = max((end_at - start_at).total_seconds(), 3600)
    hours = Decimal(seconds / 3600).quantize(Decimal("1"), rounding=ROUND_HALF_UP)

    if hours >= 24 and tariff.daily_rate:
        days = (hours / Decimal("24")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        quoted_price = days * tariff.daily_rate
    else:
        quoted_price = hours * tariff.hourly_rate

    if customer and getattr(customer, "next_booking_hourly_surcharge", Decimal("0")) > 0:
        quoted_price += hours * customer.next_booking_hourly_surcharge

    return quoted_price, tariff.deposit_amount


def bike_available_for_period(bike: Bike, start_at, end_at) -> bool:
    conflict_exists = Booking.objects.filter(
        bike=bike,
        status__in=[
            Booking.Status.PENDING,
            Booking.Status.CONFIRMED,
            Booking.Status.ACTIVE,
        ],
        start_at__lt=end_at,
        end_at__gt=start_at,
    ).exists()
    return not conflict_exists and bike.status == Bike.Status.AVAILABLE


def compute_late_fee(booking, actual_end_at):
    if actual_end_at <= booking.end_at:
        return Decimal("0.00")
    overtime_hours = Decimal((actual_end_at - booking.end_at).total_seconds() / 3600).quantize(
        Decimal("1"),
        rounding=ROUND_HALF_UP
    )
    return overtime_hours * booking.tariff.late_fee_per_hour