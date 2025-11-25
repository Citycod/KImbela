from flask import Flask, session
from flask_wtf.csrf import CSRFProtect, generate_csrf
from dotenv import load_dotenv
import os
from flask_migrate import Migrate
from extensions import db, bcrypt, login_manager, mail
from users.user import user as user_blueprint
from authentication.authenticate import auth
from admin.admin import admin as admin_blueprint
from payments.payments import payments as payments_blueprint
from models import User, Post, Comment, Like, FriendRequest, friendship
from datetime import datetime, timedelta, timezone
from extensions import db, socketio
from messages.messaging import messaging as message_blueprint
from scheduler import init_scheduler  # Add this import

load_dotenv()

csrf = CSRFProtect()

def create_app():
    app = Flask(__name__)
    
    # Stripe configuration
    app.config['STRIPE_SECRET_KEY'] = os.getenv('STRIPE_SECRET_KEY')
    app.config['STRIPE_PUBLISHABLE_KEY'] = os.getenv('STRIPE_PUBLISHABLE_KEY')
    app.config['STRIPE_WEBHOOK_SECRET'] = os.getenv('STRIPE_WEBHOOK_SECRET')
    
    # Flutterwave configuration
    app.config['FLUTTERWAVE_PUBLIC_KEY'] = os.getenv('PUBLIC_KEY')
    app.config['FLUTTERWAVE_SECRET_KEY'] = os.getenv('SECRET_KEY')
    app.config['FLUTTERWAVE_ENCRYPTION_KEY'] = os.getenv('ENCRYPTION_KEY')
    
    # Verify webhook secret is loaded
    if not app.config['STRIPE_WEBHOOK_SECRET']:
        app.logger.error("STRIPE_WEBHOOK_SECRET is not set!")
        raise Exception("STRIPE_WEBHOOK_SECRET is not set!")
    
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("SQLALCHEMY_DATABASE_URI")
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=3000)
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_pre_ping": True,  # check connections before use
        "pool_recycle": 300,  # recycle connections every 5 minutes
        "pool_size": 5,  # keep a few connections alive
        "max_overflow": 10,
    }

    # Email configuration
    app.config["MAIL_SERVER"] = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    app.config["MAIL_PORT"] = int(os.getenv("MAIL_PORT", 587))
    app.config["MAIL_USE_TLS"] = os.getenv("MAIL_USE_TLS", "True").lower() == "true"
    app.config["MAIL_USE_SSL"] = os.getenv("MAIL_USE_SSL", "False").lower() == "true"
    app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")
    app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")
    app.config["MAIL_DEFAULT_SENDER"] = os.getenv("MAIL_DEFAULT_SENDER")

    # Initialize extensions
    mail.init_app(app)
    csrf.init_app(app)
    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
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

    # Initialize scheduler - ADD THIS SECTION
    if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        with app.app_context():
            init_scheduler(app)
            app.logger.info("Scheduler initialized successfully")

    # Inject CSRF token into all templates
    @app.context_processor
    def inject_csrf_token():
        return dict(csrf_token=generate_csrf())

    # Jinja filter: Human-readable "time ago"
    @app.template_filter("time_ago")
    def time_ago_filter(timestamp):
        now = datetime.now()
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
    @app.template_filter('timeago')
    def timeago(dt):
        if dt is None:
            return "Never"
        
        # Make sure dt is a datetime object
        if isinstance(dt, str):
            try:
                dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
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
                return datetime.fromisoformat(value).strftime("%Y-%m-DD")
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