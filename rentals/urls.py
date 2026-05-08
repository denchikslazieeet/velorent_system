from django.urls import path
from .views import (
    BookingCreateView,
    BookingDetailView,
    MyBookingsListView,
    ConfirmBookingView,
    IssueRentalView,
    ReturnRentalView,
    OperatorBookingCreateView,
    CancelBookingView,
    MarkNoShowView,
    ConfirmRentalPaymentView,
    VerifyCustomerDocumentView,
    NoShowConfirmView,
    GenerateAccountAccessCodeView,
)

urlpatterns = [
    path('book/', MyBookingsListView.as_view(), name='my-bookings'),
    path('book/<slug:slug>/new/', BookingCreateView.as_view(), name='booking-create'),
    path('operator/new/', OperatorBookingCreateView.as_view(), name='operator-booking-create'),
    path('booking/<int:pk>/', BookingDetailView.as_view(), name='booking-detail'),
    path('booking/<int:pk>/cancel/', CancelBookingView.as_view(), name='booking-cancel'),
    path('booking/<int:pk>/no-show/', MarkNoShowView.as_view(), name='booking-no-show'),
    path('booking/<int:pk>/no-show/confirm/', NoShowConfirmView.as_view(), name='booking-no-show-confirm'),
    path('booking/<int:pk>/confirm-payment/', ConfirmRentalPaymentView.as_view(), name='confirm-rental-payment'),
    path('booking/<int:pk>/verify-customer/', VerifyCustomerDocumentView.as_view(), name='verify-customer'),
    path('booking/<int:pk>/access-code/', GenerateAccountAccessCodeView.as_view(), name='booking-access-code'),
    path('operator/booking/<int:pk>/confirm/', ConfirmBookingView.as_view(), name='booking-confirm'),
    path('operator/booking/<int:pk>/issue/', IssueRentalView.as_view(), name='rental-issue'),
    path('operator/booking/<int:pk>/return/', ReturnRentalView.as_view(), name='rental-return'),
]
