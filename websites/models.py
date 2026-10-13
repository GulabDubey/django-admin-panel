import secrets

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models

from .domains import normalize_domain


def generate_site_key():
    return "site_" + secrets.token_urlsafe(24)


class Website(models.Model):
    """A customer website registered to use the chatbot widget."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="websites",
        help_text="Customer whose paid subscription covers this website.",
    )
    name = models.CharField(max_length=255)
    domain = models.CharField(
        max_length=253,
        unique=True,
        help_text=(
            "Approved domain, e.g. example.com. 'www.' is treated as the same site. "
            "When DEBUG is on, local addresses such as http://127.0.0.1:8012 are also allowed."
        ),
    )
    site_key = models.CharField(
        max_length=64,
        unique=True,
        default=generate_site_key,
        editable=False,
        help_text="Public key embedded in the customer's chatbot widget.",
    )
    collection_name = models.CharField(
        max_length=100,
        blank=True,
        validators=[
            RegexValidator(
                r"^[a-zA-Z0-9_-]+$",
                "Use only letters, numbers, hyphens and underscores.",
            )
        ],
        help_text="Knowledge collection the chatbot answers from (the crawl's collection, e.g. FlaskshopV2).",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Untick to block the chatbot on this website regardless of subscription.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["domain"]

    def __str__(self):
        return self.domain

    def clean(self):
        normalized = normalize_domain(self.domain)
        if not normalized:
            message = "Enter a valid domain, e.g. example.com."
            if settings.DEBUG:
                message += " Local addresses like http://127.0.0.1:8012 are also accepted."
            raise ValidationError({"domain": message})
        self.domain = normalized

    def save(self, *args, **kwargs):
        self.domain = normalize_domain(self.domain) or self.domain
        super().save(*args, **kwargs)
