#!/bin/bash
set -e -x

scripts/start/install_extensions.sh

rm -f '/tmp/celerybeat.pid'
uv run celery -A app.main:celery_app beat -l info -s /tmp/celerybeat-schedule --pidfile=/tmp/celerybeat.pid
