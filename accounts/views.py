from datetime import timedelta
import secrets

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.core.mail import send_mail
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, FormView, ListView, UpdateView

from .forms import (
    AccountClaimForm,
    EmailVerificationForm,
    PasswordChangeByEmailForm,
    ProfileForm,
    UserLoginForm,
    UserRegisterForm,
)
from .models import EmailVerificationCode, PasswordChangeCode, User, UserNotification
from .vk_oauth import VKOAuthError, build_authorize_url, exchange_code, get_user_profile
from integrations.email_delivery import send_email_reliably
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
        user.email_verified_at = timezone.now()
        changed_fields.append('email')
        changed_fields.append('email_verified_at')
    elif token_data.get('email') and user.email == token_data['email'] and not user.email_verified_at:
        user.email_verified_at = timezone.now()
        changed_fields.append('email_verified_at')

    return changed_fields


def send_email_verification_code(user, email):
    verification_code, raw_code = EmailVerificationCode.create_for_user(user, email)
    try:
        sent_count = send_mail(
            subject="ВелоРент: код подтверждения email",
            message=(
                f"Код подтверждения email: {raw_code}\n\n"
                f"Код действует {settings.EMAIL_VERIFICATION_CODE_TTL_MINUTES} минут.\n"
                "Если вы не добавляли этот email в ВелоРент, просто проигнорируйте письмо."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=False,
        )
    except Exception:
        verification_code.mark_used()
        return False
    if sent_count <= 0:
        verification_code.mark_used()
        return False
    return True


def send_password_change_code(user):
    password_code, raw_code = PasswordChangeCode.create_for_user(user)
    try:
        sent_count = send_mail(
            subject="ВелоРент: код смены пароля",
            message=(
                f"Код смены пароля: {raw_code}\n\n"
                f"Код действует {settings.PASSWORD_CHANGE_CODE_TTL_MINUTES} минут.\n"
                "Если вы не запрашивали смену пароля, не сообщайте этот код никому."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
    except Exception:
        password_code.mark_used()
        return False
    if sent_count <= 0:
        password_code.mark_used()
        return False
    return True


def email_resend_wait_seconds(verification_code):
    if not verification_code:
        return 0
    available_at = verification_code.created_at + timedelta(seconds=settings.EMAIL_VERIFICATION_RESEND_SECONDS)
    remaining = int((available_at - timezone.now()).total_seconds())
    return max(remaining, 0)


def password_resend_wait_seconds(password_code):
    if not password_code:
        return 0
    available_at = password_code.created_at + timedelta(seconds=settings.PASSWORD_CHANGE_RESEND_SECONDS)
    remaining = int((available_at - timezone.now()).total_seconds())
    return max(remaining, 0)


def get_pending_password_change_code(user):
    return (
        user.password_change_codes
        .filter(
            used_at__isnull=True,
            expires_at__gte=timezone.now(),
            attempts__lt=settings.PASSWORD_CHANGE_CODE_MAX_ATTEMPTS,
        )
        .first()
    )


def email_verification_context(request, form=None, pending_code=None):
    pending_code = pending_code or (
        request.user.email_verification_codes
        .filter(
            used_at__isnull=True,
            expires_at__gte=timezone.now(),
            attempts__lt=settings.EMAIL_VERIFICATION_CODE_MAX_ATTEMPTS,
        )
        .first()
    )
    pending_password_code = get_pending_password_change_code(request.user)
    return {
        'form': ProfileForm(instance=request.user, allow_email_edit=True),
        'email_verification_form': form or EmailVerificationForm(user=request.user),
        'pending_email_code': pending_code,
        'pending_email_resend_wait': email_resend_wait_seconds(pending_code),
        'email_edit_mode': True,
        'password_change_form': PasswordChangeByEmailForm(user=request.user),
        'pending_password_code': pending_password_code,
        'pending_password_resend_wait': password_resend_wait_seconds(pending_password_code),
        'vk_community_url': settings.VK_COMMUNITY_URL,
        'vk_group_token_present': bool(settings.VK_GROUP_TOKEN),
        'personal_data_email': settings.PERSONAL_DATA_EMAIL,
    }


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

    def email_edit_mode(self):
        if not self.request.user.email_is_verified:
            return True
        if self.get_pending_email_code():
            return True
        if self.request.method == 'POST':
            return self.request.POST.get('edit_email') == '1'
        return self.request.GET.get('edit_email') == '1'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['allow_email_edit'] = self.email_edit_mode()
        return kwargs

    def get_pending_email_code(self):
        return (
            self.request.user.email_verification_codes
            .filter(
                used_at__isnull=True,
                expires_at__gte=timezone.now(),
                attempts__lt=settings.EMAIL_VERIFICATION_CODE_MAX_ATTEMPTS,
            )
            .first()
        )

    def get_initial(self):
        initial = super().get_initial()
        pending_email_code = self.get_pending_email_code()
        if pending_email_code:
            initial['email'] = pending_email_code.email
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['vk_community_url'] = settings.VK_COMMUNITY_URL
        context['vk_group_token_present'] = bool(settings.VK_GROUP_TOKEN)
        context['personal_data_email'] = settings.PERSONAL_DATA_EMAIL
        pending_email_code = self.get_pending_email_code()
        pending_password_code = get_pending_password_change_code(self.request.user)
        context['pending_email_code'] = pending_email_code
        context['pending_email_resend_wait'] = email_resend_wait_seconds(pending_email_code)
        context['pending_password_code'] = pending_password_code
        context['pending_password_resend_wait'] = password_resend_wait_seconds(pending_password_code)
        context['email_edit_mode'] = self.email_edit_mode()
        context.setdefault('email_verification_form', EmailVerificationForm(user=self.request.user))
        context.setdefault('password_change_form', PasswordChangeByEmailForm(user=self.request.user))
        return context

    def form_valid(self, form):
        current_user = User.objects.get(pk=self.request.user.pk)
        current_email = (current_user.email or '').strip().lower()
        email_edit_mode = self.email_edit_mode()
        requested_email = current_email
        if email_edit_mode:
            requested_email = (form.cleaned_data.get('email') or '').strip().lower()

        user = form.save(commit=False)
        email_changed = email_edit_mode and requested_email != current_email

        if email_changed and not requested_email:
            user.email = ""
            user.email_verified_at = None
            user.email_verification_codes.filter(used_at__isnull=True).update(used_at=timezone.now())
            user.save()
            messages.success(self.request, "Профиль обновлен. Email отключен.")
            return redirect(self.success_url)

        user.email = current_user.email
        user.email_verified_at = current_user.email_verified_at
        user.save()

        if email_changed:
            sent = send_email_verification_code(user, requested_email)
            if sent:
                messages.info(self.request, f"Код подтверждения отправлен на {requested_email}.")
            else:
                messages.error(self.request, "Не удалось отправить код. Проверьте настройки почты и попробуйте еще раз.")
        else:
            messages.success(self.request, "Профиль обновлен.")
        return redirect(self.success_url)


class EmailVerificationConfirmView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        form = EmailVerificationForm(request.POST, user=request.user)
        if not form.is_valid():
            pending_code = (
                request.user.email_verification_codes
                .filter(
                    used_at__isnull=True,
                    expires_at__gte=timezone.now(),
                    attempts__lt=settings.EMAIL_VERIFICATION_CODE_MAX_ATTEMPTS,
                )
                .first()
            )
            return render(
                request,
                'accounts/profile.html',
                email_verification_context(request, form=form, pending_code=pending_code),
            )

        verification_code = form.verification_code
        user = request.user
        user.email = verification_code.email
        user.email_verified_at = timezone.now()
        user.save(update_fields=['email', 'email_verified_at'])
        verification_code.mark_used()
        user.email_verification_codes.filter(used_at__isnull=True).update(used_at=timezone.now())
        messages.success(request, "Email подтвержден и подключен к уведомлениям.")
        return redirect('profile')


class EmailVerificationResendView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        pending_code = (
            request.user.email_verification_codes
            .filter(
                used_at__isnull=True,
                expires_at__gte=timezone.now(),
                attempts__lt=settings.EMAIL_VERIFICATION_CODE_MAX_ATTEMPTS,
            )
            .first()
        )
        if not pending_code:
            messages.warning(request, "Нет активного email для подтверждения.")
            return redirect('profile')

        wait_seconds = email_resend_wait_seconds(pending_code)
        if wait_seconds > 0:
            messages.warning(request, f"Новый код можно отправить через {wait_seconds} сек.")
            return redirect('profile')

        sent = send_email_verification_code(request.user, pending_code.email)
        if sent:
            messages.info(request, f"Новый код отправлен на {pending_code.email}.")
        else:
            messages.error(request, "Не удалось отправить код. Попробуйте позже.")
        return redirect('profile')


class EmailVerificationCancelView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        request.user.email_verification_codes.filter(used_at__isnull=True).update(used_at=timezone.now())
        messages.success(request, "Подтверждение email отменено.")
        return redirect('profile')


class PasswordChangeStartView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        user = request.user
        pending_code = get_pending_password_change_code(user)

        if not user.has_usable_password():
            messages.warning(request, "Сначала задайте пароль через код от оператора.")
            return redirect('profile')

        if not user.email_is_verified:
            messages.warning(request, "Для смены пароля сначала подтвердите email.")
            return redirect('profile')

        wait_seconds = password_resend_wait_seconds(pending_code)
        if pending_code and wait_seconds > 0:
            messages.warning(request, f"Новый код можно отправить через {wait_seconds} сек.")
            return redirect('profile')

        sent = send_password_change_code(user)
        if sent:
            messages.info(request, f"Код смены пароля отправлен на {user.email}.")
        else:
            messages.error(request, "Не удалось отправить код. Проверьте настройки почты и попробуйте позже.")
        return redirect('profile')


class PasswordChangeConfirmView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        form = PasswordChangeByEmailForm(request.POST, user=request.user)
        if not form.is_valid():
            pending_email_code = (
                request.user.email_verification_codes
                .filter(
                    used_at__isnull=True,
                    expires_at__gte=timezone.now(),
                    attempts__lt=settings.EMAIL_VERIFICATION_CODE_MAX_ATTEMPTS,
                )
                .first()
            )
            context = email_verification_context(request, pending_code=pending_email_code)
            context['password_change_form'] = form
            return render(request, 'accounts/profile.html', context)

        user = request.user
        user.set_password(form.cleaned_data["password1"])
        user.save(update_fields=["password"])
        form.password_code.mark_used()
        user.password_change_codes.filter(used_at__isnull=True).update(used_at=timezone.now())
        update_session_auth_hash(request, user)
        send_email_reliably(
            user.email,
            "ВелоРент: пароль успешно изменён",
            (
                "Пароль вашей учётной записи ВелоРент успешно изменён.\n\n"
                "Если это сделали не вы, немедленно свяжитесь с оператором ВелоРент."
            ),
            kind="password_changed",
        )
        messages.success(request, "Пароль изменен.")
        return redirect('profile')


class PasswordChangeCancelView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        request.user.password_change_codes.filter(used_at__isnull=True).update(used_at=timezone.now())
        messages.success(request, "Смена пароля отменена.")
        return redirect('profile')


class NotificationsListView(LoginRequiredMixin, ListView):
    template_name = 'accounts/notifications.html'
    context_object_name = 'notifications'
    paginate_by = 12

    def get(self, request, *args, **kwargs):
        UserNotification.objects.filter(
            user=request.user,
            read_at__isnull=True,
        ).update(read_at=timezone.now())
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        return self.request.user.notifications.all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['unread_total'] = self.request.user.notifications.filter(read_at__isnull=True).count()
        context['back_url'] = reverse(get_role_home(self.request.user))
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
