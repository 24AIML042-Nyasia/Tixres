from django.urls import path
from workflows import views

urlpatterns = [
    path("statuses/",        views.status_list_create, name="workflow-status-list"),
    path("statuses/<int:pk>/", views.status_detail,   name="workflow-status-detail"),
]
