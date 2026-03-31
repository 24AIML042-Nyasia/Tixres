"""
tickets/assignment.py
---------------------
Resolver auto-assignment for new tickets.

Selection rules (in order):
1. Sticky reuse: if a recent open/ack ticket with the same key already has an assignee
   and that resolver is still eligible, reuse them.
2. Skill + ABAC match: eligible resolvers who match metric skill, agent, and purpose,
   choose the least-loaded (open/ack ticket count). Tie-breaker: oldest assigned_at,
   then user_id.
3. Purpose-only fallback: optional flag to allow purpose match without skill.
4. On-call fallback: configurable resolver id in settings.AUTO_ASSIGN_ONCALL_RESOLVER_ID.
5. Otherwise leave unassigned and record reason.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, List, Optional, Tuple

from django.conf import settings
from django.db.models import Count

from auth_core.models import Role, SSOUser
from auth_core.services import AuthService
from tickets.models import (
    Ticket,
    TICKET_STATUS_OPEN,
    TICKET_STATUS_ACK,
)

logger = logging.getLogger(__name__)


@dataclass
class AssignmentDecision:
    assignee: Optional[SSOUser]
    strategy: str
    reason: str
    auto_assigned: bool = True


class AssignmentService:
    """
    Stateless picker for ticket assignees.
    """

    @staticmethod
    def assign(ticket: Ticket) -> AssignmentDecision:
        """
        Auto-assign a ticket in-place if unassigned.

        Returns the decision (assignee may be None). Persists ticket changes.
        """
        if ticket.assigned_to_id:
            return AssignmentDecision(ticket.assigned_to, "existing", "Ticket already assigned", auto_assigned=False)

        decision = AssignmentService.pick_assignee(ticket)
        if decision.assignee:
            now = datetime.now(tz=timezone.utc)
            ticket.assigned_to = decision.assignee
            ticket.assigned_at = now
            ticket.assignment_strategy = decision.strategy
            ticket.assignment_reason = decision.reason
            ticket.auto_assigned = decision.auto_assigned
            ticket.save(
                update_fields=[
                    "assigned_to",
                    "assigned_at",
                    "assignment_strategy",
                    "assignment_reason",
                    "auto_assigned",
                ]
            )
            AssignmentService._append_history(ticket, decision, now)
        else:
            AssignmentService._append_history(ticket, decision, datetime.now(tz=timezone.utc))
        return decision

    # ------------------------------------------------------------------
    # Core picker
    # ------------------------------------------------------------------

    @staticmethod
    def pick_assignee(ticket: Ticket) -> AssignmentDecision:
        allow_purpose_fallback = getattr(settings, "AUTO_ASSIGN_ALLOW_PURPOSE_FALLBACK", False)
        oncall_resolver_id = getattr(settings, "AUTO_ASSIGN_ONCALL_RESOLVER_ID", None)

        eligible_resolvers = AssignmentService._eligible_resolvers(ticket)
        if not eligible_resolvers:
            return AssignmentDecision(None, "none", "No eligible resolvers for agent/purpose", auto_assigned=True)

        load_map = AssignmentService._load_map()
        min_load = min(load_map.get(r.pk, 0) for r in eligible_resolvers) if eligible_resolvers else 0
        sticky_tolerance = getattr(settings, "AUTO_ASSIGN_STICKY_LOAD_DELTA", 1)

        # 1) Sticky reuse (only if it does not increase load beyond current minimum)
        sticky = AssignmentService._sticky_assignee(ticket, eligible_resolvers)
        if sticky:
            sticky_load = load_map.get(sticky.pk, 0)
            if sticky_load <= (min_load + sticky_tolerance):
                return AssignmentDecision(sticky, "sticky", "Reused recent assignee for same signal")

        # 2) Skill match
        skill_matches = [r for r in eligible_resolvers if AuthService.has_skill_for_metric(r, ticket.metric_name)]
        if skill_matches:
            chosen = AssignmentService._least_loaded(skill_matches, load_map)
            return AssignmentDecision(chosen, "skill", "Skill + ABAC match")

        # 3) Purpose-only fallback (optional)
        if allow_purpose_fallback:
            purpose_matches = [r for r in eligible_resolvers if AuthService.can_access_purpose(r, ticket.purpose)]
            if purpose_matches:
                chosen = AssignmentService._least_loaded(purpose_matches, load_map)
                return AssignmentDecision(
                    chosen,
                    "purpose_fallback",
                    "Purpose match, skill missing; allowed by flag",
                )

        # 4) On-call fallback
        if oncall_resolver_id:
            candidate = AssignmentService._fetch_resolver(oncall_resolver_id)
            if candidate and AssignmentService._is_eligible(candidate, ticket, skip_skill=True):
                return AssignmentDecision(candidate, "oncall", "Fallback to configured on-call resolver")

        # 5) Unassigned
        return AssignmentDecision(None, "unassigned", "No resolver passed skill/ABAC filters")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _eligible_resolvers(ticket: Ticket) -> List[SSOUser]:
        resolvers = list(
            SSOUser.objects.select_related("_resolver_profile")
            .filter(role=Role.RESOLVER, is_active=True)
            .order_by("user_id")
        )
        return [r for r in resolvers if AssignmentService._is_eligible(r, ticket, skip_skill=True)]

    @staticmethod
    def _is_eligible(user: SSOUser, ticket: Ticket, *, skip_skill: bool = False) -> bool:
        if not user.is_active or not user.is_resolver:
            return False
        if not AuthService.can_access_agent(user, ticket.agent_id):
            return False
        if not AuthService.can_access_purpose(user, ticket.purpose):
            return False
        if skip_skill:
            return True
        return AuthService.has_skill_for_metric(user, ticket.metric_name)

    @staticmethod
    def _sticky_assignee(ticket: Ticket, eligible: List[SSOUser]) -> Optional[SSOUser]:
        candidate = (
            Ticket.objects.filter(
                metric_name=ticket.metric_name,
                severity=ticket.severity,
                purpose=ticket.purpose,
                status__in=[TICKET_STATUS_OPEN, TICKET_STATUS_ACK],
                assigned_to__isnull=False,
            )
            # related_name on ResolverProfile is "_resolver_profile" (leading underscore)
            .select_related("assigned_to", "assigned_to___resolver_profile")
            .order_by("-assigned_at", "-last_occurred_at")
            .first()
        )
        if candidate and candidate.assigned_to in eligible:
            return candidate.assigned_to
        return None

    @staticmethod
    def _load_map() -> dict:
        rows = (
            Ticket.objects.filter(
                status__in=[TICKET_STATUS_OPEN, TICKET_STATUS_ACK],
                assigned_to__isnull=False,
            )
            .values("assigned_to")
            .annotate(load=Count("id"))
        )
        return {r["assigned_to"]: r["load"] for r in rows}

    @staticmethod
    def _least_loaded(candidates: Iterable[SSOUser], load_map: dict) -> SSOUser:
        def sort_key(user: SSOUser):
            return (
                load_map.get(user.pk, 0),
                AssignmentService._last_assigned_at(user),
                user.user_id,
            )

        return sorted(candidates, key=sort_key)[0]

    @staticmethod
    def _last_assigned_at(user: SSOUser):
        latest = (
            Ticket.objects.filter(assigned_to=user)
            .order_by("-assigned_at")
            .values_list("assigned_at", flat=True)
            .first()
        )
        return latest or datetime.min.replace(tzinfo=timezone.utc)

    @staticmethod
    def _fetch_resolver(user_id: str) -> Optional[SSOUser]:
        try:
            user = SSOUser.objects.select_related("_resolver_profile").get(pk=user_id)
            if user.role == Role.RESOLVER and user.is_active:
                return user
        except SSOUser.DoesNotExist:
            return None
        return None

    @staticmethod
    def _append_history(ticket: Ticket, decision: AssignmentDecision, at: datetime) -> None:
        """
        Store an append-only audit trail inside ticket.meta.assignment_history.
        """
        try:
            meta: dict = json.loads(ticket.meta or "{}")
        except (json.JSONDecodeError, TypeError):
            meta = {}

        history = meta.get("assignment_history") or []
        entry = {
            "at": at.isoformat(),
            "strategy": decision.strategy,
            "reason": decision.reason,
            "assignee_id": getattr(decision.assignee, "user_id", None),
        }
        history.append(entry)
        meta["assignment_history"] = history
        ticket.meta = json.dumps(meta)
        ticket.save(update_fields=["meta"])
