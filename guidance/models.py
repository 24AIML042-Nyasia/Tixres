"""
guidance/models.py
------------------
Django model for Guidance (runbook records).

Natural key: (metric_name, priority, purpose).
"""

from django.db import models


class Priority(models.TextChoices):
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"


class Guidance(models.Model):
    metric_name      = models.CharField(max_length=255, db_index=True)
    purpose          = models.CharField(max_length=100, default="general", db_index=True)
    priority         = models.CharField(max_length=5, choices=Priority.choices, default=Priority.P4, db_index=True)

    # [{\"step\": 1, \"action\": \"...\"}]
    resolution_steps = models.JSONField(default=list)

    resolver_notes   = models.TextField(null=True, blank=True)

    # {\"tags\": [], \"sla_minutes\": 60}
    resolution_meta  = models.JSONField(null=True, blank=True, default=dict)

    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "guidance"
        constraints = [
            models.UniqueConstraint(
                fields=["metric_name", "priority", "purpose"],
                name="uq_guidance_metric_priority_purpose",
            )
        ]

    def __repr__(self):
        return (
            f"<Guidance id={self.pk} metric='{self.metric_name}' "
            f"priority='{self.priority}' purpose='{self.purpose}'>"
        )
