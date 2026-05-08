import secrets

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, FormView, ListView, UpdateView

from .forms import AccountClaimForm, ProfileForm, UserLoginForm, UserRegisterForm
from .models import User, UserNotification
from .vk_oauth import VKOAuthError, build_authorize_url, exchange_code, get_user_profile
from integrations.vk_notifications import send_vk_message


def get_role_home(user: User) -> str:
    if user.role in {User.Role.OPERATOR, User.Role.ADMIN} or user.is_staff or user.is_superuser:
        return 'operator-dashboard'
    return 'user-dashboard'


def get_vk_redirect_uri(request) -> str:
    return settings.VK_REDIRECT_URI or request.build_absolute_uri(reverse('vk-callback'))


def unique_vk_username(vk_id: str) -> str:
    base = f"vk_{vk_id}"[:145]
    username = base
    suffix = 1
    while User.objects.filter(username=username).exists():
        username = f"{base}_{suffix}"[:150]
        suffix += 1
    return username


def vk_settings_ready() -> bool:
    return bool(settings.VK_CLIENT_ID and settings.VK_CLIENT_SECRET)


def update_user_from_vk(user, profile, token_data, overwrite_empty_only=True):
    changed_fields = []
    field_values = [
        ('first_name', profile.get('first_name') or '', 150),
        ('last_name', profile.get('last_name') or '', 150),
        ('vk_screen_name', profile.get('screen_name') or '', 120),
        ('vk_photo_url', profile.get('photo_100') or '', None),
    ]

    for field, value, limit in field_values:
        value = value[:limit] if limit else value
        if not value:
            continue
        if overwrite_empty_only and field in {'first_name', 'last_name'} and getattr(user, field):
            continue
        if getattr(user, field) != value:
            setattr(user, field, value)
            changed_fields.append(field)

    if token_data.get('email') and not user.email:
        user.email = token_data['email']
        changed_fields.append('email')

    return changed_fields


class UserRegisterView(CreateView):
    form_class = UserRegisterForm
    template_name = 'accounts/register.html'
    success_url = reverse_lazy('user-dashboard')

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect(get_role_home(request.user))
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)
        messages.success(
            self.request,
            "Аккаунт создан. Для первой аренды возьмите с собой документ, удостоверяющий личность."
        )
        return response


class UserLoginView(LoginView):
    template_name = 'accounts/login.html'
    authentication_form = UserLoginForm

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect(get_role_home(request.user))
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        return reverse_lazy(get_role_home(self.request.user))


class AccountClaimView(FormView):
    form_class = AccountClaimForm
    template_name = 'accounts/claim.html'
    success_url = reverse_lazy('user-dashboard')

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect(get_role_home(request.user))
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        user = form.save()
        login(self.request, user)
        messages.success(
            self.request,
            "Пароль задан. Теперь вы можете входить по телефону и паролю."
        )
        return super().form_valid(form)


class VKLoginStartView(View):
    def get(self, request, *args, **kwargs):
        if not vk_settings_ready():
            messages.error(
                request,
                "Вход через VK пока не настроен. Укажите VK_CLIENT_ID и VK_CLIENT_SECRET в .env."
            )
            return redirect('login')

        state = secrets.token_urlsafe(24)
        request.session['vk_oauth_state'] = state
        request.session['vk_oauth_mode'] = 'login'
        request.session['vk_oauth_next'] = request.GET.get('next') or ''
        return redirect(build_authorize_url(get_vk_redirect_uri(request), state))


class VKLinkStartView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        if not vk_settings_ready():
            messages.error(
                request,
                "Привязка VK пока не настроена. Укажите VK_CLIENT_ID и VK_CLIENT_SECRET в .env."
            )
            return redirect('profile')

        state = secrets.token_urlsafe(24)
        request.session['vk_oauth_state'] = state
        request.session['vk_oauth_mode'] = 'link'
        return redirect(build_authorize_url(get_vk_redirect_uri(request), state))


class VKCallbackView(View):
    def get(self, request, *args, **kwargs):
        mode = request.session.get('vk_oauth_mode', 'login')
        fallback_url = 'profile' if mode == 'link' else 'login'

        if request.GET.get('error'):
            messages.error(request, "VK не разрешил вход. Попробуйте еще раз.")
            return redirect(fallback_url)

        state = request.GET.get('state')
        if not state or state != request.session.get('vk_oauth_state'):
            messages.error(request, "Не удалось проверить запрос VK. Попробуйте еще раз.")
            return redirect('login')

        code = request.GET.get('code')
        if not code:
            messages.error(request, "VK не вернул код авторизации.")
            return redirect(fallback_url)

        redirect_uri = get_vk_redirect_uri(request)
        try:
            token_data = exchange_code(code, redirect_uri)
            vk_id = str(token_data.get('user_id') or '')
            access_token = token_data.get('access_token')
            if not vk_id or not access_token:
                raise VKOAuthError("VK не вернул необходимые данные для входа.")
            profile = get_user_profile(access_token, vk_id)
        except VKOAuthError as exc:
            messages.error(request, str(exc))
            return redirect(fallback_url)
        finally:
            request.session.pop('vk_oauth_state', None)

        mode = request.session.pop('vk_oauth_mode', 'login')

        if mode == 'link':
            if not request.user.is_authenticated:
                messages.error(request, "Для привязки VK сначала войдите в аккаунт.")
                return redirect('login')

            linked_user = User.objects.filter(vk_id=vk_id).exclude(pk=request.user.pk).first()
            if linked_user:
                messages.error(request, "Этот VK уже привязан к другому аккаунту.")
                return redirect('profile')

            user = request.user
            user.vk_id = vk_id
            user.vk_notifications_enabled = True
            changed_fields = update_user_from_vk(user, profile, token_data, overwrite_empty_only=True)
            changed_fields.extend(['vk_id', 'vk_notifications_enabled'])
            user.save(update_fields=sorted(set(changed_fields)))
            messages.success(request, "VK привязан. Уведомления VK включены.")
            return redirect('profile')

        user = User.objects.filter(vk_id=vk_id).first()
        created = False
        if user is None:
            user = User(
                username=unique_vk_username(vk_id),
                vk_id=vk_id,
                role=User.Role.CUSTOMER,
                vk_notifications_enabled=True,
                email=token_data.get('email') or '',
                first_name=(profile.get('first_name') or '')[:150],
                last_name=(profile.get('last_name') or '')[:150],
                vk_screen_name=(profile.get('screen_name') or '')[:120],
                vk_photo_url=profile.get('photo_100') or '',
            )
            user.set_unusable_password()
            user.mark_consents_accepted()
            user.save()
            created = True
        else:
            changed_fields = update_user_from_vk(user, profile, token_data, overwrite_empty_only=False)
            if changed_fields:
                user.save(update_fields=changed_fields)

        login(request, user)
        if created:
            messages.success(request, "Аккаунт создан через VK. Для первой аренды возьмите с собой документ.")
        else:
            messages.success(request, "Вы вошли через VK.")
        return redirect(get_role_home(user))


class VKUnlinkView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        user = request.user
        user.vk_id = None
        user.vk_screen_name = ""
        user.vk_photo_url = ""
        user.vk_notifications_enabled = False
        user.save(update_fields=[
            'vk_id',
            'vk_screen_name',
            'vk_photo_url',
            'vk_notifications_enabled',
        ])
        messages.success(request, "VK отвязан от аккаунта.")
        return redirect('profile')


class VKNotificationsToggleView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        user = request.user
        if not user.vk_id:
            messages.warning(request, "Сначала привяжите VK.")
            return redirect('profile')

        user.vk_notifications_enabled = request.POST.get('enabled') == 'on'
        user.save(update_fields=['vk_notifications_enabled'])
        if user.vk_notifications_enabled:
            messages.success(request, "Уведомления VK включены.")
        else:
            messages.success(request, "Уведомления VK выключены.")
        return redirect('profile')


class VKTestNotificationView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        user = request.user
        if not user.vk_id:
            messages.warning(request, "Сначала привяжите VK.")
            return redirect('profile')

        sent = send_vk_message(
            user,
            "Тестовое уведомление ВелоРент. Если вы видите это сообщение, уведомления VK работают."
        )
        if sent:
            messages.success(request, "Тестовое уведомление отправлено в VK.")
        else:
            messages.warning(
                request,
                "Не удалось отправить сообщение. Проверьте VK_GROUP_TOKEN и разрешение сообщений от сообщества."
            )
        return redirect('profile')


class UserLogoutView(LogoutView):
    next_page = reverse_lazy('home')


class ProfileView(LoginRequiredMixin, UpdateView):
    form_class = ProfileForm
    template_name = 'accounts/profile.html'
    success_url = reverse_lazy('profile')

    def get_object(self, queryset=None):
        return self.request.user

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['vk_community_url'] = settings.VK_COMMUNITY_URL
        context['vk_group_token_present'] = bool(settings.VK_GROUP_TOKEN)
        return context

    def form_valid(self, form):
        messages.success(self.request, "Профиль обновлен.")
        return super().form_valid(form)


class NotificationsListView(LoginRequiredMixin, ListView):
    template_name = 'accounts/notifications.html'
    context_object_name = 'notifications'
    paginate_by = 12

    def get_queryset(self):
        return self.request.user.notifications.all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['unread_total'] = self.request.user.notifications.filter(read_at__isnull=True).count()
        if context.get('is_paginated'):
            paginator = context['paginator']
            page_number = context['page_obj'].number
            context['page_range'] = paginator.get_elided_page_range(
                page_number,
                on_each_side=1,
                on_ends=1,
            )
        return context


class MarkNotificationsReadView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        UserNotification.objects.filter(
            user=request.user,
            read_at__isnull=True,
        ).update(read_at=timezone.now())
        messages.success(request, "Уведомления отмечены как прочитанные.")
        return redirect('notifications')
