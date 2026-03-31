"""
auth_core/services.py
---------------------
AuthService — programmatic operations on SSOUser / ResolverProfile.

Views that need to read or mutate user attributes should go through this
service rather than hitting the ORM directly.
"""

from __future__ import annotations

from auth_core.models import Role, SSOUser, ResolverProfile


class UserNotFoundError(Exception):
    def __init__(self, identifier: str):
        super().__init__(f"User not found: {identifier}")


class AuthService:

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    @staticmethod
    def get_user(user_id: str) -> SSOUser:
        try:
            return SSOUser.objects.select_related("_resolver_profile").get(pk=user_id)
        except SSOUser.DoesNotExist:
            raise UserNotFoundError(user_id)

    @staticmethod
    def list_users(
        *,
        role: str | None = None,
        is_active: bool | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[int, list[SSOUser]]:
        qs = SSOUser.objects.select_related("_resolver_profile").all()
        if role is not None:
            qs = qs.filter(role=role)
        if is_active is not None:
            qs = qs.filter(is_active=is_active)
        total = qs.count()
        records = list(qs.order_by("email")[skip : skip + limit])
        return total, records

    # ------------------------------------------------------------------
    # Write — role + attributes
    # ------------------------------------------------------------------

    @staticmethod
    def set_role(user_id: str, role: str) -> SSOUser:
        """
        Update a user's role.  When downgrading from resolver, the
        ResolverProfile is deleted to keep data clean.
        """
        user = AuthService.get_user(user_id)
        old_role = user.role
        user.role = role
        user.save(update_fields=["role", "updated_at"])

        if old_role == Role.RESOLVER and role != Role.RESOLVER:
            ResolverProfile.objects.filter(user=user).delete()

        return user

    @staticmethod
    def set_attributes(
        user_id: str,
        *,
        allowed_agents: list[str] | None   = None,
        allowed_purposes: list[str] | None = None,
    ) -> SSOUser:
        """Patch ABAC attributes.  Pass None to leave a field unchanged."""
        user = AuthService.get_user(user_id)
        updated: list[str] = ["updated_at"]

        if allowed_agents is not None:
            user.allowed_agents = allowed_agents
            updated.append("allowed_agents")
        if allowed_purposes is not None:
            user.allowed_purposes = allowed_purposes
            updated.append("allowed_purposes")

        user.save(update_fields=updated)
        return user

    @staticmethod
    def set_active(user_id: str, is_active: bool) -> SSOUser:
        user = AuthService.get_user(user_id)
        user.is_active = is_active
        user.save(update_fields=["is_active", "updated_at"])
        return user

    # ------------------------------------------------------------------
    # Write — resolver skills
    # ------------------------------------------------------------------

    @staticmethod
    def set_resolver_skills(user_id: str, skill_set: list[str]) -> ResolverProfile:
        """
        Set the skill_set for a resolver.  Creates the ResolverProfile if it
        doesn't exist yet, raises ValueError if the user is not a resolver.
        """
        user = AuthService.get_user(user_id)
        if user.role != Role.RESOLVER:
            raise ValueError(f"User {user_id} is not a resolver (role={user.role})")

        profile, _ = ResolverProfile.objects.update_or_create(
            user      = user,
            defaults  = {"skill_set": skill_set},
        )
        return profile

    @staticmethod
    def add_resolver_skill(user_id: str, skill: str) -> ResolverProfile:
        """Add a single skill to a resolver's skill_set (idempotent)."""
        user    = AuthService.get_user(user_id)
        if user.role != Role.RESOLVER:
            raise ValueError(f"User {user_id} is not a resolver")

        profile, _ = ResolverProfile.objects.get_or_create(user=user)
        if skill not in profile.skill_set:
            profile.skill_set = sorted(profile.skill_set + [skill])
            profile.save(update_fields=["skill_set"])
        return profile

    @staticmethod
    def remove_resolver_skill(user_id: str, skill: str) -> ResolverProfile:
        """Remove a single skill from a resolver's skill_set."""
        user    = AuthService.get_user(user_id)
        profile = ResolverProfile.objects.filter(user=user).first()
        if profile and skill in profile.skill_set:
            profile.skill_set = [s for s in profile.skill_set if s != skill]
            profile.save(update_fields=["skill_set"])
        return profile

    # ------------------------------------------------------------------
    # ABAC helpers (used by views for queryset filtering)
    # ------------------------------------------------------------------

    @staticmethod
    def can_access_agent(user: SSOUser, agent_id: str) -> bool:
        """True if admin or allowed_agents is unrestricted or contains agent_id."""
        if user.is_admin:
            return True
        return not user.allowed_agents or agent_id in user.allowed_agents

    @staticmethod
    def can_access_purpose(user: SSOUser, purpose: str) -> bool:
        """True if admin or allowed_purposes is unrestricted or contains purpose."""
        if user.is_admin:
            return True
        return not user.allowed_purposes or purpose in user.allowed_purposes

    @staticmethod
    def has_skill_for_metric(user: SSOUser, metric_name: str) -> bool:
        """True if admin; for resolvers, delegates to ResolverProfile.matches_metric."""
        if user.is_admin:
            return True
        if not user.is_resolver:
            return False
        profile = user.resolver_profile
        return profile is not None and profile.matches_metric(metric_name)

    @staticmethod
    def filter_agents(user: SSOUser, agent_ids: list[str]) -> list[str]:
        """Return the subset of agent_ids accessible to this user."""
        if user.is_admin or not user.allowed_agents:
            return agent_ids
        return [a for a in agent_ids if a in user.allowed_agents]

    @staticmethod
    def filter_purposes(user: SSOUser, purposes: list[str]) -> list[str]:
        """Return the subset of purposes accessible to this user."""
        if user.is_admin or not user.allowed_purposes:
            return purposes
        return [p for p in purposes if p in user.allowed_purposes]
