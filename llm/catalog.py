"""
Known LLM providers offered in the admin's "Provider" select.

Model lists are not hardcoded (they change every few months): the admin
loads the models a key can actually use from the provider's API
(see `fetch_models`). To support another OpenAI-compatible provider, add an
entry here; anything else can be added with the "Custom" option.
"""

import requests

ANTHROPIC = "anthropic"
OPENAI = "openai"

PRESETS = {
    "anthropic": {
        "name": "Anthropic",
        "api_type": ANTHROPIC,
        "base_url": "",
        "key_url": "https://console.anthropic.com/settings/keys",
        "key_hint": "Starts with sk-ant-",
    },
    "openai": {
        "name": "OpenAI",
        "api_type": OPENAI,
        "base_url": "",
        "key_url": "https://platform.openai.com/api-keys",
        "key_hint": "Starts with sk-",
    },
    "gemini": {
        "name": "Google Gemini",
        "api_type": OPENAI,
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "key_url": "https://aistudio.google.com/app/apikey",
        "key_hint": "Google AI Studio key",
    },
    "groq": {
        "name": "Groq",
        "api_type": OPENAI,
        "base_url": "https://api.groq.com/openai/v1",
        "key_url": "https://console.groq.com/keys",
        "key_hint": "Starts with gsk_",
    },
    "openrouter": {
        "name": "OpenRouter",
        "api_type": OPENAI,
        "base_url": "https://openrouter.ai/api/v1",
        "key_url": "https://openrouter.ai/settings/keys",
        "key_hint": "Starts with sk-or-",
    },
    "deepseek": {
        "name": "DeepSeek",
        "api_type": OPENAI,
        "base_url": "https://api.deepseek.com/v1",
        "key_url": "https://platform.deepseek.com/api_keys",
        "key_hint": "Starts with sk-",
    },
    "mistral": {
        "name": "Mistral",
        "api_type": OPENAI,
        "base_url": "https://api.mistral.ai/v1",
        "key_url": "https://console.mistral.ai/api-keys",
        "key_hint": "Mistral La Plateforme key",
    },
    "xai": {
        "name": "xAI (Grok)",
        "api_type": OPENAI,
        "base_url": "https://api.x.ai/v1",
        "key_url": "https://console.x.ai/",
        "key_hint": "Starts with xai-",
    },
    "ollama": {
        "name": "Ollama (local)",
        "api_type": OPENAI,
        "base_url": "http://127.0.0.1:11434/v1",
        "key_url": "https://ollama.com/download",
        "key_hint": "Ollama needs no key; any value (e.g. ollama) works",
        "key_optional": True,
    },
    "custom": {
        "name": "",
        "api_type": OPENAI,
        "base_url": "",
        "key_url": "",
        "key_hint": "Key for your OpenAI-compatible endpoint",
        "custom": True,
    },
}

PRESET_CHOICES = [(key, preset["name"] or "Custom (OpenAI-compatible)") for key, preset in PRESETS.items()]

# Models these words mark are not chat models (embeddings, speech, images…).
NON_CHAT_MARKERS = (
    "embed", "tts", "whisper", "dall-e", "moderation", "rerank", "transcribe",
    "image", "audio", "realtime", "speech", "guard", "aqa", "imagen", "veo",
)

TIMEOUT = 15
MAX_MODELS = 1000


class ModelListError(Exception):
    pass


def is_chat_model(model_id):
    lowered = model_id.lower()
    return not any(marker in lowered for marker in NON_CHAT_MARKERS)


def _get(url, headers, params=None):
    try:
        response = requests.get(url, headers=headers, params=params, timeout=TIMEOUT, allow_redirects=False)
    except requests.Timeout:
        raise ModelListError("The provider did not respond in time.")
    except requests.RequestException:
        raise ModelListError("Could not connect to the provider. Check the base URL.")

    if response.status_code in (401, 403):
        raise ModelListError("The provider rejected this API key.")
    if response.status_code == 404:
        raise ModelListError("This endpoint has no model list. Check the base URL, or add models manually below.")
    if not response.ok:
        raise ModelListError(f"The provider returned HTTP {response.status_code}.")
    try:
        return response.json()
    except ValueError:
        raise ModelListError("The provider returned an unexpected response.")


def fetch_models(api_type, base_url, api_key):
    """
    Chat models the key can use, as [{"id": ..., "name": ...}], sorted by id.
    Raises ModelListError with a message safe to show an admin.
    """
    models = []

    if api_type == ANTHROPIC:
        url = "https://api.anthropic.com/v1/models"
        headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
        params = {"limit": 100}
        for _ in range(10):  # pages
            data = _get(url, headers, params)
            for item in data.get("data") or []:
                if isinstance(item, dict) and isinstance(item.get("id"), str):
                    models.append({"id": item["id"], "name": item.get("display_name") or item["id"]})
            if not data.get("has_more") or not data.get("last_id"):
                break
            params = {"limit": 100, "after_id": data["last_id"]}

    elif api_type == OPENAI:
        url = (base_url or "https://api.openai.com/v1").rstrip("/") + "/models"
        data = _get(url, {"Authorization": f"Bearer {api_key}"})
        items = data.get("data") if isinstance(data, dict) else data
        for item in items or []:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                continue
            # Gemini lists "models/gemini-…" but chat calls take "gemini-…".
            model_id = item["id"].removeprefix("models/")
            if is_chat_model(model_id):
                models.append({"id": model_id, "name": item.get("name") or model_id})
    else:
        raise ModelListError("Unknown API type.")

    unique = {model["id"]: model for model in models if len(model["id"]) <= 150}
    return sorted(unique.values(), key=lambda model: model["id"])[:MAX_MODELS]
