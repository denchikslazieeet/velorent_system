from django.urls import path
from .views import (
    CatalogListView,
    BikeDetailView,
    SendBikeToServiceView,
    ReturnBikeFromServiceView,
)

urlpatterns = [
    path("", CatalogListView.as_view(), name="catalog"),
    path("<slug:slug>/", BikeDetailView.as_view(), name="bike-detail"),
    path("<int:pk>/service/", SendBikeToServiceView.as_view(), name="bike-service"),
    path("<int:pk>/return-from-service/", ReturnBikeFromServiceView.as_view(), name="bike-return-from-service"),
]