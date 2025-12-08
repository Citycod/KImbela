# app_config.py - FIXED VERSION
from flask import Flask, session, render_template, request
from flask_wtf.csrf import CSRFProtect, generate_csrf
from dotenv import load_dotenv
import os
from flask_migrate import Migrate
from extensions import db, bcrypt, login_manager, mail
from flask_caching import Cache
from flask_socketio import SocketIO
from datetime import datetime, timedelta, timezone
import humanize

# Import blueprints
from users.user import user as user_blueprint
from marketplace.market import market as market_blueprint
from authentication.authenticate import auth
from admin.admin import admin as admin_blueprint
from matchmaking.matchmake import match as matchmaking_blueprint
from payments.payments import payments as payments_blueprint
from messages.messaging import messaging as message_blueprint

from models import User, Post, Comment, Like, FriendRequest, friendship
from extensions import db, socketio
from scheduler import init_scheduler
from payments.payment_service import PaymentService

load_dotenv()

csrf = CSRFProtect()
cache = Cache(config={'CACHE_TYPE': 'SimpleCache'})  # FIXED cache initialization

def create_app():
    app = Flask(__name__)
    
    # ========== BASIC CONFIG ==========
    app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
    app.config["UPLOAD_FOLDER"] = "uploads"
    app.config["ALLOWED_EXTENSIONS"] = {"jpg", "jpeg", "png", "gif", "mp4", "mov"}
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    
    # ========== CACHE CONFIG ==========
    app.config["CACHE_TYPE"] = "SimpleCache"
    app.config["CACHE_DEFAULT_TIMEOUT"] = 180
    
    # ========== PAYMENT CONFIG ==========
    app.config["STRIPE_SECRET_KEY"] = os.getenv("STRIPE_SECRET_KEY")
    app.config["STRIPE_PUBLISHABLE_KEY"] = os.getenv("STRIPE_PUBLISHABLE_KEY")
    app.config["STRIPE_WEBHOOK_SECRET"] = os.getenv("STRIPE_WEBHOOK_SECRET")
    
    # Flutterwave
    app.config["FLUTTERWAVE_PUBLIC_KEY"] = os.getenv("PUBLIC_KEY")
    app.config["FLUTTERWAVE_SECRET_KEY"] = os.getenv("SECRET_KEY")
    app.config["FLUTTERWAVE_ENCRYPTION_KEY"] = os.getenv("ENCRYPTION_KEY")
    
    # ========== DATABASE CONFIG ==========
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("SQLALCHEMY_DATABASE_URI")
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=12)
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_pre_ping": True,
        "pool_recycle": 1800,
        "pool_size": 10,
        "max_overflow": 20,
    }
    
    # ========== EMAIL CONFIG ==========
    app.config["MAIL_SERVER"] = os.getenv("MAIL_SERVER")
    app.config["MAIL_PORT"] = int(os.getenv("MAIL_PORT", 587))
    app.config["MAIL_USE_TLS"] = True
    app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")
    app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")
    app.config["MAIL_DEFAULT_SENDER"] = os.getenv("MAIL_DEFAULT_SENDER")
    
    # ========== INITIALIZE EXTENSIONS ==========
    # Initialize cache FIRST
    cache.init_app(app)
    
    # Initialize other extensions
    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)
    csrf.init_app(app)
    
    migrate = Migrate(app, db)
    
    # Initialize Socket.IO
    socketio.init_app(app, cors_allowed_origins="*")
    
    # ========== LOGIN MANAGER ==========
    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "info"
    
    # ========== REGISTER BLUEPRINTS ==========
    app.register_blueprint(auth)
    app.register_blueprint(user_blueprint)
    app.register_blueprint(message_blueprint)
    app.register_blueprint(admin_blueprint)
    app.register_blueprint(payments_blueprint)
    app.register_blueprint(matchmaking_blueprint)
    app.register_blueprint(market_blueprint)
    
    # ========== SCHEDULER ==========
    if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        with app.app_context():
            try:
                init_scheduler(app)
                app.logger.info("Scheduler initialized")
            except Exception as e:
                app.logger.error(f"Scheduler error: {e}")
    
    # ========== CONTEXT PROCESSORS ==========
    @app.context_processor
    def inject_csrf_token():
        return dict(csrf_token=generate_csrf())
    
    # ========== TEMPLATE FILTERS ==========
    @app.template_filter("time_ago")
    def time_ago_filter(timestamp):
        if timestamp is None:
            return "Never"
        
        now = datetime.utcnow()
        diff = now - timestamp
        
        if diff.days > 365:
            return f"{diff.days // 365}y ago"
        elif diff.days > 30:
            return f"{diff.days // 30}mo ago"
        elif diff.days > 0:
            return f"{diff.days}d ago"
        elif diff.seconds > 3600:
            return f"{diff.seconds // 3600}h ago"
        elif diff.seconds > 60:
            return f"{diff.seconds // 60}m ago"
        else:
            return "just now"
    
    @app.template_filter("timeago")
    def timeago(dt):
        if dt is None:
            return "Never"
        return time_ago_filter(dt)
    
    @app.template_filter("datetimeformat")
    def datetimeformat(value):
        if value:
            try:
                return datetime.fromisoformat(value).strftime("%Y-%m-%d")
            except:
                return "N/A"
        return "N/A"
    
    @app.template_filter("monthformat")
    def monthformat(value):
        if value:
            try:
                return datetime.fromisoformat(value).strftime("%b")
            except:
                return "N/A"
        return "N/A"
    
    # ========== BEFORE REQUEST ==========
    @app.before_request
    def update_last_seen():
        from flask_login import current_user
        if current_user.is_authenticated:
            current_user.last_seen = datetime.utcnow()
            db.session.commit()
    
    return app

# Create app instance for production
app = create_app()