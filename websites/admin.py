from django.contrib import admin, messages
from django.urls import reverse
from django.utils.html import format_html, format_html_join

from llm.resolver import LLMNotConfigured, resolve_llm
from payments.subscriptions import website_subscription
from .models import Website, generate_site_key
from .questions import usage_summary


@admin.register(Website)
class WebsiteAdmin(admin.ModelAdmin):
    list_select_related = ("owner", "payment__package")
    list_display = ("domain", "name", "owner", "collection_name", "llm_display", "limit_display", "site_key", "is_active", "subscription_status", "created_at")
    list_filter = ("is_active", "created_at")
    search_fields = ("domain", "name", "owner__email", "owner__username", "site_key")
    autocomplete_fields = ("owner", "payment")
    readonly_fields = ("site_key", "subscription_status", "llm_providers_table", "effective_llm", "question_usage", "created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("name", "domain", "owner", "payment", "collection_name", "is_active")}),
        ("AI model", {
            "fields": ("llm_providers_table", "effective_llm"),
            "description": "LLM providers (API keys and models) this website's chatbot can use. The active one answers chats.",
        }),
        ("Question limit", {
            "fields": (("question_limit", "question_limit_period"), "question_limit_message", "question_usage"),
            "description": "How many questions each chatbot visitor can ask. Visitors are anonymous; "
                           "each browser counts as one visitor.",
        }),
        ("Status", {"fields": ("site_key", "subscription_status", "created_at", "updated_at")}),
    )
    actions = ("regenerate_site_keys",)
    list_per_page = 25

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("llm_providers__models")

    @admin.display(description="Subscription")
    def subscription_status(self, obj):
        if obj.pk is None:
            return "—"
        subscription = website_subscription(obj)
        source = "attached payment" if obj.payment_id else "owner's payments"
        if subscription is None:
            return format_html('<span style="color:#dc2626">No paid plan ({})</span>', source)
        expires = subscription.expires_at.strftime("%d %b %Y")
        if subscription.is_active:
            return format_html('<span style="color:#16a34a">{} · until {} ({})</span>', subscription.plan, expires, source)
        return format_html('<span style="color:#dc2626">{} · expired {} ({})</span>', subscription.plan, expires, source)

    @staticmethod
    def _active_provider(obj):
        return next((p for p in obj.llm_providers.all() if p.is_default and p.is_active), None)

    @admin.display(description="LLM")
    def llm_display(self, obj):
        provider = self._active_provider(obj)
        if provider is None:
            return "—"
        model = next((m for m in provider.models.all() if m.is_default and m.is_active), None) or next(
            (m for m in provider.models.all() if m.is_active), None
        )
        return f"{provider.name} · {model.model_id}" if model else f"{provider.name} · no model"

    @admin.display(description="LLM providers")
    def llm_providers_table(self, obj):
        if obj.pk is None:
            return "Save the website first, then add its LLM providers here."

        add_url = reverse("admin:llm_llmprovider_add") + f"?website={obj.pk}"
        add_button = format_html('<a class="button" href="{}">+ Add LLM provider</a>', add_url)
        providers = list(obj.llm_providers.all())
        if not providers:
            return format_html("<p>No providers yet.</p>{}", add_button)

        def row(provider):
            models_ = [m for m in provider.models.all() if m.is_active]
            names = ", ".join(f"{m.model_id}{' ★' if m.is_default else ''}" for m in models_) or "no models"
            if provider.is_default and provider.is_active:
                state = format_html('<strong style="color:#16a34a">{}</strong>', "● Active")
            elif not provider.is_active:
                state = format_html('<span style="color:#6b7280">{}</span>', "Disabled")
            else:
                state = "—"
            edit_url = reverse("admin:llm_llmprovider_change", args=[provider.pk])
            return (edit_url, provider.name, provider.get_preset_display(), provider.api_key_hint or "—", names, state, edit_url)

        rows = format_html_join(
            "",
            '<tr><td><a href="{}"><strong>{}</strong></a><br><small>{}</small></td><td><code>{}</code></td>'
            '<td>{}</td><td>{}</td><td><a href="{}">Edit</a></td></tr>',
            (row(provider) for provider in providers),
        )
        return format_html(
            '<table style="width:100%"><thead><tr><th>Provider</th><th>API key</th><th>Models (★ used)</th>'
            "<th>Status</th><th></th></tr></thead><tbody>{}</tbody></table><p>{}</p>",
            rows,
            add_button,
        )

    @admin.display(description="Question limit")
    def limit_display(self, obj):
        if obj.question_limit <= 0:
            return "unlimited"
        return f"{obj.question_limit} {obj.get_question_limit_period_display()}"

    @admin.display(description="Usage")
    def question_usage(self, obj):
        if obj.pk is None:
            return "—"
        summary = usage_summary(obj)
        period = summary["period"]
        when = "in total" if period.resets_at is None else (
            f"since {period.start:%d %b %Y %H:%M} (resets {period.resets_at:%d %b %Y %H:%M})"
        )
        text = f"{summary['questions']} questions from {summary['visitors']} visitors {when}"
        if obj.question_limit > 0:
            text += f" · {summary['at_limit']} visitor(s) reached the limit"
        return text

    @admin.display(description="Chatbot uses")
    def effective_llm(self, obj):
        if obj.pk is None:
            return "—"
        try:
            resolved = resolve_llm(obj)
        except LLMNotConfigured:
            return format_html(
                '<span style="color:#dc2626">{}</span>',
                "No active provider with a model yet. Until then the chatbot uses web-agent's own .env settings.",
            )
        return format_html("<strong>{}</strong> · <code>{}</code>", resolved.provider.name, resolved.model.model_id)

    @admin.action(description="Regenerate site key (old key stops working)", permissions=["change"])
    def regenerate_site_keys(self, request, queryset):
        for website in queryset:
            website.site_key = generate_site_key()
            website.save(update_fields=["site_key", "updated_at"])
        self.message_user(
            request,
            f"Regenerated {queryset.count()} site key(s). Update the widget embed code on those sites.",
            messages.WARNING,
        )
