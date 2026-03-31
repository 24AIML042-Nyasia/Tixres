"""
agents/models.py
----------------
Lightweight Django models for Agents and Purposes.

These are populated via API calls from the upstream server — this service
does not own agent registration or credentials.
"""

from django.db import models


class Purpose(models.Model):
    purpose = models.CharField(max_length=255, unique=True, default="general")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "purposes"

    def __str__(self):
        return self.purpose


class Agent(models.Model):
    # agent_id is the primary key (string, assigned by upstream)
    agent_id = models.CharField(max_length=255, primary_key=True)
    agent_version = models.CharField(max_length=50)
    hostname = models.CharField(max_length=255)
    os = models.CharField(max_length=100)
    fingerprint = models.CharField(max_length=255, null=True, blank=True)
    heartbeat = models.DateTimeField(null=True, blank=True)
    purpose = models.ForeignKey(
        Purpose,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="agents",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "agents"

    def __str__(self):
        return self.agent_id

    @property
    def purpose_name(self) -> str:
        """Return the agent's purpose string, or 'general' as fallback."""
        if self.purpose_id and self.purpose:
            return self.purpose.purpose
        return "general"
