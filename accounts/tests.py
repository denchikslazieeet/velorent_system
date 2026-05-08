from django.test import TestCase, override_settings
from django.urls import reverse

from .forms import AccountClaimForm
from .models import AccountAccessCode, User
from integrations.vk_notifications import send_vk_message


class AccountClaimFormTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="79991234567",
            phone="79991234567",
        )
        self.user.set_unusable_password()
        self.user.save(update_fields=["password"])
        self.access_code, self.raw_code = AccountAccessCode.create_for_user(self.user)

    def form_data(self, code=None):
        return {
            "phone": "+7 (999) 123-45-67",
            "code": code or self.raw_code,
            "password1": "StrongPass123",
            "password2": "StrongPass123",
            "accept_terms": "on",
            "accept_personal_data": "on",
        }

    def test_claim_sets_password_and_uses_code(self):
        form = AccountClaimForm(data=self.form_data())

        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()

        user.refresh_from_db()
        self.access_code.refresh_from_db()
        self.assertTrue(user.has_usable_password())
        self.assertTrue(user.check_password("StrongPass123"))
        self.assertTrue(user.terms_accepted)
        self.assertIsNotNone(self.access_code.used_at)

    def test_invalid_code_does_not_set_password_and_counts_attempt(self):
        form = AccountClaimForm(data=self.form_data(code="000000"))

        self.assertFalse(form.is_valid())

        self.user.refresh_from_db()
        self.access_code.refresh_from_db()
        self.assertFalse(self.user.has_usable_password())
        self.assertEqual(self.access_code.attempts, 1)


class VKOAuthViewTests(TestCase):
    @override_settings(VK_CLIENT_ID="123", VK_CLIENT_SECRET="secret")
    def test_vk_login_redirects_to_vk_and_stores_state(self):
        response = self.client.get(reverse("vk-login"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("oauth.vk.com/authorize", response["Location"])
        self.assertIn("vk_oauth_state", self.client.session)

    def test_vk_login_without_settings_returns_to_login(self):
        response = self.client.get(reverse("vk-login"))

        self.assertRedirects(response, reverse("login"))

    def test_vk_callback_rejects_invalid_state(self):
        response = self.client.get(reverse("vk-callback"), {"state": "bad", "code": "code"})

        self.assertRedirects(response, reverse("login"))

    def test_vk_link_requires_login(self):
        response = self.client.get(reverse("vk-link"))

        self.assertEqual(response.status_code, 302)


class VKNotificationTests(TestCase):
    def test_notification_without_group_token_is_skipped(self):
        user = User.objects.create_user(
            username="vk-user",
            vk_id="12345",
            vk_notifications_enabled=True,
        )

        self.assertFalse(send_vk_message(user, "test"))
