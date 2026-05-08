import logging
import secrets
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError

from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse
from django.utils import timezone

from accounts.models import User, UserNotification


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


def absolute_booking_url(booking):
    return f"{settings.SITE_URL.rstrip('/')}{booking_url(booking)}"


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

    if event == "created":
        return f"Ваша бронь создана.\n{common}\nСтоимость: {booking.quoted_price} ₽"
    if event == "confirmed":
        return f"Ваша бронь подтверждена.\n{common}"
    if event == "issued":
        return f"Велосипед выдан.\n{common}"
    if event == "completed":
        final_price = getattr(getattr(booking, "rental", None), "final_price", booking.quoted_price)
        return f"Аренда завершена.\n{common}\nИтог к оплате: {final_price} ₽"
    if event == "cancelled":
        return f"Бронь отменена.\n{common}"
    if event == "no_show":
        return f"Бронь отмечена как неявка.\n{common}"
    if event == "payment_paid":
        return f"Оплата по брони подтверждена.\n{common}"
    return f"Обновление по брони.\n{common}"


def build_booking_title(booking, event):
    titles = {
        "created": f"Бронь {booking.number} создана",
        "confirmed": f"Бронь {booking.number} подтверждена",
        "issued": f"Велосипед выдан по брони {booking.number}",
        "completed": f"Аренда {booking.number} завершена",
        "cancelled": f"Бронь {booking.number} отменена",
        "no_show": f"Неявка по брони {booking.number}",
        "payment_paid": f"Оплата по брони {booking.number} подтверждена",
    }
    return titles.get(event, f"Обновление по брони {booking.number}")


def create_site_notification(booking, event, title, message):
    level = UserNotification.Level.INFO
    if event in {"created", "confirmed", "issued", "completed", "payment_paid"}:
        level = UserNotification.Level.SUCCESS
    if event in {"cancelled", "no_show"}:
        level = UserNotification.Level.WARNING

    return UserNotification.objects.create(
        user=booking.customer,
        title=title,
        message=message,
        url=booking_url(booking),
        level=level,
    )


def create_operator_booking_notifications(booking):
    operators = User.objects.filter(role__in=[User.Role.OPERATOR, User.Role.ADMIN])
    staff_users = User.objects.filter(is_staff=True)
    recipients = (operators | staff_users).distinct()

    title = f"Новая бронь {booking.number}"
    message = (
        f"Создана новая бронь.\n"
        f"Клиент: {booking.customer.full_name_or_phone}\n"
        f"Телефон: {booking.customer.phone or '-'}\n"
        f"Велосипед: {booking.bike.title}\n"
        f"Период: {format_booking_period(booking)}\n"
        f"Точка выдачи: {booking.pickup_location.name}\n"
        f"Стоимость: {booking.quoted_price} ₽"
    )
    url = booking_url(booking)

    return [
        UserNotification.objects.create(
            user=user,
            title=title,
            message=message,
            url=url,
            level=UserNotification.Level.INFO,
        )
        for user in recipients
    ]


def send_booking_email(booking, title, message):
    if not booking.customer.email:
        return False

    email_body = (
        f"{message}\n\n"
        f"Открыть бронь: {absolute_booking_url(booking)}\n\n"
        "Если вы не оформляли бронь, свяжитесь с оператором ВелоРент."
    )

    try:
        sent_count = send_mail(
            subject=f"ВелоРент: {title}",
            message=email_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[booking.customer.email],
            fail_silently=False,
        )
    except Exception:
        logger.exception("Email notification failed for user %s", booking.customer_id)
        return False
    return sent_count > 0


def notify_booking_event(booking, event):
    title = build_booking_title(booking, event)
    message = build_booking_message(booking, event)
    site_notification = create_site_notification(booking, event, title, message)
    operator_notifications = []
    if event == "created":
        operator_notifications = create_operator_booking_notifications(booking)
    email_sent = send_booking_email(booking, title, message)
    vk_sent = send_vk_message(booking.customer, message)
    return {
        "site_notification": site_notification,
        "operator_notifications": operator_notifications,
        "email_sent": email_sent,
        "vk_sent": vk_sent,
    }
