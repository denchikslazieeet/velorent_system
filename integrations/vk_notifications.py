import logging
import secrets
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError

from django.conf import settings
from django.urls import reverse
from django.utils import timezone


logger = logging.getLogger(__name__)
VK_MESSAGES_SEND_URL = "https://api.vk.com/method/messages.send"


def vk_notifications_available():
    return bool(settings.VK_GROUP_TOKEN)


def send_vk_message(user, message):
    if not vk_notifications_available():
        return False
    if not getattr(user, "vk_id", None) or not getattr(user, "vk_notifications_enabled", False):
        return False

    payload = urlencode({
        "user_id": user.vk_id,
        "message": message,
        "random_id": secrets.randbelow(2_147_483_647),
        "access_token": settings.VK_GROUP_TOKEN,
        "v": settings.VK_API_VERSION,
    }).encode("utf-8")

    request = Request(VK_MESSAGES_SEND_URL, data=payload, method="POST")
    try:
        with urlopen(request, timeout=10) as response:
            body = response.read().decode("utf-8")
    except URLError:
        logger.exception("VK notification request failed for user %s", user.pk)
        return False

    if '"error"' in body:
        logger.warning("VK notification failed for user %s: %s", user.pk, body)
        return False
    return True


def booking_url(booking):
    return reverse("booking-detail", kwargs={"pk": booking.pk})


def format_booking_period(booking):
    start = timezone.localtime(booking.start_at).strftime("%d.%m.%Y %H:%M")
    end = timezone.localtime(booking.end_at).strftime("%d.%m.%Y %H:%M")
    return f"{start} - {end}"


def build_booking_message(booking, event):
    period = format_booking_period(booking)
    common = (
        f"Бронь {booking.number}\n"
        f"Велосипед: {booking.bike.title}\n"
        f"Период: {period}\n"
        f"Точка выдачи: {booking.pickup_location.name}"
    )

    messages = {
        "created": f"Ваша бронь создана.\n{common}\nСтоимость: {booking.quoted_price} ₽",
        "confirmed": f"Ваша бронь подтверждена.\n{common}",
        "issued": f"Велосипед выдан.\n{common}",
        "completed": f"Аренда завершена.\n{common}\nИтог к оплате: {booking.rental.final_price} ₽",
        "cancelled": f"Бронь отменена.\n{common}",
        "no_show": f"Бронь отмечена как неявка.\n{common}",
        "payment_paid": f"Оплата по брони подтверждена.\n{common}",
    }
    return messages.get(event, f"Обновление по брони.\n{common}")


def notify_booking_event(booking, event):
    return send_vk_message(booking.customer, build_booking_message(booking, event))
