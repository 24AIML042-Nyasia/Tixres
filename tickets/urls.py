from django.urls import path
from tickets import views

urlpatterns = [
    path("<str:agent_id>/latest/", views.ticket_list,       name="ticket-list"),
    path("create/",                views.ticket_create,     name="ticket-create"),
    path("<int:ticket_id>/acknowledge/", views.ticket_acknowledge, name="ticket-acknowledge"),
]
