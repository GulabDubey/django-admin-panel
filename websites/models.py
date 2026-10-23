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
    payment = models.ForeignKey(
        "payments.Payment",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="websites",
        limit_choices_to={"status": "paid", "package__isnull": False},
        help_text=(
            "Paid payment whose plan covers this website. Leave empty to use the "
            "owner's latest paid plan (payments made by them or with their email)."
        ),
    )
    PERIOD_HOUR = "hour"
    PERIOD_DAY = "day"
    PERIOD_WEEK = "week"
    PERIOD_MONTH = "month"
    PERIOD_TOTAL = "total"
    QUESTION_PERIOD_CHOICES = [
        (PERIOD_HOUR, "per hour"),
        (PERIOD_DAY, "per day"),
        (PERIOD_WEEK, "per week"),
        (PERIOD_MONTH, "per month"),
        (PERIOD_TOTAL, "in total (never resets)"),
    ]

    question_limit = models.PositiveIntegerField(
        "Questions per visitor",
        default=0,
        db_default=0,  # kept in MySQL so code that predates this column can still insert rows
        help_text="How many questions each chatbot visitor may ask. 0 = unlimited.",
    )
    question_limit_period = models.CharField(
        "Per",
        max_length=10,
        choices=QUESTION_PERIOD_CHOICES,
        default=PERIOD_DAY,
        db_default=PERIOD_DAY,
    )
    question_limit_message = models.CharField(
        "Limit reached message",
        max_length=300,
        blank=True,
        default="",
        db_default="",
        help_text="Shown to the visitor when they reach the limit. Leave empty for a default message.",
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


class QuestionUsage(models.Model):
    """
    Chatbot questions counted per visitor (and per hashed IP, as a backstop)
    for one limit period of a website. Written only through
    websites.questions.consume_question / refund_question.
    """

    KIND_VISITOR = "visitor"
    KIND_IP = "ip"
    KIND_CHOICES = [(KIND_VISITOR, "Visitor"), (KIND_IP, "IP address (hashed)")]

    website = models.ForeignKey(Website, on_delete=models.CASCADE, related_name="question_usage")
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    identity = models.CharField(max_length=64, help_text="Anonymous visitor ID or IP hash; never a raw IP.")
    period_start = models.DateTimeField()
    count = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["website", "kind", "identity", "period_start"], name="unique_question_usage_period"
            ),
        ]
        indexes = [models.Index(fields=["website", "period_start"]), models.Index(fields=["updated_at"])]

    def __str__(self):
        return f"{self.website} · {self.kind} {self.identity[:8]}… · {self.count}"
