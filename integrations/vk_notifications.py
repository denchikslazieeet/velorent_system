import json
import logging
import secrets
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User, UserNotification
from integrations.email_delivery import send_email_reliably, send_emails_reliably
from integrations.models import BookingNotificationEvent


logger = logging.getLogger(__name__)
VK_MESSAGES_SEND_URL = "https://api.vk.com/method/messages.send"
OPERATOR_EVENTS = {
    "created",
    "confirmed",
    "issued",
    "extended",
    "completed",
    "cancelled",
    "no_show",
    "expired",
    "payment_paid",
    "document_verified",
    "return_overdue",
}


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

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        logger.warning("VK notification returned invalid JSON for user %s: %s", user.pk, body)
        return False

    if data.get("error"):
        logger.warning("VK notification failed for user %s: %s", user.pk, data["error"])
        return False
    return "response" in data


def booking_url(booking):
    return reverse("booking-detail", kwargs={"pk": booking.pk})


def absolute_booking_url(booking):
    return f"{settings.SITE_URL.rstrip('/')}{booking_url(booking)}"


def format_booking_period(booking):
    start = timezone.localtime(booking.start_at).strftime("%d.%m.%Y %H:%M")
    end = timezone.localtime(booking.end_at).strftime("%d.%m.%Y %H:%M")
    return f"{start} - {end}"


def format_amount(amount):
    return f"{amount:.2f}"


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
        return (
            f"Велосипед выдан.\n{common}\n"
            f"Залог принят: {format_amount(booking.deposit_amount)} ₽"
        )
    if event == "extended":
        return f"Аренда продлена.\n{common}\nНовый плановый возврат: {timezone.localtime(booking.end_at):%d.%m.%Y %H:%M}"
    if event == "completed":
        rental = getattr(booking, "rental", None)
        final_price = getattr(rental, "final_price", booking.quoted_price)
        late_fee = getattr(rental, "late_fee", 0)
        damage_fee = getattr(rental, "damage_fee", 0)
        return (
            f"Аренда завершена.\n{common}\n"
            f"Стоимость аренды: {format_amount(booking.quoted_price)} ₽\n"
            f"Штраф за просрочку: {format_amount(late_fee)} ₽\n"
            f"Штраф за повреждение: {format_amount(damage_fee)} ₽\n"
            f"Итого к оплате: {format_amount(final_price)} ₽"
        )
    if event == "cancelled":
        reason = getattr(booking, "cancellation_reason", "")
        reason_line = f"\nПричина: {reason}" if reason else ""
        return f"Бронь отменена.\n{common}{reason_line}"
    if event == "no_show":
        surcharge = booking.customer.next_booking_hourly_surcharge
        return (
            f"Бронь отмечена как неявка.\n{common}\n"
            f"Надбавка к следующей аренде: {format_amount(surcharge)} ₽ за час"
        )
    if event == "expired":
        return (
            f"Срок бронирования истёк, бронь автоматически закрыта.\n{common}\n"
            "Если велосипед всё ещё нужен, создайте новую бронь на свободное время."
        )
    if event == "payment_paid":
        rental_payment = booking.payments.filter(
            kind="rental",
            status="paid",
        ).order_by("-created_at").first()
        refund = booking.payments.filter(
            kind="refund",
            status="paid",
        ).order_by("-created_at").first()
        payment_line = (
            f"\nОплачено: {format_amount(rental_payment.amount)} ₽, "
            f"способ: {rental_payment.get_method_display()}"
            if rental_payment
            else ""
        )
        refund_line = (
            f"\nЗалог возвращён: {format_amount(refund.amount)} ₽"
            if refund
            else ""
        )
        return f"Оплата по брони подтверждена.\n{common}{payment_line}{refund_line}"
    if event == "document_verified":
        customer = booking.customer
        return (
            f"Документ клиента проверен оператором.\n{common}\n"
            f"Документ: {customer.get_document_type_display()}, последние цифры: "
            f"{customer.document_last4}"
        )
    if event == "pickup_reminder":
        return (
            f"Напоминаем о предстоящей выдаче велосипеда.\n{common}\n"
            "Возьмите с собой документ, удостоверяющий личность."
        )
    if event == "return_reminder":
        return (
            f"Скоро наступит время возврата велосипеда.\n{common}\n"
            f"Плановый возврат: {timezone.localtime(booking.end_at):%d.%m.%Y %H:%M}"
        )
    if event == "return_overdue":
        return (
            f"Плановый срок возврата велосипеда истёк.\n{common}\n"
            f"Плановый возврат: {timezone.localtime(booking.end_at):%d.%m.%Y %H:%M}"
        )
    return f"Обновление по брони.\n{common}"


def build_booking_title(booking, event):
    titles = {
        "created": f"Бронь {booking.number} создана",
        "confirmed": f"Бронь {booking.number} подтверждена",
        "issued": f"Велосипед выдан по брони {booking.number}",
        "extended": f"Аренда {booking.number} продлена",
        "completed": f"Аренда {booking.number} завершена",
        "cancelled": f"Бронь {booking.number} отменена",
        "no_show": f"Неявка по брони {booking.number}",
        "expired": f"Срок брони {booking.number} истёк",
        "payment_paid": f"Оплата по брони {booking.number} подтверждена",
        "document_verified": f"Документ по брони {booking.number} проверен",
        "pickup_reminder": f"Напоминание о выдаче по брони {booking.number}",
        "return_reminder": f"Напоминание о возврате по брони {booking.number}",
        "return_overdue": f"Просрочен возврат по брони {booking.number}",
    }
    return titles.get(event, f"Обновление по брони {booking.number}")


def create_site_notification(booking, event, title, message):
    level = UserNotification.Level.INFO
    if event in {
        "created",
        "confirmed",
        "issued",
        "extended",
        "completed",
        "payment_paid",
        "document_verified",
    }:
        level = UserNotification.Level.SUCCESS
    if event in {"cancelled", "no_show", "expired", "return_reminder", "return_overdue"}:
        level = UserNotification.Level.WARNING

    return UserNotification.objects.create(
        user=booking.customer,
        title=title,
        message=message,
        url=booking_url(booking),
        level=level,
    )


def operator_booking_message(booking, message):
    return (
        f"{message}\n\n"
        f"Клиент: {booking.customer.full_name_or_phone}\n"
        f"Телефон: {booking.customer.phone or '-'}\n"
        f"Email: {booking.customer.email or '-'}"
    )


def create_operator_booking_notifications(booking, event, title, message):
    operators = User.objects.filter(role__in=[User.Role.OPERATOR, User.Role.ADMIN])
    staff_users = User.objects.filter(is_staff=True)
    recipients = (operators | staff_users).distinct()

    if event == "created":
        title = f"Новая бронь {booking.number}"
    message = operator_booking_message(booking, message)
    url = booking_url(booking)
    level = UserNotification.Level.INFO
    if event in {"cancelled", "no_show", "expired", "return_overdue"}:
        level = UserNotification.Level.WARNING

    return [
        UserNotification.objects.create(
            user=user,
            title=title,
            message=message,
            url=url,
            level=level,
        )
        for user in recipients
    ]


def send_booking_email(booking, title, message):
    if not booking.customer.email_is_verified:
        return False

    email_body = (
        f"{message}\n\n"
        f"Открыть бронь: {absolute_booking_url(booking)}\n\n"
        "Если вы не оформляли бронь, свяжитесь с оператором ВелоРент."
    )

    return send_email_reliably(
        booking.customer.email,
        f"ВелоРент: {title}",
        email_body,
        kind="booking_customer",
    )


def send_operator_booking_email(booking, event, title, message):
    email_body = (
        f"{operator_booking_message(booking, message)}\n\n"
        f"Открыть бронь: {absolute_booking_url(booking)}"
    )
    return send_emails_reliably(
        settings.OPERATOR_NOTIFICATION_EMAILS,
        f"ВелоРент оператору: {title}",
        email_body,
        kind=f"booking_operator_{event}",
    )


def notify_booking_event(booking, event, notify_customer=True, notify_operators=None):
    if notify_operators is None:
        notify_operators = event in OPERATOR_EVENTS

    title = build_booking_title(booking, event)
    message = build_booking_message(booking, event)
    site_notification = None
    email_sent = False
    vk_sent = False
    if notify_customer:
        site_notification = create_site_notification(booking, event, title, message)
        email_sent = send_booking_email(booking, title, message)
        vk_sent = send_vk_message(booking.customer, message)

    operator_notifications = []
    operator_email_sent = False
    if notify_operators:
        operator_notifications = create_operator_booking_notifications(
            booking,
            event,
            title,
            message,
        )
        operator_email_sent = send_operator_booking_email(booking, event, title, message)

    return {
        "site_notification": site_notification,
        "operator_notifications": operator_notifications,
        "email_sent": email_sent,
        "operator_email_sent": operator_email_sent,
        "vk_sent": vk_sent,
    }


def notify_booking_event_once(booking, event, audience, deduplication_event=None):
    notification_event, created = BookingNotificationEvent.objects.get_or_create(
        booking=booking,
        event=deduplication_event or event,
        audience=audience,
    )
    if not created:
        return None

    try:
        if audience == BookingNotificationEvent.Audience.CUSTOMER:
            return notify_booking_event(
                booking,
                event,
                notify_customer=True,
                notify_operators=False,
            )
        return notify_booking_event(
            booking,
            event,
            notify_customer=False,
            notify_operators=True,
        )
    except Exception:
        notification_event.delete()
        raise
