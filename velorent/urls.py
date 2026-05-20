from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path
from django.views.generic import TemplateView
from dashboard.views import HomePageView

admin.site.site_header = "ВелоРент"
admin.site.site_title = "ВелоРент"
admin.site.index_title = "Администрирование проката"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("manifest.webmanifest", TemplateView.as_view(
        template_name="manifest.webmanifest",
        content_type="application/manifest+json",
    ), name="webmanifest"),
    path("service-worker.js", TemplateView.as_view(
        template_name="service-worker.js",
        content_type="application/javascript",
    ), name="service-worker"),
    path("offline/", TemplateView.as_view(template_name="offline.html"), name="offline"),
    path("", HomePageView.as_view(), name="home"),
    path("", include("dashboard.urls")),
    path("accounts/", include("accounts.urls")),
    path("catalog/", include("catalog.urls")),
    path("rentals/", include("rentals.urls")),
    path("api/", include("api.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
