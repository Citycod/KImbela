# app_config.py - FIX CACHE INITIALIZATION
from flask import Flask, session
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
cache = Cache()  # SINGLE cache instance for the whole app


def create_app():
    app = Flask(__name__)

    # Stripe configuration
    app.config["STRIPE_SECRET_KEY"] = os.getenv("STRIPE_SECRET_KEY")
    app.config["STRIPE_PUBLISHABLE_KEY"] = os.getenv("STRIPE_PUBLISHABLE_KEY")
    app.config["STRIPE_WEBHOOK_SECRET"] = os.getenv("STRIPE_WEBHOOK_SECRET")

    # Flutterwave configuration
    app.config["FLUTTERWAVE_PUBLIC_KEY"] = os.getenv("PUBLIC_KEY")
    app.config["FLUTTERWAVE_SECRET_KEY"] = os.getenv("SECRET_KEY")
    app.config["FLUTTERWAVE_ENCRYPTION_KEY"] = os.getenv("ENCRYPTION_KEY")

    # Cache configuration - FIXED
    app.config["CACHE_TYPE"] = "SimpleCache"  # Must be exact string
    app.config["CACHE_DEFAULT_TIMEOUT"] = 300
    app.config["CACHE_THRESHOLD"] = 1000

    app.payment_service = PaymentService()

    # Alternative cache config options:
    # app.config['CACHE_TYPE'] = 'filesystem'
    # app.config['CACHE_DIR'] = '/tmp/flask-cache'

    # For Redis (when ready):
    # app.config['CACHE_TYPE'] = 'RedisCache'
    # app.config['CACHE_REDIS_URL'] = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    # app.config['CACHE_KEY_PREFIX'] = 'kimbela_'

    # Verify webhook secret is loaded
    if not app.config["STRIPE_WEBHOOK_SECRET"]:
        app.logger.error("STRIPE_WEBHOOK_SECRET is not set!")
        raise Exception("STRIPE_WEBHOOK_SECRET is not set!")

    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("SQLALCHEMY_DATABASE_URI")
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=3000)
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "pool_size": 5,
        "max_overflow": 10,
    }

    # Email configuration
    app.config["MAIL_SERVER"] = os.getenv("MAIL_SERVER")
    app.config["MAIL_PORT"] = int(os.getenv("MAIL_PORT"))
    app.config["MAIL_USE_TLS"] = True
    app.config["MAIL_USE_SSL"] = False
    app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")
    app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")
    app.config["MAIL_DEFAULT_SENDER"] = os.getenv("MAIL_DEFAULT_SENDER")
    app.config["MAIL_SUPPRESS_SEND"] = False
    app.config["MAIL_DEBUG"] = True

    # Initialize extensions
    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)
    csrf.init_app(app)

    # Initialize cache FIRST
    cache.init_app(app)

    # Verify cache initialization
    with app.app_context():
        if "cache" not in app.extensions:
            app.logger.warning(
                "Cache not properly initialized, using simple dict cache"
            )
            # Create a simple cache as fallback
            from werkzeug.contrib.cache import SimpleCache

            app.extensions["cache"] = SimpleCache()

    migrate = Migrate(app, db)
    socketio.init_app(app)

    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "info"

    # Register blueprints
    app.register_blueprint(auth)
    app.register_blueprint(user_blueprint)
    app.register_blueprint(message_blueprint)
    app.register_blueprint(admin_blueprint)
    app.register_blueprint(payments_blueprint)
    app.register_blueprint(matchmaking_blueprint)
    app.register_blueprint(market_blueprint)

    # Initialize scheduler
    if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        with app.app_context():
            try:
                init_scheduler(app)
                app.logger.info(
                    "Scheduler initialized successfully with marketplace subscription support"
                )

                # Test email configuration
                from flask_mail import Message

                test_msg = Message(
                    subject="Kimbela Marketplace - Email Test",
                    recipients=["admin@kimbela.com"],  # Change to your admin email
                    body="Email system is working correctly.",
                    sender=app.config["MAIL_DEFAULT_SENDER"],
                )

                # Only send test email in production or when explicitly enabled
                if app.config.get("ENABLE_EMAIL_TEST", False):
                    try:
                        mail.send(test_msg)
                        app.logger.info("Test email sent successfully")
                    except Exception as e:
                        app.logger.error(f"Email test failed: {e}")
                        app.logger.warning("Email notifications may not work properly")

            except Exception as e:
                app.logger.error(f"Failed to initialize scheduler: {e}")
                app.logger.error("Subscription reminders may not work properly")

    # Inject CSRF token into all templates
    @app.context_processor
    def inject_csrf_token():
        return dict(csrf_token=generate_csrf())

    # Jinja filter: Human-readable "time ago"
    @app.template_filter("time_ago")
    def time_ago_filter(timestamp):
        if timestamp is None:
            return "Never"

        now = datetime.now()
        if timestamp.tzinfo is not None:
            now = datetime.now(timezone.utc)

        diff = now - timestamp

        periods = [
            ("year", 60 * 60 * 24 * 365),
            ("month", 60 * 60 * 24 * 30),
            ("day", 60 * 60 * 24),
            ("hour", 60 * 60),
            ("minute", 60),
            ("second", 1),
        ]

        for period_name, period_seconds in periods:
            if diff.total_seconds() >= period_seconds:
                value = int(diff.total_seconds() / period_seconds)
                return f"{value} {period_name}{'s' if value != 1 else ''} ago"

        return "just now"

    # Register template filters
    @app.template_filter("timeago")
    def timeago(dt):
        if dt is None:
            return "Never"

        if isinstance(dt, str):
            try:
                dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
            except:
                return "Unknown"

        now = datetime.utcnow()
        return humanize.naturaltime(now - dt)

    # Jinja filter: Convert UTC to WAT time
    def to_wat(dt):
        if dt:
            wat_time = dt.astimezone(timezone(timedelta(hours=1)))
            return wat_time.strftime("%b %d, %H:%M")
        return "N/A"

    # Jinja filter: Format ISO date to YYYY-MM-DD
    def datetimeformat(value):
        if value:
            try:
                return datetime.fromisoformat(value).strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                return "N/A"
        return "N/A"

    def monthformat(value):
        if value:
            try:
                return datetime.fromisoformat(value).strftime("%b")
            except (ValueError, TypeError):
                return "N/A"
        return "N/A"

    app.jinja_env.filters["monthformat"] = monthformat

    # Register filters
    app.jinja_env.filters["to_wat"] = to_wat
    app.jinja_env.filters["datetimeformat"] = datetimeformat

    return app
