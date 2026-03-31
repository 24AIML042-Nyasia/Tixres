"""
alerts/models.py
----------------
Django model for Alert.

An Alert represents a correlated, deduplicated view of one or more Tickets
sharing the same (metric_name, severity, purpose) key.
"""

from django.db import models

ALERT_STATUS_OPEN   = "OPEN"
ALERT_STATUS_ACK    = "ACK"
ALERT_STATUS_CLOSED = "CLOSED"

_STATUS_CHOICES = [
    (ALERT_STATUS_OPEN,   "Open"),
    (ALERT_STATUS_ACK,    "Acknowledged"),
    (ALERT_STATUS_CLOSED, "Closed"),
]

_TYPE_CHOICES = [
    ("SINGLE", "Single"),
    ("GROUP",  "Group"),
]

_SEVERITY_CHOICES = [
    ("P1", "P1"),
    ("P2", "P2"),
    ("P3", "P3"),
    ("P4", "P4"),
]


class Alert(models.Model):
    # --- Identity key: (metric_name, severity, purpose) ---
    metric_name = models.CharField(max_length=255, db_index=True)
    severity    = models.CharField(max_length=10,  choices=_SEVERITY_CHOICES, db_index=True)
    purpose     = models.CharField(max_length=255, default="general", db_index=True)

    # --- Classification ---
    # SINGLE → only one agent has fired this alert
    # GROUP  → two or more agents have fired it (escalated)
    type   = models.CharField(max_length=10, choices=_TYPE_CHOICES,   default="SINGLE")
    status = models.CharField(max_length=10, choices=_STATUS_CHOICES, default=ALERT_STATUS_OPEN)

    # JSON-encoded list of agent_ids that contributed, e.g. '["agent_1","agent_2"]'
    agent_ids = models.TextField(default="[]")

    # Running total of occurrences across all contributing tickets
    total_occurrence = models.IntegerField(default=0)

    # Timestamps
    first_seen_at  = models.DateTimeField(null=True, blank=True)
    last_seen_at   = models.DateTimeField(null=True, blank=True)

    # When the notification cooldown expires
    cooldown_until = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    closed_at  = models.DateTimeField(null=True, blank=True)

    # ACK tracking
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    acknowledged_by = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = "alerts"
        # One OPEN alert per (metric_name, severity, purpose, status)
        constraints = [
            models.UniqueConstraint(
                fields=["metric_name", "severity", "purpose", "status"],
                name="uq_alert_metric_severity_purpose_status",
            )
        ]
        ordering = ["-last_seen_at"]

    def __str__(self):
        return f"<Alert id={self.pk} metric={self.metric_name} sev={self.severity} status={self.status}>"
