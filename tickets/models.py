"""
tickets/models.py
-----------------
Django model for Ticket.

A Ticket is an agent-level issue record created by anomaly detectors.
Tickets deduplicate noisy events and feed Alerts.
"""

from django.db import models

TICKET_STATUS_OPEN   = "OPEN"
TICKET_STATUS_ACK    = "ACK"
TICKET_STATUS_CLOSED = "CLOSED"

_STATUS_CHOICES = [
    (TICKET_STATUS_OPEN,   "Open"),
    (TICKET_STATUS_ACK,    "Acknowledged"),
    (TICKET_STATUS_CLOSED, "Closed"),
]

_SEVERITY_CHOICES = [
    ("P1", "P1"),
    ("P2", "P2"),
    ("P3", "P3"),
    ("P4", "P4"),
]


class Ticket(models.Model):
    agent_id         = models.CharField(max_length=255, db_index=True)
    metric_name      = models.CharField(max_length=255, db_index=True)
    severity         = models.CharField(max_length=10, choices=_SEVERITY_CHOICES)
    purpose          = models.CharField(max_length=255, default="general", db_index=True)
    status           = models.CharField(max_length=20, choices=_STATUS_CHOICES, default=TICKET_STATUS_OPEN)

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

    class Meta:
        db_table = "tickets"
        ordering = ["-last_occurred_at"]

    def __str__(self):
        return f"<Ticket id={self.pk} agent={self.agent_id} metric={self.metric_name} sev={self.severity}>"
