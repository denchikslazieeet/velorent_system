from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path
from dashboard.views import HomePageView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", HomePageView.as_view(), name="home"),
    path("", include("dashboard.urls")),
    path("accounts/", include("accounts.urls")),
    path("catalog/", include("catalog.urls")),
    path("rentals/", include("rentals.urls")),
    path("api/", include("api.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
