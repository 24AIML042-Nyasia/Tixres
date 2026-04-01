from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include

from config import views as config_views

urlpatterns = [
    path('demo/ui/',       config_views.feature_client_ui, name='feature-client-ui'),
    path('demo/guidance/', config_views.guidance_ui,       name='guidance-ui'),
    path('admin/',        admin.site.urls),
    path('api/dev-auth/',   include('dev_auth.urls')),
    path('api/auth/',       include('auth_core.urls')),
    path('api/workflows/',  include('workflows.urls')),
    path('api/tickets/',  include('tickets.urls')),
    path('api/alerts/',   include('alerts.urls')),
    path('api/attachments/', include('attachments.urls')),
    path('api/guidance/', include('guidance.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
