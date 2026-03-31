"""
tickets/models.py
-----------------
Django model for Ticket and TicketComment.

A Ticket is an agent-level issue record created by anomaly detectors.
Tickets deduplicate noisy events and feed Alerts.

Status values are NOT hardcoded here.  They are DB rows in the
WorkflowStatus table (workflows app), scoped per purpose/team.
WorkflowService provides all runtime lookups.

The constants below are default fallbacks used only when no WorkflowStatus
rows exist yet (e.g. during test setup before migrations have run).
"""

from attachments.fields import SafeGenericRelation
from django.db import models

# Fallback defaults — real values come from WorkflowStatus rows.
TICKET_STATUS_OPEN   = "OPEN"
TICKET_STATUS_ACK    = "ACK"
TICKET_STATUS_CLOSED = "CLOSED"


class Ticket(models.Model):
    agent_id         = models.CharField(max_length=255, db_index=True)
    metric_name      = models.CharField(max_length=255, db_index=True)
    severity         = models.CharField(max_length=50)
    purpose          = models.CharField(max_length=255, default="general", db_index=True)
    status           = models.CharField(max_length=50, default=TICKET_STATUS_OPEN)

    # JSON string — list of detector names e.g. '["zscore"]'
    detectors        = models.TextField(default="[]")

    meta             = models.TextField(blank=True, default="{}")
    message          = models.TextField(blank=True, default="")

    occurrence_count = models.IntegerField(default=1)

    first_occurred_at = models.DateTimeField()
    last_occurred_at  = models.DateTimeField()
    created_at        = models.DateTimeField(auto_now_add=True)

    # ACK metadata — populated when a resolver acknowledges the ticket
    acknowledged_at  = models.DateTimeField(null=True, blank=True)
    acknowledged_by  = models.CharField(max_length=255, null=True, blank=True)

    # Auto-assignment metadata
    assigned_to          = models.ForeignKey(
        "auth_core.SSOUser",
        null         = True,
        blank        = True,
        on_delete    = models.SET_NULL,
        related_name = "assigned_tickets",
        db_index     = True,
    )
    assigned_at          = models.DateTimeField(null=True, blank=True)
    assignment_strategy  = models.CharField(max_length=50, blank=True, default="")
    assignment_reason    = models.TextField(blank=True, default="")
    auto_assigned        = models.BooleanField(default=False)

    class Meta:
        db_table = "tickets"
        ordering = ["-last_occurred_at"]

    def __str__(self):
        return f"<Ticket id={self.pk} agent={self.agent_id} metric={self.metric_name} sev={self.severity}>"


# ---------------------------------------------------------------------------
# TicketComment
# ---------------------------------------------------------------------------

COMMENT_VISIBILITY_EXTERNAL = "external"
COMMENT_VISIBILITY_INTERNAL = "internal"

_VISIBILITY_CHOICES = [
    (COMMENT_VISIBILITY_EXTERNAL, "External"),   # visible to all roles
    (COMMENT_VISIBILITY_INTERNAL, "Internal"),   # resolver + admin only
]


class TicketComment(models.Model):
    """
    A comment attached to a Ticket.

    Visibility
    ----------
    external — visible to all authenticated users (the primary channel for
               end-users to communicate with the resolver team).
    internal — resolver + admin only (back-channel notes, investigation logs).

    Soft-delete
    -----------
    Calling delete() sets is_deleted=True and blanks content.  The row is kept
    for audit.  Admin can soft-delete any comment; authors can delete their own.
    """

    ticket = models.ForeignKey(
        Ticket,
        on_delete    = models.CASCADE,
        related_name = "comments",
        db_index     = True,
    )
    # Nullable so the row survives if the author account is removed
    author = models.ForeignKey(
        "auth_core.SSOUser",
        on_delete    = models.SET_NULL,
        null         = True,
        blank        = True,
        related_name = "ticket_comments",
    )
    attachments = SafeGenericRelation(
        "attachments.Attachment",
        related_query_name="ticket_comment",
    )
    content    = models.TextField()
    visibility = models.CharField(
        max_length = 10,
        choices    = _VISIBILITY_CHOICES,
        default    = COMMENT_VISIBILITY_EXTERNAL,
        db_index   = True,
    )
    is_deleted = models.BooleanField(default=False, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "ticket_comments"
        ordering = ["created_at"]

    def __str__(self):
        return (
            f"<TicketComment id={self.pk} ticket={self.ticket_id} "
            f"vis={self.visibility} deleted={self.is_deleted}>"
        )
