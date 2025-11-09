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
from flask_wtf.csrf import generate_csrf
from werkzeug.security import check_password_hash

from flask_login import login_user, logout_user, login_required, current_user
import cloudinary.uploader, os
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os, requests, json
from extensions import db, bcrypt
from werkzeug.utils import secure_filename

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
from models import User


from flask_login import login_user, logout_user, login_required, current_user

from extensions import db
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from io import BytesIO

import random
from extensions import db, login_manager, mail
import string
from flask_mail import Message



auth = Blueprint("auth", __name__)


load_dotenv()

env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=env_path)


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


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
    today = datetime.utcnow().date()
    age = today.year - birth_date.year
    if (today.month, today.day) < (birth_date.month, birth_date.day):
        age -= 1
    return age


@auth.route("/")
@auth.route("/index", methods=["GET", "POST"])
def index():
    return render_template("index.html")


@auth.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        # Extract form data
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone_number = request.form.get("phone_number", "").strip()
        dob_str = request.form.get("dob")
        gender = request.form.get("gender")
        city = request.form.get("city", "").strip()
        country = request.form.get("country", "").strip()
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")
        terms = request.form.get("terms")
        interests = request.form.get("interests", "").strip()

        errors = {}

        # === Individual Field Validation ===
        if not first_name:
            errors['first_name'] = "First name is required."
        
        if not last_name:
            errors['last_name'] = "Last name is required."
            
        if not email:
            errors['email'] = "Email is required."
        elif not re.match(r"^[^@]+@[^@]+\.[^@]+$", email):
            errors['email'] = "Please enter a valid email address."
        elif User.query.filter_by(email=email).first():
            errors['email'] = "This email is already registered."

        if not phone_number:
            errors['phone_number'] = "Phone number is required."
        elif not re.match(r"^\+?[\d\s\-\(\)]{10,}$", phone_number):
            errors['phone_number'] = "Please enter a valid phone number."

        if not dob_str:
            errors['dob'] = "Date of birth is required."
        else:
            try:
                dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
                age = calculate_age(dob)
                if age < 31:
                    errors['dob'] = "You must be at least 31 years old to join Kimbela."
            except ValueError:
                errors['dob'] = "Invalid date of birth."

        if not gender:
            errors['gender'] = "Gender is required."

        if not city:
            errors['city'] = "City is required."

        if not country:
            errors['country'] = "Country is required."

        if not password:
            errors['password'] = "Password is required."
        elif not is_strong_password(password):
            errors['password'] = "Password must be at least 8 characters with uppercase, lowercase, number, and symbol."

        if not confirm_password:
            errors['confirm_password'] = "Please confirm your password."
        elif password != confirm_password:
            errors['confirm_password'] = "Passwords do not match."

        if not terms:
            errors['terms'] = "You must agree to the Terms of Service and Privacy Policy."

        # If there are errors, return to form
        if errors:
            for field, error in errors.items():
                flash(error, "danger")
            max_dob = (datetime.utcnow().date() - timedelta(days=31*365)).strftime("%Y-%m-%d")
            return render_template(
                "register.html", 
                max_dob=max_dob,
                errors=errors,
                request=request
            )

        # === Create User ===
        try:
            user = User(
                first_name=first_name,
                last_name=last_name,
                email=email,
                phone_number=phone_number,
                dob=dob,
                gender=gender,
                city=city,
                country=country,
                interests=interests,
                is_active=False  
            )
            user.set_password(password)

            # Generate 6-digit OTP
            otp = user.generate_otp()  # ← This method sets email_token & expires

            db.session.add(user)
            db.session.commit()

            # === Send Verification Email with OTP ===
            try:
                msg = Message(
                    subject="Your Kimbela Verification Code",
                    sender=current_app.config['MAIL_DEFAULT_SENDER'],
                    recipients=[email]
                )
                msg.html = render_template(
                    "emails/verify_email.html",
                    user=user,
                    otp=otp  # ← Pass the 6-digit code
                )
                mail.send(msg)
                flash("Check your email for the 6-digit verification code.", "success")
            except Exception as e:
                print(f"Email send failed: {e}")
                flash("Registration successful, but failed to send verification email. Please contact support.", "warning")

            # Redirect to OTP entry page
            return redirect(url_for("auth.verify_page", email=email))

        except Exception as e:
            db.session.rollback()
            flash("An error occurred during registration. Please try again.", "danger")
            print(f"Registration error: {e}")
            max_dob = (datetime.utcnow().date() - timedelta(days=31*365)).strftime("%Y-%m-%d")
            return render_template(
                "register.html", 
                max_dob=max_dob,
                errors={},
                request=request
            )

    # === GET request ===
    max_dob = (datetime.utcnow().date() - timedelta(days=31*365)).strftime("%Y-%m-%d")
    return render_template(
        "register.html", 
        max_dob=max_dob, 
        csrf_token=generate_csrf(), 
        errors={}
    )



@auth.route("/verify", methods=["GET", "POST"])
def verify_page():
    email = request.args.get("email") or request.form.get("email")
    if not email:
        flash("No email supplied.", "danger")
        return redirect(url_for("auth.login"))

    user = User.query.filter_by(email=email, is_active=False).first()
    if not user:
        flash("Account already verified or not found.", "info")
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        token = request.form.get("token", "").strip()
        if user.email_token != token:
            flash("Invalid token.", "danger")
            return render_template("verify.html", email=email)

        # Token is correct → activate
        if user.email_token_expires < datetime.utcnow():
            flash("Token expired. Please register again.", "danger")
            return redirect(url_for("auth.register"))

        user.is_active = True
        user.email_token = None
        user.email_token_expires = None
        db.session.commit()

        flash("Email verified! You can now log in.", "success")
        return redirect(url_for("auth.login"))

    # GET – show the form
    return render_template("verify.html", email=email)



@auth.route("/resend-verification")
def resend_verification():
    email = request.args.get("email")
    user = User.query.filter_by(email=email, is_active=False).first()
    if not user:
        flash("No pending verification for this email.", "info")
        return redirect(url_for("auth.login"))

    token = user.generate_email_token()
    db.session.commit()

    short_token = user.generate_short_token()
    msg = Message("Your Kimbela verification token", sender=current_app.config['MAIL_DEFAULT_SENDER'], recipients=[email])
    msg.html = render_template("emails/verify_email.html", user=user, verify_url=verify_url)
    mail.send(msg)

    flash("A new token has been sent to your email.", "success")
    return redirect(url_for("auth.verify_page", email=email))




@auth.route("/login", methods=["GET", "POST"])
def login():
    # If already logged in → go to dashboard
    if current_user.is_authenticated:
        return redirect(url_for("main.user_dashboard"))

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
            flash("Please verify your email before logging in. <a href='/resend-verification?email=" + email + "' class='alert-link'>Resend code</a>", "warning")
            return render_template("login.html")

        # === Login successful ===
        login_user(user, remember=remember)
        flash(f"Welcome back, {user.first_name}! You're now logged in.", "success")

        # Optional: redirect to next page (e.g. ?next=/profile)
        next_page = request.args.get("next")
        if next_page and next_page.startswith("/"):
            return redirect(next_page)

        return redirect(url_for("auth.user_dashboard"))

    # === GET request ===
    return render_template("login.html")



@auth.route("/user_dashboard", methods=["GET", "POST"])
def user_dashboard():
    return render_template("user_dashboard.html", user=current_user)





@auth.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    return render_template("forgot_password.html")





@auth.route("/about", methods=["GET", "POST"])
def about():
    return render_template("about.html")

@auth.route("/features", methods=["GET", "POST"])
def features():
    return render_template("features.html")

@auth.route("/contact", methods=["GET", "POST"])
def contact():
    return render_template("contact.html")


@auth.route("/terms", methods=["GET", "POST"])
def terms():
    return render_template("terms.html")

@auth.route("/privacy", methods=["GET", "POST"])
def privacy():
    return render_template("privacy.html")

