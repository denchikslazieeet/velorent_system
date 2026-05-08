from django.contrib.auth.mixins import UserPassesTestMixin

from accounts.models import User


class OperatorRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        user = self.request.user
        return user.is_authenticated and (
            user.role in {User.Role.OPERATOR, User.Role.ADMIN}
            or user.is_staff
            or user.is_superuser
        )
