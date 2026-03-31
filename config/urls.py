from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/',        admin.site.urls),
    path('api/tickets/',  include('tickets.urls')),
    path('api/alerts/',   include('alerts.urls')),
    path('api/guidance/', include('guidance.urls')),
]
