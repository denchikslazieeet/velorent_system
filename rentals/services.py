from decimal import Decimal, ROUND_CEILING
from django.utils import timezone
from catalog.models import Bike
from .models import Booking


def billable_hours_between(start_at, end_at):
    seconds = max((end_at - start_at).total_seconds(), 3600)
    hours = Decimal(str(seconds)) / Decimal("3600")
    return hours.quantize(Decimal("1"), rounding=ROUND_CEILING)


def billable_days_from_hours(hours):
    days = hours / Decimal("24")
    return days.quantize(Decimal("1"), rounding=ROUND_CEILING)


def calculate_booking_quote(start_at, end_at, tariff, customer=None):
    hours = billable_hours_between(start_at, end_at)

    if hours >= 24 and tariff.daily_rate:
        days = billable_days_from_hours(hours)
        quoted_price = days * tariff.daily_rate
    else:
        quoted_price = hours * tariff.hourly_rate

    if customer and getattr(customer, "next_booking_hourly_surcharge", Decimal("0")) > 0:
        quoted_price += hours * customer.next_booking_hourly_surcharge

    return quoted_price, tariff.deposit_amount


def bike_available_for_period(bike: Bike, start_at, end_at) -> bool:
    if bike.status in {Bike.Status.SERVICE, Bike.Status.RETIRED, Bike.Status.IN_RENT}:
        return False

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
    return not conflict_exists


ACTIVE_BOOKING_STATUSES = [
    Booking.Status.PENDING,
    Booking.Status.CONFIRMED,
    Booking.Status.ACTIVE,
]


def bike_reservation_booking(bike: Bike, from_at=None):
    from_at = from_at or timezone.now()
    bookings = Booking.objects.filter(
        bike=bike,
        status__in=ACTIVE_BOOKING_STATUSES,
    )

    next_booking = bookings.filter(end_at__gt=from_at).order_by("start_at", "end_at").first()
    if next_booking:
        return next_booking

    return bookings.order_by("-end_at").first()


def bike_next_available_at(bike: Bike, from_at=None):
    reservation = bike_reservation_booking(bike, from_at=from_at)
    if reservation:
        return reservation.end_at
    return None


def compute_late_fee(booking, actual_end_at):
    if actual_end_at <= booking.end_at:
        return Decimal("0.00")
    overtime_hours = billable_hours_between(booking.end_at, actual_end_at)
    return overtime_hours * booking.tariff.late_fee_per_hour
