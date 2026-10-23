import json
import logging
from urllib.parse import urlsplit

from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.forms.models import BaseInlineFormSet
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import path, reverse
from django.utils.html import format_html
from django.views.decorators.http import require_POST

from websites.models import Website
from .catalog import PRESETS, ModelListError, fetch_models
from .crypto import DecryptionError
from .models import LLMModel, LLMProvider

logger = logging.getLogger(__name__)

MODEL_ID_FIELD = LLMModel._meta.get_field("model_id")


class LLMProviderForm(forms.ModelForm):
    api_key = forms.CharField(
        label="API key",
        required=False,
        strip=True,
        widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "new-password", "size": 60}),
        help_text="Stored encrypted and never shown again. Leave empty to keep the current key.",
    )
    # Model IDs ticked in "Available models" (JSON list, filled by the page script).
    selected_models = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = LLMProvider
        fields = ("website", "preset", "name", "api_type", "base_url", "api_key", "is_active", "is_default")

    def clean_selected_models(self):
        raw = self.cleaned_data.get("selected_models") or "[]"
        try:
            ids = json.loads(raw)
        except ValueError:
            raise forms.ValidationError("Invalid model selection.")
        if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
            raise forms.ValidationError("Invalid model selection.")
        cleaned = []
        for model_id in dict.fromkeys(i.strip() for i in ids if i.strip()):
            try:
                MODEL_ID_FIELD.run_validators(model_id)
            except forms.ValidationError:
                raise forms.ValidationError(f"Invalid model ID: {model_id}")
            if len(model_id) > MODEL_ID_FIELD.max_length:
                raise forms.ValidationError(f"Model ID too long: {model_id}")
            cleaned.append(model_id)
        return cleaned

    def clean(self):
        cleaned = super().clean()
        # On edit the website is read-only, so it comes from the saved provider.
        website = self.instance.website if self.instance.website_id else cleaned.get("website")
        name = cleaned.get("name")
        if website and name and (
            LLMProvider.objects.filter(website=website, name__iexact=name).exclude(pk=self.instance.pk).exists()
        ):
            self.add_error("name", "This website already has a provider with this name.")
        preset = PRESETS.get(cleaned.get("preset") or "custom", PRESETS["custom"])

        if preset.get("key_optional") and not cleaned.get("api_key") and not self.instance.api_key_encrypted:
            cleaned["api_key"] = "ollama"
        if not self.instance.api_key_encrypted and not cleaned.get("api_key"):
            self.add_error("api_key", "An API key is required.")
        if cleaned.get("api_type") == LLMProvider.API_ANTHROPIC and cleaned.get("base_url"):
            self.add_error("base_url", "Leave empty for Anthropic.")
        if preset.get("custom") and not cleaned.get("base_url"):
            self.add_error("base_url", "Enter the base URL of your OpenAI-compatible endpoint.")
        if cleaned.get("api_key"):
            # Encrypt during validation so a missing/invalid LLM_ENCRYPTION_KEYS
            # shows as a form error instead of a server error on save.
            try:
                self.instance.set_api_key(cleaned["api_key"])
            except ImproperlyConfigured as exc:
                self.add_error("api_key", str(exc))
        return cleaned


class LLMModelFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        defaults = [
            form for form in self.forms
            if form.cleaned_data.get("is_default") and not form.cleaned_data.get("DELETE")
        ]
        if len(defaults) > 1:
            raise forms.ValidationError("Only one model can be the default for this provider.")
        for form in defaults:
            if not form.cleaned_data.get("is_active"):
                form.add_error("is_default", "An inactive model can't be the default.")


class LLMModelInline(admin.TabularInline):
    model = LLMModel
    formset = LLMModelFormSet
    fields = ("model_id", "label", "is_active", "is_default")
    extra = 0
    verbose_name_plural = "Models (tick models above, or add/edit them here)"


@admin.register(LLMProvider)
class LLMProviderAdmin(admin.ModelAdmin):
    """Managed from each website's page (Admin → Websites → AI model); not listed in the menu."""

    form = LLMProviderForm
    inlines = (LLMModelInline,)
    change_form_template = "admin/llm/llmprovider/change_form.html"
    list_display = ("name", "website", "preset", "base_url_display", "api_key_hint", "model_list", "is_active", "default_badge", "key_link", "updated_at")
    list_select_related = ("website",)
    list_filter = ("preset", "api_type", "is_active", "is_default")
    search_fields = ("name", "base_url", "models__model_id", "website__domain", "website__name")
    autocomplete_fields = ("website",)
    readonly_fields = ("api_key_hint", "created_at", "updated_at")
    fieldsets = (
        ("Provider", {"fields": ("website", "preset", "name", "api_type", "base_url")}),
        ("API key", {"fields": ("api_key", "api_key_hint")}),
        ("Available models", {"fields": ("selected_models",), "classes": ("llm-available-models",)}),
        ("Usage", {"fields": ("is_active", "is_default")}),
        ("Timestamps", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def has_module_permission(self, request):
        # Providers belong to a website, so they are reached from the website page.
        return False

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if obj is not None:
            readonly.append("website")  # a provider (and its key) never moves to another site
        return readonly

    # --- Return to the website after saving / deleting ---------------------

    @staticmethod
    def _website_url(website_id):
        return reverse("admin:websites_website_change", args=[website_id])

    def response_add(self, request, obj, post_url_continue=None):
        response = super().response_add(request, obj, post_url_continue)
        return self._back_to_website(request, obj, response)

    def response_change(self, request, obj):
        response = super().response_change(request, obj)
        return self._back_to_website(request, obj, response)

    def _back_to_website(self, request, obj, response):
        if "_continue" in request.POST or "_popup" in request.POST or not isinstance(response, HttpResponseRedirect):
            return response
        if "_addanother" in request.POST:
            return HttpResponseRedirect(reverse("admin:llm_llmprovider_add") + f"?website={obj.website_id}")
        return HttpResponseRedirect(self._website_url(obj.website_id))

    def delete_view(self, request, object_id, extra_context=None):
        provider = self.get_object(request, object_id)
        response = super().delete_view(request, object_id, extra_context)
        if provider is not None and request.method == "POST" and isinstance(response, HttpResponseRedirect):
            return HttpResponseRedirect(self._website_url(provider.website_id))
        return response

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("models")

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if obj is None:
            form.base_fields["api_key"].help_text = "Stored encrypted and never shown again."
        return form

    def get_urls(self):
        return [
            path(
                "load-models/",
                self.admin_site.admin_view(require_POST(self.load_models_view)),
                name="llm_llmprovider_load_models",
            ),
        ] + super().get_urls()

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        website = None
        if object_id and str(object_id).isdigit():
            website = Website.objects.filter(llm_providers__pk=int(object_id)).first()
        elif str(request.GET.get("website", "")).isdigit():
            website = Website.objects.filter(pk=int(request.GET["website"])).first()
        extra_context = {
            **(extra_context or {}),
            "llm_website": website,
            "llm_presets": PRESETS,
            "llm_load_models_url": reverse("admin:llm_llmprovider_load_models"),
            "llm_existing_models": list(
                LLMModel.objects.filter(provider_id=object_id).values_list("model_id", flat=True)
            ) if object_id else [],
        }
        return super().changeform_view(request, object_id, form_url, extra_context)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        provider = form.instance
        existing = set(provider.models.values_list("model_id", flat=True))
        added = [
            LLMModel.objects.create(provider=provider, model_id=model_id)
            for model_id in form.cleaned_data.get("selected_models", []) if model_id not in existing
        ]
        if added and not provider.models.filter(is_default=True, is_active=True).exists():
            first = added[0]
            first.is_default = True
            first.save()
        if added:
            self.message_user(request, f"Added {len(added)} model(s) to {provider.name}.", messages.SUCCESS)

    def load_models_view(self, request):
        """List the models a key can use, straight from the provider's API (for the form's checkboxes)."""
        if not self.has_add_permission(request) and not self.has_change_permission(request):
            raise PermissionDenied
        try:
            data = json.loads(request.body)
        except ValueError:
            return JsonResponse({"error": "Invalid request."}, status=400)

        api_type = data.get("api_type")
        base_url = (data.get("base_url") or "").strip()
        api_key = (data.get("api_key") or "").strip()

        if api_type not in (LLMProvider.API_ANTHROPIC, LLMProvider.API_OPENAI):
            return JsonResponse({"error": "Choose an API type first."}, status=400)
        if base_url:
            parts = urlsplit(base_url)
            if parts.scheme not in ("http", "https") or not parts.hostname:
                return JsonResponse({"error": "Enter a valid base URL."}, status=400)
            if parts.scheme == "http" and not settings.DEBUG:
                return JsonResponse({"error": "Use an https:// base URL."}, status=400)

        provider_id = str(data.get("provider_id") or "")
        if provider_id and not provider_id.isdigit():
            return JsonResponse({"error": "Invalid request."}, status=400)
        if not api_key and provider_id:
            # Editing: reuse the stored key so it never has to be pasted again.
            provider = get_object_or_404(LLMProvider, pk=int(provider_id))
            try:
                api_key = provider.get_api_key()
            except (DecryptionError, ImproperlyConfigured):
                return JsonResponse({"error": "The stored key can't be decrypted. Paste the key again."}, status=400)
        if not api_key:
            return JsonResponse({"error": "Paste the API key first."}, status=400)

        try:
            models = fetch_models(api_type, base_url, api_key)
        except ModelListError as exc:
            return JsonResponse({"error": str(exc)}, status=502)
        except Exception:
            logger.exception("Loading models failed for %s", base_url or api_type)
            return JsonResponse({"error": "Could not load models from the provider."}, status=502)

        if not models:
            return JsonResponse({"error": "No chat models found for this key. Add model IDs manually below."}, status=404)
        return JsonResponse({"models": models})

    @admin.display(description="Base URL", ordering="base_url")
    def base_url_display(self, obj):
        return obj.base_url or "official API"

    @admin.display(description="Models")
    def model_list(self, obj):
        names = [
            f"{m.model_id}{' ★' if m.is_default else ''}"
            for m in obj.models.all() if m.is_active
        ]
        return ", ".join(names) or format_html('<span style="color:#dc2626">{}</span>', "none")

    @admin.display(description="Active", boolean=True, ordering="is_default")
    def default_badge(self, obj):
        return obj.is_default

    @admin.display(description="Keys")
    def key_link(self, obj):
        url = PRESETS.get(obj.preset, {}).get("key_url")
        if not url:
            return "—"
        return format_html('<a href="{}" target="_blank" rel="noopener noreferrer">Manage keys ↗</a>', url)
