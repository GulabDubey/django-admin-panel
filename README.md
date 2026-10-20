# NextGen AI — Django site & admin

Landing page with dynamic pricing plans, Razorpay checkout, user accounts, a blog,
and an admin with AI blog generation (Anthropic).

Stack: Django 5.2 · MySQL · gunicorn · nginx · WhiteNoise · Python 3.11

## Configuration

All settings come from environment variables. Copy `.env.example` to `.env` and
fill it in; every variable is documented there. With `DJANGO_DEBUG=False` the
app refuses to start without `DJANGO_SECRET_KEY` and enables HTTPS redirect,
secure cookies and HSTS by default.

## Local development

```bash
python3.11 -m venv .venv
# macOS/Homebrew without pkg-config: export MYSQLCLIENT_CFLAGS="-I$(brew --prefix mysql)/include/mysql" MYSQLCLIENT_LDFLAGS="-L$(brew --prefix mysql)/lib -lmysqlclient"
.venv/bin/pip install -r requirements.txt
cp .env.example .env      # set DJANGO_DEBUG=True for development
mysql -uroot -e "CREATE DATABASE django_app CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_packages
.venv/bin/python manage.py createsuperuser
.venv/bin/python manage.py runserver
```

Run tests: `.venv/bin/python manage.py test`

## Production deployment (Docker)

```bash
cp .env.example .env               # fill in all secrets, real hosts, DB user/passwords
docker compose up -d --build       # nginx → gunicorn → MySQL
docker compose exec web python manage.py seed_packages      # first deploy only
docker compose exec web python manage.py createsuperuser
```

- Migrations run automatically on container start (`RUN_MIGRATIONS=0` to disable).
- Static files are collected at build time and served by WhiteNoise; uploads are
  served by nginx from the `media` volume.
- Health check: `GET /healthz/` (checks the database; usable by IP over HTTP).
- **TLS**: nginx listens on port 80. Terminate HTTPS either at a load balancer
  that sends `X-Forwarded-Proto` (works as-is), or add a `listen 443 ssl` block
  with your certificates to `deploy/nginx/default.conf`.
- **Backups**: the `mysql_data` and `media` volumes hold all state — back them up.

### Production without Docker

```bash
.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py collectstatic --noinput
.venv/bin/gunicorn config.wsgi:application -c gunicorn.conf.py
```

Put nginx in front using `deploy/nginx/default.conf` (change `server web:8000`
to the gunicorn address and `/app/media/` to `DJANGO_MEDIA_ROOT`) and run
gunicorn under systemd or another process manager.

## Payments (Razorpay)

1. Set `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` (use live keys in production).
2. In Razorpay Dashboard → Webhooks, add `https://<domain>/api/payments/webhook/`
   with events `payment.captured` and `payment.failed`, and put its secret in
   `RAZORPAY_WEBHOOK_SECRET`. The webhook confirms payments even if the buyer
   closes the browser before checkout returns.

## Website crawler (admin)

Admin → **Website crawler** → **Add** takes a URL, an optional collection name
and max pages (1–200), and calls the web-agent API
(`POST CRAWLER_API_URL`) to crawl the site into the chatbot knowledge base.
The crawl runs in the background; the list page auto-refreshes and shows
status, pages crawled and chunks stored. Use the **Re-run selected crawls**
action to refresh a site's data.

- `CRAWLER_API_URL` — e.g. `http://127.0.0.1:8010/api/v1/extract-website-data`
  (from Docker: `http://host.docker.internal:8010/...`)
- `CRAWLER_API_TOKEN` — optional, sent as `Authorization: Bearer …`
- `CRAWLER_API_TIMEOUT` — seconds to wait for a crawl (default 900)

## Chatbot subscription verification (internal API)

`POST /api/internal/chatbot/verify-subscription/` — called server-to-server by
the chatbot (FastAPI) service with `Authorization: Bearer <CHATBOT_SERVICE_TOKENS entry>`
and `{"site_key": "...", "domain": "..."}`. Returns 200 `{"authorized": true, ...}`
or 403 `{"authorized": false, "reason": ...}`; 400/401/429/503 for bad input,
bad credential, rate limit and outages.

Register customer sites in Admin → **Chatbot websites** (owner, domain; the
public `site_key` is generated). A site is authorized while its owner has a
`paid` payment whose `created_at + package.duration` days is in the future.

## Pre-launch checklist

- `python manage.py check --deploy` passes (HSTS preload is opt-in by design)
- `DJANGO_ADMIN_URL` set to a non-default path
- `DJANGO_ADMINS` + SMTP settings set so 500 errors are emailed
- Cache table exists (`manage.py createcachetable`; rate limits on login/register/checkout use it)
- `CHATBOT_WIDGET_URL` points to the production widget (HTTPS) or is empty
- `CHATBOT_SERVICE_TOKENS` set (long random value), shared only with the chatbot service
