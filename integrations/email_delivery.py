import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from .models import EmailDelivery


logger = logging.getLogger(__name__)


def attempt_email_delivery(delivery):
    if delivery.status == EmailDelivery.Status.SENT:
        return True

    delivery.attempts += 1
    try:
        sent_count = send_mail(
            subject=delivery.subject,
            message=delivery.body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[delivery.recipient],
            fail_silently=False,
        )
        if sent_count <= 0:
            raise RuntimeError("Почтовый сервер не подтвердил отправку письма.")
    except Exception as exc:
        delivery.status = EmailDelivery.Status.FAILED
        delivery.last_error = str(exc)
        delivery.next_attempt_at = timezone.now() + timedelta(
            minutes=settings.EMAIL_RETRY_DELAY_MINUTES
        )
        delivery.save(update_fields=[
            "attempts",
            "status",
            "last_error",
            "next_attempt_at",
            "updated_at",
        ])
        logger.exception("Email delivery failed for %s", delivery.recipient)
        return False

    delivery.status = EmailDelivery.Status.SENT
    delivery.sent_at = timezone.now()
    delivery.last_error = ""
    delivery.save(update_fields=[
        "attempts",
        "status",
        "sent_at",
        "last_error",
        "updated_at",
    ])
    return True


def send_email_reliably(recipient, subject, body, kind="", deduplication_key=None):
    if not recipient:
        return False

    defaults = {
        "recipient": recipient,
        "subject": subject,
        "body": body,
        "kind": kind,
    }
    if deduplication_key:
        delivery, created = EmailDelivery.objects.get_or_create(
            deduplication_key=deduplication_key,
            defaults=defaults,
        )
        if not created and delivery.status == EmailDelivery.Status.SENT:
            return True
    else:
        delivery = EmailDelivery.objects.create(**defaults)

    return attempt_email_delivery(delivery)


def send_emails_reliably(recipients, subject, body, kind="", deduplication_key=None):
    results = []
    for recipient in dict.fromkeys(recipient for recipient in recipients if recipient):
        recipient_key = f"{deduplication_key}:{recipient}" if deduplication_key else None
        results.append(
            send_email_reliably(
                recipient,
                subject,
                body,
                kind=kind,
                deduplication_key=recipient_key,
            )
        )
    return bool(results) and all(results)
