"""
attachments/views.py
--------------------
Simple image upload endpoint. Stores the file under MEDIA_ROOT/attachments and
returns a JSON blob that can be dropped straight into the existing
`attachments` array used by comments and guidance records.

Future-friendly: accepts only images for now, but the shape matches the
Attachment model so other kinds can be enabled later.
"""

import uuid
from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from auth_core.decorators import require_auth


_ALLOWED_MIME_PREFIX = "image/"
_SUBDIR = "attachments"


@csrf_exempt
@require_auth
@require_http_methods(["POST"])
def upload(request):
    """
    POST /api/attachments/upload/
    Form-data (multipart):
      - file: image file (required)

    Response 201:
    {
      "attachment": {
        "url": "<media url>",
        "mime_type": "image/png",
        "file_name": "example.png",
        "size_bytes": 12345,
        "kind": "image"
      }
    }
    """
    uploaded = request.FILES.get("file")
    if not uploaded:
        return JsonResponse({"error": "'file' is required (multipart/form-data)"}, status=400)

    mime_type = uploaded.content_type or ""
    if not mime_type.startswith(_ALLOWED_MIME_PREFIX):
        return JsonResponse(
            {"error": "Only image uploads are allowed", "mime_type": mime_type or None},
            status=400,
        )

    # Store under MEDIA_ROOT/attachments/<uuid>.<ext>
    storage = FileSystemStorage(
        location=Path(settings.MEDIA_ROOT) / _SUBDIR,
        base_url=f"{settings.MEDIA_URL}{_SUBDIR}/",
    )
    ext = Path(uploaded.name).suffix.lower()
    safe_name = f"{uuid.uuid4().hex}{ext}"
    saved_name = storage.save(safe_name, uploaded)

    url = storage.url(saved_name)
    payload = {
        "url": url,
        "mime_type": mime_type,
        "file_name": uploaded.name,
        "size_bytes": uploaded.size,
        "kind": "image",
    }
    return JsonResponse({"attachment": payload}, status=201)
