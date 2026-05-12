from django.utils.cache import add_never_cache_headers


class AuthenticatedPageNoStoreMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        user = getattr(request, "user", None)
        content_type = response.get("Content-Type", "")

        if (
            getattr(user, "is_authenticated", False)
            and content_type.startswith("text/html")
        ):
            add_never_cache_headers(response)

        return response
