from django.contrib import admin
from .models import Blog
from .forms import BlogAdminForm
from django.urls import path
from django.http import JsonResponse
from ai_agents.blog_crew import generate_blog

def generate_blog_view(request):

    import json

    data=json.loads(
        request.body
    )

    topic=data["topic"]


    result = generate_blog(topic)


    return JsonResponse({

        "title": topic,

        "content": str(result),

        "meta": str(result)[:160]

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
                )
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