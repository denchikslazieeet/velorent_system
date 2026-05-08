from datetime import timedelta
from decimal import Decimal, InvalidOperation
from decimal import ROUND_HALF_UP

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, ListView

from catalog.models import Bike
from accounts.models import AccountAccessCode
from dashboard.mixins import OperatorRequiredMixin
from integrations.services import queue_booking_sync
from integrations.vk_notifications import notify_booking_event
from .forms import BookingForm, OperatorBookingForm
from .models import Booking, Rental, Payment, make_booking_number


def bike_available_for_period(bike, start_at, end_at):
    from .services import bike_available_for_period as original_check
    return original_check(bike, start_at, end_at)


def calculate_booking_quote(start_at, end_at, tariff, customer=None):
    from .services import calculate_booking_quote as original_calc
    return original_calc(start_at, end_at, tariff, customer=customer)


def compute_late_fee(booking, actual_end_at):
    from .services import compute_late_fee as original_fee
    return original_fee(booking, actual_end_at)


class BookingCreateView(LoginRequiredMixin, CreateView):
    form_class = BookingForm
    template_name = 'rentals/booking_form.html'

    def dispatch(self, request, *args, **kwargs):
        self.bike = get_object_or_404(Bike, slug=kwargs['slug'])
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['bike'] = self.bike
        context['page_title'] = 'Бронирование велосипеда'
        return context

    def form_valid(self, form):
        booking = form.save(commit=False)
        booking.number = make_booking_number()
        booking.customer = self.request.user
        booking.bike = self.bike
        booking.tariff = self.bike.tariff

        if not bike_available_for_period(self.bike, booking.start_at, booking.end_at):
            form.add_error(None, 'Выбранный велосипед недоступен в этот период.')
            return self.form_invalid(form)

        quoted_price, deposit_amount = calculate_booking_quote(
            booking.start_at,
            booking.end_at,
            self.bike.tariff,
            customer=self.request.user
        )
        booking.quoted_price = quoted_price
        booking.deposit_amount = deposit_amount
        booking.save()

        if booking.customer.next_booking_hourly_surcharge > 0:
            booking.customer.next_booking_hourly_surcharge = 0
            booking.customer.next_booking_penalty_reason = ""
            booking.customer.save(update_fields=[
                "next_booking_hourly_surcharge",
                "next_booking_penalty_reason",
            ])

        Rental.objects.create(booking=booking)
        queue_booking_sync(booking)
        notify_booking_event(booking, "created")

        messages.success(self.request, f'Бронь {booking.number} создана.')
        return redirect(reverse('booking-detail', kwargs={'pk': booking.pk}))


class OperatorBookingCreateView(LoginRequiredMixin, OperatorRequiredMixin, CreateView):
    form_class = OperatorBookingForm
    template_name = 'rentals/operator_booking_form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Создание брони по телефону'
        return context

    def form_valid(self, form):
        booking = form.save(commit=False)
        booking.number = make_booking_number()
        booking.customer = form.resolve_customer(created_by=self.request.user)
        booking.bike = form.cleaned_data['bike']
        booking.tariff = booking.bike.tariff

        if not bike_available_for_period(booking.bike, booking.start_at, booking.end_at):
            form.add_error('bike', 'Выбранный велосипед недоступен в этот период.')
            return self.form_invalid(form)

        quoted_price, deposit_amount = calculate_booking_quote(
            booking.start_at,
            booking.end_at,
            booking.bike.tariff,
            customer=booking.customer
        )
        booking.quoted_price = quoted_price
        booking.deposit_amount = deposit_amount
        booking.save()

        if booking.customer.next_booking_hourly_surcharge > 0:
            booking.customer.next_booking_hourly_surcharge = 0
            booking.customer.next_booking_penalty_reason = ""
            booking.customer.save(update_fields=[
                "next_booking_hourly_surcharge",
                "next_booking_penalty_reason",
            ])

        Rental.objects.create(booking=booking)
        queue_booking_sync(booking)
        notify_booking_event(booking, "created")

        if form.account_access_code:
            self.request.session['account_access_code_notice'] = {
                'booking_id': booking.pk,
                'code': form.account_access_code,
                'ttl_minutes': settings.ACCOUNT_ACCESS_CODE_TTL_MINUTES,
            }
            messages.success(
                self.request,
                f'Бронь {booking.number} создана. Покажите клиенту код доступа к аккаунту.'
            )
        else:
            messages.success(
                self.request,
                f'Бронь {booking.number} создана для клиента {booking.customer}.'
            )
        return redirect(reverse('booking-detail', kwargs={'pk': booking.pk}))


class BookingDetailView(LoginRequiredMixin, DetailView):
    model = Booking
    template_name = 'rentals/booking_detail.html'
    context_object_name = 'booking'

    def get_queryset(self):
        qs = (
            Booking.objects
            .select_related(
                'bike',
                'pickup_location',
                'customer',
                'customer__document_verified_by',
                'rental',
                'tariff'
            )
            .prefetch_related('payments')
        )
        user = self.request.user
        if user.role in {'operator', 'admin'} or user.is_staff or user.is_superuser:
            return qs
        return qs.filter(customer=user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        booking = self.object

        pending_rental_payment = booking.payments.filter(
            kind=Payment.Kind.RENTAL,
            status=Payment.Status.PENDING
        ).first()

        can_mark_no_show = False
        no_show_allowed_at = booking.start_at + timedelta(minutes=15)

        if booking.status in {Booking.Status.PENDING, Booking.Status.CONFIRMED}:
            can_mark_no_show = timezone.now() >= no_show_allowed_at

        context['pending_rental_payment'] = pending_rental_payment
        context['document_type_choices'] = booking.customer.DocumentType.choices
        context['can_mark_no_show'] = can_mark_no_show
        context['no_show_allowed_at'] = no_show_allowed_at
        context['customer_needs_password'] = not booking.customer.has_usable_password()

        duration_hours = booking.duration_hours().quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        if duration_hours >= 24 and booking.tariff.daily_rate:
            billing_units = (duration_hours / Decimal("24")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            base_rate = booking.tariff.daily_rate
            base_label = "сут."
        else:
            billing_units = duration_hours
            base_rate = booking.tariff.hourly_rate
            base_label = "ч."

        surcharge_per_hour = getattr(booking.customer, "next_booking_hourly_surcharge", Decimal("0")) or Decimal("0")
        surcharge_total = Decimal("0")
        if surcharge_per_hour > 0:
            surcharge_total = duration_hours * surcharge_per_hour

        context['price_breakdown'] = {
            'tariff_name': booking.tariff.name,
            'duration_hours': duration_hours,
            'billing_units': billing_units,
            'base_rate': base_rate,
            'base_label': base_label,
            'base_total': billing_units * base_rate,
            'surcharge_per_hour': surcharge_per_hour,
            'surcharge_total': surcharge_total,
            'deposit_amount': booking.deposit_amount,
            'quoted_price': booking.quoted_price,
        }

        access_code_notice = self.request.session.get('account_access_code_notice')
        if access_code_notice and access_code_notice.get('booking_id') == booking.pk:
            context['account_access_code_notice'] = access_code_notice
            del self.request.session['account_access_code_notice']
            self.request.session.modified = True
        return context


class GenerateAccountAccessCodeView(LoginRequiredMixin, OperatorRequiredMixin, View):
    def post(self, request, pk, *args, **kwargs):
        booking = get_object_or_404(
            Booking.objects.select_related('customer'),
            pk=pk
        )

        if booking.customer.has_usable_password():
            messages.info(request, 'У клиента уже есть пароль для входа.')
            return redirect('booking-detail', pk=booking.pk)

        _, raw_code = AccountAccessCode.create_for_user(
            booking.customer,
            created_by=request.user,
        )
        request.session['account_access_code_notice'] = {
            'booking_id': booking.pk,
            'code': raw_code,
            'ttl_minutes': settings.ACCOUNT_ACCESS_CODE_TTL_MINUTES,
        }
        messages.success(request, 'Новый код доступа создан.')
        return redirect('booking-detail', pk=booking.pk)


class MyBookingsListView(LoginRequiredMixin, ListView):
    model = Booking
    template_name = 'rentals/my_bookings.html'
    context_object_name = 'bookings'

    def get_queryset(self):
        return (
            Booking.objects
            .filter(customer=self.request.user)
            .select_related('bike', 'pickup_location', 'rental')
            .order_by('-created_at')
        )


class VerifyCustomerDocumentView(LoginRequiredMixin, OperatorRequiredMixin, View):
    def post(self, request, pk, *args, **kwargs):
        booking = get_object_or_404(
            Booking.objects.select_related('customer'),
            pk=pk
        )
        customer = booking.customer

        first_name = (request.POST.get('first_name') or '').strip()
        last_name = (request.POST.get('last_name') or '').strip()
        document_type = (request.POST.get('document_type') or '').strip()
        document_last4 = ''.join(ch for ch in (request.POST.get('document_last4') or '') if ch.isdigit())

        if not first_name:
            messages.warning(request, 'Укажите имя клиента.')
            return redirect('booking-detail', pk=booking.pk)

        if not last_name:
            messages.warning(request, 'Укажите фамилию клиента.')
            return redirect('booking-detail', pk=booking.pk)

        valid_document_types = {value for value, _ in customer.DocumentType.choices}
        if document_type not in valid_document_types:
            messages.warning(request, 'Выберите тип документа.')
            return redirect('booking-detail', pk=booking.pk)

        if len(document_last4) != 4:
            messages.warning(request, 'Введите последние 4 цифры документа.')
            return redirect('booking-detail', pk=booking.pk)

        customer.first_name = first_name
        customer.last_name = last_name
        customer.document_type = document_type
        customer.document_last4 = document_last4
        customer.document_verified = True
        customer.document_verified_at = timezone.now()
        customer.document_verified_by = request.user
        customer.save(update_fields=[
            'first_name',
            'last_name',
            'document_type',
            'document_last4',
            'document_verified',
            'document_verified_at',
            'document_verified_by',
        ])

        messages.success(request, f'Клиент {customer.full_name_or_phone} успешно верифицирован.')
        return redirect('booking-detail', pk=booking.pk)


class ConfirmBookingView(LoginRequiredMixin, OperatorRequiredMixin, DetailView):
    model = Booking

    def post(self, request, *args, **kwargs):
        booking = self.get_object()

        if booking.status != Booking.Status.PENDING:
            messages.warning(request, 'Подтвердить можно только новую бронь.')
            return redirect('operator-dashboard')

        booking.status = Booking.Status.CONFIRMED
        booking.bike.status = booking.bike.Status.RESERVED
        booking.bike.save(update_fields=['status'])
        booking.save(update_fields=['status', 'updated_at'])

        queue_booking_sync(booking)
        notify_booking_event(booking, "confirmed")
        messages.success(request, f'Бронь {booking.number} подтверждена.')
        return redirect('operator-dashboard')


class IssueRentalView(LoginRequiredMixin, OperatorRequiredMixin, DetailView):
    model = Booking

    def post(self, request, *args, **kwargs):
        booking = self.get_object()

        if booking.status != Booking.Status.CONFIRMED:
            messages.warning(request, 'Выдать можно только подтверждённую бронь.')
            return redirect('operator-dashboard')

        if not booking.customer.document_verified:
            messages.warning(
                request,
                'Нельзя выдать велосипед: документ клиента ещё не проверен оператором.'
            )
            return redirect('booking-detail', pk=booking.pk)

        rental = booking.rental
        rental.status = Rental.Status.ACTIVE
        rental.issued_by = request.user
        rental.actual_start_at = timezone.now()
        rental.start_condition = request.POST.get('start_condition', '')
        rental.save(update_fields=[
            'status', 'issued_by', 'actual_start_at', 'start_condition', 'updated_at'
        ])

        booking.status = Booking.Status.ACTIVE
        booking.save(update_fields=['status', 'updated_at'])

        booking.bike.status = booking.bike.Status.IN_RENT
        booking.bike.save(update_fields=['status'])

        if booking.deposit_amount:
            Payment.objects.create(
                booking=booking,
                amount=booking.deposit_amount,
                kind=Payment.Kind.DEPOSIT,
                method=Payment.Method.CARD,
                status=Payment.Status.PAID,
            )

        queue_booking_sync(booking)
        notify_booking_event(booking, "issued")
        messages.success(request, f'Велосипед по брони {booking.number} выдан.')
        return redirect('operator-dashboard')


class ReturnRentalView(LoginRequiredMixin, OperatorRequiredMixin, DetailView):
    model = Booking

    def post(self, request, *args, **kwargs):
        booking = self.get_object()
        rental = booking.rental

        if booking.status != Booking.Status.ACTIVE or rental.status != Rental.Status.ACTIVE:
            messages.warning(request, 'Завершить можно только активную аренду.')
            return redirect('operator-dashboard')

        actual_end_at = timezone.now()

        try:
            damage_fee = Decimal(request.POST.get('damage_fee') or "0")
        except InvalidOperation:
            damage_fee = Decimal("0")

        try:
            extra_time_fee = Decimal(request.POST.get('extra_time_fee') or "0")
        except InvalidOperation:
            extra_time_fee = Decimal("0")

        rental.received_by = request.user
        rental.actual_end_at = actual_end_at
        rental.end_condition = request.POST.get('end_condition', '')
        rental.damage_fee = damage_fee
        rental.late_fee = compute_late_fee(booking, actual_end_at)
        rental.extra_time_fee = extra_time_fee
        rental.final_price = booking.quoted_price + rental.late_fee + rental.damage_fee + rental.extra_time_fee
        rental.status = Rental.Status.COMPLETED
        rental.save()

        booking.status = Booking.Status.COMPLETED
        booking.save(update_fields=['status', 'updated_at'])

        booking.bike.status = booking.bike.Status.AVAILABLE
        booking.bike.save(update_fields=['status'])

        existing_pending = booking.payments.filter(
            kind=Payment.Kind.RENTAL,
            status=Payment.Status.PENDING
        ).exists()

        if not existing_pending:
            Payment.objects.create(
                booking=booking,
                amount=rental.final_price,
                kind=Payment.Kind.RENTAL,
                method=Payment.Method.CASH,
                status=Payment.Status.PENDING,
            )

        queue_booking_sync(booking)
        notify_booking_event(booking, "completed")
        messages.success(
            request,
            f'Аренда {booking.number} завершена. Сумма к оплате рассчитана.'
        )
        return redirect('booking-detail', pk=booking.pk)


class ConfirmRentalPaymentView(LoginRequiredMixin, OperatorRequiredMixin, View):
    def post(self, request, pk, *args, **kwargs):
        booking = get_object_or_404(
            Booking.objects.select_related('rental'),
            pk=pk
        )

        payment = booking.payments.filter(
            kind=Payment.Kind.RENTAL,
            status=Payment.Status.PENDING
        ).order_by('-created_at').first()

        if not payment:
            messages.warning(request, 'Для этой брони нет ожидающего платежа.')
            return redirect('booking-detail', pk=booking.pk)

        method = request.POST.get('method') or Payment.Method.CASH
        if method not in {
            Payment.Method.CASH,
            Payment.Method.CARD,
            Payment.Method.ONLINE,
        }:
            method = Payment.Method.CASH

        payment.method = method
        payment.status = Payment.Status.PAID
        payment.save(update_fields=['method', 'status'])

        refund_exists = booking.payments.filter(
            kind=Payment.Kind.REFUND,
            status=Payment.Status.PAID
        ).exists()

        if booking.deposit_amount and not refund_exists:
            Payment.objects.create(
                booking=booking,
                amount=booking.deposit_amount,
                kind=Payment.Kind.REFUND,
                method=method,
                status=Payment.Status.PAID,
            )

        notify_booking_event(booking, "payment_paid")
        messages.success(request, f'Оплата по брони {booking.number} подтверждена.')
        return redirect('booking-detail', pk=booking.pk)


class CancelBookingView(LoginRequiredMixin, View):
    def post(self, request, pk, *args, **kwargs):
        booking = get_object_or_404(
            Booking.objects.select_related('bike', 'rental', 'customer'),
            pk=pk
        )

        user = request.user
        is_operator = user.role in {'operator', 'admin'} or user.is_staff or user.is_superuser

        if not is_operator and booking.customer != user:
            messages.error(request, 'У вас нет доступа к этой брони.')
            return redirect('user-dashboard')

        if booking.status not in {Booking.Status.PENDING, Booking.Status.CONFIRMED}:
            messages.warning(request, 'Эту бронь уже нельзя отменить.')
            return redirect('booking-detail', pk=booking.pk)

        booking.status = Booking.Status.CANCELLED
        booking.save(update_fields=['status', 'updated_at'])

        if hasattr(booking, 'rental') and booking.rental.status == Rental.Status.READY:
            booking.rental.status = Rental.Status.CANCELLED
            booking.rental.save(update_fields=['status', 'updated_at'])

        if booking.bike.status == booking.bike.Status.RESERVED:
            booking.bike.status = booking.bike.Status.AVAILABLE
            booking.bike.save(update_fields=['status'])

        queue_booking_sync(booking)
        notify_booking_event(booking, "cancelled")
        messages.success(request, f'Бронь {booking.number} отменена.')

        if is_operator:
            return redirect('operator-dashboard')
        return redirect('my-bookings')


class NoShowConfirmView(LoginRequiredMixin, OperatorRequiredMixin, DetailView):
    model = Booking
    template_name = 'rentals/no_show_confirm.html'
    context_object_name = 'booking'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        booking = self.object
        context['no_show_allowed_at'] = booking.start_at + timedelta(minutes=15)
        return context


class MarkNoShowView(LoginRequiredMixin, OperatorRequiredMixin, View):
    def post(self, request, pk, *args, **kwargs):
        booking = get_object_or_404(
            Booking.objects.select_related('bike', 'rental', 'customer'),
            pk=pk
        )

        if booking.status not in {Booking.Status.PENDING, Booking.Status.CONFIRMED}:
            messages.warning(request, 'Неявку можно отметить только для новой или подтверждённой брони.')
            return redirect('booking-detail', pk=booking.pk)

        allowed_no_show_time = booking.start_at + timedelta(minutes=15)
        if timezone.now() < allowed_no_show_time:
            messages.warning(
                request,
                'Неявку можно отметить только через 15 минут после запланированного начала аренды.'
            )
            return redirect('booking-detail', pk=booking.pk)

        try:
            surcharge = Decimal(request.POST.get("surcharge_per_hour") or "0")
        except InvalidOperation:
            surcharge = Decimal("0")

        if surcharge < 0:
            surcharge = Decimal("0")

        booking.status = Booking.Status.EXPIRED
        booking.save(update_fields=["status", "updated_at"])

        if hasattr(booking, 'rental') and booking.rental.status == Rental.Status.READY:
            booking.rental.status = Rental.Status.CANCELLED
            booking.rental.save(update_fields=['status', 'updated_at'])

        if booking.bike.status == booking.bike.Status.RESERVED:
            booking.bike.status = booking.bike.Status.AVAILABLE
            booking.bike.save(update_fields=['status'])

        if surcharge > 0:
            booking.customer.next_booking_hourly_surcharge = surcharge
            booking.customer.next_booking_penalty_reason = f"Неявка по брони {booking.number}"
            booking.customer.save(update_fields=[
                "next_booking_hourly_surcharge",
                "next_booking_penalty_reason",
            ])

        queue_booking_sync(booking)
        notify_booking_event(booking, "no_show")

        if surcharge > 0:
            messages.success(
                request,
                f'Бронь {booking.number} помечена как неявка. '
                f'Назначена надбавка {surcharge} ₽/час на следующее бронирование.'
            )
        else:
            messages.success(request, f'Бронь {booking.number} помечена как неявка.')

        return redirect('operator-dashboard')
