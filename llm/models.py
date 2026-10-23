from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models, transaction
from django.db.models import Q

from . import crypto
from .catalog import PRESET_CHOICES


class LLMProvider(models.Model):
    """
    An LLM API account (credentials + endpoint) belonging to one website.
    The website's chatbot uses its *active* provider and that provider's
    default model. Any OpenAI-compatible service (OpenAI, Gemini, Groq,
    OpenRouter, DeepSeek, Mistral, Ollama, …) works by choosing that API type
    and its base URL.
    """

    API_ANTHROPIC = "anthropic"
    API_OPENAI = "openai"
    API_TYPE_CHOICES = [
        (API_ANTHROPIC, "Anthropic (Claude)"),
        (API_OPENAI, "OpenAI-compatible (OpenAI, Gemini, Groq, OpenRouter, DeepSeek, Mistral, Ollama…)"),
    ]

    website = models.ForeignKey(
        "websites.Website",
        on_delete=models.CASCADE,
        related_name="llm_providers",
        help_text="Website whose chatbot uses this provider.",
    )
    preset = models.CharField(
        "Provider",
        max_length=30,
        choices=PRESET_CHOICES,
        default="custom",
        help_text="Known provider: fills in the API type and base URL and links to where you get a key.",
    )
    name = models.CharField(max_length=100, help_text="Display name, e.g. Anthropic, OpenAI, Groq.")
    api_type = models.CharField(
        "API type",
        max_length=20,
        choices=API_TYPE_CHOICES,
        help_text="Which client the chatbot uses to call this provider.",
    )
    base_url = models.URLField(
        "Base URL",
        blank=True,
        help_text=(
            "Leave empty for the official Anthropic / OpenAI API. Required for other "
            "OpenAI-compatible providers, e.g. https://api.groq.com/openai/v1"
        ),
    )
    api_key_encrypted = models.TextField(editable=False, blank=True)
    api_key_hint = models.CharField(
        "API key", max_length=12, editable=False, blank=True, help_text="Last characters of the stored key."
    )
    is_active = models.BooleanField(default=True, help_text="Inactive providers are never used by the chatbot.")
    is_default = models.BooleanField(
        "Active for this website",
        default=False,
        help_text="The website's chatbot uses this provider. Only one provider per website can be active.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["website", "-is_default", "name"]
        verbose_name = "LLM provider"
        constraints = [
            models.UniqueConstraint(fields=["website", "name"], name="llm_unique_provider_name_per_website"),
            models.UniqueConstraint(
                fields=["website"], condition=Q(is_default=True), name="llm_single_active_provider_per_website"
            ),
        ]

    def __str__(self):
        return f"{self.name} (active)" if self.is_default else self.name

    def set_api_key(self, value):
        value = value.strip()
        self.api_key_encrypted = crypto.encrypt(value)
        self.api_key_hint = "…" + value[-4:] if len(value) >= 8 else "…"

    def get_api_key(self):
        return crypto.decrypt(self.api_key_encrypted) if self.api_key_encrypted else ""

    def clean(self):
        if self.is_default and not self.is_active:
            raise ValidationError({"is_default": "A disabled provider can't be the active one."})

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if (
                self._state.adding and self.is_active and not self.is_default
                and not LLMProvider.objects.filter(website_id=self.website_id, is_default=True).exists()
            ):
                # A website's first usable provider becomes its active one.
                self.is_default = True
            if self.is_default:
                LLMProvider.objects.filter(website_id=self.website_id, is_default=True).exclude(pk=self.pk).update(
                    is_default=False
                )
            super().save(*args, **kwargs)

    def default_model(self):
        models_ = self.models.filter(is_active=True)
        return models_.filter(is_default=True).first() or models_.order_by("id").first()


class LLMModel(models.Model):
    provider = models.ForeignKey(LLMProvider, on_delete=models.CASCADE, related_name="models")
    model_id = models.CharField(
        "Model ID",
        max_length=150,
        validators=[RegexValidator(r"^[A-Za-z0-9._:/@-]+$", "Use the provider's exact model ID, e.g. claude-sonnet-4-5.")],
        help_text="Exact ID the provider's API expects, e.g. claude-sonnet-4-5, gpt-4o-mini, llama-3.3-70b-versatile.",
    )
    label = models.CharField(max_length=150, blank=True, help_text="Optional friendly name shown in the admin.")
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False, help_text="Used for websites that pick this provider but no model.")

    class Meta:
        ordering = ["provider__name", "-is_default", "model_id"]
        verbose_name = "LLM model"
        constraints = [
            models.UniqueConstraint(fields=["provider", "model_id"], name="llm_unique_model_per_provider"),
            models.UniqueConstraint(
                fields=["provider"], condition=Q(is_default=True), name="llm_single_default_model_per_provider"
            ),
        ]

    def __str__(self):
        name = self.label or self.model_id
        return f"{self.provider.name} · {name}"

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if self.is_default:
                LLMModel.objects.filter(provider_id=self.provider_id, is_default=True).exclude(pk=self.pk).update(
                    is_default=False
                )
            super().save(*args, **kwargs)
