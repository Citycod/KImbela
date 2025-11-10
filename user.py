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
from models import User, Post, Comment


from flask_login import login_user, logout_user, login_required, current_user

from extensions import db
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from io import BytesIO

import random
from extensions import db, login_manager, mail
import string
from flask_mail import Message
from dotenv import load_dotenv



load_dotenv()

env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=env_path)

# config.py or top of app.py
import cloudinary
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True
)


auth = Blueprint("auth", __name__)



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
        marital_status = request.form.get("marital_status")
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
            
        if not marital_status:
            errors['marital_status'] = "Marital status is required."

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
                marital_status=marital_status,
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



from flask import jsonify, request

@auth.route('/user_dashboard')
def user_dashboard():
    # Your existing code to get posts
    posts = Post.query.filter_by(author_id=current_user.id).order_by(Post.created_at.desc()).all()
    
    # Convert comments and likes to lists for each post
    for post in posts:
        post.comments_list = list(post.comments)  # Convert to list
        post.likes_list = list(post.likes)        # Convert to list
    
    return render_template('user_dashboard.html', posts=posts)

# Like Post
@auth.route("/like_post/<int:post_id>", methods=["POST"])
@login_required
def like_post(post_id):
    post = Post.query.get_or_404(post_id)
    if current_user in post.likes:
        post.likes.remove(current_user)
        liked = False
    else:
        post.likes.append(current_user)
        liked = True
    db.session.commit()
    return jsonify(likes=len(post.likes), liked=liked)

# Delete Post
@auth.route("/delete_post/<int:post_id>", methods=["POST"])
@login_required
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.author_id != current_user.id:
        return jsonify(error="Unauthorized"), 403
    db.session.delete(post)
    db.session.commit()
    return jsonify(success=True)

# Edit Post
@auth.route("/edit_post", methods=["POST"])
@login_required
def edit_post():
    post_id = request.form.get("post_id")
    post = Post.query.get_or_404(post_id)
    if post.author_id != current_user.id:
        return jsonify(error="Unauthorized"), 403
    post.content = request.form.get("content", "").strip()
    db.session.commit()
    return jsonify(success=True)

# Add Comment
@auth.route("/add_comment/<int:post_id>", methods=["POST"])
@login_required
def add_comment(post_id):
    post = Post.query.get_or_404(post_id)
    content = request.json.get("content", "").strip()
    if not content:
        return jsonify(error="Empty"), 400
    comment = Comment(content=content, author_id=current_user.id, post_id=post_id)
    db.session.add(comment)
    db.session.commit()
    return jsonify(
        name=f"{current_user.first_name} {current_user.last_name}",
        avatar=current_user.profile_pic or url_for('static', filename='assets/img/default-avatar.png'),
        content=content
    )


import cloudinary.uploader
import cloudinary.utils

@auth.route("/<int:user_id>", methods=["GET", "POST"])
@login_required
def profile(user_id):
    user = User.query.get_or_404(user_id)

    # Only allow users to edit their own profile
    if user.id != current_user.id:
        flash("You can only edit your own profile.", "warning")
        return redirect(url_for('auth.profile', user_id=current_user.id))

    if request.method == "POST":
        try:
            # === 1. PROFILE PICTURE ===
            if 'profile_pic' in request.files:
                file = request.files['profile_pic']
                if file and file.filename != '' and allowed_file(file.filename):
                    print(f"Uploading profile picture: {file.filename}")  # Debug
                    result = cloudinary.uploader.upload(
                        file,
                        folder="kimbela/profiles",
                        transformation=[
                            {'width': 400, 'height': 400, 'crop': 'fill', 'gravity': 'face'},
                            {'quality': 'auto', 'fetch_format': 'auto'}
                        ]
                    )
                    current_user.profile_pic = result['secure_url']
                    db.session.commit()
                    flash("Profile picture updated!", "success")
                elif file and file.filename != '':
                    flash("Invalid file type for profile picture.", "danger")

            # === 2. COVER PHOTO ===
            if 'cover_pic' in request.files:
                file = request.files['cover_pic']
                if file and file.filename != '' and allowed_file(file.filename):
                    print(f"Uploading cover photo: {file.filename}")  # Debug
                    result = cloudinary.uploader.upload(
                        file,
                        folder="kimbela/covers",
                        transformation=[
                            {'width': 1200, 'height': 400, 'crop': 'fill'},
                            {'quality': 'auto', 'fetch_format': 'auto'}
                        ]
                    )
                    current_user.cover_pic = result['secure_url']
                    db.session.commit()
                    flash("Cover photo updated!", "success")
                elif file and file.filename != '':
                    flash("Invalid file type for cover photo.", "danger")

            # === 3. BIO UPDATE ===
            bio = request.form.get("bio")
            if bio is not None:
                current_user.bio = bio.strip()
                db.session.commit()
                flash("Bio updated!", "success")

            # === 4. CREATE NEW POST (TEXT + MEDIA) ===
            post_content = request.form.get("post_content")
            media_file = request.files.get('media')
            
            if post_content or (media_file and media_file.filename != ''):
                image_url = None
                video_url = None

                if media_file and media_file.filename != '' and allowed_file(media_file.filename):
                    try:
                        # Determine resource type based on content type
                        resource_type = "auto"
                        if media_file.content_type.startswith('video'):
                            resource_type = "video"
                        
                        result = cloudinary.uploader.upload(
                            media_file,
                            folder="kimbela/posts",
                            resource_type=resource_type,
                            transformation=[
                                {'width': 800, 'crop': 'limit'},
                                {'quality': 'auto', 'fetch_format': 'auto'}
                            ]
                        )
                        
                        if media_file.content_type.startswith('video'):
                            video_url = result['secure_url']
                        else:
                            image_url = result['secure_url']
                            
                    except Exception as e:
                        print(f"Media upload error: {e}")  # Debug
                        flash("Failed to upload media.", "danger")

                # Create post
                new_post = Post(
                    content=post_content or "",
                    image=image_url,
                    video=video_url,
                    author_id=current_user.id,
                    created_at=datetime.utcnow()
                )
                db.session.add(new_post)
                db.session.commit()
                flash("Post created!", "success")

            return redirect(url_for('auth.profile', user_id=current_user.id))

        except Exception as e:
            print(f"Error in profile update: {e}")  # Debug
            flash("An error occurred while updating your profile.", "danger")
            return redirect(url_for('auth.profile', user_id=current_user.id))

    # === GET REQUEST: Load profile data ===
    posts = Post.query.filter_by(author_id=current_user.id)\
                      .order_by(Post.created_at.desc()).all()

    # Mock friends (replace with real Friend model later)
    friends = User.query.filter(User.id != current_user.id).limit(9).all()

    return render_template(
        "profile.html",
        user=current_user,
        posts=posts,
        friends=friends
    )
    
    
@auth.route("/get_comments/<int:post_id>")
def get_comments(post_id):
    post = Post.query.get_or_404(post_id)
    comments = []
    for c in post.comments:
        comments.append({
            'id': c.id,
            'name': f"{c.author.first_name} {c.author.last_name}",
            'avatar': c.author.profile_pic or url_for('static', filename='assets/img/default-avatar.png'),
            'content': c.content,
            'replies': []  # Add later
        })
    return jsonify(comments)


def allowed_file(filename):
    """Check if file extension is allowed"""
    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'mov', 'avi'}
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions
           
           
           
@auth.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))




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

