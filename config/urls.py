from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/',        admin.site.urls),
    path('api/dev-auth/',   include('dev_auth.urls')),
    path('api/auth/',       include('auth_core.urls')),
    path('api/workflows/',  include('workflows.urls')),
    path('api/tickets/',  include('tickets.urls')),
    path('api/alerts/',   include('alerts.urls')),
    path('api/guidance/', include('guidance.urls')),
]
