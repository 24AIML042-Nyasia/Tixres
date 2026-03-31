from datetime import datetime, timezone, timedelta

from django.test import TestCase, override_settings

from auth_core.models import SSOUser, Role, ResolverProfile
from tickets.assignment import AssignmentService
from tickets.models import Ticket, TICKET_STATUS_OPEN
from tickets.services import TicketService


class AssignmentServiceTests(TestCase):
    def setUp(self):
        self.now = datetime.now(tz=timezone.utc)
        self.resolver_a = SSOUser.objects.create(
            user_id="r1",
            email="r1@example.com",
            role=Role.RESOLVER,
            name="Resolver A",
        )
        self.resolver_b = SSOUser.objects.create(
            user_id="r2",
            email="r2@example.com",
            role=Role.RESOLVER,
            name="Resolver B",
        )
        ResolverProfile.objects.create(user=self.resolver_a, skill_set=["cpu"])
        ResolverProfile.objects.create(user=self.resolver_b, skill_set=["cpu"])

    def _ticket(self, **kwargs):
        defaults = dict(
            agent_id="agent-1",
            metric_name="cpu.utilization",
            severity="P2",
            purpose="general",
            status=TICKET_STATUS_OPEN,
            detectors="[]",
            meta="{}",
            message="hi",
            occurrence_count=1,
            first_occurred_at=self.now - timedelta(minutes=5),
            last_occurred_at=self.now - timedelta(minutes=1),
        )
        defaults.update(kwargs)
        return Ticket.objects.create(**defaults)

    def test_assign_picks_least_loaded_skill_match(self):
        # Add load to resolver A so resolver B should be chosen
        self._ticket(assigned_to=self.resolver_a, assigned_at=self.now - timedelta(minutes=10))
        self._ticket(assigned_to=self.resolver_a, assigned_at=self.now - timedelta(minutes=8))

        new_ticket = self._ticket(assigned_to=None, assigned_at=None, metric_name="cpu.utilization")
        decision = AssignmentService.assign(new_ticket)

        self.assertEqual(new_ticket.assigned_to, self.resolver_b)
        self.assertEqual(decision.strategy, "skill")
        self.assertTrue(new_ticket.auto_assigned)

    def test_sticky_reuses_recent_assignee(self):
        sticky_ticket = self._ticket(assigned_to=self.resolver_a, assigned_at=self.now - timedelta(minutes=2))

        new_ticket = self._ticket(assigned_to=None, assigned_at=None, metric_name=sticky_ticket.metric_name)
        decision = AssignmentService.assign(new_ticket)

        self.assertEqual(new_ticket.assigned_to, self.resolver_a)
        self.assertEqual(decision.strategy, "sticky")

    @override_settings(AUTO_ASSIGN_ALLOW_PURPOSE_FALLBACK=True)
    def test_purpose_fallback_when_no_skill(self):
        # Remove skills to force purpose fallback
        self.resolver_a.resolver_profile.skill_set = []
        self.resolver_a.resolver_profile.save(update_fields=["skill_set"])
        self.resolver_b.resolver_profile.skill_set = []
        self.resolver_b.resolver_profile.save(update_fields=["skill_set"])

        new_ticket = self._ticket(assigned_to=None, assigned_at=None, metric_name="memory.usage")
        decision = AssignmentService.assign(new_ticket)

        self.assertIsNotNone(new_ticket.assigned_to)
        self.assertEqual(decision.strategy, "purpose_fallback")

    def test_duplicate_merge_does_not_change_existing_assignment(self):
        ticket = TicketService.create_ticket(
            agent_id="agent-1",
            metric_name="cpu.utilization",
            severity="P2",
            detector="z",
            meta="{}",
            message="first",
        )["ticket"]
        # Force an assignment change to a specific resolver
        ticket.assigned_to = self.resolver_a
        ticket.assignment_strategy = "manual"
        ticket.auto_assigned = False
        ticket.assigned_at = self.now
        ticket.save(update_fields=["assigned_to", "assignment_strategy", "auto_assigned", "assigned_at"])

        result = TicketService.create_ticket(
            agent_id="agent-1",
            metric_name="cpu.utilization",
            severity="P2",
            detector="z",
            meta="{}",
            message="duplicate",
        )

        merged = result["ticket"]
        self.assertFalse(result["created"])
        self.assertEqual(merged.assigned_to, self.resolver_a)
        self.assertEqual(merged.assignment_strategy, "manual")
