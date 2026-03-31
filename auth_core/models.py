"""
auth_core/models.py
--------------------
SSOUser — represents a user who has authenticated via an external SSO
provider (Google, Okta, Auth0, Keycloak, …).  Django's built-in User table
is kept separate for the admin panel only.

SSOUser.user_id = the `sub` claim from the provider's JWT.
Role/attribute values are managed locally by admins; the SSO provider only
supplies identity (sub, email, name).

ResolverProfile — resolver-specific attributes attached 1-to-1 to an
SSOUser whose role is `resolver`.  Stores the skill_set used to match
metric_names for ABAC skill checks.
"""

from django.db import models


class Role(models.TextChoices):
    END_USER = "end_user",  "End User"
    RESOLVER = "resolver",  "Resolver"
    ADMIN    = "admin",     "Admin"


class SSOUser(models.Model):
    # Primary key = `sub` claim from the SSO JWT (opaque string, provider-specific)
    user_id  = models.CharField(max_length=255, primary_key=True)
    email    = models.EmailField(unique=True)
    name     = models.CharField(max_length=255, blank=True, default="")
    role     = models.CharField(max_length=20, choices=Role.choices, default=Role.END_USER)
    is_active = models.BooleanField(default=True)

    # ── ABAC attributes ────────────────────────────────────────────────
    # Empty list  → no restriction (all agents / all purposes allowed).
    # Non-empty   → only the listed IDs / names are accessible.
    # Admin always bypasses these checks regardless of the stored value.
    allowed_agents   = models.JSONField(default=list, blank=True)
    allowed_purposes = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "sso_users"

    def __str__(self):
        return f"{self.email} [{self.role}]"

    # ── Helpers ────────────────────────────────────────────────────────

    @property
    def is_admin(self) -> bool:
        return self.role == Role.ADMIN

    @property
    def is_resolver(self) -> bool:
        return self.role == Role.RESOLVER

    @property
    def resolver_profile(self) -> "ResolverProfile | None":
        try:
            return self._resolver_profile  # type: ignore[attr-defined]
        except ResolverProfile.DoesNotExist:
            return None


class ResolverProfile(models.Model):
    """
    Extended attributes for users with role=resolver.

    skill_set  — list of metric-name prefixes this resolver is trained on.
                 e.g. ["cpu", "memory", "disk"]
                 A metric "cpu_v1.0.0.pct" matches skill "cpu" via startswith.
                 Empty list = no skills assigned yet (resolver cannot act on anything).
    """
    user      = models.OneToOneField(
        SSOUser,
        on_delete     = models.CASCADE,
        primary_key   = True,
        related_name  = "_resolver_profile",
    )
    skill_set = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "resolver_profiles"

    def __str__(self):
        return f"ResolverProfile({self.user_id}, skills={self.skill_set})"

    def matches_metric(self, metric_name: str) -> bool:
        """
        Return True if metric_name starts with any skill in skill_set.
        An empty skill_set means the resolver has no clearance → always False.
        """
        return any(metric_name.startswith(skill) for skill in self.skill_set)
