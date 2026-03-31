"""
guidance/services.py
--------------------
GuidanceService — CRUD for runbook guidance records.

Natural key: (metric_name, priority, purpose).
Upsert is the primary write path; the key is immutable after creation.
"""

from __future__ import annotations

from typing import Optional

from attachments.services import AttachmentService
from guidance.models import Guidance, Priority


class GuidanceNotFoundError(Exception):
    def __init__(self, identifier: str):
        super().__init__(f"Guidance record not found: {identifier}")


class GuidanceService:

    # ------------------------------------------------------------------ #
    #  Upsert  — the primary write path                                   #
    # ------------------------------------------------------------------ #

    @staticmethod
    def upsert(payload: dict) -> tuple[Guidance, bool]:
        """
        Create or update the guidance record for (metric_name, priority, purpose).

        Returns (Guidance, created: bool).
        created=True  → new record was inserted.
        created=False → existing record was updated.

        The natural key (metric_name, priority, purpose) is immutable once created;
        only resolution_steps, resolver_notes, and resolution_meta are written on update.
        """
        metric_name      = payload["metric_name"]
        priority         = payload.get("priority", Priority.P4)
        purpose          = payload.get("purpose", "general")
        resolution_steps = payload.get("resolution_steps", [])
        resolver_notes   = payload.get("resolver_notes")
        resolution_meta  = payload.get("resolution_meta") or {}

        obj, created = Guidance.objects.get_or_create(
            metric_name = metric_name,
            priority    = priority,
            purpose     = purpose,
            defaults={
                "resolution_steps": resolution_steps,
                "resolver_notes":   resolver_notes,
                "resolution_meta":  resolution_meta,
            },
        )

        if not created:
            # Update mutable fields
            obj.resolution_steps = resolution_steps
            obj.resolver_notes   = resolver_notes
            obj.resolution_meta  = resolution_meta
            obj.save(update_fields=["resolution_steps", "resolver_notes", "resolution_meta", "last_updated"])

        return obj, created

    # ------------------------------------------------------------------ #
    #  Read                                                               #
    # ------------------------------------------------------------------ #

    @staticmethod
    def get_by_id(guidance_id: int) -> Guidance:
        try:
            return Guidance.objects.prefetch_related("attachments").get(pk=guidance_id)
        except Guidance.DoesNotExist:
            raise GuidanceNotFoundError(f"id={guidance_id}")

    @staticmethod
    def get_by_natural_key(
        metric_name: str,
        priority: str,
        purpose: str = "general",
    ) -> Guidance:
        try:
            return Guidance.objects.prefetch_related("attachments").get(
                metric_name = metric_name,
                priority    = priority,
                purpose     = purpose,
            )
        except Guidance.DoesNotExist:
            raise GuidanceNotFoundError(
                f"metric='{metric_name}', priority='{priority}', purpose='{purpose}'"
            )

    @staticmethod
    def list(
        *,
        skip: int = 0,
        limit: int = 20,
        priority: Optional[str] = None,
        metric_name: Optional[str] = None,
        purpose: Optional[str] = None,
    ) -> tuple[int, list[Guidance]]:
        """Paginated list with optional filters. Returns (total, records)."""
        qs = Guidance.objects.all().prefetch_related("attachments")

        if priority:
            qs = qs.filter(priority=priority)
        if metric_name:
            qs = qs.filter(metric_name__icontains=metric_name)
        if purpose:
            qs = qs.filter(purpose=purpose)

        total = qs.count()
        records = list(qs.order_by("-last_updated")[skip : skip + limit])
        return total, records

    # ------------------------------------------------------------------ #
    #  Update  — patch mutable fields only                                #
    # ------------------------------------------------------------------ #

    @staticmethod
    def update_by_id(guidance_id: int, payload: dict) -> Guidance:
        """
        Patch resolution_steps / resolver_notes / resolution_meta by primary key.
        Only fields explicitly set in the payload are applied (PATCH semantics).
        """
        try:
            obj = Guidance.objects.prefetch_related("attachments").get(pk=guidance_id)
        except Guidance.DoesNotExist:
            raise GuidanceNotFoundError(f"id={guidance_id}")

        mutable = ["resolution_steps", "resolver_notes", "resolution_meta"]
        updated_fields = []
        for field in mutable:
            if field in payload and payload[field] is not None:
                setattr(obj, field, payload[field])
                updated_fields.append(field)

        if updated_fields:
            updated_fields.append("last_updated")
            obj.save(update_fields=updated_fields)

        return obj

    # ------------------------------------------------------------------ #
    #  Delete                                                             #
    # ------------------------------------------------------------------ #

    @staticmethod
    def delete_by_id(guidance_id: int) -> dict:
        try:
            obj = Guidance.objects.get(pk=guidance_id)
        except Guidance.DoesNotExist:
            raise GuidanceNotFoundError(f"id={guidance_id}")
        AttachmentService.purge_for_object(obj)
        obj.delete()
        return {"deleted": True, "id": guidance_id}

    # ------------------------------------------------------------------ #
    #  Helpers / aggregates                                               #
    # ------------------------------------------------------------------ #

    @staticmethod
    def get_resolution_steps(
        metric_name: str, priority: str, purpose: str = "general"
    ) -> list[dict]:
        """Return only the resolution_steps for a natural key (lightweight triage lookup)."""
        obj = GuidanceService.get_by_natural_key(metric_name, priority, purpose)
        return obj.resolution_steps or []

    @staticmethod
    def summarize_by_priority() -> dict[str, int]:
        """Count of guidance records per priority level. e.g. {"P1": 3, "P2": 7, ...}"""
        summary = {p.value: 0 for p in Priority}
        for obj in Guidance.objects.only("priority"):
            if obj.priority in summary:
                summary[obj.priority] += 1
        return summary
