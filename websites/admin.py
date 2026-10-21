from django.contrib import admin, messages
from django.utils.html import format_html

from payments.subscriptions import website_subscription
from .models import Website, generate_site_key


@admin.register(Website)
class WebsiteAdmin(admin.ModelAdmin):
    list_select_related = ("owner", "payment__package")
    list_display = ("domain", "name", "owner", "collection_name", "site_key", "is_active", "subscription_status", "created_at")
    list_filter = ("is_active", "created_at")
    search_fields = ("domain", "name", "owner__email", "owner__username", "site_key")
    autocomplete_fields = ("owner", "payment")
    readonly_fields = ("site_key", "subscription_status", "created_at", "updated_at")
    fields = ("name", "domain", "owner", "payment", "collection_name", "is_active", "site_key", "subscription_status", "created_at", "updated_at")
    actions = ("regenerate_site_keys",)
    list_per_page = 25

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
