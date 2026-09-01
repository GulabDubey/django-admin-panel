from django.conf import settings
from django.db import models
from packages.models import Package


class Payment(models.Model):
    STATUS_CHOICES = [
        ("created", "Created"),
        ("paid", "Paid"),
        ("failed", "Failed"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="payments",
        help_text="Linked automatically when the buyer is logged in.",
    )
    package = models.ForeignKey(
        Package,
        null=True,
        on_delete=models.SET_NULL,
        related_name="payments",
    )
    buyer_name = models.CharField(max_length=255)
    buyer_email = models.EmailField()
    buyer_contact = models.CharField(max_length=20, blank=True)

    razorpay_order_id = models.CharField(max_length=100, unique=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True)
    razorpay_signature = models.CharField(max_length=255, blank=True)

    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, default="INR")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="created")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.buyer_email} - {self.package} - {self.status}"
