#!/bin/bash
set -e -x

scripts/start/install_extensions.sh

echo "Starting Celery worker..."
uv run celery -A app.main:celery_app worker --loglevel=info --pool=threads -c "${CELERY_CONCURRENCY:-4}" -Q default,sdk_sync,garmin_sync,webhook_sync,xml_sync -n worker@%h
