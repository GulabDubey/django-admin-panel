import json
import logging
import re
from datetime import timezone as dt_timezone

from django.core.exceptions import ImproperlyConfigured
from django.db import DatabaseError
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from core.ratelimit import ratelimit
from core.service_auth import require_service_token
from llm.crypto import DecryptionError
from llm.resolver import LLMNotConfigured, resolve_llm
from payments.subscriptions import website_subscription
from .domains import normalize_domain
from .models import Website
from .questions import consume_question, refund_question

logger = logging.getLogger(__name__)


def deny(reason, status=403):
    return JsonResponse({"authorized": False, "reason": reason}, status=status)


@csrf_exempt
@never_cache
@require_POST
@ratelimit("chatbot_verify", limit=1200, period=60)
@require_service_token("CHATBOT_SERVICE_TOKENS")
def verify_subscription(request):
    """
    Server-to-server check used by the chatbot (FastAPI) service before it
    serves a website. Responses:
      200 {"authorized": true, ...}        website may use the chatbot
      403 {"authorized": false, "reason"}  denied (see reasons below)
      400 invalid_request · 401 bad service credential · 429 rate limited
      503 service_unavailable (database or configuration problem)
    """
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return deny("invalid_request", status=400)

    if not isinstance(data, dict):
        return deny("invalid_request", status=400)

    site_key = data.get("site_key")
    domain = normalize_domain(data.get("domain") if isinstance(data.get("domain"), str) else "")
    if not isinstance(site_key, str) or not site_key or len(site_key) > 64 or not domain:
        return deny("invalid_request", status=400)

    try:
        website = Website.objects.select_related("owner", "payment__package").filter(site_key=site_key).first()

        if website is None:
            return deny("invalid_site_key")
        if not website.is_active or not website.owner.is_active:
            return deny("site_disabled")
        if domain != website.domain:
            logger.warning(
                "Site %s used from unapproved domain %r (approved: %s)", website.pk, domain, website.domain
            )
            return deny("domain_not_allowed")

        subscription = website_subscription(website)
    except DatabaseError:
        logger.exception("Database error while verifying chatbot subscription")
        return deny("service_unavailable", status=503)

    if subscription is None:
        return deny("subscription_inactive")
    if not subscription.is_active:
        return deny("subscription_expired")

    return JsonResponse({
        "authorized": True,
        "site_id": str(website.pk),
        "customer_id": str(website.owner_id),
        "plan": subscription.plan,
        "expires_at": subscription.expires_at.astimezone(dt_timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    })


@csrf_exempt
@never_cache
@require_POST
@ratelimit("chatbot_llm_config", limit=600, period=60)
@require_service_token("CHATBOT_SERVICE_TOKENS")
def llm_config(request):
    """
    Server-to-server: the LLM provider, model and credentials the chatbot
    must use for a website (its active provider in Admin → Websites).

      POST {"site_id": "3"}
      200 {"provider": ..., "provider_id": ..., "api_type": "anthropic"|"openai",
           "base_url": "", "model": "claude-sonnet-4-5", "api_key": "...", "source": "website"}
      404 {"error": "site_not_found"} · {"error": "llm_not_configured"}
      400 invalid_request · 401 bad service credential · 503 service_unavailable
    """
    try:
        data = json.loads(request.body or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "invalid_request"}, status=400)

    site_id = data.get("site_id") if isinstance(data, dict) else None
    if site_id is not None and not (isinstance(site_id, str) and site_id.isdigit() and len(site_id) <= 20):
        return JsonResponse({"error": "invalid_request"}, status=400)

    try:
        website = None
        if site_id is not None:
            website = Website.objects.filter(pk=int(site_id)).first()
            if website is None:
                return JsonResponse({"error": "site_not_found"}, status=404)

        try:
            resolved = resolve_llm(website)
        except LLMNotConfigured as exc:
            logger.info("LLM config requested for site %s but not configured: %s", site_id or "-", exc)
            return JsonResponse({"error": "llm_not_configured"}, status=404)

        api_key = resolved.provider.get_api_key()
    except DatabaseError:
        logger.exception("Database error while resolving LLM config")
        return JsonResponse({"error": "service_unavailable"}, status=503)
    except (DecryptionError, ImproperlyConfigured):
        logger.exception("Cannot decrypt the API key of LLM provider")
        return JsonResponse({"error": "service_unavailable"}, status=503)

    return JsonResponse({
        "provider": resolved.provider.name,
        "provider_id": str(resolved.provider.pk),
        "api_type": resolved.provider.api_type,
        "base_url": resolved.provider.base_url,
        "model": resolved.model.model_id,
        "api_key": api_key,
        "source": resolved.source,
    })


VISITOR_ID_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
IP_HASH_RE = re.compile(r"^[a-f0-9]{64}$")


def _question_request(request):
    """Parse {"site_id", "visitor_id", "ip_hash"?}; returns (website, visitor_id, ip_hash) or a JsonResponse."""
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "invalid_request"}, status=400)
    if not isinstance(data, dict):
        return JsonResponse({"error": "invalid_request"}, status=400)

    site_id, visitor_id, ip_hash = data.get("site_id"), data.get("visitor_id"), data.get("ip_hash") or ""
    if not (isinstance(site_id, str) and site_id.isdigit() and len(site_id) <= 20):
        return JsonResponse({"error": "invalid_request"}, status=400)
    if not (isinstance(visitor_id, str) and VISITOR_ID_RE.match(visitor_id)):
        return JsonResponse({"error": "invalid_request"}, status=400)
    if not (isinstance(ip_hash, str) and (ip_hash == "" or IP_HASH_RE.match(ip_hash))):
        return JsonResponse({"error": "invalid_request"}, status=400)

    website = Website.objects.filter(pk=int(site_id)).first()
    if website is None:
        return JsonResponse({"error": "site_not_found"}, status=404)
    return website, visitor_id, ip_hash


@csrf_exempt
@never_cache
@require_POST
@ratelimit("chatbot_questions", limit=6000, period=60)
@require_service_token("CHATBOT_SERVICE_TOKENS")
def consume_question_view(request):
    """
    Server-to-server: count one chatbot question for a visitor, or refuse it.

      POST {"site_id": "3", "visitor_id": "<anonymous id>", "ip_hash": "<sha256 hex>"}
      200 {"allowed": true,  "limit": 20, "remaining": 19, "period": "day", "resets_at": "...Z"}
      200 {"allowed": false, "limit": 20, "remaining": 0, ..., "reason": "question_limit", "message": "..."}
      limit 0 = unlimited (nothing is counted)
    """
    try:
        parsed = _question_request(request)
        if isinstance(parsed, JsonResponse):
            return parsed
        decision = consume_question(*parsed)
    except DatabaseError:
        logger.exception("Database error while counting a chatbot question")
        return JsonResponse({"error": "service_unavailable"}, status=503)
    return JsonResponse(decision.as_json())


@csrf_exempt
@never_cache
@require_POST
@ratelimit("chatbot_questions", limit=6000, period=60)
@require_service_token("CHATBOT_SERVICE_TOKENS")
def refund_question_view(request):
    """Server-to-server: give back a question whose reply failed. 200 {"refunded": true}."""
    try:
        parsed = _question_request(request)
        if isinstance(parsed, JsonResponse):
            return parsed
        refund_question(*parsed)
    except DatabaseError:
        logger.exception("Database error while refunding a chatbot question")
        return JsonResponse({"error": "service_unavailable"}, status=503)
    return JsonResponse({"refunded": True})
