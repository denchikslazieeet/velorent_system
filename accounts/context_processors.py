def unread_notifications(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {"unread_notifications_count": 0}

    return {
        "unread_notifications_count": user.notifications.filter(read_at__isnull=True).count()
    }
