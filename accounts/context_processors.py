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
