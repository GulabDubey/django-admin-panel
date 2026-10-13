import json
import logging

from django.conf import settings
from django.contrib import admin
from django.http import JsonResponse
from django.urls import path
from django.views.decorators.http import require_POST

from .forms import BlogAdminForm
from .models import Blog

logger = logging.getLogger(__name__)


@require_POST
def generate_blog_view(request):
    if not settings.ANTHROPIC_API_KEY:
        return JsonResponse({"error": "ANTHROPIC_API_KEY is not configured."}, status=503)

    try:
        topic = (json.loads(request.body).get("topic") or "").strip()
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({"error": "Invalid request body."}, status=400)

    if not topic:
        return JsonResponse({"error": "Enter a blog topic first."}, status=400)

    # Imported lazily: crewai is heavy and only needed for this view.
    from ai_agents.blog_crew import generate_blog

    try:
        result = str(generate_blog(topic))
    except Exception:
        logger.exception("Blog generation failed for topic %r", topic)
        return JsonResponse({"error": "Blog generation failed. Please try again."}, status=502)

    return JsonResponse({
        "title": topic,
        "content": result,
        "meta": result[:160],
    })

@admin.register(Blog)
class BlogAdmin(admin.ModelAdmin):

    form = BlogAdminForm

    change_form_template = (
        "admin/blogs/blog/change_form.html"
    )

    def get_urls(self):

        urls = super().get_urls()

        custom_urls=[

            path(
                "generate-blog/",
                self.admin_site.admin_view(
                    generate_blog_view
                ),
                name="blogs_blog_generate",
            )

        ]

        return custom_urls + urls

    list_display = (
        "title",
        "status",
        "created_at",
    )

    list_filter = (
        "status",
        "created_at",
    )

    search_fields = (
        "title",
        "content",
    )

    prepopulated_fields = {
        "slug": ("title",)
    }

    list_per_page = 20