from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum, Q, Count
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView, ListView, DetailView

from catalog.models import Bike
from rentals.models import Booking, Rental, Payment
from rentals.contracts import rental_contract_context
from accounts.models import AccountAccessCode
from .mixins import OperatorRequiredMixin

User = get_user_model()


def booking_rental(booking):
    try:
        return booking.rental
    except Rental.DoesNotExist:
        return None


def booking_next_action(booking, now, today_start, tomorrow_start):
    rental = booking_rental(booking)
    if booking.status == Booking.Status.PENDING:
        return {'label': 'Подтвердить', 'tone': 'warning'}
    if booking.status == Booking.Status.CONFIRMED:
        if today_start <= booking.start_at < tomorrow_start:
            return {'label': 'Выдать сегодня', 'tone': 'info'}
        return {'label': 'Ждет выдачи', 'tone': 'info'}
    if booking.status == Booking.Status.ACTIVE:
        if booking.end_at < now:
            return {'label': 'Принять возврат', 'tone': 'danger'}
        if booking.end_at < tomorrow_start:
            return {'label': 'Вернуть сегодня', 'tone': 'warning'}
        if rental and rental.status == Rental.Status.ACTIVE:
            return {'label': 'В аренде', 'tone': 'active'}
        return {'label': 'Проверить аренду', 'tone': 'warning'}
    if booking.status == Booking.Status.COMPLETED:
        return {'label': 'Закрыто', 'tone': 'completed'}
    if booking.status == Booking.Status.EXPIRED:
        return {'label': 'Неявка', 'tone': 'danger'}
    if booking.status == Booking.Status.CANCELLED:
        return {'label': 'Отменено', 'tone': 'muted'}
    return {'label': 'Проверить', 'tone': 'info'}


def booking_attention_badges(booking, now, today_start, tomorrow_start):
    badges = []
    if not booking.customer.document_verified:
        badges.append({'label': 'Документ', 'tone': 'warning'})
    if not booking.customer.email_is_verified:
        badges.append({'label': 'Нет email', 'tone': 'info'})
    if booking.status == Booking.Status.CONFIRMED and today_start <= booking.start_at < tomorrow_start:
        badges.append({'label': 'Выдача сегодня', 'tone': 'info'})
    if booking.status == Booking.Status.ACTIVE and booking.end_at < now:
        badges.append({'label': 'Возврат просрочен', 'tone': 'danger'})
    elif booking.status == Booking.Status.ACTIVE and booking.end_at < tomorrow_start:
        badges.append({'label': 'Возврат сегодня', 'tone': 'warning'})
    if booking.payments.filter(status=Payment.Status.PENDING).exists():
        badges.append({'label': 'Оплата', 'tone': 'warning'})
    return badges


class HomePageView(TemplateView):
    template_name = 'home.html'


class TermsView(TemplateView):
    template_name = 'terms.html'


class PrivacyPolicyView(TemplateView):
    template_name = 'privacy_policy.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['personal_data_email'] = settings.PERSONAL_DATA_EMAIL
        context['provider_name'] = settings.RENTAL_PROVIDER_NAME
        context['provider_details'] = settings.RENTAL_PROVIDER_DETAILS
        return context


class ContractTemplateView(TemplateView):
    template_name = 'rentals/booking_contract.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(rental_contract_context())
        return context


class UserDashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'dashboard/user_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        now = timezone.now()
        context['bookings'] = (
            Booking.objects
            .filter(customer=self.request.user)
            .select_related('bike')
            .order_by('-created_at')[:5]
        )
        context['upcoming_booking'] = (
            Booking.objects
            .filter(
                customer=self.request.user,
                start_at__gte=now,
                status__in=[
                    Booking.Status.PENDING,
                    Booking.Status.CONFIRMED,
                    Booking.Status.ACTIVE,
                ],
            )
            .select_related('bike', 'pickup_location')
            .order_by('start_at')
            .first()
        )
        context['rentals'] = (
            Rental.objects
            .filter(booking__customer=self.request.user)
            .select_related('booking__bike')
            .order_by('-created_at')[:5]
        )
        return context


class OperatorDashboardView(LoginRequiredMixin, OperatorRequiredMixin, TemplateView):
    template_name = 'dashboard/operator_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        q = (self.request.GET.get('q') or '').strip()
        status = (self.request.GET.get('status') or '').strip()
        quick = (self.request.GET.get('quick') or '').strip()
        has_global_filters = bool(q or status)
        if has_global_filters:
            quick = 'all'
        elif not quick:
            quick = 'work'

        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_start = today_start + timedelta(days=1)

        context['available_bikes'] = Bike.objects.filter(status=Bike.Status.AVAILABLE).count()
        context['active_rentals'] = Rental.objects.filter(status=Rental.Status.ACTIVE).count()
        context['pending_bookings'] = Booking.objects.filter(status=Booking.Status.PENDING).count()
        context['upcoming_today'] = Booking.objects.filter(
            status=Booking.Status.CONFIRMED,
            start_at__gte=today_start,
            start_at__lt=tomorrow_start,
        ).count()
        context['returns_today'] = Booking.objects.filter(
            status=Booking.Status.ACTIVE,
            end_at__lt=tomorrow_start,
        ).count()
        context['service_bikes'] = Bike.objects.filter(status=Bike.Status.SERVICE).count()

        base_bookings = (
            Booking.objects
            .select_related('bike', 'customer', 'rental')
            .order_by('-created_at')
        )
        bookings = base_bookings

        if not has_global_filters and quick == 'work':
            bookings = bookings.filter(
                status__in=[
                    Booking.Status.PENDING,
                    Booking.Status.CONFIRMED,
                    Booking.Status.ACTIVE,
                ]
            )
        elif not has_global_filters and quick == 'pending':
            bookings = bookings.filter(status=Booking.Status.PENDING)
        elif not has_global_filters and quick == 'today':
            bookings = bookings.filter(
                status=Booking.Status.CONFIRMED,
                start_at__gte=today_start,
                start_at__lt=tomorrow_start,
            )
        elif not has_global_filters and quick == 'active':
            bookings = bookings.filter(status=Booking.Status.ACTIVE)
        elif not has_global_filters and quick == 'returns':
            bookings = bookings.filter(
                status=Booking.Status.ACTIVE,
                end_at__lt=tomorrow_start,
            )

        if q:
            bookings = bookings.filter(
                Q(number__icontains=q) |
                Q(customer__first_name__icontains=q) |
                Q(customer__last_name__icontains=q) |
                Q(customer__username__icontains=q) |
                Q(customer__phone__icontains=q)
            )

        if status:
            bookings = bookings.filter(status=status)

        recent_bookings = list(bookings[:20])
        for booking in recent_bookings:
            booking.operator_next_action = booking_next_action(
                booking,
                now,
                today_start,
                tomorrow_start,
            )
            booking.attention_badges = booking_attention_badges(
                booking,
                now,
                today_start,
                tomorrow_start,
            )

        context['recent_bookings'] = recent_bookings
        context['current_query'] = q
        context['current_status'] = status
        context['current_quick'] = quick
        context['status_choices'] = Booking.Status.choices
        work_bookings_count = base_bookings.filter(
            status__in=[
                Booking.Status.PENDING,
                Booking.Status.CONFIRMED,
                Booking.Status.ACTIVE,
            ]
        ).count()
        context['quick_filters'] = [
            {
                'key': 'all',
                'label': 'Все',
                'count': base_bookings.count(),
                'url': f"{reverse('operator-dashboard')}?quick=all#bookings-list",
            },
            {
                'key': 'work',
                'label': 'В работе',
                'count': work_bookings_count,
                'url': f"{reverse('operator-dashboard')}?quick=work#bookings-list",
            },
            {
                'key': 'pending',
                'label': 'Новые',
                'count': context['pending_bookings'],
                'url': f"{reverse('operator-dashboard')}?quick=pending#bookings-list",
            },
            {
                'key': 'today',
                'label': 'Выдать сегодня',
                'count': context['upcoming_today'],
                'url': f"{reverse('operator-dashboard')}?quick=today#bookings-list",
            },
            {
                'key': 'active',
                'label': 'Активные',
                'count': context['active_rentals'],
                'url': f"{reverse('operator-dashboard')}?quick=active#bookings-list",
            },
            {
                'key': 'returns',
                'label': 'Вернуть сегодня',
                'count': context['returns_today'],
                'url': f"{reverse('operator-dashboard')}?quick=returns#bookings-list",
            },
        ]
        context['today_important'] = [
            {
                'label': 'Новые брони',
                'value': context['pending_bookings'],
                'note': 'Новые заявки ждут решения оператора.',
                'url': f"{reverse('operator-dashboard')}?quick=pending#bookings-list",
                'tone': 'warning',
            },
            {
                'label': 'Выдать сегодня',
                'value': context['upcoming_today'],
                'note': 'Подтвержденные брони с началом сегодня.',
                'url': f"{reverse('operator-dashboard')}?quick=today#bookings-list",
                'tone': 'info',
            },
            {
                'label': 'Активные аренды',
                'value': context['active_rentals'],
                'note': 'Следите за плановыми возвратами.',
                'url': f"{reverse('operator-dashboard')}?quick=active#bookings-list",
                'tone': 'info',
            },
            {
                'label': 'Вернуть сегодня',
                'value': context['returns_today'],
                'note': 'Плановые и просроченные возвраты.',
                'url': f"{reverse('operator-dashboard')}?quick=returns#bookings-list",
                'tone': 'warning',
            },
        ]

        return context


class OperatorCustomersListView(LoginRequiredMixin, OperatorRequiredMixin, ListView):
    template_name = 'dashboard/customers_list.html'
    context_object_name = 'customers'
    paginate_by = 10

    def get_queryset(self):
        q = (self.request.GET.get('q') or '').strip()

        queryset = (
            User.objects
            .filter(role=User.Role.CUSTOMER)
            .annotate(
                total_rentals=Count('bookings__rental', distinct=True),
                completed_rentals=Count(
                    'bookings__rental',
                    filter=Q(bookings__rental__status=Rental.Status.COMPLETED),
                    distinct=True
                ),
                no_shows=Count(
                    'bookings',
                    filter=Q(bookings__status=Booking.Status.EXPIRED),
                    distinct=True
                ),
            )
            .order_by('-date_joined', '-id')
        )

        if q:
            queryset = queryset.filter(
                Q(first_name__icontains=q) |
                Q(last_name__icontains=q) |
                Q(username__icontains=q) |
                Q(phone__icontains=q) |
                Q(email__icontains=q)
            )

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_query'] = (self.request.GET.get('q') or '').strip()
        context['customers_total'] = User.objects.filter(role=User.Role.CUSTOMER).count()
        context['verified_total'] = User.objects.filter(
            role=User.Role.CUSTOMER,
            document_verified=True
        ).count()
        context['with_surcharge_total'] = User.objects.filter(
            role=User.Role.CUSTOMER,
            next_booking_hourly_surcharge__gt=0
        ).count()
        if context.get('is_paginated'):
            paginator = context['paginator']
            page_number = context['page_obj'].number
            context['page_range'] = paginator.get_elided_page_range(
                page_number,
                on_each_side=1,
                on_ends=1,
            )
        return context


class OperatorBikeListView(LoginRequiredMixin, OperatorRequiredMixin, ListView):
    template_name = 'dashboard/bikes_list.html'
    context_object_name = 'bikes'
    paginate_by = 10

    def get_queryset(self):
        q = (self.request.GET.get('q') or '').strip()
        status = (self.request.GET.get('status') or '').strip()

        queryset = (
            Bike.objects
            .select_related('category', 'tariff', 'current_location')
            .exclude(status=Bike.Status.RETIRED)
            .order_by('title')
        )

        if q:
            queryset = queryset.filter(
                Q(title__icontains=q) |
                Q(serial_number__icontains=q) |
                Q(category__name__icontains=q)
            )

        if status:
            queryset = queryset.filter(status=status)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_query'] = (self.request.GET.get('q') or '').strip()
        context['current_status'] = (self.request.GET.get('status') or '').strip()
        context['status_choices'] = Bike.Status.choices
        context['available_total'] = Bike.objects.filter(status=Bike.Status.AVAILABLE).count()
        context['service_total'] = Bike.objects.filter(status=Bike.Status.SERVICE).count()
        context['in_rent_total'] = Bike.objects.filter(status=Bike.Status.IN_RENT).count()
        if context.get('is_paginated'):
            paginator = context['paginator']
            page_number = context['page_obj'].number
            context['page_range'] = paginator.get_elided_page_range(
                page_number,
                on_each_side=1,
                on_ends=1,
            )
        return context


class OperatorCustomerDetailView(LoginRequiredMixin, OperatorRequiredMixin, DetailView):
    template_name = 'dashboard/customer_detail.html'
    context_object_name = 'customer'

    def get_queryset(self):
        return User.objects.filter(role=User.Role.CUSTOMER)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        customer = self.object

        bookings = (
            Booking.objects
            .filter(customer=customer)
            .select_related('bike', 'pickup_location', 'tariff')
            .order_by('-created_at')
        )

        rentals = (
            Rental.objects
            .filter(booking__customer=customer)
            .select_related('booking', 'booking__bike', 'issued_by', 'received_by')
            .order_by('-created_at')
        )

        payments = (
            Payment.objects
            .filter(booking__customer=customer)
            .select_related('booking', 'booking__bike')
            .order_by('-created_at')
        )

        context['total_rentals'] = rentals.count()
        context['completed_rentals'] = rentals.filter(status=Rental.Status.COMPLETED).count()
        context['active_rentals'] = rentals.filter(status=Rental.Status.ACTIVE).count()

        context['total_paid'] = (
            payments.filter(
                status=Payment.Status.PAID,
                kind__in=[Payment.Kind.RENTAL, Payment.Kind.FINE],
            ).exclude(
                booking__status__in=[Booking.Status.CANCELLED, Booking.Status.EXPIRED]
            ).aggregate(total=Sum('amount'))['total'] or 0
)

        context['all_rentals'] = rentals
        context['all_payments'] = payments

        access_code_notice = self.request.session.get('customer_access_code_notice')
        if access_code_notice and access_code_notice.get('customer_id') == customer.pk:
            context['customer_access_code_notice'] = access_code_notice
            del self.request.session['customer_access_code_notice']
            self.request.session.modified = True

        return context


class GenerateCustomerAccessCodeView(LoginRequiredMixin, OperatorRequiredMixin, View):
    def post(self, request, pk, *args, **kwargs):
        customer = get_object_or_404(User.objects.filter(role=User.Role.CUSTOMER), pk=pk)

        if customer.has_usable_password():
            messages.info(request, "У клиента уже есть пароль. Смена пароля выполняется через подтвержденный email клиента.")
            return redirect('operator-customer-detail', pk=customer.pk)

        _, raw_code = AccountAccessCode.create_for_user(customer, created_by=request.user)
        request.session['customer_access_code_notice'] = {
            'customer_id': customer.pk,
            'code': raw_code,
            'ttl_minutes': settings.ACCOUNT_ACCESS_CODE_TTL_MINUTES,
        }
        messages.success(request, "Код доступа создан. Покажите его клиенту лично.")
        return redirect('operator-customer-detail', pk=customer.pk)


class AnalyticsView(LoginRequiredMixin, OperatorRequiredMixin, TemplateView):
    template_name = 'dashboard/analytics.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        period = (self.request.GET.get('period') or '30').strip()
        allowed_periods = {'7', '30', '90'}
        if period not in allowed_periods:
            period = '30'

        now = timezone.now()
        start_date = now - timedelta(days=int(period) - 1)

        payments = Payment.objects.filter(
            status=Payment.Status.PAID,
            kind__in=[Payment.Kind.RENTAL, Payment.Kind.FINE],
            created_at__gte=start_date
        )

        bookings = Booking.objects.filter(created_at__gte=start_date)
        rentals = Rental.objects.filter(created_at__gte=start_date)

        context['selected_period'] = period
        context['period_options'] = [
            ('7', '7 дней'),
            ('30', '30 дней'),
            ('90', '90 дней'),
        ]

        context['analytics_revenue'] = payments.aggregate(total=Sum('amount'))['total'] or 0
        context['analytics_bookings'] = bookings.count()
        context['analytics_completed_rentals'] = rentals.filter(status=Rental.Status.COMPLETED).count()
        context['analytics_no_shows'] = bookings.filter(status=Booking.Status.EXPIRED).count()
        context['analytics_cancelled'] = bookings.filter(status=Booking.Status.CANCELLED).count()

        context['popular_bikes'] = (
            bookings
            .values('bike__title')
            .annotate(total=Count('id'))
            .order_by('-total', 'bike__title')[:10]
        )

        context['revenue_by_bike'] = (
            payments
            .values('booking__bike__title')
            .annotate(total=Sum('amount'))
            .order_by('-total', 'booking__bike__title')[:10]
        )

        return context


class AnalyticsBookingsDetailView(LoginRequiredMixin, OperatorRequiredMixin, ListView):
    template_name = 'dashboard/analytics_bookings.html'
    context_object_name = 'bookings'

    def get_period(self):
        period = (self.request.GET.get('period') or '30').strip()
        return period if period in {'7', '30', '90'} else '30'

    def get_start_date(self):
        return timezone.now() - timedelta(days=int(self.get_period()) - 1)

    def get_queryset(self):
        qs = (
            Booking.objects
            .filter(created_at__gte=self.get_start_date())
            .select_related('bike', 'customer')
            .order_by('-created_at')
        )

        status = (self.request.GET.get('status') or '').strip()
        bike_title = (self.request.GET.get('bike') or '').strip()

        if status:
            qs = qs.filter(status=status)

        if bike_title:
            qs = qs.filter(bike__title=bike_title)

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        status = (self.request.GET.get('status') or '').strip()
        bike_title = (self.request.GET.get('bike') or '').strip()

        title = "Брони"
        if status == Booking.Status.CANCELLED:
            title = "Отменённые брони"
        elif status == Booking.Status.EXPIRED:
            title = "Неявки"
        elif bike_title:
            title = f"Брони по велосипеду: {bike_title}"

        context['page_title'] = title
        context['selected_period'] = self.get_period()
        return context


class AnalyticsRentalsDetailView(LoginRequiredMixin, OperatorRequiredMixin, ListView):
    template_name = 'dashboard/analytics_rentals.html'
    context_object_name = 'rentals'

    def get_period(self):
        period = (self.request.GET.get('period') or '30').strip()
        return period if period in {'7', '30', '90'} else '30'

    def get_start_date(self):
        return timezone.now() - timedelta(days=int(self.get_period()) - 1)

    def get_queryset(self):
        return (
            Rental.objects
            .filter(created_at__gte=self.get_start_date(), status=Rental.Status.COMPLETED)
            .select_related('booking', 'booking__bike', 'booking__customer')
            .order_by('-created_at')
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = "Завершённые аренды"
        context['selected_period'] = self.get_period()
        return context


class AnalyticsPaymentsDetailView(LoginRequiredMixin, OperatorRequiredMixin, ListView):
    template_name = 'dashboard/analytics_payments.html'
    context_object_name = 'payments'

    def get_period(self):
        period = (self.request.GET.get('period') or '30').strip()
        return period if period in {'7', '30', '90'} else '30'

    def get_start_date(self):
        return timezone.now() - timedelta(days=int(self.get_period()) - 1)

    def get_queryset(self):
        return (
            Payment.objects
            .filter(
                created_at__gte=self.get_start_date(),
                status=Payment.Status.PAID,
                kind__in=[Payment.Kind.RENTAL, Payment.Kind.FINE]
            )
            .select_related('booking', 'booking__customer', 'booking__bike')
            .order_by('-created_at')
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qs = self.get_queryset()
        context['page_title'] = "Выручка"
        context['selected_period'] = self.get_period()
        context['total_revenue'] = qs.aggregate(total=Sum('amount'))['total'] or 0
        return context


class RevenueListView(LoginRequiredMixin, OperatorRequiredMixin, ListView):
    template_name = 'dashboard/revenue_list.html'
    context_object_name = 'payments'

    def get_queryset(self):
        return (
            Payment.objects
            .filter(
                status=Payment.Status.PAID,
                kind__in=[Payment.Kind.RENTAL, Payment.Kind.FINE]
            )
            .select_related('booking', 'booking__customer', 'booking__bike')
            .order_by('-created_at')
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['total_revenue'] = (
            self.get_queryset().aggregate(total=Sum('amount'))['total'] or 0
        )
        return context
