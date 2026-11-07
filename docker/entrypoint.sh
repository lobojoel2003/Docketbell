#!/bin/sh
# Usage: docketbell-entrypoint web | worker | manage <command> | <any command>
set -e

case "${1:-web}" in
  web)
    if [ "${MIGRATE_ON_START:-true}" = "true" ]; then
      docketbell migrate --noinput
    fi
    exec gunicorn docketbell.wsgi:application \
      --bind "0.0.0.0:${PORT:-8000}" \
      --workers "${WEB_CONCURRENCY:-3}" \
      --access-logfile - \
      --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-127.0.0.1}"
    ;;
  worker)
    exec docketbell run_worker
    ;;
  manage)
    shift
    exec docketbell "$@"
    ;;
  *)
    exec "$@"
    ;;
esac
