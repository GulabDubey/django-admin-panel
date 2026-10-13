import json
from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import DatabaseError
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from packages.models import Package
from payments.models import Payment
from .domains import normalize_domain
from .models import Website

URL = "/api/internal/chatbot/verify-subscription/"
TOKEN = "current-service-token-0123456789abcdef"
OLD_TOKEN = "previous-service-token-0123456789abcd"


class NormalizeDomainTests(SimpleTestCase):
    def test_normalizes_urls_and_hosts(self):
        cases = {
            "example.com": "example.com",
            "WWW.Example.COM": "example.com",
            "https://www.example.com:443/pricing?x=1": "example.com",
            "shop.example.co.in.": "shop.example.co.in",
            "bücher.de": "xn--bcher-kva.de",
        }
        for value, expected in cases.items():
            self.assertEqual(normalize_domain(value), expected, value)

    def test_rejects_invalid(self):
        for value in ["", "   ", "localhost", "exa mple.com", "http://", "-bad-.com", "a" * 300 + ".com", None]:
            self.assertEqual(normalize_domain(value, allow_local=False), "", value)

    def test_local_hosts_keep_port_when_allowed(self):
        cases = {
            "http://127.0.0.1:8012": "127.0.0.1:8012",
            "http://127.0.0.1:8012/some/page?x=1": "127.0.0.1:8012",
            "127.0.0.1:8012": "127.0.0.1:8012",
            "http://LOCALHOST:3000/": "localhost:3000",
            "http://[::1]:8012": "[::1]:8012",
            "http://127.0.0.1": "127.0.0.1",
            # Public domains are unaffected: port still stripped.
            "https://www.example.com:8443": "example.com",
        }
        for value, expected in cases.items():
            self.assertEqual(normalize_domain(value, allow_local=True), expected, value)

    def test_local_hosts_rejected_when_not_allowed(self):
        for value in ["http://127.0.0.1:8012", "localhost:3000", "http://[::1]:8012"]:
            self.assertEqual(normalize_domain(value, allow_local=False), "", value)

    def test_invalid_port_rejected(self):
        self.assertEqual(normalize_domain("http://127.0.0.1:99999", allow_local=True), "")

    def test_defaults_to_debug_setting(self):
        with self.settings(DEBUG=True):
            self.assertEqual(normalize_domain("http://127.0.0.1:8012"), "127.0.0.1:8012")
        with self.settings(DEBUG=False):
            self.assertEqual(normalize_domain("http://127.0.0.1:8012"), "")


@override_settings(CHATBOT_SERVICE_TOKENS=[TOKEN, OLD_TOKEN])
class VerifySubscriptionTests(TestCase):
    def setUp(self):
        cache.clear()
        self.plan = Package.objects.create(name="Professional", price=7999, duration=30)
        self.customer = User.objects.create_user("cust@example.com", "cust@example.com", "pw")
        self.website = Website.objects.create(owner=self.customer, name="Customer", domain="customer-example.com")

    def pay(self, user=None, email=None, status="paid", days_ago=0, package="default"):
        payment = Payment.objects.create(
            user=user,
            package=self.plan if package == "default" else package,
            buyer_name="Buyer",
            buyer_email=email or (user.email if user else "guest@example.com"),
            razorpay_order_id=f"order_{Payment.objects.count() + 1}",
            amount=7999,
            status=status,
        )
        # created_at is auto_now_add, so backdate with update().
        Payment.objects.filter(pk=payment.pk).update(created_at=timezone.now() - timedelta(days=days_ago))
        return payment

    def verify(self, site_key=None, domain="customer-example.com", token=TOKEN, body=None):
        headers = {"HTTP_AUTHORIZATION": f"Bearer {token}"} if token is not None else {}
        payload = body if body is not None else json.dumps(
            {"site_key": site_key or self.website.site_key, "domain": domain}
        )
        return self.client.post(URL, payload, content_type="application/json", **headers)

    def assertDenied(self, response, reason, status=403):
        self.assertEqual(response.status_code, status)
        self.assertEqual(response.json(), {"authorized": False, "reason": reason})

    # --- Service credential ---------------------------------------------------

    def test_active_subscription_authorized(self):
        payment = self.pay(user=self.customer, days_ago=5)
        response = self.verify()

        self.assertEqual(response.status_code, 200)
        expected_expiry = Payment.objects.get(pk=payment.pk).created_at + timedelta(days=30)
        self.assertEqual(response.json(), {
            "authorized": True,
            "site_id": str(self.website.pk),
            "customer_id": str(self.customer.pk),
            "plan": "Professional",
            "expires_at": expected_expiry.strftime("%Y-%m-%dT%H:%M:%SZ"),
        })
        self.assertEqual(response["Cache-Control"].split(",")[0], "max-age=0")

    def test_previous_token_still_accepted_during_rotation(self):
        self.pay(user=self.customer)
        self.assertEqual(self.verify(token=OLD_TOKEN).status_code, 200)

    def test_missing_credential(self):
        self.pay(user=self.customer)
        response = self.verify(token=None)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"error": "unauthorized"})

    def test_invalid_credential(self):
        self.pay(user=self.customer)
        for token in ["wrong", TOKEN[:-1], TOKEN + "x", ""]:
            self.assertEqual(self.verify(token=token).status_code, 401, token)

    def test_non_bearer_scheme_rejected(self):
        response = self.client.post(
            URL, "{}", content_type="application/json", HTTP_AUTHORIZATION=f"Basic {TOKEN}"
        )
        self.assertEqual(response.status_code, 401)

    def test_site_key_is_not_a_service_credential(self):
        self.pay(user=self.customer)
        self.assertEqual(self.verify(token=self.website.site_key).status_code, 401)

    @override_settings(CHATBOT_SERVICE_TOKENS=[])
    def test_unconfigured_tokens_fail_closed(self):
        self.pay(user=self.customer)
        self.assertEqual(self.verify(token="").status_code, 503)

    def test_get_not_allowed(self):
        self.assertEqual(self.client.get(URL, HTTP_AUTHORIZATION=f"Bearer {TOKEN}").status_code, 405)

    # --- Request validation ---------------------------------------------------

    def test_invalid_payloads(self):
        for body in ["not json", "[]", json.dumps({"domain": "customer-example.com"}),
                     json.dumps({"site_key": "x", "domain": ""}),
                     json.dumps({"site_key": 123, "domain": "customer-example.com"}),
                     json.dumps({"site_key": "x" * 65, "domain": "customer-example.com"})]:
            self.assertDenied(self.verify(body=body), "invalid_request", status=400)

    # --- Website / domain -------------------------------------------------------

    def test_invalid_site_key(self):
        self.pay(user=self.customer)
        self.assertDenied(self.verify(site_key="site_doesnotexist"), "invalid_site_key")

    def test_unregistered_domain(self):
        self.pay(user=self.customer)
        self.assertDenied(self.verify(domain="attacker.com"), "domain_not_allowed")
        self.assertDenied(self.verify(domain="evil.customer-example.com"), "domain_not_allowed")

    def test_domain_variants_of_approved_domain_accepted(self):
        self.pay(user=self.customer)
        for domain in ["https://www.Customer-Example.com/page", "customer-example.com:8443"]:
            self.assertEqual(self.verify(domain=domain).status_code, 200, domain)

    def test_disabled_website(self):
        self.pay(user=self.customer)
        Website.objects.filter(pk=self.website.pk).update(is_active=False)
        self.assertDenied(self.verify(), "site_disabled")

    def test_deactivated_customer(self):
        self.pay(user=self.customer)
        User.objects.filter(pk=self.customer.pk).update(is_active=False)
        self.assertDenied(self.verify(), "site_disabled")

    # --- Payment / subscription ---------------------------------------------

    def test_missing_payment_records(self):
        self.assertDenied(self.verify(), "subscription_inactive")

    def test_unpaid_and_failed_payments(self):
        self.pay(user=self.customer, status="created")
        self.pay(user=self.customer, status="failed")
        self.assertDenied(self.verify(), "subscription_inactive")

    def test_expired_subscription(self):
        self.pay(user=self.customer, days_ago=31)
        self.assertDenied(self.verify(), "subscription_expired")

    def test_renewal_after_expiry_restores_access(self):
        self.pay(user=self.customer, days_ago=40)
        self.pay(user=self.customer, days_ago=2)
        self.assertEqual(self.verify().status_code, 200)

    def test_payment_belonging_to_another_customer(self):
        other = User.objects.create_user("other@example.com", "other@example.com", "pw")
        self.pay(user=other)
        self.pay(email="someone-else@example.com")  # guest payment, different email
        self.assertDenied(self.verify(), "subscription_inactive")

    def test_other_users_payment_with_same_email_not_counted(self):
        # Email fallback applies only to guest checkouts, never to another account's payment.
        other = User.objects.create_user("other", "other@example.com", "pw")
        self.pay(user=other, email="cust@example.com")
        self.assertDenied(self.verify(), "subscription_inactive")

    def test_guest_checkout_with_owner_email_counts(self):
        self.pay(email="CUST@example.com")
        self.assertEqual(self.verify().status_code, 200)

    def test_paid_payment_without_plan_not_counted(self):
        self.pay(user=self.customer, package=None)
        self.assertDenied(self.verify(), "subscription_inactive")

    # --- Failures ----------------------------------------------------------------

    def test_database_error_returns_503_without_details(self):
        with mock.patch("websites.views.Website.objects.select_related", side_effect=DatabaseError("boom: secret")):
            response = self.verify()
        self.assertDenied(response, "service_unavailable", status=503)
        self.assertNotIn(b"boom", response.content)

    def test_rate_limited(self):
        self.pay(user=self.customer)
        with mock.patch("core.ratelimit.cache.incr", return_value=10_000):
            response = self.verify()
        self.assertEqual(response.status_code, 429)


@override_settings(CHATBOT_SERVICE_TOKENS=[TOKEN])
class LocalDomainTests(TestCase):
    """Local development addresses (e.g. http://127.0.0.1:8012) are only usable with DEBUG on."""

    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_superuser("admin", "admin@example.com", "pw")
        plan = Package.objects.create(name="Starter", price=2999, duration=30)
        Payment.objects.create(
            user=self.owner, package=plan, buyer_name="A", buyer_email="admin@example.com",
            razorpay_order_id="order_local", amount=2999, status="paid",
        )
        self.client.force_login(self.owner)

    def add_via_admin(self, domain):
        return self.client.post("/admin/websites/website/add/", {
            "name": "Local app", "domain": domain, "owner": self.owner.pk, "is_active": "on",
        })

    def verify(self, site_key, domain):
        return self.client.post(
            URL, json.dumps({"site_key": site_key, "domain": domain}),
            content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {TOKEN}",
        )

    @override_settings(DEBUG=True)
    def test_admin_accepts_local_address_in_debug_and_verify_matches_port(self):
        response = self.add_via_admin("http://127.0.0.1:8012")
        self.assertEqual(response.status_code, 302)
        website = Website.objects.get()
        self.assertEqual(website.domain, "127.0.0.1:8012")

        self.assertEqual(self.verify(website.site_key, "http://127.0.0.1:8012/chat").status_code, 200)
        # A different local port is a different site.
        response = self.verify(website.site_key, "http://127.0.0.1:8000")
        self.assertEqual(response.json()["reason"], "domain_not_allowed")

    @override_settings(DEBUG=False)
    def test_admin_rejects_local_address_without_debug(self):
        response = self.add_via_admin("http://127.0.0.1:8012")
        self.assertEqual(response.status_code, 200)
        self.assertIn("domain", response.context["adminform"].form.errors)
        self.assertFalse(Website.objects.exists())

    @override_settings(DEBUG=False)
    def test_local_record_left_from_debug_never_authorizes_in_production(self):
        with self.settings(DEBUG=True):
            website = Website.objects.create(owner=self.owner, name="Local", domain="http://127.0.0.1:8012")
        self.assertEqual(website.domain, "127.0.0.1:8012")

        response = self.verify(website.site_key, "http://127.0.0.1:8012")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["authorized"])


class WebsiteModelTests(TestCase):
    def test_domain_normalized_and_site_key_generated(self):
        owner = User.objects.create_user("o", "o@example.com", "pw")
        a = Website.objects.create(owner=owner, name="A", domain="https://WWW.Shop.example.com/")
        b = Website.objects.create(owner=owner, name="B", domain="other.com")
        self.assertEqual(a.domain, "shop.example.com")
        self.assertTrue(a.site_key.startswith("site_"))
        self.assertNotEqual(a.site_key, b.site_key)


class CrawlAccessTests(TestCase):
    """Crawls (which call the costly crawler API) can only be started by authorized staff."""

    def test_anonymous_and_non_staff_cannot_start_crawls(self):
        from crawler.models import WebsiteCrawl

        crawl = WebsiteCrawl.objects.create(url="https://example.com/", status="failed")
        targets = ["/admin/crawler/websitecrawl/add/", f"/admin/crawler/websitecrawl/{crawl.pk}/rerun/"]

        for target in targets:
            response = self.client.post(target, {"url": "https://example.com/", "max_pages": 5})
            self.assertEqual(response.status_code, 302, target)
            self.assertIn("/admin/login/", response["Location"])

        self.client.force_login(User.objects.create_user("customer", password="pw"))
        for target in targets:
            response = self.client.post(target, {"url": "https://example.com/", "max_pages": 5})
            self.assertEqual(response.status_code, 302, target)
            self.assertIn("/admin/login/", response["Location"])

        self.assertEqual(WebsiteCrawl.objects.count(), 1)
