from django.urls import path
from alerts import views

urlpatterns = [
    path("",                        views.alert_list,      name="alert-list"),
    path("<int:alert_id>/",         views.alert_detail,    name="alert-detail"),
    path("<int:alert_id>/ack/",     views.alert_ack,       name="alert-ack"),
    path("<int:alert_id>/resolve/",   views.alert_resolve,   name="alert-resolve"),
    path("<int:alert_id>/broadcast/", views.alert_broadcast, name="alert-broadcast"),
]
