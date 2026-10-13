from functools import wraps

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse


def client_ip(request):
    # Behind nginx, REMOTE_ADDR is the proxy and nginx sets X-Real-IP to the
    # client. Only trust the header then, otherwise clients could spoof it.
    if settings.BEHIND_PROXY and request.META.get("HTTP_X_REAL_IP"):
        return request.META["HTTP_X_REAL_IP"]
    return request.META.get("REMOTE_ADDR", "")


def ratelimit(key, limit, period):
    """Allow at most `limit` requests per client IP per `period` seconds."""

    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            cache_key = f"ratelimit:{key}:{client_ip(request)}"
            cache.add(cache_key, 0, timeout=period)
            try:
                count = cache.incr(cache_key)
            except ValueError:
                # Key expired between add() and incr().
                cache.set(cache_key, 1, timeout=period)
                count = 1

            if count > limit:
                return JsonResponse(
                    {"error": "Too many requests. Please try again later."},
                    status=429,
                )
            return view(request, *args, **kwargs)

        return wrapped

    return decorator
