from django.urls import path
from attachments import views

urlpatterns = [
    path("upload/", views.upload, name="attachment-upload"),
]
