"""
workflows/models.py
-------------------
WorkflowStatus — defines the permitted lifecycle statuses for tickets and
alerts on a per-purpose (i.e. per-team) basis.

Design goals
------------
* No status value is hardcoded anywhere in the application code.
  Services query this table at runtime to learn what statuses exist,
  which one is the default, and which ones are terminal / auto-resolvable.

* Scoping: a `WorkflowStatus` with purpose=None acts as the global default
  and applies to all purposes that haven't defined their own statuses.
  A purpose-specific status overrides the global default entirely for that
  purpose.

* applies_to: a status can apply to tickets, alerts, or both.

Semantic flags
--------------
is_initial        — the status a new ticket/alert is created with.
                    Exactly one per (purpose, applies_to) scope should be
                    initial=True.  WorkflowService enforces this.
is_terminal       — no further transitions are expected after this.
                    ResolutionService and TicketService treat these as "closed".
is_auto_resolvable — ResolutionService may move a ticket/alert into a terminal
                    status automatically when the SLA window expires.
                    Only meaningful on terminal statuses.

Default data
------------
A data migration (0002_seed_default_statuses) seeds the global defaults:
  OPEN → ACK → CLOSED
These can be modified or supplemented per-purpose via the admin API.
"""

from django.db import models


class AppliesTo(models.TextChoices):
    TICKET = "ticket", "Ticket"
    ALERT  = "alert",  "Alert"
    BOTH   = "both",   "Both"


class WorkflowStatus(models.Model):
    """
    One row = one permitted status value for one scope (purpose + applies_to).

    The `key` is the value stored in Ticket.status / Alert.status.
    """

    # Scope ─────────────────────────────────────────────────────────────
    # purpose=None  → global default (all purposes)
    # purpose="ops" → overrides global, only applied to the "ops" purpose
    purpose    = models.CharField(
        max_length = 255,
        null       = True,
        blank      = True,
        db_index   = True,
        help_text  = "Scope to a specific purpose/team. NULL = global default.",
    )
    applies_to = models.CharField(
        max_length = 10,
        choices    = AppliesTo.choices,
        default    = AppliesTo.BOTH,
        db_index   = True,
    )

    # Identity ───────────────────────────────────────────────────────────
    key   = models.CharField(max_length=50, help_text="Value stored in the status field, e.g. 'OPEN'")
    label = models.CharField(max_length=100, help_text="Human-readable display name, e.g. 'Open'")
    color = models.CharField(
        max_length = 20,
        blank      = True,
        default    = "",
        help_text  = "Optional UI hint e.g. '#22c55e' or 'green'",
    )

    # Semantic flags ─────────────────────────────────────────────────────
    is_initial         = models.BooleanField(
        default   = False,
        help_text = "Status assigned when a ticket/alert is first created.",
    )
    is_terminal        = models.BooleanField(
        default   = False,
        help_text = "No further transitions expected. Treated as 'closed'.",
    )
    is_auto_resolvable = models.BooleanField(
        default   = False,
        help_text = "ResolutionService may auto-close items in this status.",
    )

    # Display ────────────────────────────────────────────────────────────
    order = models.IntegerField(
        default  = 0,
        help_text = "Display ordering within the same scope.",
    )

    class Meta:
        db_table = "workflow_statuses"
        # One key per (purpose, applies_to) scope
        constraints = [
            models.UniqueConstraint(
                fields = ["purpose", "key", "applies_to"],
                name   = "uq_workflow_status_scope",
            )
        ]
        ordering = ["purpose", "applies_to", "order", "key"]

    def __str__(self):
        scope = f"purpose={self.purpose or '*'}, applies_to={self.applies_to}"
        return f"<WorkflowStatus key={self.key!r} [{scope}]>"
