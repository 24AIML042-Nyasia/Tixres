from django.urls import path
from auth_core import views

urlpatterns = [
    path("me/",                                  views.me,           name="auth-me"),
    path("users/",                               views.user_list,    name="auth-user-list"),
    path("users/<str:user_id>/",                 views.user_detail,  name="auth-user-detail"),
    path("users/<str:user_id>/skills/add/",      views.skill_add,    name="auth-skill-add"),
    path("users/<str:user_id>/skills/remove/",   views.skill_remove, name="auth-skill-remove"),
]
