#!/bin/bash
set -e
echo "Running migrations..."
python manage.py migrate --noinput
echo "Starting Daphne server..."
exec daphne -b 0.0.0.0 -p ${PORT:-8080} moodtune.asgi:application
