import hmac
import logging
from functools import wraps

from django.conf import settings
from django.http import JsonResponse

from .ratelimit import client_ip

security_logger = logging.getLogger("django.security.service_auth")


def _bearer_token(request):
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    return token.strip() if scheme.lower() == "bearer" else ""


def is_valid_service_token(token, valid_tokens):
    """Constant-time check against every configured token (supports rotation)."""
    if not token:
        return False
    matched = False
    for valid in valid_tokens:
        # Compare against all tokens so timing does not reveal which one matched.
        matched |= hmac.compare_digest(token.encode(), valid.encode())
    return matched


def require_service_token(setting_name):
    """
    Require `Authorization: Bearer <token>` matching one of the tokens in the
    named list setting. Several tokens can be valid at once so a secret can be
    rotated without downtime.
    """

    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            valid_tokens = getattr(settings, setting_name)
            if not valid_tokens:
                security_logger.error("%s is not configured; rejecting %s", setting_name, request.path)
                return JsonResponse({"error": "service_unavailable"}, status=503)

            if not is_valid_service_token(_bearer_token(request), valid_tokens):
                security_logger.warning(
                    "Rejected service call to %s from %s: missing or invalid credential",
                    request.path, client_ip(request),
                )
                return JsonResponse({"error": "unauthorized"}, status=401)

            return view(request, *args, **kwargs)

        return wrapped

    return decorator
