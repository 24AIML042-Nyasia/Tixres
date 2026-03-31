"""
tickets/comment_views.py
------------------------
JSON API views for TicketComment CRUD.

Visibility enforcement
----------------------
* GET  — end_user sees only `external` comments.
          resolver + admin see both.
* POST — end_user may only post `external` comments; attempt to post
          `internal` is silently coerced to `external`.
          resolver + admin may post either.
* PATCH — authors may edit their own non-deleted comment (content + attachments).
          Visibility cannot be changed after creation.
* DELETE — soft-delete: is_deleted=True, content blanked.
           Authors can delete their own; admin can delete any.
"""

import json

from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from attachments.models import AttachmentKind
from attachments.services import AttachmentService, AttachmentValidationError
from auth_core.decorators import require_auth
from auth_core.models import Role
from tickets.models import (
    Ticket,
    TicketComment,
    COMMENT_VISIBILITY_EXTERNAL,
    COMMENT_VISIBILITY_INTERNAL,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _json_body(request):
    try:
        return json.loads(request.body), None
    except (json.JSONDecodeError, TypeError):
        return {}, JsonResponse({"error": "Invalid JSON body"}, status=400)


def _serialize(comment: TicketComment) -> dict:
    return {
        "id":          comment.pk,
        "ticket_id":   comment.ticket_id,
        "author_id":   comment.author_id,
        "author_name": comment.author.name if comment.author else None,
        "content":     comment.content,
        "visibility":  comment.visibility,
        "is_deleted":  comment.is_deleted,
        "created_at":  comment.created_at.isoformat(),
        "updated_at":  comment.updated_at.isoformat(),
        "attachments": AttachmentService.serialize_many(getattr(comment, "attachments").all()),
    }


def _can_see_internal(user) -> bool:
    return user.role in (Role.RESOLVER, Role.ADMIN)


# ---------------------------------------------------------------------------
# GET + POST  /api/tickets/<ticket_id>/comments/
# ---------------------------------------------------------------------------

@csrf_exempt
@require_auth
@require_http_methods(["GET", "POST"])
def comment_list_create(request, ticket_id: int):
    # Verify ticket exists
    try:
        ticket = Ticket.objects.get(pk=ticket_id)
    except Ticket.DoesNotExist:
        return JsonResponse({"error": f"Ticket {ticket_id} not found"}, status=404)

    user = request.sso_user

    if request.method == "GET":
        qs = ticket.comments.filter(is_deleted=False)
        if not _can_see_internal(user):
            qs = qs.filter(visibility=COMMENT_VISIBILITY_EXTERNAL)
        comments = list(qs.select_related("author").prefetch_related("attachments").order_by("created_at"))
        return JsonResponse({
            "ticket_id": ticket_id,
            "count":     len(comments),
            "comments":  [_serialize(c) for c in comments],
        })

    # POST — create a comment
    data, err = _json_body(request)
    if err:
        return err

    attachments_payload = data.get("attachments", None)
    content = (data.get("content") or "").strip()
    if not content:
        return JsonResponse({"error": "'content' is required"}, status=400)

    requested_visibility = data.get("visibility", COMMENT_VISIBILITY_EXTERNAL)

    # end_user cannot post internal comments — coerce silently
    if not _can_see_internal(user):
        visibility = COMMENT_VISIBILITY_EXTERNAL
    elif requested_visibility == COMMENT_VISIBILITY_INTERNAL:
        visibility = COMMENT_VISIBILITY_INTERNAL
    else:
        visibility = COMMENT_VISIBILITY_EXTERNAL

    try:
        with transaction.atomic():
            comment = TicketComment.objects.create(
                ticket     = ticket,
                author     = user,
                content    = content,
                visibility = visibility,
            )
            if attachments_payload is not None:
                AttachmentService.sync_for_object(
                    comment,
                    attachments_payload,
                    allowed_kinds=[AttachmentKind.IMAGE],
                )
    except AttachmentValidationError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    return JsonResponse(_serialize(comment), status=201)


# ---------------------------------------------------------------------------
# PATCH + DELETE  /api/tickets/<ticket_id>/comments/<comment_id>/
# ---------------------------------------------------------------------------

@csrf_exempt
@require_auth
@require_http_methods(["PATCH", "DELETE"])
def comment_detail(request, ticket_id: int, comment_id: int):
    try:
        comment = TicketComment.objects.select_related("author").prefetch_related("attachments").get(
            pk=comment_id, ticket_id=ticket_id
        )
    except TicketComment.DoesNotExist:
        return JsonResponse({"error": "Comment not found"}, status=404)

    if comment.is_deleted:
        return JsonResponse({"error": "Comment has been deleted"}, status=410)

    user = request.sso_user

    if request.method == "PATCH":
        # Only the author can edit their own comment
        if comment.author_id != user.user_id:
            return JsonResponse({"error": "You can only edit your own comments"}, status=403)

        data, err = _json_body(request)
        if err:
            return err

        attachments_supplied = "attachments" in data
        attachments_payload  = data.get("attachments")

        content_supplied = "content" in data
        if content_supplied:
            content = (data.get("content") or "").strip()
            if not content:
                return JsonResponse({"error": "'content' is required"}, status=400)
        elif not attachments_supplied:
            return JsonResponse({"error": "No updatable fields provided"}, status=400)

        try:
            with transaction.atomic():
                if content_supplied:
                    comment.content = content
                if content_supplied or attachments_supplied:
                    fields = ["updated_at"]
                    if content_supplied:
                        fields.insert(0, "content")
                    comment.save(update_fields=fields)
                if attachments_supplied:
                    AttachmentService.sync_for_object(
                        comment,
                        attachments_payload,
                        allowed_kinds=[AttachmentKind.IMAGE],
                    )
        except AttachmentValidationError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        return JsonResponse(_serialize(comment))

    # DELETE — soft-delete
    is_own    = comment.author_id == user.user_id
    is_admin  = user.role == Role.ADMIN

    if not is_own and not is_admin:
        return JsonResponse({"error": "You can only delete your own comments"}, status=403)

    comment.is_deleted = True
    comment.content    = ""          # blank content for privacy
    comment.save(update_fields=["is_deleted", "content", "updated_at"])
    AttachmentService.purge_for_object(comment)
    return JsonResponse({"deleted": True, "comment_id": comment_id})
