from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "NextGen AI Admin"
admin.site.site_title = "NextGen AI Admin"

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path("", include("core.urls")),
    path("accounts/", include("accounts.urls")),
    path("blogs/", include("blogs.urls")),
    path("api/packages/", include("packages.urls")),
    path("api/payments/", include("payments.urls")),
    path("api/internal/chatbot/", include("websites.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
