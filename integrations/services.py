import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from .models import SyncEvent

logger = logging.getLogger(__name__)

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
    event = SyncEvent.objects.create(
        entity="booking",
        entity_id=str(booking.id),
        event_type="booking.created_or_updated",
        payload=payload,
        direction=SyncEvent.Direction.TO_ONEC,
    )
    if settings.ONEC_API_URL and settings.ONEC_SYNC_IMMEDIATE:
        send_sync_event(event)
    return event


def send_sync_event(event):
    if not settings.ONEC_API_URL:
        event.status = SyncEvent.Status.FAILED
        event.response_text = "ONEC_API_URL is not configured."
        event.save(update_fields=["status", "response_text"])
        return False

    body = json.dumps({
        "id": event.id,
        "entity": event.entity,
        "entity_id": event.entity_id,
        "event_type": event.event_type,
        "direction": event.direction,
        "payload": event.payload,
        "created_at": event.created_at.isoformat(),
    }, ensure_ascii=False).encode("utf-8")

    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json",
    }
    if settings.ONEC_API_TOKEN:
        headers["Authorization"] = f"Bearer {settings.ONEC_API_TOKEN}"

    request = Request(settings.ONEC_API_URL, data=body, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=settings.ONEC_API_TIMEOUT_SECONDS) as response:
            response_text = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        response_text = exc.read().decode("utf-8", errors="replace")
        event.status = SyncEvent.Status.FAILED
        event.response_text = f"HTTP {exc.code}: {response_text}"
        event.save(update_fields=["status", "response_text"])
        logger.warning("1C sync event %s failed with HTTP %s", event.pk, exc.code)
        return False
    except URLError as exc:
        event.status = SyncEvent.Status.FAILED
        event.response_text = str(exc.reason)
        event.save(update_fields=["status", "response_text"])
        logger.warning("1C sync event %s failed: %s", event.pk, exc.reason)
        return False

    event.status = SyncEvent.Status.SENT
    event.response_text = response_text[:5000]
    event.save(update_fields=["status", "response_text"])
    return True

def onec_configuration():
    return {
        "url": settings.ONEC_API_URL,
        "token_present": bool(settings.ONEC_API_TOKEN),
        "sync_immediate": settings.ONEC_SYNC_IMMEDIATE,
    }
