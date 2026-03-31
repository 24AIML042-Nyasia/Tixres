"""
attachments/models.py
---------------------
Reusable attachment model using a generic relation so any object can own
attachments.  For now we only accept image attachments at the API layer,
but `kind` and `metadata` are flexible for future asset types.
"""

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models


class AttachmentKind(models.TextChoices):
    IMAGE = "image", "Image"
    FILE = "file", "File"
    LINK = "link", "Link"


class Attachment(models.Model):
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id    = models.PositiveIntegerField(db_index=True)
    content_object = GenericForeignKey("content_type", "object_id")

    kind       = models.CharField(max_length=20, choices=AttachmentKind.choices, default=AttachmentKind.IMAGE, db_index=True)
    url        = models.TextField(help_text="Absolute or data URL pointing to the asset")
    file_name  = models.CharField(max_length=255, blank=True, null=True)
    mime_type  = models.CharField(max_length=100, default="image/png")
    size_bytes = models.PositiveIntegerField(null=True, blank=True)
    metadata   = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "attachments"
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
            models.Index(fields=["kind"]),
        ]

    def __repr__(self) -> str:
        return f"<Attachment id={self.pk} kind={self.kind} object={self.content_type_id}:{self.object_id}>"
