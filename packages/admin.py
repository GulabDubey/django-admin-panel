from django.contrib import admin
from django.db.models import Count, Q
from .models import Package

@admin.register(Package)
class PackageAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "badge",
        "display_price",
        "duration",
        "is_recommended",
        "purchases_count",
        "order",
        "status",
        "created_at",
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            paid_purchases=Count("payments", filter=Q(payments__status="paid"))
        )

    @admin.display(description="Purchases", ordering="paid_purchases")
    def purchases_count(self, obj):
        return obj.paid_purchases

    list_editable = (
        "order",
        "is_recommended",
        "status",
    )

    list_filter = (
        "status",
        "is_recommended",
        "created_at",
    )

    search_fields = (
        "name",
        "badge",
        "description",
    )

    ordering = ("order", "id")

    list_per_page = 20

    fieldsets = (
        ("Plan details", {
            "fields": ("name", "badge", "description", "status")
        }),
        ("Pricing", {
            "fields": ("price", "is_custom_price", "duration")
        }),
        ("Features & call to action", {
            "fields": ("features", "cta_text", "cta_link")
        }),
        ("Display", {
            "fields": ("is_recommended", "order")
        }),
    )

    @admin.display(description="Price")
    def display_price(self, obj):
        return obj.display_price()
