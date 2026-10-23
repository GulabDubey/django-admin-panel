"""Which provider and model the chatbot uses for a website."""

from dataclasses import dataclass

from .models import LLMModel, LLMProvider


class LLMNotConfigured(Exception):
    pass


@dataclass(frozen=True)
class ResolvedLLM:
    provider: LLMProvider
    model: LLMModel
    source: str = "website"


def resolve_llm(website):
    """
    The website's active provider and that provider's default model (or its
    first active model). Raises LLMNotConfigured when there is no usable one;
    the chatbot then falls back to web-agent's own .env settings.
    """
    if website is None:
        raise LLMNotConfigured("No website given.")

    provider = website.llm_providers.filter(is_default=True, is_active=True).first()
    if provider is None:
        raise LLMNotConfigured(f"Website {website.pk} has no active LLM provider.")

    model = provider.default_model()
    if model is None:
        raise LLMNotConfigured(f"LLM provider {provider.pk} has no active models.")
    if not provider.api_key_encrypted:
        raise LLMNotConfigured(f"LLM provider {provider.pk} has no API key.")

    return ResolvedLLM(provider=provider, model=model)
