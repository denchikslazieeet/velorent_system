from django.conf import settings
from .models import SyncEvent

def queue_booking_sync(booking):
    payload = {
        "number": booking.number,
        "customer": {
            "username": booking.customer.username,
            "email": booking.customer.email,
            "phone": booking.customer.phone,
        },
        "bike": booking.bike.title,
        "pickup_location": booking.pickup_location.name,
        "start_at": booking.start_at.isoformat(),
        "end_at": booking.end_at.isoformat(),
        "quoted_price": str(booking.quoted_price),
        "deposit_amount": str(booking.deposit_amount),
        "status": booking.status,
    }
    return SyncEvent.objects.create(
        entity="booking",
        entity_id=str(booking.id),
        event_type="booking.created_or_updated",
        payload=payload,
        direction=SyncEvent.Direction.TO_ONEC,
    )

def onec_configuration():
    return {
        "url": settings.ONEC_API_URL,
        "token_present": bool(settings.ONEC_API_TOKEN),
    }
