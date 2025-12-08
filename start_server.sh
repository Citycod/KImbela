#!/bin/bash

echo "========================================="
echo "🚀 Starting Kimbela Server"
echo "========================================="

# Kill any existing gunicorn processes
echo "🛑 Stopping any existing processes..."
pkill -f gunicorn 2>/dev/null || true
sleep 2

# Activate virtual environment
echo "🐍 Activating virtual environment..."
source venv/bin/activate

# Install requirements if needed
echo "📦 Checking requirements..."
pip install -r requirements.txt --quiet

# Create uploads directory
echo "📁 Creating uploads directory..."
mkdir -p uploads

# Start gunicorn with proper configuration
echo "🔧 Starting with increased upload limits..."
echo "📊 Upload limit: 20MB"
echo "📏 Request limits increased"
echo "🌐 Server: http://0.0.0.0:5000"
echo "========================================="

# Start gunicorn
exec gunicorn \
  --config gunicorn.conf.py \
  --bind 0.0.0.0:5000 \
  runserver:app
