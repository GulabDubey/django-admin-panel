from django.contrib import admin
from .models import Payment

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "buyer_name",
        "buyer_email",
        "package",
        "amount",
        "currency",
        "status",
        "user",
        "created_at",
    )

    list_filter = (
        "status",
        "package",
        "created_at",
    )

    search_fields = (
        "buyer_name",
        "buyer_email",
        "buyer_contact",
        "razorpay_order_id",
        "razorpay_payment_id",
        "user__username",
        "user__email",
    )

    ordering = ("-created_at",)

    list_per_page = 25

    readonly_fields = (
        "user",
        "package",
        "buyer_name",
        "buyer_email",
        "buyer_contact",
        "razorpay_order_id",
        "razorpay_payment_id",
        "razorpay_signature",
        "amount",
        "currency",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False
