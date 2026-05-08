from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import BikeViewSet, BookingViewSet, OperatorActionViewSet, ReferenceViewSet

router = DefaultRouter()
router.register("bikes", BikeViewSet, basename="api-bikes")
router.register("bookings", BookingViewSet, basename="api-bookings")
router.register("operator", OperatorActionViewSet, basename="api-operator")
router.register("references", ReferenceViewSet, basename="api-references")

urlpatterns = [
    path("", include(router.urls)),
]
