"""
dev_auth/models.py
------------------
⚠️  DEVELOPMENT / DEMO USE ONLY ⚠️

Stores a hashed password alongside each SSOUser so developers can get a
JWT from a local endpoint without needing an external SSO provider.

In production, delete this app from INSTALLED_APPS and remove the
/api/dev-auth/ URLs.  JWTs will then come exclusively from your real
SSO provider (Okta, Auth0, Google, Keycloak, …).
"""

from django.contrib.auth.hashers import make_password, check_password
from django.db import models

from auth_core.models import SSOUser


class DevCredential(models.Model):
    """
    One-to-one local password credential per SSOUser.
    Only exists in development; never store real credentials here in prod.
    """
    user          = models.OneToOneField(
        SSOUser,
        on_delete    = models.CASCADE,
        primary_key  = True,
        related_name = "dev_credential",
    )
    password_hash = models.CharField(max_length=255)
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "dev_credentials"

    # ------------------------------------------------------------------ #
    def set_password(self, raw_password: str) -> None:
        """Hash and store a new password."""
        self.password_hash = make_password(raw_password)

    def verify_password(self, raw_password: str) -> bool:
        """Return True if raw_password matches the stored hash."""
        return check_password(raw_password, self.password_hash)
