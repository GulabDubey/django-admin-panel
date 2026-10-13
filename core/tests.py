from django.core.cache import cache
from django.test import TestCase, override_settings


class HealthCheckTests(TestCase):
    @override_settings(ALLOWED_HOSTS=["example.com"], SECURE_SSL_REDIRECT=True)
    def test_healthz_bypasses_host_check_and_ssl_redirect(self):
        response = self.client.get("/healthz/", HTTP_HOST="10.0.0.5")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})


class HomeTests(TestCase):
    def test_home_renders_and_sets_csrf_cookie(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("csrftoken", response.cookies)

    @override_settings(CHATBOT_WIDGET_URL="")
    def test_chatbot_widget_omitted_when_unset(self):
        response = self.client.get("/")
        self.assertNotContains(response, "chatbot.js")


class RateLimitTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_login_is_rate_limited(self):
        for _ in range(10):
            response = self.client.post(
                "/accounts/login/", {"email": "a@b.com", "password": "x"}, content_type="application/json"
            )
            self.assertEqual(response.status_code, 400)

        response = self.client.post(
            "/accounts/login/", {"email": "a@b.com", "password": "x"}, content_type="application/json"
        )
        self.assertEqual(response.status_code, 429)
