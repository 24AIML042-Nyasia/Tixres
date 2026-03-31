"""
attachments/services.py
-----------------------
Helpers to validate, persist, and serialize attachments.

API layer currently restricts attachments to images, but `kind` + `metadata`
are intentionally general so new asset types can be allowed later.
"""

from __future__ import annotations

from typing import Iterable, Sequence

from django.contrib.contenttypes.models import ContentType
from django.db import transaction

from attachments.models import Attachment, AttachmentKind


class AttachmentValidationError(ValueError):
    pass


class AttachmentService:
    @staticmethod
    def serialize(attachment: Attachment) -> dict:
        return {
            "id":         attachment.pk,
            "kind":       attachment.kind,
            "url":        attachment.url,
            "file_name":  attachment.file_name,
            "mime_type":  attachment.mime_type,
            "size_bytes": attachment.size_bytes,
            "metadata":   attachment.metadata or {},
            "created_at": attachment.created_at.isoformat(),
        }

    @staticmethod
    def serialize_many(attachments: Sequence[Attachment]) -> list[dict]:
        return [AttachmentService.serialize(att) for att in attachments]

    @staticmethod
    def sync_for_object(obj, payload, *, allowed_kinds: Iterable[str | AttachmentKind] | None = None) -> list[Attachment]:
        """
        Replace the attachments on `obj` with the provided payload.

        payload:
          - None            â†’ leave attachments untouched
          - [] (empty list) â†’ clear all attachments
          - list[dict]      â†’ create attachments from items

        Returns the resulting attachment list (post-sync).
        Raises AttachmentValidationError for bad payloads.
        """
        if payload is None:
            return list(getattr(obj, "attachments").all()) if hasattr(obj, "attachments") else []

        if not isinstance(payload, list):
            raise AttachmentValidationError("attachments must be a list")

        if not getattr(obj, "pk", None):
            raise AttachmentValidationError("object must be saved before adding attachments")

        allowed = AttachmentService._normalize_allowed_kinds(allowed_kinds)
        content_type = ContentType.objects.get_for_model(obj.__class__)

        with transaction.atomic():
            Attachment.objects.filter(content_type=content_type, object_id=obj.pk).delete()
            created: list[Attachment] = []
            for idx, item in enumerate(payload):
                if not isinstance(item, dict):
                    raise AttachmentValidationError(f"attachments[{idx}] must be an object")

                kind = item.get("kind") or item.get("type") or AttachmentKind.IMAGE
                if kind not in allowed:
                    allowed_list = ", ".join(sorted(allowed))
                    raise AttachmentValidationError(
                        f"attachments[{idx}].kind must be one of: {allowed_list}"
                    )

                url = (item.get("url") or "").strip()
                if not url:
                    raise AttachmentValidationError(f"attachments[{idx}].url is required")

                mime_type = (item.get("mime_type") or "").strip() or AttachmentService._default_mime(kind)
                if kind == AttachmentKind.IMAGE and not mime_type.startswith("image/"):
                    raise AttachmentValidationError(
                        f"attachments[{idx}].mime_type must start with 'image/'"
                    )

                file_name  = (item.get("file_name") or "").strip() or None
                size_bytes = item.get("size_bytes")
                metadata   = item.get("metadata") or {}
                if metadata is None:
                    metadata = {}

                if size_bytes is not None and not isinstance(size_bytes, int):
                    raise AttachmentValidationError(
                        f"attachments[{idx}].size_bytes must be an integer when provided"
                    )
                if size_bytes is not None and size_bytes < 0:
                    raise AttachmentValidationError(
                        f"attachments[{idx}].size_bytes cannot be negative"
                    )
                if not isinstance(metadata, dict):
                    raise AttachmentValidationError(
                        f"attachments[{idx}].metadata must be an object when provided"
                    )

                created.append(
                    Attachment.objects.create(
                        content_type = content_type,
                        object_id    = obj.pk,
                        kind         = kind,
                        url          = url,
                        file_name    = file_name,
                        mime_type    = mime_type,
                        size_bytes   = size_bytes,
                        metadata     = metadata,
                    )
                )

        return created

    @staticmethod
    def purge_for_object(obj) -> None:
        if not getattr(obj, "pk", None):
            return
        content_type = ContentType.objects.get_for_model(obj.__class__)
        Attachment.objects.filter(content_type=content_type, object_id=obj.pk).delete()

    @staticmethod
    def _normalize_allowed_kinds(allowed: Iterable[str | AttachmentKind] | None) -> set[str]:
        if not allowed:
            return {AttachmentKind.IMAGE}
        normalized = set()
        for kind in allowed:
            normalized.add(kind.value if isinstance(kind, AttachmentKind) else str(kind))
        return normalized

    @staticmethod
    def _default_mime(kind: str) -> str:
        return "image/png" if kind == AttachmentKind.IMAGE else "application/octet-stream"
