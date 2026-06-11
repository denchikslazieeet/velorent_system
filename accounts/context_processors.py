def unread_notifications(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {"unread_notifications_count": 0}

    return {
        "unread_notifications_count": user.notifications.filter(read_at__isnull=True).count()
    }


def primary_pickup_location(request):
    from catalog.models import PickupLocation

    location = (
        PickupLocation.objects
        .filter(is_active=True)
        .order_by("id")
        .first()
    )
    return {"primary_pickup_location": location}


def business_details(request):
    from django.conf import settings

    phone_digits = "".join(character for character in settings.RENTAL_PROVIDER_PHONE if character.isdigit())
    return {
        "rental_provider_name": settings.RENTAL_PROVIDER_NAME,
        "rental_provider_inn": settings.RENTAL_PROVIDER_INN,
        "rental_provider_ogrnip": settings.RENTAL_PROVIDER_OGRNIP,
        "rental_provider_registration_details": settings.RENTAL_PROVIDER_REGISTRATION_DETAILS,
        "rental_provider_address": settings.RENTAL_PROVIDER_ADDRESS,
        "rental_provider_phone": settings.RENTAL_PROVIDER_PHONE,
        "rental_provider_phone_uri": f"+{phone_digits}",
        "rental_provider_email": settings.RENTAL_PROVIDER_EMAIL,
        "personal_data_email": settings.PERSONAL_DATA_EMAIL,
    }
