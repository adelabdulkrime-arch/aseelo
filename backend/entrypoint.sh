#!/usr/bin/env sh
set -e

ROLE="${1:-api}"

wait_for_db() {
  echo "[entrypoint] waiting for database ..."
  python - <<'PY'
import os, sys, time
import psycopg
url = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
for attempt in range(60):
    try:
        with psycopg.connect(url, connect_timeout=3):
            print("[entrypoint] database is ready")
            sys.exit(0)
    except Exception as exc:  # noqa: BLE001
        print(f"[entrypoint] db not ready ({attempt + 1}/60): {exc.__class__.__name__}")
        time.sleep(2)
print("[entrypoint] database never became ready", file=sys.stderr)
sys.exit(1)
PY
}

case "$ROLE" in
  api)
    wait_for_db
    echo "[entrypoint] running migrations ..."
    alembic upgrade head
    echo "[entrypoint] seeding templates ..."
    python -m app.services.seed
    echo "[entrypoint] starting API ..."
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'
    ;;
  worker)
    wait_for_db
    echo "[entrypoint] starting Celery worker ..."
    exec celery -A app.worker.celery_app:celery_app worker \
        --loglevel="${LOG_LEVEL:-INFO}" \
        --concurrency="${WORKER_CONCURRENCY:-2}" \
        -Q renders
    ;;
  migrate)
    wait_for_db
    exec alembic upgrade head
    ;;
  shell)
    exec sh
    ;;
  *)
    exec "$@"
    ;;
esac
