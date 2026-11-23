from django.conf import settings
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError


class PasswordPolicyBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        user = super().authenticate(request, username, password, **kwargs)
        if user is not None and settings.REQUIRE_STRONG_LOGIN_PASSWORDS:
            # create_user/set_password bypass validators; imported demo accounts
            # must not gain production access with their old weak credentials.
            try:
                validate_password(password, user)
            except ValidationError:
                return None
        return user
