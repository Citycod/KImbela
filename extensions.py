# extensions.py - UPDATED with better WebSocket handling
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

# Initialize Socket.IO with better WebSocket support
socketio = SocketIO(
    async_mode='threading',
    cors_allowed_origins="*",
    logger=True,  # Enable logging to debug
    engineio_logger=True,  # Enable Engine.IO logging
    ping_timeout=60,
    ping_interval=25,
    max_http_buffer_size=1e8,
    # WebSocket specific settings
    allow_upgrades=True,
    http_compression=True,
    compression_threshold=1024,
)

print("✅ Extensions initialized with WebSocket support")