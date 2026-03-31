# gunicorn_config.py
import os

os.environ.setdefault("EVENTLET_NO_GREENDNS", "yes")

bind = "0.0.0.0:5000"
workers = 1
worker_class = "eventlet"
timeout = 120
keepalive = 2

# CRITICAL: Increase these limits for file uploads
limit_request_line = 8190  # Default is 4094 (too small for uploads)
limit_request_field_size = 8190  # For large file uploads
limit_request_fields = 100  # Increase if needed

# Worker settings
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 50

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"
capture_output = True
enable_stdio_inheritance = True
raw_env = ["EVENTLET_NO_GREENDNS=yes"]

# Debug for upload issues
spew = False  # Set to True for extreme debugging
