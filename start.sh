#!/bin/sh
set -eu
exec gunicorn --bind "0.0.0.0:${PORT:-8080}" --workers 1 --threads 16 --timeout 0 --graceful-timeout 20 --access-logfile - --error-logfile - app:app
