from rest_framework.permissions import BasePermission

class IsOperator(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return user.is_authenticated and (
            user.role in {"operator", "admin"}
            or user.is_staff
            or user.is_superuser
        )
