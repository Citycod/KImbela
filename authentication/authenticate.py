from flask import (
    Flask,
    url_for,
    redirect,
    render_template,
    request,
    flash,
    Blueprint,
    session,
    current_app,
)

from datetime import datetime
import humanize

from sqlalchemy import event
from flask_wtf.csrf import generate_csrf
from werkzeug.security import check_password_hash

from flask_login import login_user, logout_user, login_required, current_user
import cloudinary.uploader, os
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os, requests, json
from extensions import db, bcrypt
from werkzeug.utils import secure_filename

import cloudinary.uploader
import cloudinary.utils


from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    request,
    flash,
    jsonify,
    send_file,
)
import logging, secrets, re
from models import (
    User,
    Post,
    Comment,
    Like,
    FriendRequest,
    friendship,
    Notification,
    NotificationType,
    Group,
    SponsoredAd,
    ReportedContent,
    LoginHistory,
    UserSession,
    group_members,
    ReportedContent,
    # ReportedPost,
)

from flask_login import login_user, logout_user, login_required, current_user

from extensions import db
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from io import BytesIO

import random
from extensions import db, login_manager, mail
import string
from resend_mail import Message
from dotenv import load_dotenv

from flask import jsonify, request
from random import sample
from datetime import datetime
from flask_limiter.util import get_remote_address
from flask_limiter import Limiter
from user_agents import parse as parse_user_agent


from time_utils import utcnow
limiter = Limiter(key_func=get_remote_address)


load_dotenv()

env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=env_path)

# config.py or top of app.py
import cloudinary

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True,
)


auth = Blueprint("auth", __name__)


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


MAIL_USERNAME = os.getenv("MAIL_USERNAME")
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
MAIL_PORT = os.getenv("MAIL_PORT")
MAIL_SERVER = os.getenv("MAIL_SERVER")
MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER")


# Add this function to create a timeago filter
def timeago_filter(dt):
    if dt is None:
        return "Never"

    # Make sure dt is a datetime object
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except:
            return "Unknown"

    now = utcnow()
    return humanize.naturaltime(now - dt)


def is_strong_password(password):
    if len(password) < 8:
        return False
    if not re.search(r"[a-z]", password):
        return False
    if not re.search(r"[A-Z]", password):
        return False
    if not re.search(r"\d", password):
        return False
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        return False
    return True


def calculate_age(birth_date):
    today = utcnow().date()
    age = today.year - birth_date.year
    if (today.month, today.day) < (birth_date.month, birth_date.day):
        age -= 1
    return age


def resolve_client_ip():
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.headers.get("X-Real-IP") or request.remote_addr


def resolve_location_from_headers():
    return {
        "country": (
            request.headers.get("CF-IPCountry")
            or request.headers.get("X-Geo-Country")
            or request.headers.get("X-Country-Code")
        ),
        "region": (
            request.headers.get("X-Geo-Region")
            or request.headers.get("X-Region")
            or request.headers.get("X-Country-Region")
        ),
        "city": request.headers.get("X-Geo-City") or request.headers.get("X-City"),
    }


def format_location(location_data):
    parts = [
        (location_data.get("city") or "").strip(),
        (location_data.get("region") or "").strip(),
        (location_data.get("country") or "").strip(),
    ]
    return ", ".join([part for part in parts if part]) or "Unknown location"


def build_login_metadata(remember=False):
    user_agent_string = (request.user_agent.string or "").strip()
    parsed_agent = parse_user_agent(user_agent_string)
    location_data = resolve_location_from_headers()
    ip_address = resolve_client_ip() or "Unknown"

    browser_parts = [
        parsed_agent.browser.family if user_agent_string else "Unknown browser",
        parsed_agent.browser.version_string,
    ]
    os_parts = [
        parsed_agent.os.family if user_agent_string else "Unknown OS",
        parsed_agent.os.version_string,
    ]
    browser = " ".join([part for part in browser_parts if part]).strip()
    operating_system = " ".join([part for part in os_parts if part]).strip()

    if parsed_agent.is_mobile:
        device_kind = "Mobile"
    elif parsed_agent.is_tablet:
        device_kind = "Tablet"
    elif parsed_agent.is_pc:
        device_kind = "Desktop"
    else:
        device_kind = "Device"

    device = f"{device_kind}: {browser or 'Unknown browser'} on {operating_system or 'Unknown OS'}"
    login_time = utcnow()

    return {
        "ip_address": ip_address,
        "user_agent": user_agent_string or "Unknown user agent",
        "browser": browser or "Unknown browser",
        "operating_system": operating_system or "Unknown OS",
        "device": device,
        "location": format_location(location_data),
        "remember": remember,
        "login_time": login_time,
        "login_time_display": login_time.strftime("%A, %B %d, %Y at %H:%M UTC"),
    }


def ensure_login_tracking_tables():
    try:
        LoginHistory.__table__.create(bind=db.engine, checkfirst=True)
        UserSession.__table__.create(bind=db.engine, checkfirst=True)
    except Exception as exc:
        current_app.logger.warning("Unable to verify login tracking tables: %s", exc)


def record_login_activity(user, metadata):
    ensure_login_tracking_tables()

    session_identifier = session.get("user_session_id")
    if not session_identifier:
        session_identifier = secrets.token_urlsafe(24)
        session["user_session_id"] = session_identifier

    db.session.add(
        LoginHistory(
            user_id=user.id,
            ip_address=(metadata["ip_address"] or "")[:50],
            user_agent=metadata["user_agent"],
            device=(metadata["device"] or "")[:200],
            location=(metadata["location"] or "")[:200],
            success=True,
            created_at=metadata["login_time"],
        )
    )

    active_session = UserSession.query.filter_by(session_id=session_identifier).first()
    if active_session:
        active_session.user_id = user.id
        active_session.ip_address = (metadata["ip_address"] or "")[:50]
        active_session.user_agent = metadata["user_agent"]
        active_session.device = (metadata["device"] or "")[:200]
        active_session.location = (metadata["location"] or "")[:200]
        active_session.last_active = metadata["login_time"]
    else:
        db.session.add(
            UserSession(
                user_id=user.id,
                session_id=session_identifier,
                ip_address=(metadata["ip_address"] or "")[:50],
                user_agent=metadata["user_agent"],
                device=(metadata["device"] or "")[:200],
                location=(metadata["location"] or "")[:200],
                last_active=metadata["login_time"],
                created_at=metadata["login_time"],
            )
        )

    db.session.commit()


def send_login_alert_email(user, metadata):
    msg = Message(
        subject="New Sign-in to Your Kimbela Account",
        sender=current_app.config["MAIL_DEFAULT_SENDER"],
        recipients=[user.email],
    )
    msg.html = render_template(
        "login_alert_email.html",
        user=user,
        login_time_display=metadata["login_time_display"],
        ip_address=metadata["ip_address"],
        browser=metadata["browser"],
        operating_system=metadata["operating_system"],
        device=metadata["device"],
        location=metadata["location"],
        remember=metadata["remember"],
        account_settings_url=url_for("market.seller_settings", _external=True),
    )
    msg.body = (
        f"Hello {user.first_name},\n\n"
        "We noticed a new sign-in to your Kimbela account.\n\n"
        f"Time: {metadata['login_time_display']}\n"
        f"Location: {metadata['location']}\n"
        f"IP Address: {metadata['ip_address']}\n"
        f"Device: {metadata['device']}\n"
        f"Browser: {metadata['browser']}\n"
        f"Operating System: {metadata['operating_system']}\n"
        f"Remember Me: {'Yes' if metadata['remember'] else 'No'}\n\n"
        "If this was not you, reset your password and review your account immediately."
    )
    mail.send(msg)


def send_verification_email(user):
    otp = user.generate_otp()
    msg = Message(
        subject="Your Kimbela Verification Code",
        sender=current_app.config["MAIL_DEFAULT_SENDER"],
        recipients=[user.email],
    )
    msg.html = render_template("welcome_email.html", user=user, otp=otp)
    msg.body = (
        f"Hello {user.first_name},\n\n"
        f"Your Kimbela verification code is: {otp}\n\n"
        "This code will expire in 10 minutes. If you did not create this account, please ignore this email."
    )
    mail.send(msg)
    return otp


@auth.route("/test-email", methods=["GET", "POST"])
def test_email():
    """Test email functionality with local debug server"""
    if request.method == "POST":
        test_email = request.form.get("test_email", "").strip() or "test@example.com"

        try:
            print(f"\n📧 Attempting to send test email to: {test_email}")
            print("🔧 Using Resend email delivery")

            # Create test email
            msg = Message(
                subject="🎉 Kimbela Email Test - SUCCESS!",
                sender=current_app.config["MAIL_DEFAULT_SENDER"],
                recipients=[test_email],
                body=f"""Hello!

This is a test email from your Kimbela application.

✅ If you can see this in your terminal, your email setup is working!
✅ The local SMTP server is correctly intercepting and displaying emails.

Timestamp: {utcnow()}

This email was sent through the Resend email delivery API.

Next steps:
1. Replace the temporary Resend API key in your environment
2. Verify your sending domain inside Resend
3. Your email templates and logic will work the same way

Cheers,
Kimbela Team
""",
            )

            # Add HTML version too
            msg.html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 20px; }}
                    .success {{ color: #28a745; font-weight: bold; }}
                    .info {{ background: #f8f9fa; padding: 15px; border-radius: 5px; }}
                </style>
            </head>
            <body>
                <h1 class="success">✅ Kimbela Email Test - SUCCESS!</h1>
                <p>Hello!</p>
                <p>This is a test email from your Kimbela application.</p>
                
                <div class="info">
                    <p><strong>Resend Delivery Active</strong></p>
                    <p>This email was generated by your Kimbela app and sent through Resend.</p>
                    <p>Timestamp: {utcnow()}</p>
                </div>
                
                <p>Your email functionality is working correctly for development!</p>
                
                <hr>
                <p><small>Kimbela Team</small></p>
            </body>
            </html>
            """

            mail.send(msg)

            success_msg = (
                f"✅ Test email processed successfully! Check your terminal for output."
            )
            flash(success_msg, "success")
            flash("📧 Test email was sent through Resend.", "info")

        except Exception as e:
            error_msg = f"❌ Email processing failed: {str(e)}"
            print(f"ERROR: {e}")
            flash(error_msg, "danger")

            # Additional troubleshooting help
            flash("💡 Make sure RESEND_API_KEY and MAIL_DEFAULT_SENDER are configured.", "info")

        return render_template("test_email.html")

    return render_template("test_email.html")


@auth.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def register():
    # Define options for dropdowns
    EDUCATIONAL_LEVELS = [
        "Primary or Elementary School",
        "Middle School or Junior High School",
        "High School",
        "Vocational College",
        "Associate Degree",
        "Bachelor's Degree",
        "Master's Degree",
        "PhD or Doctorate",
        "No Formal Education",
        "Other",
    ]

    INTERESTS_LIST = [
        "Reading",
        "Traveling",
        "Cooking",
        "Photography",
        "Music",
        "Sports",
        "Gardening",
        "Painting",
        "Dancing",
        "Hiking",
        "Movies",
        "Technology",
        "Art",
        "Writing",
        "Fishing",
        "Yoga",
        "Meditation",
        "Chess",
        "Gaming",
        "Knitting",
        "Bird Watching",
        "Wine Tasting",
        "Volunteering",
        "Learning Languages",
        "Camping",
        "Cycling",
        "Swimming",
        "Running",
        "Weightlifting",
        "Pottery",
        "Sculpting",
        "Drawing",
        "Singing",
        "Playing Instruments",
        "Theater",
        "Dancing",
        "Poetry",
        "Blogging",
        "Podcasting",
        "DIY Projects",
        "Woodworking",
        "Car Restoration",
        "Home Decorating",
        "Watching Sports",
        "Fantasy Sports",
        "Collecting",
        "Antique Hunting",
        "Stargazing",
        "Meteorology",
        "Genealogy",
        "History Research",
        "Baking",
        "Coffee Brewing",
        "Tea Tasting",
        "Mixology",
        "Foodie Culture",
        "Motorcycles",
        "Sailing",
        "Scuba Diving",
        "Rock Climbing",
        "Mountain Biking",
        "Fashion",
        "Makeup Artistry",
        "Hair Styling",
        "Fitness Training",
        "Nutrition",
        "Philosophy",
        "Psychology",
        "Sociology",
        "Political Science",
        "Economics",
        "Astronomy",
        "Physics",
        "Biology",
        "Chemistry",
        "Mathematics",
        "Computer Programming",
        "Web Development",
        "Data Science",
        "Artificial Intelligence",
        "Cryptocurrency",
        "Stock Trading",
        "Real Estate",
        "Entrepreneurship",
        "Startups",
    ]

    RELIGIONS = [
        "Islam",
        "Roman Catholic",
        "No religion / Atheist / Agnostic",
        "Hinduism",
        "Buddhism",
        "Pentecostal",
        "Traditional / Indigenous beliefs",
        "Orthodox Christian",
        "Charismatic",
        "Non-denominational churches",
        "Anglican",
        "Baptist",
        "Methodist",
        "Seventh - day Adventist",
        "Jehovah’s Witness",
        "Latter-day Saints (Mormons)",
        "Sikhism",
        "Judaism",
        "Bahá'í Faith",
        "Jainism",
        "White Garment Churches",
        "Other",
    ]

    ETHNICITIES = [
        "African",
        "African American",
        "Asian",
        "Caucasian",
        "Hispanic/Latino",
        "Native American",
        "Pacific Islander",
        "Middle Eastern",
        "Mixed Race",
        "Caribbean",
        "European",
        "South Asian",
        "East Asian",
        "Southeast Asian",
        "Indigenous Australian",
        "Maori",
        "Other",
    ]

    if request.method == "POST":
        # Extract form data
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        dob_str = request.form.get("dob")
        gender = request.form.get("gender")
        marital_status = request.form.get("marital_status")
        city = request.form.get("city", "").strip()
        country = request.form.get("country", "").strip()
        state = request.form.get("state", "").strip()
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")
        terms = request.form.get("terms")
        interests = request.form.getlist("interests")
        educational_level = request.form.get("educational_level")
        occupation = request.form.get("occupation", "").strip()
        ethnicity = request.form.get("ethnicity")
        religion = request.form.get("religion")
        about_me = request.form.get("about_me", "").strip()  # NEW FIELD

        errors = {}

        # === Individual Field Validation ===
        if not first_name:
            errors["first_name"] = "First name is required."

        if not last_name:
            errors["last_name"] = "Last name is required."

        if not email:
            errors["email"] = "Email is required."
        elif not re.match(r"^[^@]+@[^@]+\.[^@]+$", email):
            errors["email"] = "Please enter a valid email address."
        elif User.query.filter_by(email=email).first():
            errors["email"] = "This email is already registered."

        if not dob_str:
            errors["dob"] = "Date of birth is required."
        else:
            try:
                dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
                age = calculate_age(dob)
                if age < 31:
                    errors["dob"] = "You must be at least 31 years old to join Kimbela."
            except ValueError:
                errors["dob"] = "Invalid date of birth."

        if not gender:
            errors["gender"] = "Gender is required."

        if not marital_status:
            errors["marital_status"] = "Marital status is required."

        if not country:
            errors["country"] = "Country is required."

        if not state:
            errors["state"] = "State / Province is required."

        if not city:
            errors["city"] = "City is required."

        if not password:
            errors["password"] = "Password is required."
        elif not is_strong_password(password):
            errors["password"] = (
                "Password must be at least 8 characters with uppercase, lowercase, number, and symbol."
            )

        if not confirm_password:
            errors["confirm_password"] = "Please confirm your password."
        elif password != confirm_password:
            errors["confirm_password"] = "Passwords do not match."

        if not terms:
            errors["terms"] = (
                "You must agree to the Terms of Service and Privacy Policy."
            )

        # If there are errors, return to form
        if errors:
            for field, error in errors.items():
                flash(error, "danger")
            max_dob = (utcnow().date() - timedelta(days=31 * 365)).strftime(
                "%Y-%m-%d"
            )
            return render_template(
                "register.html",
                max_dob=max_dob,
                errors=errors,
                request=request,
                educational_levels=EDUCATIONAL_LEVELS,
                interests_list=INTERESTS_LIST,
                religions=RELIGIONS,
                ethnicities=ETHNICITIES,
            )

        # === Create User ===
        try:
            # Convert interests list to comma-separated string
            interests_str = ", ".join(interests) if interests else None

            user = User(
                first_name=first_name,
                last_name=last_name,
                email=email,
                phone_number="",
                dob=dob,
                gender=gender,
                city=city,
                marital_status=marital_status,
                country=country,
                state=state,
                interests=interests_str,
                educational_level=educational_level,
                occupation=occupation,
                ethnicity=ethnicity,
                religion=religion,
                about_me=about_me,  # NEW FIELD
                is_active=False,
            )
            user.set_password(password)

            # Generate 6-digit OTP
            db.session.add(user)
            db.session.commit()
            # === Send Verification Email with OTP ===
            try:
                send_verification_email(user)
                flash("Check your email for the 6-digit verification code.", "success")
            except Exception as e:
                print(f"Email send failed: {e}")
                flash(
                    "Registration successful, but failed to send verification email. Please contact support.",
                    "warning",
                )

            return redirect(url_for("auth.verify_page", email=email))

        except Exception as e:
            db.session.rollback()
            flash("An error occurred during registration. Please try again.", "danger")
            print(f"Registration error: {e}")
            max_dob = (utcnow().date() - timedelta(days=31 * 365)).strftime(
                "%Y-%m-%d"
            )
            return render_template(
                "register.html",
                max_dob=max_dob,
                errors={},
                request=request,
                educational_levels=EDUCATIONAL_LEVELS,
                interests_list=INTERESTS_LIST,
                religions=RELIGIONS,
                ethnicities=ETHNICITIES,
            )

    # === GET request ===
    max_dob = (utcnow().date() - timedelta(days=31 * 365)).strftime("%Y-%m-%d")
    return render_template(
        "register.html",
        max_dob=max_dob,
        csrf_token=generate_csrf(),
        errors={},
        educational_levels=EDUCATIONAL_LEVELS,
        interests_list=INTERESTS_LIST,
        religions=RELIGIONS,
        ethnicities=ETHNICITIES,
    )


@auth.route("/verify", methods=["GET", "POST"])
def verify_page():
    email = (request.args.get("email") or request.form.get("email") or "").strip().lower()
    if not email:
        flash("No email supplied.", "danger")
        return redirect(url_for("auth.login"))

    user = User.query.filter_by(email=email, is_active=False).first()
    if not user:
        flash("Account already verified or not found.", "info")
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        token = request.form.get("token", "").strip()
        if user.otp != token:
            flash("Invalid token.", "danger")
            return render_template("verify.html", email=email, user=user)

        # Token is correct → activate
        if not user.otp_expires or user.otp_expires < utcnow():
            flash("Token expired. Please register again.", "danger")
            return redirect(url_for("auth.register"))

        user.is_active = True
        user.otp = None
        user.otp_expires = None
        db.session.commit()

        # === Send Welcome Email ===
        try:
            msg = Message(
                subject="Welcome to Kimbela! Start Your Journey",
                sender=current_app.config["MAIL_DEFAULT_SENDER"],
                recipients=[email],
            )
            msg.html = render_template("welcome_email.html", user=user)
            mail.send(msg)
            print(f"Welcome email sent to {email}")
        except Exception as e:
            print(f"Welcome email send failed: {e}")
            # Don't flash error to user since verification was successful

        flash(
            "Email verified! Welcome to Kimbela! Check your email for a welcome message.",
            "success",
        )
        return redirect(url_for("auth.login"))

    # GET – show the form
    return render_template("verify.html", email=email, user=user)


@auth.route("/resend-verification")
def resend_verification():
    email = (request.args.get("email") or "").strip().lower()
    if not email:
        flash("No email supplied.", "danger")
        return redirect(url_for("auth.login"))

    user = User.query.filter_by(email=email, is_active=False).first()
    if not user:
        flash("No pending verification for this email.", "info")
        return redirect(url_for("auth.login"))

    try:
        send_verification_email(user)
    except Exception as exc:
        current_app.logger.exception("Failed to resend verification email: %s", exc)
        flash("We could not resend the verification code right now. Please try again.", "danger")
        return redirect(url_for("auth.verify_page", email=email))

    flash("A new token has been sent to your email.", "success")
    return redirect(url_for("auth.verify_page", email=email))


@auth.route("/login", methods=["GET", "POST"])
def login():
    # If already logged in → go to dashboard
    if current_user.is_authenticated:
        return redirect(url_for("user.user_dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password")
        remember = bool(request.form.get("remember"))

        # === Basic validation ===
        if not email:
            flash("Please enter your email.", "danger")
            return render_template("login.html")
        if not password:
            flash("Please enter your password.", "danger")
            return render_template("login.html")

        # === Find user ===
        user = User.query.filter_by(email=email).first()

        # === Check credentials & account status ===
        if not user:
            flash("Invalid email or password.", "danger")
            return render_template("login.html")

        if not user.check_password(password):
            flash("Invalid email or password.", "danger")
            return render_template("login.html")

        if not user.is_active:
            flash(
                "Please verify your email address before logging in.",
                "warning",
            )
            return redirect(url_for("auth.verify_page", email=email))

        # === Login successful ===
        login_metadata = build_login_metadata(remember=remember)
        login_user(user, remember=remember)

        try:
            record_login_activity(user, login_metadata)
        except Exception as exc:
            db.session.rollback()
            current_app.logger.exception("Failed to record login activity: %s", exc)

        try:
            send_login_alert_email(user, login_metadata)
        except Exception as exc:
            current_app.logger.exception("Failed to send login alert email: %s", exc)

        flash(f"Welcome back, {user.first_name}! You're now logged in.", "success")

        # Optional: redirect to next page (e.g. ?next=/profile)
        next_page = request.args.get("next")
        if next_page and next_page.startswith("/"):
            return redirect(next_page)

        if user.is_super_admin:
            return redirect(url_for("admin.admin_dashboard"))
        if user.is_admin:
            return redirect(url_for("admin.admin_reports"))

        return redirect(url_for("user.user_dashboard"))

    # === GET request ===
    return render_template("login.html")


@auth.route("/forgot-password", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()

        if not email:
            flash("Please enter your email address.", "danger")
            return render_template("forgot_password.html")

        if not re.match(r"^[^@]+@[^@]+\.[^@]+$", email):
            flash("Please enter a valid email address.", "danger")
            return render_template("forgot_password.html")

        user = User.query.filter_by(email=email, is_active=True).first()

        # Always show success message even if email doesn't exist (for security)
        if user:
            # Generate reset token
            reset_token = user.generate_password_reset_token()
            db.session.commit()

            # Send reset email
            try:
                msg = Message(
                    subject="Reset Your Kimbela Password",
                    sender=current_app.config["MAIL_DEFAULT_SENDER"],
                    recipients=[email],
                )
                msg.html = render_template(
                    "password_reset_email.html",
                    user=user,
                    reset_token=reset_token,
                    reset_url=url_for(
                        "auth.reset_password", token=reset_token, _external=True
                    ),
                )
                mail.send(msg)
                print(f"Password reset email sent to {email}")
            except Exception as e:
                print(f"Password reset email failed: {e}")
                flash("Failed to send reset email. Please try again later.", "danger")
                return render_template("forgot_password.html")

        flash(
            "If that email exists in our system, we've sent password reset instructions.",
            "success",
        )
        return redirect(url_for("auth.login"))

    return render_template("forgot_password.html")


@auth.route("/reset-password/<token>", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def reset_password(token):
    # Verify token
    user = User.verify_password_reset_token(token)
    if not user:
        flash(
            "Invalid or expired reset token. Please request a new password reset.",
            "danger",
        )
        return redirect(url_for("auth.forgot_password"))

    if request.method == "POST":
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")

        errors = {}

        if not password:
            errors["password"] = "Password is required."
        elif not is_strong_password(password):
            errors["password"] = (
                "Password must be at least 8 characters with uppercase, lowercase, number, and symbol."
            )

        if not confirm_password:
            errors["confirm_password"] = "Please confirm your password."
        elif password != confirm_password:
            errors["confirm_password"] = "Passwords do not match."

        if errors:
            for field, error in errors.items():
                flash(error, "danger")
            return render_template("reset_password.html", token=token)

        # Update password
        user.set_password(password)
        user.password_reset_token = None
        user.password_reset_expires = None
        db.session.commit()

        # Send confirmation email
        try:
            msg = Message(
                subject="Your Kimbela Password Has Been Reset",
                sender=current_app.config["MAIL_DEFAULT_SENDER"],
                recipients=[user.email],
            )
            msg.html = render_template("password_reset_success_email.html", user=user)
            mail.send(msg)
        except Exception as e:
            print(f"Password reset confirmation email failed: {e}")

        flash(
            "Your password has been reset successfully! You can now login with your new password.",
            "success",
        )
        return redirect(url_for("auth.login"))

    return render_template("reset_password.html", token=token)
