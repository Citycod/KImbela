#!/bin/bash

# Stop existing processes
echo "Stopping existing server..."
pkill -f gunicorn 2>/dev/null || true
sleep 2

# Activate venv
source venv/bin/activate

# Run with proper settings
gunicorn \
  --bind 0.0.0.0:5000 \
  --workers 3 \
  --timeout 120 \
  --limit-request-line 8190 \
  --limit-request-field_size 8190 \
  runserver:app
