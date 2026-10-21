import json
import logging
from datetime import timezone as dt_timezone

from django.db import DatabaseError
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from core.ratelimit import ratelimit
from core.service_auth import require_service_token
from payments.subscriptions import website_subscription
from .domains import normalize_domain
from .models import Website

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
