import logging
import threading

import requests
from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone

from .models import WebsiteCrawl

logger = logging.getLogger(__name__)


class CrawlerAPIError(Exception):
    pass


def call_extract_api(url, website, max_pages):
    """POST to the crawler API and return its `data` payload."""
    if not settings.CRAWLER_API_URL:
        raise CrawlerAPIError("CRAWLER_API_URL is not configured.")

    payload = {"url": url, "max_pages": max_pages}
    if website:
        payload["website"] = website

    headers = {"Accept": "application/json"}
    if settings.CRAWLER_API_TOKEN:
        headers["Authorization"] = f"Bearer {settings.CRAWLER_API_TOKEN}"

    try:
        response = requests.post(
            settings.CRAWLER_API_URL,
            json=payload,
            headers=headers,
            timeout=(10, settings.CRAWLER_API_TIMEOUT),
        )
    except requests.Timeout:
        raise CrawlerAPIError(
            f"Crawler API did not respond within {settings.CRAWLER_API_TIMEOUT}s."
        )
    except requests.RequestException as exc:
        raise CrawlerAPIError(f"Could not reach the crawler API: {exc}")

    try:
        body = response.json()
    except ValueError:
        body = {}

    if not response.ok or not body.get("success"):
        message = body.get("message") or f"Crawler API returned HTTP {response.status_code}."
        errors = body.get("errors")
        if errors:
            message = f"{message} {errors}"
        raise CrawlerAPIError(message)

    return body.get("data") or {}, body.get("message", "")


def run_crawl(crawl_id):
    """Run one crawl job and record the outcome. Called from a worker thread."""
    crawl = WebsiteCrawl.objects.get(pk=crawl_id)
    crawl.status = "running"
    crawl.started_at = timezone.now()
    crawl.save(update_fields=["status", "started_at"])

    try:
        data, message = call_extract_api(crawl.url, crawl.website, crawl.max_pages)
    except CrawlerAPIError as exc:
        logger.warning("Crawl %s failed: %s", crawl.pk, exc)
        crawl.status = "failed"
        crawl.message = str(exc)
    except Exception:
        logger.exception("Crawl %s crashed", crawl.pk)
        crawl.status = "failed"
        crawl.message = "Unexpected error while calling the crawler API. Check the server logs."
    else:
        crawl.status = "success"
        crawl.collection = data.get("website", "")
        crawl.pages_crawled = data.get("pages_crawled")
        crawl.chunks_stored = data.get("chunks_stored")
        crawl.message = message
        logger.info(
            "Crawl %s finished: %s pages, %s chunks",
            crawl.pk, crawl.pages_crawled, crawl.chunks_stored,
        )

    crawl.finished_at = timezone.now()
    crawl.save()


def _run_in_thread(crawl_id):
    try:
        run_crawl(crawl_id)
    finally:
        # Worker threads own their DB connection; close it so it is not leaked.
        connection.close()


def start_crawl(crawl):
    """
    Run the crawl in a background thread once the current transaction commits,
    so the admin request returns immediately. Crawls can outlast the gunicorn
    request timeout.
    """
    def launch():
        threading.Thread(
            target=_run_in_thread,
            args=(crawl.pk,),
            name=f"website-crawl-{crawl.pk}",
            daemon=True,
        ).start()

    transaction.on_commit(launch)
