from datetime import timedelta

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.utils import timezone


class WebsiteCrawl(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("running", "Running"),
        ("success", "Success"),
        ("failed", "Failed"),
    ]

    url = models.URLField(max_length=500, help_text="Homepage to start crawling from.")
    website = models.CharField(
        max_length=100,
        blank=True,
        validators=[
            RegexValidator(
                r"^[a-zA-Z0-9_-]+$",
                "Use only letters, numbers, hyphens and underscores.",
            )
        ],
        help_text="Name for the knowledge collection. Leave blank to derive it from the domain.",
    )
    max_pages = models.PositiveIntegerField(
        default=30,
        validators=[MinValueValidator(1), MaxValueValidator(200)],
        help_text="Homepage plus same-domain pages, up to 200.",
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    collection = models.CharField(
        max_length=100,
        blank=True,
        help_text="Collection name the crawler API stored the data under.",
    )
    pages_crawled = models.PositiveIntegerField(null=True, blank=True)
    chunks_stored = models.PositiveIntegerField(null=True, blank=True)
    message = models.TextField(blank=True)

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="website_crawls",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.website or self.url} ({self.status})"

    @property
    def is_active(self):
        return self.status in ("pending", "running")

    def is_stale(self):
        """Active for longer than the API timeout allows, so the worker thread is gone."""
        limit = timedelta(seconds=settings.CRAWLER_API_TIMEOUT + 60)
        started = self.started_at or self.created_at
        return self.is_active and timezone.now() - started > limit
