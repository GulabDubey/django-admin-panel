import json
from unittest import mock

from cryptography.fernet import Fernet
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.management import call_command
from django.db import DatabaseError
from django.test import TestCase, override_settings

from websites.models import Website
from .models import LLMModel, LLMProvider

ENC_KEY = Fernet.generate_key().decode()
TOKEN = "service-token-0123456789abcdefghijklmnop"
URL = "/api/internal/chatbot/llm-config/"


def make_site(owner=None, domain="s.example.com"):
    owner = owner or User.objects.create_user(f"owner-{domain}", f"o@{domain}", "pw")
    return Website.objects.create(owner=owner, name=domain, domain=domain)


def make_provider(website, name="Anthropic", api_type=LLMProvider.API_ANTHROPIC, key="sk-test-secret-1234",
                  active=None, models=("model-a",), base_url="", preset="custom"):
    provider = LLMProvider(website=website, name=name, api_type=api_type, base_url=base_url, preset=preset)
    if active is not None:
        provider.is_default = active
    provider.set_api_key(key)
    provider.save()
    for i, model_id in enumerate(models):
        LLMModel.objects.create(provider=provider, model_id=model_id, is_default=(i == 0))
    return provider


@override_settings(LLM_ENCRYPTION_KEYS=[ENC_KEY])
class ProviderModelTests(TestCase):
    def setUp(self):
        self.site = make_site()

    def test_api_key_encrypted_at_rest(self):
        provider = make_provider(self.site, key="sk-ant-very-secret-9876")
        raw = LLMProvider.objects.filter(pk=provider.pk).values_list("api_key_encrypted", flat=True).get()
        self.assertNotIn("very-secret", raw)
        self.assertEqual(LLMProvider.objects.get(pk=provider.pk).get_api_key(), "sk-ant-very-secret-9876")
        self.assertEqual(provider.api_key_hint, "…9876")

    def test_first_provider_of_a_website_becomes_active(self):
        first = make_provider(self.site, "A")
        second = make_provider(self.site, "B")
        self.assertTrue(first.is_default)
        self.assertFalse(second.is_default)

    def test_one_active_provider_per_website(self):
        a = make_provider(self.site, "A")
        b = make_provider(self.site, "B", active=True)
        a.refresh_from_db()
        self.assertFalse(a.is_default)
        self.assertTrue(b.is_default)

    def test_active_flags_are_independent_per_website(self):
        other = make_site(domain="other.example.com")
        a = make_provider(self.site, "A")
        b = make_provider(other, "A")
        a.refresh_from_db()
        self.assertTrue(a.is_default and b.is_default)

    def test_providers_deleted_with_website(self):
        make_provider(self.site)
        self.site.delete()
        self.assertFalse(LLMProvider.objects.exists())
        self.assertFalse(LLMModel.objects.exists())

    def test_only_one_default_model_per_provider(self):
        provider = make_provider(self.site, models=("m1",))
        LLMModel.objects.create(provider=provider, model_id="m2", is_default=True)
        self.assertEqual(list(provider.models.filter(is_default=True).values_list("model_id", flat=True)), ["m2"])

    def test_key_rotation(self):
        provider = make_provider(self.site, key="sk-rotate-me-1234")
        new_key = Fernet.generate_key().decode()
        with self.settings(LLM_ENCRYPTION_KEYS=[new_key, ENC_KEY]):
            call_command("rotate_llm_keys", stdout=mock.MagicMock())
        with self.settings(LLM_ENCRYPTION_KEYS=[new_key]):
            self.assertEqual(LLMProvider.objects.get(pk=provider.pk).get_api_key(), "sk-rotate-me-1234")


@override_settings(LLM_ENCRYPTION_KEYS=[ENC_KEY])
class ProviderAdminTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("admin", "admin@example.com", "pw")
        self.client.force_login(self.admin)
        self.site = make_site(self.admin)

    def provider_data(self, **overrides):
        data = {
            "website": self.site.pk, "preset": "groq", "name": "Groq", "api_type": "openai",
            "base_url": "https://api.groq.com/openai/v1", "api_key": "gsk-secret-value-4321",
            "is_active": "on", "is_default": "on", "selected_models": "[]",
            "models-TOTAL_FORMS": "2", "models-INITIAL_FORMS": "0",
            "models-MIN_NUM_FORMS": "0", "models-MAX_NUM_FORMS": "1000",
            "models-0-model_id": "llama-3.3-70b-versatile", "models-0-is_active": "on", "models-0-is_default": "on",
            "models-1-model_id": "llama-3.1-8b-instant", "models-1-is_active": "on",
        }
        data.update(overrides)
        return data

    def test_add_from_website_returns_to_website_and_key_never_rendered(self):
        add_page = self.client.get(f"/admin/llm/llmprovider/add/?website={self.site.pk}")
        self.assertEqual(add_page.context["adminform"].form.initial["website"], str(self.site.pk))
        self.assertContains(add_page, f'href="/admin/websites/website/{self.site.pk}/change/"')  # breadcrumb

        response = self.client.post("/admin/llm/llmprovider/add/", self.provider_data())
        self.assertRedirects(response, f"/admin/websites/website/{self.site.pk}/change/", fetch_redirect_response=False)
        provider = LLMProvider.objects.get()
        self.assertEqual((provider.website, provider.is_default), (self.site, True))
        self.assertEqual(provider.get_api_key(), "gsk-secret-value-4321")
        self.assertEqual(provider.default_model().model_id, "llama-3.3-70b-versatile")

        page = self.client.get(f"/admin/llm/llmprovider/{provider.pk}/change/")
        self.assertNotContains(page, "gsk-secret-value-4321")
        self.assertContains(page, "…4321")

    def test_website_is_read_only_after_creation(self):
        provider = make_provider(self.site, "Groq", api_type="openai")
        page = self.client.get(f"/admin/llm/llmprovider/{provider.pk}/change/")
        self.assertNotIn("website", page.context["adminform"].form.fields)

    def test_blank_key_on_edit_keeps_existing_key(self):
        provider = make_provider(self.site, "Groq", api_type="openai", key="gsk-original-key-0000")
        model = provider.models.get()
        data = self.provider_data(api_key="", base_url="", **{
            "models-TOTAL_FORMS": "1", "models-INITIAL_FORMS": "1",
            "models-0-id": model.pk, "models-0-provider": provider.pk,
            "models-0-model_id": model.model_id, "models-0-is_active": "on", "models-0-is_default": "on",
        })
        data.pop("website")
        response = self.client.post(f"/admin/llm/llmprovider/{provider.pk}/change/", data)
        self.assertRedirects(response, f"/admin/websites/website/{self.site.pk}/change/", fetch_redirect_response=False)
        self.assertEqual(LLMProvider.objects.get(pk=provider.pk).get_api_key(), "gsk-original-key-0000")

    def test_add_another_keeps_the_website(self):
        response = self.client.post("/admin/llm/llmprovider/add/", self.provider_data(_addanother="1"))
        self.assertEqual(response["Location"], f"/admin/llm/llmprovider/add/?website={self.site.pk}")

    def test_delete_returns_to_website(self):
        provider = make_provider(self.site)
        response = self.client.post(f"/admin/llm/llmprovider/{provider.pk}/delete/", {"post": "yes"})
        self.assertRedirects(response, f"/admin/websites/website/{self.site.pk}/change/", fetch_redirect_response=False)
        self.assertFalse(LLMProvider.objects.exists())

    def test_duplicate_name_on_same_website_rejected(self):
        make_provider(self.site, "Groq", api_type="openai")
        response = self.client.post("/admin/llm/llmprovider/add/", self.provider_data(name="groq"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("name", response.context["adminform"].form.errors)

    def test_same_name_on_another_website_allowed(self):
        make_provider(make_site(domain="other.example.com"), "Groq", api_type="openai")
        self.assertEqual(self.client.post("/admin/llm/llmprovider/add/", self.provider_data()).status_code, 302)

    def test_website_required(self):
        response = self.client.post("/admin/llm/llmprovider/add/", self.provider_data(website=""))
        self.assertEqual(response.status_code, 200)
        self.assertIn("website", response.context["adminform"].form.errors)

    def test_key_required_on_add(self):
        response = self.client.post("/admin/llm/llmprovider/add/", self.provider_data(api_key=""))
        self.assertEqual(response.status_code, 200)
        self.assertIn("api_key", response.context["adminform"].form.errors)

    def test_two_default_models_rejected(self):
        response = self.client.post("/admin/llm/llmprovider/add/", self.provider_data(**{"models-1-is_default": "on"}))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(LLMProvider.objects.exists())

    @override_settings(LLM_ENCRYPTION_KEYS=[])
    def test_missing_encryption_key_is_a_form_error(self):
        response = self.client.post("/admin/llm/llmprovider/add/", self.provider_data())
        self.assertEqual(response.status_code, 200)
        self.assertIn("LLM_ENCRYPTION_KEYS", str(response.context["adminform"].form.errors))

    def test_not_listed_in_admin_menu(self):
        index = self.client.get("/admin/")
        self.assertNotContains(index, "/admin/llm/")
        self.assertContains(index, "/admin/websites/website/")


@override_settings(LLM_ENCRYPTION_KEYS=[ENC_KEY])
class WebsitePageTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("admin", "admin@example.com", "pw")
        self.client.force_login(self.admin)
        self.site = make_site(self.admin)

    def test_website_page_lists_its_providers_with_add_button(self):
        groq = make_provider(self.site, "Groq", api_type="openai", key="gsk-aaaa-5555",
                             models=("llama-3.3-70b-versatile", "llama-3.1-8b-instant"))
        make_provider(self.site, "OpenAI", api_type="openai", models=("gpt-4o",))
        make_provider(make_site(domain="other.example.com"), "Other site provider")

        page = self.client.get(f"/admin/websites/website/{self.site.pk}/change/")
        self.assertContains(page, f"/admin/llm/llmprovider/add/?website={self.site.pk}")
        self.assertContains(page, f"/admin/llm/llmprovider/{groq.pk}/change/")
        self.assertContains(page, "llama-3.3-70b-versatile ★")
        self.assertContains(page, "…5555")
        self.assertContains(page, "● Active")
        self.assertContains(page, "OpenAI")
        self.assertNotContains(page, "Other site provider")
        self.assertContains(page, "<strong>Groq</strong> · <code>llama-3.3-70b-versatile</code>", html=False)

    def test_add_website_page_explains_save_first(self):
        self.assertContains(self.client.get("/admin/websites/website/add/"), "Save the website first")

    def test_website_without_provider_shows_fallback(self):
        page = self.client.get(f"/admin/websites/website/{self.site.pk}/change/")
        self.assertContains(page, "No providers yet")
        self.assertContains(page, "web-agent&#x27;s own .env settings")

    def test_list_column_shows_active_provider(self):
        make_provider(self.site, "Groq", api_type="openai", models=("llama-3.3-70b-versatile",))
        self.assertContains(self.client.get("/admin/websites/website/"), "Groq · llama-3.3-70b-versatile")


@override_settings(LLM_ENCRYPTION_KEYS=[ENC_KEY], CHATBOT_SERVICE_TOKENS=[TOKEN])
class LLMConfigEndpointTests(TestCase):
    def setUp(self):
        cache.clear()
        self.site = make_site()
        self.groq = make_provider(self.site, "Groq", api_type="openai", key="gsk-groq-2222",
                                  base_url="https://api.groq.com/openai/v1",
                                  models=("llama-3.3-70b-versatile", "llama-3.1-8b-instant"))
        self.claude = make_provider(self.site, "Anthropic", key="sk-ant-1111", models=("claude-sonnet-5-5",))

    def call(self, body=None, token=TOKEN):
        headers = {"HTTP_AUTHORIZATION": f"Bearer {token}"} if token else {}
        return self.client.post(URL, json.dumps(body if body is not None else {}), content_type="application/json", **headers)

    def test_requires_service_token(self):
        self.assertEqual(self.call(token=None).status_code, 401)
        self.assertEqual(self.call(token="wrong").status_code, 401)

    def test_returns_websites_active_provider_and_default_model(self):
        response = self.call({"site_id": str(self.site.pk)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "provider": "Groq", "provider_id": str(self.groq.pk), "api_type": "openai",
            "base_url": "https://api.groq.com/openai/v1", "model": "llama-3.3-70b-versatile",
            "api_key": "gsk-groq-2222", "source": "website",
        })
        self.assertIn("no-cache", response["Cache-Control"])

    def test_switching_active_provider(self):
        self.claude.is_default = True
        self.claude.save()
        data = self.call({"site_id": str(self.site.pk)}).json()
        self.assertEqual((data["provider"], data["model"], data["api_key"]), ("Anthropic", "claude-sonnet-5-5", "sk-ant-1111"))

    def test_other_websites_provider_never_used(self):
        other = make_site(domain="other.example.com")
        make_provider(other, "Other", key="sk-other-9999", models=("x",))
        self.assertEqual(self.call({"site_id": str(self.site.pk)}).json()["api_key"], "gsk-groq-2222")

    def test_inactive_default_model_falls_back_to_first_active_model(self):
        LLMModel.objects.filter(provider=self.groq, is_default=True).update(is_active=False)
        self.assertEqual(self.call({"site_id": str(self.site.pk)}).json()["model"], "llama-3.1-8b-instant")

    def test_disabled_active_provider_is_not_configured(self):
        LLMProvider.objects.filter(pk=self.groq.pk).update(is_active=False)
        response = self.call({"site_id": str(self.site.pk)})
        self.assertEqual((response.status_code, response.json()), (404, {"error": "llm_not_configured"}))

    def test_site_without_providers_is_not_configured(self):
        other = make_site(domain="empty.example.com")
        self.assertEqual(self.call({"site_id": str(other.pk)}).json(), {"error": "llm_not_configured"})

    def test_no_site_id_is_not_configured(self):
        self.assertEqual(self.call({}).json(), {"error": "llm_not_configured"})

    def test_unknown_site_and_bad_input(self):
        self.assertEqual(self.call({"site_id": "999999"}).json(), {"error": "site_not_found"})
        for bad in [{"site_id": 3}, {"site_id": "abc"}, {"site_id": "1" * 25}]:
            self.assertEqual(self.call(bad).status_code, 400, bad)

    def test_undecryptable_key_returns_503_without_leaking(self):
        with self.settings(LLM_ENCRYPTION_KEYS=[Fernet.generate_key().decode()]):
            response = self.call({"site_id": str(self.site.pk)})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"error": "service_unavailable"})

    def test_database_error(self):
        with mock.patch("websites.views.Website.objects.filter", side_effect=DatabaseError("x")):
            response = self.call({"site_id": str(self.site.pk)})
        self.assertEqual(response.status_code, 503)


# --- Provider catalog, key links and model loading --------------------------------

from .catalog import PRESETS, ModelListError, fetch_models  # noqa: E402


def fake_response(status=200, payload=None):
    response = mock.Mock(status_code=status, ok=status < 400)
    response.json.return_value = payload if payload is not None else {}
    return response


class FetchModelsTests(TestCase):
    @mock.patch("llm.catalog.requests.get")
    def test_anthropic_paginates_and_uses_key_header(self, get):
        get.side_effect = [
            fake_response(200, {"data": [{"id": "claude-opus-5-5", "display_name": "Claude Opus 5.5"}],
                                "has_more": True, "last_id": "claude-opus-5-5"}),
            fake_response(200, {"data": [{"id": "claude-haiku-4-5-20251001", "display_name": "Claude Haiku 4.5"}],
                                "has_more": False}),
        ]
        models = fetch_models("anthropic", "", "sk-ant-x")
        self.assertEqual([m["id"] for m in models], ["claude-haiku-4-5-20251001", "claude-opus-5-5"])
        self.assertEqual(get.call_args_list[0].kwargs["headers"]["x-api-key"], "sk-ant-x")
        self.assertEqual(get.call_args_list[1].kwargs["params"]["after_id"], "claude-opus-5-5")

    @mock.patch("llm.catalog.requests.get")
    def test_openai_compatible_filters_non_chat_and_strips_gemini_prefix(self, get):
        get.return_value = fake_response(200, {"data": [
            {"id": "models/gemini-2.5-flash"}, {"id": "gpt-4o-mini"}, {"id": "text-embedding-3-small"},
            {"id": "whisper-1"}, {"id": "dall-e-3"}, {"id": "tts-1"}, {"id": "gpt-4o-mini"},
        ]})
        models = fetch_models("openai", "https://example.test/v1/", "k")
        self.assertEqual([m["id"] for m in models], ["gemini-2.5-flash", "gpt-4o-mini"])
        self.assertEqual(get.call_args.args[0], "https://example.test/v1/models")
        self.assertEqual(get.call_args.kwargs["headers"]["Authorization"], "Bearer k")

    @mock.patch("llm.catalog.requests.get")
    def test_openai_default_base_url(self, get):
        get.return_value = fake_response(200, {"data": []})
        fetch_models("openai", "", "k")
        self.assertEqual(get.call_args.args[0], "https://api.openai.com/v1/models")

    @mock.patch("llm.catalog.requests.get")
    def test_errors_are_friendly(self, get):
        for status, text in [(401, "rejected this API key"), (404, "no model list"), (500, "HTTP 500")]:
            get.return_value = fake_response(status)
            with self.assertRaisesMessage(ModelListError, text):
                fetch_models("openai", "", "k")

    def test_every_preset_is_consistent(self):
        for key, preset in PRESETS.items():
            self.assertIn(preset["api_type"], ("anthropic", "openai"), key)
            if not preset.get("custom"):
                self.assertTrue(preset["key_url"].startswith("https://"), key)
                self.assertTrue(preset["name"], key)


@override_settings(LLM_ENCRYPTION_KEYS=[ENC_KEY])
class ProviderFormPresetTests(TestCase):
    LOAD_URL = "/admin/llm/llmprovider/load-models/"

    def setUp(self):
        self.admin = User.objects.create_superuser("admin", "admin@example.com", "pw")
        self.client.force_login(self.admin)
        self.site = make_site(self.admin)

    def form_data(self, **overrides):
        data = {
            "website": self.site.pk, "preset": "openai", "name": "OpenAI", "api_type": "openai", "base_url": "",
            "api_key": "sk-test-0000", "is_active": "on", "selected_models": "[]",
            "models-TOTAL_FORMS": "0", "models-INITIAL_FORMS": "0",
            "models-MIN_NUM_FORMS": "0", "models-MAX_NUM_FORMS": "1000",
        }
        data.update(overrides)
        return data

    def load(self, **body):
        return self.client.post(self.LOAD_URL, json.dumps(body), content_type="application/json")

    def test_add_page_has_provider_select_key_link_data_and_picker(self):
        page = self.client.get(f"/admin/llm/llmprovider/add/?website={self.site.pk}")
        self.assertContains(page, 'id="id_preset"')
        for name in ["Anthropic", "OpenAI", "Google Gemini", "Groq", "OpenRouter", "DeepSeek", "Mistral", "Ollama (local)"]:
            self.assertContains(page, f">{name}</option>")
        self.assertContains(page, 'id="llm-presets"')
        self.assertContains(page, "https://console.anthropic.com/settings/keys")
        self.assertContains(page, "llm/provider_form.js")
        self.assertContains(page, 'name="selected_models"')

    def test_ticked_models_are_created_and_first_becomes_default(self):
        response = self.client.post("/admin/llm/llmprovider/add/", self.form_data(
            selected_models=json.dumps(["gpt-4o-mini", "gpt-4o", "gpt-4o-mini"]),
        ))
        self.assertEqual(response.status_code, 302)
        provider = LLMProvider.objects.get()
        self.assertEqual(sorted(provider.models.values_list("model_id", flat=True)), ["gpt-4o", "gpt-4o-mini"])
        self.assertEqual(provider.default_model().model_id, "gpt-4o-mini")

    def test_ticking_existing_model_does_not_duplicate_or_steal_default(self):
        provider = make_provider(self.site, "OpenAI", api_type="openai", models=("gpt-4o",))
        data = self.form_data(api_key="", selected_models=json.dumps(["gpt-4o", "o4-mini"]))
        data.pop("website")
        model = provider.models.get()
        data.update({
            "models-TOTAL_FORMS": "1", "models-INITIAL_FORMS": "1", "models-0-id": model.pk,
            "models-0-provider": provider.pk, "models-0-model_id": "gpt-4o",
            "models-0-is_active": "on", "models-0-is_default": "on",
        })
        self.assertEqual(self.client.post(f"/admin/llm/llmprovider/{provider.pk}/change/", data).status_code, 302)
        self.assertEqual(provider.models.count(), 2)
        self.assertEqual(provider.default_model().model_id, "gpt-4o")

    def test_invalid_model_id_rejected(self):
        response = self.client.post("/admin/llm/llmprovider/add/", self.form_data(selected_models='["bad id!"]'))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(LLMProvider.objects.exists())

    def test_ollama_needs_no_key(self):
        response = self.client.post("/admin/llm/llmprovider/add/", self.form_data(
            preset="ollama", name="Ollama", base_url="http://127.0.0.1:11434/v1", api_key="",
        ))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(LLMProvider.objects.get().get_api_key(), "ollama")

    def test_custom_requires_base_url(self):
        response = self.client.post("/admin/llm/llmprovider/add/", self.form_data(preset="custom", name="Mine"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("base_url", response.context["adminform"].form.errors)

    @mock.patch("llm.admin.fetch_models", return_value=[{"id": "gpt-4o", "name": "gpt-4o"}])
    def test_load_models_with_pasted_key(self, fetch):
        response = self.load(api_type="openai", base_url="", api_key="sk-pasted")
        self.assertEqual(response.json(), {"models": [{"id": "gpt-4o", "name": "gpt-4o"}]})
        fetch.assert_called_once_with("openai", "", "sk-pasted")

    @mock.patch("llm.admin.fetch_models", return_value=[{"id": "m", "name": "m"}])
    def test_load_models_reuses_stored_key_when_editing(self, fetch):
        provider = make_provider(self.site, "Groq", api_type="openai", key="gsk-stored-9999")
        self.load(api_type="openai", base_url="https://api.groq.com/openai/v1", api_key="", provider_id=str(provider.pk))
        self.assertEqual(fetch.call_args.args[2], "gsk-stored-9999")

    @mock.patch("llm.admin.fetch_models", side_effect=ModelListError("The provider rejected this API key."))
    def test_load_models_error_message(self, fetch):
        response = self.load(api_type="openai", api_key="bad")
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json(), {"error": "The provider rejected this API key."})

    def test_load_models_validation(self):
        self.assertEqual(self.load(api_type="cohere", api_key="k").status_code, 400)
        self.assertEqual(self.load(api_type="openai", api_key="").status_code, 400)
        self.assertEqual(self.load(api_type="openai", api_key="k", base_url="ftp://x").status_code, 400)
        self.assertEqual(self.load(api_type="openai", api_key="", provider_id="abc").status_code, 400)

    @override_settings(DEBUG=False)
    def test_plain_http_base_url_blocked_in_production(self):
        response = self.load(api_type="openai", api_key="k", base_url="http://10.0.0.5/v1")
        self.assertEqual(response.status_code, 400)

    def test_load_models_requires_staff_and_post(self):
        self.assertEqual(self.client.get(self.LOAD_URL).status_code, 405)
        self.client.logout()
        self.assertEqual(self.load(api_type="openai", api_key="k").status_code, 302)  # to login
        self.client.force_login(User.objects.create_user("staff", password="pw", is_staff=True))
        self.assertEqual(self.load(api_type="openai", api_key="k").status_code, 403)

    def test_list_shows_key_link(self):
        make_provider(self.site, "Anthropic", preset="anthropic")
        self.assertContains(self.client.get("/admin/llm/llmprovider/"), "Manage keys")
