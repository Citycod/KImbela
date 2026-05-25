#!/bin/bash

# Stop existing processes
echo "Stopping existing server..."
pkill -f gunicorn 2>/dev/null || true
sleep 2

# Activate venv
source venv/bin/activate

# Run with proper settings
gunicorn \
  --config gunicorn.conf.py \
  --bind 0.0.0.0:5000 \
  runserver:app
