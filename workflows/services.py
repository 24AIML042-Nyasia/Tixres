"""
workflows/services.py
---------------------
WorkflowService — runtime queries over WorkflowStatus rows.

Lookup order for a given (purpose, applies_to) query:
  1. Rows where purpose = the given purpose  (team/purpose-specific)
  2. Fall back to rows where purpose IS NULL (global defaults)
This gives teams full control while keeping a working global default.

All methods that return status keys return plain strings so callers
don't need to import the model.
"""

from __future__ import annotations

from functools import lru_cache

from workflows.models import WorkflowStatus, AppliesTo


class WorkflowService:

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _statuses_for(purpose: str | None, applies_to: str) -> list[WorkflowStatus]:
        """
        Return WorkflowStatus rows for (purpose, applies_to), falling back to
        global (purpose=None) if no purpose-specific rows exist.

        applies_to filter matches the specific value OR "both".
        """
        qs = WorkflowStatus.objects.filter(
            applies_to__in=[applies_to, AppliesTo.BOTH],
        )

        if purpose:
            specific = list(qs.filter(purpose=purpose).order_by("order", "key"))
            if specific:
                return specific
        # global defaults
        return list(qs.filter(purpose__isnull=True).order_by("order", "key"))

    # ------------------------------------------------------------------
    # Choices helpers (for display / validation)
    # ------------------------------------------------------------------

    @staticmethod
    def get_ticket_status_choices(purpose: str | None = None) -> list[tuple[str, str]]:
        rows = WorkflowService._statuses_for(purpose, AppliesTo.TICKET)
        return [(r.key, r.label) for r in rows]

    @staticmethod
    def get_alert_status_choices(purpose: str | None = None) -> list[tuple[str, str]]:
        rows = WorkflowService._statuses_for(purpose, AppliesTo.ALERT)
        return [(r.key, r.label) for r in rows]

    @staticmethod
    def get_all_status_keys(purpose: str | None = None, applies_to: str = AppliesTo.BOTH) -> list[str]:
        rows = WorkflowService._statuses_for(purpose, applies_to)
        return [r.key for r in rows]

    # ------------------------------------------------------------------
    # Semantic lookups
    # ------------------------------------------------------------------

    @staticmethod
    def get_initial_status(purpose: str | None = None, applies_to: str = AppliesTo.TICKET) -> str:
        """
        Return the key of the initial status for this scope.
        Falls back to the first status in order if none is flagged is_initial=True.
        """
        rows = WorkflowService._statuses_for(purpose, applies_to)
        for r in rows:
            if r.is_initial:
                return r.key
        # Fallback – use first in order
        if rows:
            return rows[0].key
        # Last-resort hardcoded safety net (should never be reached if seeded)
        return "OPEN"

    @staticmethod
    def get_terminal_statuses(purpose: str | None = None, applies_to: str = AppliesTo.TICKET) -> list[str]:
        """Return keys of all terminal statuses (i.e. 'closed' states)."""
        rows = WorkflowService._statuses_for(purpose, applies_to)
        return [r.key for r in rows if r.is_terminal]

    @staticmethod
    def get_auto_resolvable_statuses(purpose: str | None = None, applies_to: str = AppliesTo.TICKET) -> list[str]:
        """
        Return status keys that ResolutionService may auto-close items into.
        Typically the non-initial, non-terminal states (e.g. OPEN, ACK) where
        the SLA window has expired.
        """
        rows = WorkflowService._statuses_for(purpose, applies_to)
        return [r.key for r in rows if r.is_auto_resolvable]

    @staticmethod
    def is_terminal(status_key: str, purpose: str | None = None, applies_to: str = AppliesTo.TICKET) -> bool:
        rows = WorkflowService._statuses_for(purpose, applies_to)
        return any(r.key == status_key and r.is_terminal for r in rows)

    @staticmethod
    def is_valid_status(status_key: str, purpose: str | None = None, applies_to: str = AppliesTo.TICKET) -> bool:
        rows = WorkflowService._statuses_for(purpose, applies_to)
        return any(r.key == status_key for r in rows)

    # ------------------------------------------------------------------
    # Admin writes
    # ------------------------------------------------------------------

    @staticmethod
    def upsert_status(
        key: str,
        label: str,
        *,
        purpose: str | None = None,
        applies_to: str = AppliesTo.BOTH,
        color: str = "",
        is_initial: bool = False,
        is_terminal: bool = False,
        is_auto_resolvable: bool = False,
        order: int = 0,
    ) -> tuple[WorkflowStatus, bool]:
        """
        Create or update a WorkflowStatus.  Returns (obj, created).
        If is_initial=True, clears is_initial on all other rows in the same scope.
        """
        obj, created = WorkflowStatus.objects.update_or_create(
            key        = key,
            purpose    = purpose,
            applies_to = applies_to,
            defaults   = {
                "label":             label,
                "color":             color,
                "is_initial":        is_initial,
                "is_terminal":       is_terminal,
                "is_auto_resolvable": is_auto_resolvable,
                "order":             order,
            },
        )

        # Enforce: only one initial per scope
        if is_initial:
            WorkflowStatus.objects.filter(
                purpose    = purpose,
                applies_to = applies_to,
                is_initial = True,
            ).exclude(pk=obj.pk).update(is_initial=False)

        return obj, created

    @staticmethod
    def delete_status(key: str, purpose: str | None = None, applies_to: str = AppliesTo.BOTH) -> bool:
        """Delete a WorkflowStatus. Returns True if a row was deleted."""
        deleted, _ = WorkflowStatus.objects.filter(
            key=key, purpose=purpose, applies_to=applies_to
        ).delete()
        return bool(deleted)
