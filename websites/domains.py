import re
from urllib.parse import urlsplit

from django.conf import settings

HOSTNAME_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9-]{2,63}$")

# Development hosts, accepted only when DEBUG is on. Their port is kept, since
# several local apps commonly share one host on different ports.
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def normalize_domain(value, allow_local=None):
    """
    Reduce a domain or URL to a comparable hostname:
    "https://WWW.Example.com:443/page" -> "example.com".

    With `allow_local` (defaults to settings.DEBUG), local development hosts
    are also accepted and keep their port: "http://127.0.0.1:8012/" ->
    "127.0.0.1:8012".

    Returns "" if the value is not a valid hostname.
    """
    if allow_local is None:
        allow_local = settings.DEBUG

    value = (value or "").strip()
    if not value:
        return ""

    if "://" not in value:
        value = "//" + value
    try:
        parts = urlsplit(value)
        host = parts.hostname or ""
        port = parts.port
    except ValueError:
        return ""

    host = host.rstrip(".")

    if host in LOCAL_HOSTS:
        if not allow_local:
            return ""
        if host == "::1":
            host = "[::1]"
        return f"{host}:{port}" if port else host

    if host.startswith("www."):
        host = host[4:]

    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        return ""

    return host if HOSTNAME_RE.match(host) else ""
