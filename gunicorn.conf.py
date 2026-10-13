"""Gunicorn configuration. Values can be overridden with GUNICORN_* env vars."""

import multiprocessing
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

bind = os.getenv("GUNICORN_BIND", "0.0.0.0:8000")

# Threaded workers: the admin's AI blog generation holds a request open for
# minutes, so threads keep other requests flowing while it runs.
worker_class = "gthread"
workers = int(os.getenv("GUNICORN_WORKERS", multiprocessing.cpu_count() * 2 + 1))
threads = int(os.getenv("GUNICORN_THREADS", 4))

# Long enough for AI blog generation; nginx uses the same limit.
timeout = int(os.getenv("GUNICORN_TIMEOUT", 300))
graceful_timeout = 30
keepalive = 5

# Recycle workers periodically to contain memory growth.
max_requests = 1000
max_requests_jitter = 100

accesslog = "-"
errorlog = "-"
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")

# Trust X-Forwarded-* from the reverse proxy.
forwarded_allow_ips = os.getenv("GUNICORN_FORWARDED_ALLOW_IPS", "127.0.0.1")
