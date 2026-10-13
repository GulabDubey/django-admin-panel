from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase


class RegisterTests(TestCase):
    def setUp(self):
        cache.clear()

    def register(self, password):
        return self.client.post(
            "/accounts/register/",
            {
                "name": "Asha",
                "email": "asha@example.com",
                "contact": "9999999999",
                "password": password,
                "confirm_password": password,
            },
            content_type="application/json",
        )

    def test_weak_password_rejected(self):
        response = self.register("password123")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["field"], "password")
        self.assertFalse(User.objects.exists())

    def test_register_creates_user_and_profile(self):
        response = self.register("v3ry-Str0ng-pass")
        self.assertEqual(response.status_code, 200)
        user = User.objects.get(email="asha@example.com")
        self.assertEqual(user.profile.contact, "9999999999")
