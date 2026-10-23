import json
from datetime import datetime
from unittest import mock
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.management import call_command
from django.db import DatabaseError
from django.test import TestCase, override_settings
from django.utils import timezone

from .models import QuestionUsage, Website
from .questions import TOTAL_PERIOD_START, consume_question, current_period, refund_question

TOKEN = "service-token-0123456789abcdefghijklmnop"
VISITOR = "v_" + "a" * 30
OTHER_VISITOR = "v_" + "b" * 30
IP = "c" * 64
CONSUME = "/api/internal/chatbot/questions/consume/"
REFUND = "/api/internal/chatbot/questions/refund/"
IST = ZoneInfo("Asia/Kolkata")


def make_site(limit=3, period=Website.PERIOD_DAY, domain="q.example.com", message=""):
    owner = User.objects.create_user(f"o-{domain}", f"o@{domain}", "pw")
    return Website.objects.create(owner=owner, name=domain, domain=domain, question_limit=limit,
                                  question_limit_period=period, question_limit_message=message)


class PeriodTests(TestCase):
    def test_period_boundaries_in_local_time(self):
        now = datetime(2026, 10, 24, 15, 40, tzinfo=IST)  # Saturday
        self.assertEqual(current_period("hour", now).start, datetime(2026, 10, 24, 15, 0, tzinfo=IST))
        day = current_period("day", now)
        self.assertEqual((day.start, day.resets_at), (datetime(2026, 10, 24, tzinfo=IST), datetime(2026, 10, 25, tzinfo=IST)))
        week = current_period("week", now)
        self.assertEqual((week.start, week.resets_at), (datetime(2026, 10, 19, tzinfo=IST), datetime(2026, 10, 26, tzinfo=IST)))
        month = current_period("month", now)
        self.assertEqual((month.start, month.resets_at), (datetime(2026, 10, 1, tzinfo=IST), datetime(2026, 11, 1, tzinfo=IST)))
        december = current_period("month", datetime(2026, 12, 9, tzinfo=IST))
        self.assertEqual(december.resets_at, datetime(2027, 1, 1, tzinfo=IST))
        total = current_period("total", now)
        self.assertEqual((total.start, total.resets_at), (TOTAL_PERIOD_START, None))


@override_settings(CHATBOT_IP_QUESTION_MULTIPLIER=2)
class ConsumeTests(TestCase):
    def test_counts_until_limit_then_refuses(self):
        site = make_site(limit=2)
        first = consume_question(site, VISITOR, IP)
        self.assertEqual((first.allowed, first.remaining), (True, 1))
        self.assertEqual(consume_question(site, VISITOR, IP).remaining, 0)
        denied = consume_question(site, VISITOR, IP)
        self.assertFalse(denied.allowed)
        self.assertEqual(denied.reason, "question_limit")
        self.assertEqual(QuestionUsage.objects.get(kind="visitor").count, 2)

    def test_limits_are_per_visitor(self):
        site = make_site(limit=1)
        self.assertTrue(consume_question(site, VISITOR).allowed)
        self.assertFalse(consume_question(site, VISITOR).allowed)
        self.assertTrue(consume_question(site, OTHER_VISITOR).allowed)

    def test_limits_are_per_website(self):
        a, b = make_site(limit=1), make_site(limit=1, domain="b.example.com")
        self.assertTrue(consume_question(a, VISITOR).allowed)
        self.assertTrue(consume_question(b, VISITOR).allowed)

    def test_ip_backstop_stops_new_visitor_ids_from_same_ip(self):
        site = make_site(limit=1)  # IP allowance = 1 × 2
        self.assertTrue(consume_question(site, "v_" + "1" * 30, IP).allowed)
        self.assertTrue(consume_question(site, "v_" + "2" * 30, IP).allowed)
        denied = consume_question(site, "v_" + "3" * 30, IP)
        self.assertFalse(denied.allowed)
        # The refused question was not counted for the new visitor either.
        self.assertEqual(QuestionUsage.objects.get(identity="v_" + "3" * 30).count, 0)

    @override_settings(CHATBOT_IP_QUESTION_MULTIPLIER=0)
    def test_ip_backstop_can_be_disabled(self):
        site = make_site(limit=1)
        for i in range(5):
            self.assertTrue(consume_question(site, f"v_{i}" + "x" * 30, IP).allowed)
        self.assertFalse(QuestionUsage.objects.filter(kind="ip").exists())

    def test_unlimited_counts_nothing(self):
        site = make_site(limit=0)
        decision = consume_question(site, VISITOR, IP)
        self.assertEqual((decision.allowed, decision.limit, decision.remaining), (True, 0, None))
        self.assertFalse(QuestionUsage.objects.exists())

    def test_new_period_resets(self):
        site = make_site(limit=1)
        with mock.patch("websites.questions.timezone.now", return_value=datetime(2026, 10, 24, 23, 0, tzinfo=IST)):
            self.assertTrue(consume_question(site, VISITOR).allowed)
            self.assertFalse(consume_question(site, VISITOR).allowed)
        with mock.patch("websites.questions.timezone.now", return_value=datetime(2026, 10, 25, 0, 5, tzinfo=IST)):
            self.assertTrue(consume_question(site, VISITOR).allowed)

    def test_total_never_resets(self):
        site = make_site(limit=1, period=Website.PERIOD_TOTAL)
        self.assertTrue(consume_question(site, VISITOR).allowed)
        with mock.patch("websites.questions.timezone.now", return_value=timezone.now() + timezone.timedelta(days=400)):
            denied = consume_question(site, VISITOR)
        self.assertFalse(denied.allowed)
        self.assertIsNone(denied.resets_at)

    def test_custom_and_default_messages(self):
        site = make_site(limit=1, message="Upgrade to ask more!")
        consume_question(site, VISITOR)
        self.assertEqual(consume_question(site, VISITOR).message, "Upgrade to ask more!")
        plain = make_site(limit=1, domain="p.example.com")
        consume_question(plain, VISITOR)
        self.assertIn("question limit", consume_question(plain, VISITOR).message)

    def test_refund(self):
        site = make_site(limit=1)
        consume_question(site, VISITOR, IP)
        refund_question(site, VISITOR, IP)
        self.assertTrue(consume_question(site, VISITOR, IP).allowed)
        refund_question(site, VISITOR, IP)
        refund_question(site, VISITOR, IP)  # never below zero
        self.assertEqual(set(QuestionUsage.objects.values_list("count", flat=True)), {0})


@override_settings(CHATBOT_SERVICE_TOKENS=[TOKEN], CHATBOT_IP_QUESTION_MULTIPLIER=5)
class QuestionEndpointTests(TestCase):
    def setUp(self):
        cache.clear()
        self.site = make_site(limit=2)

    def post(self, url, body, token=TOKEN):
        headers = {"HTTP_AUTHORIZATION": f"Bearer {token}"} if token else {}
        return self.client.post(url, json.dumps(body), content_type="application/json", **headers)

    def body(self, **overrides):
        return {"site_id": str(self.site.pk), "visitor_id": VISITOR, "ip_hash": IP, **overrides}

    def test_requires_service_token(self):
        self.assertEqual(self.post(CONSUME, self.body(), token=None).status_code, 401)
        self.assertEqual(self.post(REFUND, self.body(), token="wrong").status_code, 401)

    def test_consume_then_limit(self):
        first = self.post(CONSUME, self.body()).json()
        self.assertEqual((first["allowed"], first["limit"], first["remaining"], first["period"]), (True, 2, 1, "day"))
        self.assertTrue(first["resets_at"].endswith("Z"))
        self.post(CONSUME, self.body())
        denied = self.post(CONSUME, self.body())
        self.assertEqual(denied.status_code, 200)
        self.assertEqual((denied.json()["allowed"], denied.json()["reason"]), (False, "question_limit"))

    def test_refund_endpoint(self):
        self.post(CONSUME, self.body())
        self.post(CONSUME, self.body())
        self.assertEqual(self.post(REFUND, self.body()).json(), {"refunded": True})
        self.assertTrue(self.post(CONSUME, self.body()).json()["allowed"])

    def test_validation(self):
        for bad in [
            self.body(site_id=1), self.body(site_id="x"), self.body(visitor_id="short"),
            self.body(visitor_id="bad id with spaces 12345"), self.body(ip_hash="1.2.3.4"),
        ]:
            self.assertEqual(self.post(CONSUME, bad).status_code, 400, bad)
        self.assertEqual(self.post(CONSUME, self.body(site_id="99999")).json(), {"error": "site_not_found"})
        self.assertEqual(self.post(CONSUME, self.body(ip_hash="")).status_code, 200)

    def test_database_error(self):
        with mock.patch("websites.views.consume_question", side_effect=DatabaseError("x")):
            self.assertEqual(self.post(CONSUME, self.body()).status_code, 503)


class AdminAndPruneTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("admin", "admin@example.com", "pw")
        self.client.force_login(self.admin)

    def test_website_form_has_limit_fields_and_usage(self):
        site = make_site(limit=5)
        consume_question(site, VISITOR)
        page = self.client.get(f"/admin/websites/website/{site.pk}/change/")
        for field in ["question_limit", "question_limit_period", "question_limit_message"]:
            self.assertContains(page, f'name="{field}"')
        self.assertContains(page, "1 questions from 1 visitors")
        self.assertContains(self.client.get("/admin/websites/website/"), "5 per day")

    def test_save_limit_from_admin(self):
        response = self.client.post("/admin/websites/website/add/", {
            "name": "S", "domain": "s.example.com", "owner": self.admin.pk, "is_active": "on",
            "question_limit": "10", "question_limit_period": "week", "question_limit_message": "Come back next week",
        })
        self.assertEqual(response.status_code, 302)
        site = Website.objects.get()
        self.assertEqual((site.question_limit, site.question_limit_period), (10, "week"))

    def test_prune_keeps_recent_and_total(self):
        site = make_site(limit=1)
        old = timezone.now() - timezone.timedelta(days=60)
        QuestionUsage.objects.create(website=site, kind="visitor", identity=VISITOR, period_start=old, count=1)
        QuestionUsage.objects.create(website=site, kind="visitor", identity=VISITOR, period_start=TOTAL_PERIOD_START, count=1)
        consume_question(site, OTHER_VISITOR)
        call_command("prune_question_usage", stdout=mock.MagicMock())
        self.assertEqual(QuestionUsage.objects.count(), 2)
        self.assertFalse(QuestionUsage.objects.filter(period_start=old).exists())
