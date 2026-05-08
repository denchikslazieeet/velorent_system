from django.urls import path
from .views import (
    AccountClaimView,
    EmailTestNotificationView,
    ProfileView,
    MarkNotificationsReadView,
    NotificationsListView,
    UserLoginView,
    UserLogoutView,
    UserRegisterView,
    VKCallbackView,
    VKLinkStartView,
    VKLoginStartView,
    VKNotificationsToggleView,
    VKTestNotificationView,
    VKUnlinkView,
)

urlpatterns = [
    path('login/', UserLoginView.as_view(), name='login'),
    path('claim/', AccountClaimView.as_view(), name='account-claim'),
    path('register/', UserRegisterView.as_view(), name='register'),
    path('vk/login/', VKLoginStartView.as_view(), name='vk-login'),
    path('vk/link/', VKLinkStartView.as_view(), name='vk-link'),
    path('vk/callback/', VKCallbackView.as_view(), name='vk-callback'),
    path('vk/unlink/', VKUnlinkView.as_view(), name='vk-unlink'),
    path('vk/notifications/', VKNotificationsToggleView.as_view(), name='vk-notifications'),
    path('vk/test/', VKTestNotificationView.as_view(), name='vk-test-notification'),
    path('email/test/', EmailTestNotificationView.as_view(), name='email-test-notification'),
    path('logout/', UserLogoutView.as_view(), name='logout'),
    path('profile/', ProfileView.as_view(), name='profile'),
    path('notifications/', NotificationsListView.as_view(), name='notifications'),
    path('notifications/read/', MarkNotificationsReadView.as_view(), name='notifications-read'),
]
