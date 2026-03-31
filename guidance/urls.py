from django.urls import path
from guidance import views

urlpatterns = [
    # Order matters: static paths before dynamic <pk>
    path("summary/stats/",  views.guidance_stats,           name="guidance-stats"),
    path("by-key/steps/",   views.guidance_by_key_steps,    name="guidance-by-key-steps"),
    path("by-key/",         views.guidance_by_key,          name="guidance-by-key"),
    path("",                views.guidance_list_or_upsert,  name="guidance-list-upsert"),
    path("<int:pk>/",       views.guidance_detail,          name="guidance-detail"),
]
