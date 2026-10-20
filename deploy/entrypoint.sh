#!/bin/sh
set -e

# Apply migrations before serving. Set RUN_MIGRATIONS=0 when several replicas
# start at once and migrations run as a separate release step instead.
if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
    python manage.py migrate --noinput
    python manage.py createcachetable
fi

exec "$@"
