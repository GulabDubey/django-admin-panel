from datetime import timedelta
from unittest import mock

import requests
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone

from .models import WebsiteCrawl
from .services import run_crawl

API_URL = "http://crawler.test/api/v1/extract-website-data"


def api_response(status_code, body):
    response = mock.Mock(status_code=status_code, ok=status_code < 400)
    response.json.return_value = body
    return response


@override_settings(CRAWLER_API_URL=API_URL, CRAWLER_API_TOKEN="", CRAWLER_API_TIMEOUT=900)
class RunCrawlTests(TestCase):
    def setUp(self):
        self.crawl = WebsiteCrawl.objects.create(url="https://bydo.io/", max_pages=30)

    @mock.patch("crawler.services.requests.post")
    def test_success_records_results(self, post):
        post.return_value = api_response(200, {
            "success": True,
            "message": "Website data extracted and stored successfully!",
            "data": {"website": "bydo", "pages_crawled": 12, "chunks_stored": 140},
        })
        run_crawl(self.crawl.pk)

        self.assertEqual(post.call_args.kwargs["json"], {"url": "https://bydo.io/", "max_pages": 30})
        self.crawl.refresh_from_db()
        self.assertEqual(self.crawl.status, "success")
        self.assertEqual(self.crawl.collection, "bydo")
        self.assertEqual((self.crawl.pages_crawled, self.crawl.chunks_stored), (12, 140))
        self.assertIsNotNone(self.crawl.finished_at)

    @mock.patch("crawler.services.requests.post")
    @override_settings(CRAWLER_API_TOKEN="tok")
    def test_sends_website_and_token(self, post):
        post.return_value = api_response(200, {"success": True, "data": {}})
        WebsiteCrawl.objects.filter(pk=self.crawl.pk).update(website="bydo_site")
        run_crawl(self.crawl.pk)
        self.assertEqual(post.call_args.kwargs["json"]["website"], "bydo_site")
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer tok")

    @mock.patch("crawler.services.requests.post")
    def test_api_error_message_is_recorded(self, post):
        post.return_value = api_response(422, {
            "success": False, "message": "No content could be extracted from the given URL.", "errors": None,
        })
        run_crawl(self.crawl.pk)
        self.crawl.refresh_from_db()
        self.assertEqual(self.crawl.status, "failed")
        self.assertEqual(self.crawl.message, "No content could be extracted from the given URL.")

    @mock.patch("crawler.services.requests.post", side_effect=requests.ConnectionError("refused"))
    def test_unreachable_api(self, post):
        run_crawl(self.crawl.pk)
        self.crawl.refresh_from_db()
        self.assertEqual(self.crawl.status, "failed")
        self.assertIn("Could not reach the crawler API", self.crawl.message)

    @mock.patch("crawler.services.requests.post", side_effect=requests.Timeout())
    def test_timeout(self, post):
        run_crawl(self.crawl.pk)
        self.crawl.refresh_from_db()
        self.assertEqual(self.crawl.status, "failed")
        self.assertIn("did not respond within 900s", self.crawl.message)

    @override_settings(CRAWLER_API_URL="")
    def test_missing_config(self):
        run_crawl(self.crawl.pk)
        self.crawl.refresh_from_db()
        self.assertEqual(self.crawl.status, "failed")
        self.assertIn("CRAWLER_API_URL", self.crawl.message)


@override_settings(CRAWLER_API_URL=API_URL)
class CrawlAdminTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("admin", "admin@example.com", "pass")
        self.client.force_login(self.admin)

    @mock.patch("crawler.services.run_crawl")
    def test_add_creates_job_and_starts_crawl(self, run):
        with mock.patch("crawler.services.threading.Thread") as thread:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(
                    "/admin/crawler/websitecrawl/add/",
                    {"url": "https://bydo.io/", "website": "", "max_pages": 30},
                )
        self.assertEqual(response.status_code, 302)
        crawl = WebsiteCrawl.objects.get()
        self.assertEqual(crawl.requested_by, self.admin)
        self.assertEqual(thread.call_args.kwargs["args"], (crawl.pk,))
        thread.return_value.start.assert_called_once()

    def test_rejects_invalid_inputs(self):
        response = self.client.post(
            "/admin/crawler/websitecrawl/add/",
            {"url": "not-a-url", "website": "../etc", "max_pages": 500},
        )
        self.assertEqual(response.status_code, 200)
        errors = response.context["adminform"].form.errors
        self.assertEqual(set(errors), {"url", "website", "max_pages"})
        self.assertFalse(WebsiteCrawl.objects.exists())

    def test_rejects_duplicate_active_crawl(self):
        WebsiteCrawl.objects.create(url="https://bydo.io/", status="running")
        response = self.client.post(
            "/admin/crawler/websitecrawl/add/",
            {"url": "https://bydo.io/", "website": "", "max_pages": 30},
        )
        self.assertContains(response, "already in progress")
        self.assertEqual(WebsiteCrawl.objects.count(), 1)

    def test_changelist_fails_stale_jobs_and_view_is_read_only(self):
        crawl = WebsiteCrawl.objects.create(
            url="https://bydo.io/", status="running", started_at=timezone.now() - timedelta(hours=2)
        )
        self.assertEqual(self.client.get("/admin/crawler/websitecrawl/").status_code, 200)
        crawl.refresh_from_db()
        self.assertEqual(crawl.status, "failed")

        response = self.client.get(f"/admin/crawler/websitecrawl/{crawl.pk}/change/")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="_save"')


@override_settings(CRAWLER_API_URL=API_URL)
class RerunTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("admin", "admin@example.com", "pass")
        self.client.force_login(self.admin)
        self.crawl = WebsiteCrawl.objects.create(
            url="https://bydo.io/", website="bydo", max_pages=15, status="failed"
        )
        self.rerun_url = f"/admin/crawler/websitecrawl/{self.crawl.pk}/rerun/"

    def test_rerun_starts_new_crawl_with_same_inputs(self):
        with mock.patch("crawler.services.threading.Thread") as thread:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(self.rerun_url)

        self.assertRedirects(response, "/admin/crawler/websitecrawl/", fetch_redirect_response=False)
        new = WebsiteCrawl.objects.exclude(pk=self.crawl.pk).get()
        self.assertEqual((new.url, new.website, new.max_pages), ("https://bydo.io/", "bydo", 15))
        self.assertEqual(new.requested_by, self.admin)
        self.assertEqual(thread.call_args.kwargs["args"], (new.pk,))

    def test_rerun_skipped_while_crawl_in_progress(self):
        WebsiteCrawl.objects.create(url="https://bydo.io/", status="running", started_at=timezone.now())
        response = self.client.post(self.rerun_url, follow=True)
        self.assertContains(response, "already in progress")
        self.assertEqual(WebsiteCrawl.objects.count(), 2)

    def test_rerun_requires_post(self):
        self.assertEqual(self.client.get(self.rerun_url).status_code, 405)

    def test_rerun_requires_add_permission(self):
        staff = User.objects.create_user("staff", password="pass", is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.post(self.rerun_url).status_code, 403)
        self.assertEqual(WebsiteCrawl.objects.count(), 1)

    def test_buttons_shown_on_list_and_detail(self):
        list_page = self.client.get("/admin/crawler/websitecrawl/")
        self.assertContains(list_page, f'formaction="{self.rerun_url}"')

        detail = self.client.get(f"/admin/crawler/websitecrawl/{self.crawl.pk}/change/")
        self.assertContains(detail, "Re-run crawl")
        self.assertContains(detail, f'action="{self.rerun_url}"')

    def test_no_button_for_active_crawl(self):
        WebsiteCrawl.objects.filter(pk=self.crawl.pk).update(status="running", started_at=timezone.now())
        self.assertContains(self.client.get("/admin/crawler/websitecrawl/"), "In progress")
        detail = self.client.get(f"/admin/crawler/websitecrawl/{self.crawl.pk}/change/")
        self.assertNotContains(detail, "Re-run crawl")
