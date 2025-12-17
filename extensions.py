# extensions.py - FIXED
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_mail import Mail
from flask_wtf.csrf import CSRFProtect
from flask_caching import Cache
from flask_socketio import SocketIO

# Initialize all extensions
db = SQLAlchemy()
bcrypt = Bcrypt()
login_manager = LoginManager()
mail = Mail()
csrf = CSRFProtect()
cache = Cache()

# FIXED: Use eventlet for true WebSocket support
socketio = SocketIO(
    async_mode='eventlet',
    cors_allowed_origins="*",
    logger=True,
    engineio_logger=True,
    ping_timeout=60,
    ping_interval=25,
    message_queue='redis://redis:6379/0',
    max_http_buffer_size=1e8,
    allow_upgrades=True,
    http_compression=True,
    compression_threshold=1024,
)

print("✅ Extensions initialized with WebSocket support (eventlet)")