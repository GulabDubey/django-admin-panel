from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from django.views.decorators.http import require_POST

from .models import WebsiteCrawl
from .services import start_crawl

STATUS_COLORS = {
    "pending": "#6b7280",
    "running": "#2563eb",
    "success": "#16a34a",
    "failed": "#dc2626",
}


class WebsiteCrawlForm(forms.ModelForm):
    class Meta:
        model = WebsiteCrawl
        fields = ("url", "website", "max_pages")

    def clean(self):
        cleaned = super().clean()
        url = cleaned.get("url")
        if url and WebsiteCrawl.objects.filter(url=url, status__in=("pending", "running")).exists():
            raise forms.ValidationError("A crawl for this URL is already in progress.")
        return cleaned


def fail_stale_crawls():
    """Mark jobs whose worker thread died (e.g. server restart) as failed."""
    for crawl in WebsiteCrawl.objects.filter(status__in=("pending", "running")):
        if crawl.is_stale():
            crawl.status = "failed"
            crawl.message = "Crawl stopped without a result (server restarted or timed out)."
            crawl.finished_at = timezone.now()
            crawl.save(update_fields=["status", "message", "finished_at"])


def rerun_crawl(crawl, user):
    """Start a new crawl with the same inputs. Returns None if one is already in progress."""
    if WebsiteCrawl.objects.filter(url=crawl.url, status__in=("pending", "running")).exists():
        return None
    new = WebsiteCrawl.objects.create(
        url=crawl.url,
        website=crawl.website,
        max_pages=crawl.max_pages,
        requested_by=user,
    )
    start_crawl(new)
    return new


@admin.register(WebsiteCrawl)
class WebsiteCrawlAdmin(admin.ModelAdmin):
    form = WebsiteCrawlForm

    list_display = (
        "id",
        "url",
        "collection_name",
        "max_pages",
        "status_badge",
        "pages_crawled",
        "chunks_stored",
        "requested_by",
        "created_at",
        "duration",
    )
    list_display_links = ("id", "url")
    list_filter = ("status", "created_at")
    search_fields = ("url", "website", "collection", "message")
    ordering = ("-created_at",)
    list_per_page = 25
    actions = ("rerun_crawls",)

    add_fieldsets = (
        (None, {"fields": ("url", "website", "max_pages")}),
    )
    fieldsets = (
        ("Request", {"fields": ("url", "website", "max_pages", "requested_by")}),
        ("Result", {"fields": ("status", "collection", "pages_crawled", "chunks_stored", "message")}),
        ("Timing", {"fields": ("created_at", "started_at", "finished_at")}),
    )

    def get_fieldsets(self, request, obj=None):
        return self.add_fieldsets if obj is None else self.fieldsets

    def has_change_permission(self, request, obj=None):
        # Existing jobs are a record of what happened: view-only, re-run instead of editing.
        return obj is None and super().has_change_permission(request)

    def save_model(self, request, obj, form, change):
        if not change:
            obj.requested_by = request.user
        super().save_model(request, obj, form, change)
        if not change:
            start_crawl(obj)

    def response_add(self, request, obj, post_url_continue=None):
        self.message_user(
            request,
            f"Crawl of {obj.url} started. This page refreshes until it finishes.",
            messages.SUCCESS,
        )
        return self.response_post_save_add(request, obj)

    def changelist_view(self, request, extra_context=None):
        fail_stale_crawls()
        extra_context = {
            **(extra_context or {}),
            "has_active_crawls": WebsiteCrawl.objects.filter(status__in=("pending", "running")).exists(),
        }
        return super().changelist_view(request, extra_context)

    @admin.display(description="Collection", ordering="collection")
    def collection_name(self, obj):
        return obj.collection or obj.website or "—"

    @admin.display(description="Status", ordering="status")
    def status_badge(self, obj):
        return format_html(
            '<span style="color:#fff;background:{};padding:2px 8px;border-radius:10px;font-size:11px" title="{}">{}</span>',
            STATUS_COLORS.get(obj.status, "#6b7280"),
            obj.message,
            obj.get_status_display(),
        )

    @admin.display(description="Duration")
    def duration(self, obj):
        if not obj.started_at:
            return "—"
        seconds = int(((obj.finished_at or timezone.now()) - obj.started_at).total_seconds())
        return f"{seconds // 60}m {seconds % 60}s" if seconds >= 60 else f"{seconds}s"

    @admin.action(description="Re-run selected crawls", permissions=["add"])
    def rerun_crawls(self, request, queryset):
        started = sum(1 for crawl in queryset if rerun_crawl(crawl, request.user))
        skipped = queryset.count() - started

        self.message_user(request, f"Started {started} crawl(s).", messages.SUCCESS)
        if skipped:
            self.message_user(
                request, f"Skipped {skipped} URL(s) that already have a crawl in progress.", messages.WARNING
            )

    # --- Per-crawl "Re-run" button (list rows and detail page) ---------------

    def get_urls(self):
        custom_urls = [
            path(
                "<path:object_id>/rerun/",
                self.admin_site.admin_view(require_POST(self.rerun_view)),
                name="crawler_websitecrawl_rerun",
            ),
        ]
        return custom_urls + super().get_urls()

    def get_list_display(self, request):
        list_display = super().get_list_display(request)
        if self.has_add_permission(request):
            list_display = (*list_display, "rerun_button")
        return list_display

    @admin.display(description="")
    def rerun_button(self, obj):
        if obj.is_active:
            return format_html('<span style="color:#6b7280">In progress…</span>')
        # The changelist is already a POST form with a CSRF token; formaction
        # sends it to the re-run URL instead of nesting another form.
        return format_html(
            '<button type="submit" class="button" formaction="{}" formmethod="post">Re-run</button>',
            reverse("admin:crawler_websitecrawl_rerun", args=[obj.pk]),
        )

    def change_view(self, request, object_id, form_url="", extra_context=None):
        crawl = self.get_object(request, object_id)
        extra_context = {
            **(extra_context or {}),
            "can_rerun": crawl is not None and not crawl.is_active and self.has_add_permission(request),
            "rerun_url": reverse("admin:crawler_websitecrawl_rerun", args=[object_id]),
        }
        return super().change_view(request, object_id, form_url, extra_context)

    def rerun_view(self, request, object_id):
        if not self.has_add_permission(request):
            raise PermissionDenied
        crawl = get_object_or_404(WebsiteCrawl, pk=object_id)

        if rerun_crawl(crawl, request.user):
            self.message_user(
                request,
                f"Re-running crawl of {crawl.url}. This page refreshes until it finishes.",
                messages.SUCCESS,
            )
        else:
            self.message_user(request, f"A crawl of {crawl.url} is already in progress.", messages.WARNING)

        return redirect("admin:crawler_websitecrawl_changelist")
