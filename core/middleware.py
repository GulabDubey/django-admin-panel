from django.db import connection
from django.http import JsonResponse


class HealthCheckMiddleware:
    """
    Answer /healthz/ before host validation, HTTPS redirects and sessions run,
    so load balancers and container probes can hit it by IP over plain HTTP.
    """

    path = "/healthz/"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path != self.path:
            return self.get_response(request)

        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except Exception:
            response = JsonResponse({"status": "error", "database": "unavailable"}, status=503)
        else:
            response = JsonResponse({"status": "ok"})
        response["Cache-Control"] = "no-store"
        return response
