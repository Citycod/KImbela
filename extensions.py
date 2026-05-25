# extensions.py - FIXED
import os

from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_caching import Cache
from flask_socketio import SocketIO

from resend_mail import ResendMail

# Initialize all extensions
db = SQLAlchemy()
bcrypt = Bcrypt()
login_manager = LoginManager()
mail = ResendMail()
csrf = CSRFProtect()
cache = Cache()

# FIXED: Use eventlet for true WebSocket support
socketio_kwargs = dict(
    async_mode="eventlet",
    cors_allowed_origins="*",
    logger=True,
    engineio_logger=True,
    ping_timeout=60,
    ping_interval=25,
    max_http_buffer_size=1e8,
    allow_upgrades=True,
    http_compression=True,
    compression_threshold=1024,
)

redis_url = os.getenv("REDIS_URL")
if redis_url:
    socketio_kwargs["message_queue"] = redis_url

socketio = SocketIO(**socketio_kwargs)

print("[OK] Extensions initialized with WebSocket support (eventlet)")
