from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import ListView, DetailView

from dashboard.mixins import OperatorRequiredMixin
from .models import Bike


class CatalogListView(ListView):
    model = Bike
    template_name = "catalog/catalog.html"
    context_object_name = "bikes"

    def get_queryset(self):
        qs = (
            Bike.objects
            .select_related("category", "tariff", "current_location")
            .filter(status__in=[Bike.Status.AVAILABLE, Bike.Status.RESERVED])
        )
        category = self.request.GET.get("category")
        if category:
            qs = qs.filter(category__name__icontains=category)
        return qs


class BikeDetailView(DetailView):
    model = Bike
    template_name = "catalog/bike_detail.html"
    context_object_name = "bike"
    slug_field = "slug"


class SendBikeToServiceView(LoginRequiredMixin, OperatorRequiredMixin, View):
    def post(self, request, pk, *args, **kwargs):
        bike = get_object_or_404(Bike, pk=pk)

        if bike.status == Bike.Status.IN_RENT:
            messages.warning(request, "Нельзя отправить в обслуживание велосипед, который сейчас в аренде.")
            return redirect("bike-detail", slug=bike.slug)

        if bike.status == Bike.Status.RESERVED:
            messages.warning(request, "Нельзя отправить в обслуживание забронированный велосипед.")
            return redirect("bike-detail", slug=bike.slug)

        if bike.status == Bike.Status.SERVICE:
            messages.info(request, "Этот велосипед уже находится на обслуживании.")
            return redirect("bike-detail", slug=bike.slug)

        service_note = (request.POST.get("condition_notes") or "").strip()
        if service_note:
            bike.condition_notes = service_note

        bike.status = Bike.Status.SERVICE
        bike.save(update_fields=["status", "condition_notes"])

        messages.success(request, f"Велосипед «{bike.title}» переведён в обслуживание.")
        return redirect("bike-detail", slug=bike.slug)


class ReturnBikeFromServiceView(LoginRequiredMixin, OperatorRequiredMixin, View):
    def post(self, request, pk, *args, **kwargs):
        bike = get_object_or_404(Bike, pk=pk)

        if bike.status != Bike.Status.SERVICE:
            messages.warning(request, "Вернуть в доступные можно только велосипед из обслуживания.")
            return redirect("bike-detail", slug=bike.slug)

        bike.status = Bike.Status.AVAILABLE
        bike.save(update_fields=["status"])

        messages.success(request, f"Велосипед «{bike.title}» снова доступен для бронирования.")
        return redirect("bike-detail", slug=bike.slug)
