from django.db import models

class Package(models.Model):
    STATUS_CHOICES = [
        ("active", "Active"),
        ("inactive", "Inactive"),
    ]

    name = models.CharField(max_length=255)
    badge = models.CharField(
        max_length=50,
        blank=True,
        help_text="Small label shown above the plan name, e.g. 'Recommended'."
    )
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Leave blank when 'Custom pricing' is enabled."
    )
    is_custom_price = models.BooleanField(
        default=False,
        help_text="Show 'Custom' instead of a price, e.g. for the Enterprise plan."
    )
    duration = models.PositiveIntegerField(help_text="Duration in days")
    description = models.TextField(blank=True)
    features = models.TextField(
        blank=True,
        help_text="One feature per line, e.g. '1 website'."
    )
    cta_text = models.CharField(max_length=50, default="Start Free Trial")
    cta_link = models.CharField(max_length=255, default="#contact")
    is_recommended = models.BooleanField(default=False)
    order = models.PositiveIntegerField(
        default=0,
        help_text="Controls display order on the pricing page (lowest first)."
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="active"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.name

    def feature_list(self):
        return [line.strip() for line in self.features.splitlines() if line.strip()]

    def display_price(self):
        return "Custom" if self.is_custom_price or self.price is None else f"₹{self.price:,.0f}"
