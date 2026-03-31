from django.urls import path
from tickets import views
from tickets import comment_views

urlpatterns = [
    path("<str:agent_id>/latest/",        views.ticket_list,            name="ticket-list"),
    path("create/",                        views.ticket_create,          name="ticket-create"),
    path("<int:ticket_id>/acknowledge/",   views.ticket_acknowledge,     name="ticket-acknowledge"),
    path("<int:ticket_id>/assign/",        views.ticket_assign,          name="ticket-assign"),
    # Comments
    path("<int:ticket_id>/comments/",      comment_views.comment_list_create, name="ticket-comment-list"),
    path("<int:ticket_id>/comments/<int:comment_id>/", comment_views.comment_detail, name="ticket-comment-detail"),
]
