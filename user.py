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
from models import User, Post, Comment, Like, FriendRequest, friendship, Notification, NotificationType


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

from flask import jsonify, request
from random import sample
from datetime import datetime



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
    # Define options for dropdowns
    EDUCATIONAL_LEVELS = [
        'Primary or Elementary School',
        'Middle School or Junior High School', 
        'High School',
        'Vocational College',
        'Associate Degree',
        'Bachelor\'s Degree',
        'Master\'s Degree',
        'PhD or Doctorate',
        'Professional Degree',
        'No Formal Education'
        'Other'
    ]
    
    INTERESTS_LIST = [
        'Reading', 'Traveling', 'Cooking', 'Photography', 'Music',
        'Sports', 'Gardening', 'Painting', 'Dancing', 'Hiking',
        'Movies', 'Technology', 'Art', 'Writing', 'Fishing',
        'Yoga', 'Meditation', 'Chess', 'Gaming', 'Knitting',
        'Bird Watching', 'Wine Tasting', 'Volunteering', 'Learning Languages',
        'Camping', 'Cycling', 'Swimming', 'Running', 'Weightlifting',
        'Pottery', 'Sculpting', 'Drawing', 'Singing', 'Playing Instruments',
        'Theater', 'Dancing', 'Poetry', 'Blogging', 'Podcasting',
        'DIY Projects', 'Woodworking', 'Car Restoration', 'Home Decorating',
        'Watching Sports', 'Fantasy Sports', 'Collecting', 'Antique Hunting',
        'Stargazing', 'Meteorology', 'Genealogy', 'History Research',
        'Baking', 'Coffee Brewing', 'Tea Tasting', 'Mixology', 'Foodie Culture',
        'Motorcycles', 'Sailing', 'Scuba Diving', 'Rock Climbing', 'Mountain Biking',
        'Fashion', 'Makeup Artistry', 'Hair Styling', 'Fitness Training', 'Nutrition',
        'Philosophy', 'Psychology', 'Sociology', 'Political Science', 'Economics',
        'Astronomy', 'Physics', 'Biology', 'Chemistry', 'Mathematics',
        'Computer Programming', 'Web Development', 'Data Science', 'Artificial Intelligence',
        'Cryptocurrency', 'Stock Trading', 'Real Estate', 'Entrepreneurship', 'Startups'
    ]
    
    RELIGIONS = [
        'Christianity', 'Islam', 'Hinduism', 'Buddhism', 'Judaism',
        'Sikhism', 'Baháʼí Faith', 'Jainism', 'Shinto', 'Taoism',
        'Zoroastrianism', 'Atheism', 'Agnosticism', 'Spiritual but not religious', 'Traditional / Indegenous Beliefs', 'No Religion / Atheist / Agnostic', 'Roman Catholic', 'Anglican', 'Pentecostal', 'Methodist', 'Baptist', 'Seventh Day Adventist', "Jehova's Witnesses", 'Latter Day Saints', 'Mormon', 'Lutheran', 'Presbyterian', 'Episcopal', 'Bible Church', 'Orthodox Christian', 'White Garment Churches',
        'Other'
    ]
    
    ETHNICITIES = [
        'African', 'African American', 'Asian', 'Caucasian', 'Hispanic/Latino',
        'Native American', 'Pacific Islander', 'Middle Eastern', 'Mixed Race',
        'Caribbean', 'European', 'South Asian', 'East Asian', 'Southeast Asian',
        'Indigenous Australian', 'Maori', 'Other'
    ]

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
        interests = request.form.getlist("interests")
        educational_level = request.form.get("educational_level")
        occupation = request.form.get("occupation", "").strip()
        ethnicity = request.form.get("ethnicity")
        religion = request.form.get("religion")
        about_me = request.form.get("about_me", "").strip()  # NEW FIELD

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
                request=request,
                educational_levels=EDUCATIONAL_LEVELS,
                interests_list=INTERESTS_LIST,
                religions=RELIGIONS,
                ethnicities=ETHNICITIES
            )

        # === Create User ===
        try:
            # Convert interests list to comma-separated string
            interests_str = ", ".join(interests) if interests else None
            
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
                interests=interests_str,
                educational_level=educational_level,
                occupation=occupation,
                ethnicity=ethnicity,
                religion=religion,
                about_me=about_me,  # NEW FIELD
                is_active=False  
            )
            user.set_password(password)

            # Generate 6-digit OTP
            otp = user.generate_otp()

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
                    otp=otp
                )
                mail.send(msg)
                flash("Check your email for the 6-digit verification code.", "success")
            except Exception as e:
                print(f"Email send failed: {e}")
                flash("Registration successful, but failed to send verification email. Please contact support.", "warning")

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
                request=request,
                educational_levels=EDUCATIONAL_LEVELS,
                interests_list=INTERESTS_LIST,
                religions=RELIGIONS,
                ethnicities=ETHNICITIES
            )

    # === GET request ===
    max_dob = (datetime.utcnow().date() - timedelta(days=31*365)).strftime("%Y-%m-%d")
    return render_template(
        "register.html", 
        max_dob=max_dob, 
        csrf_token=generate_csrf(), 
        errors={},
        educational_levels=EDUCATIONAL_LEVELS,
        interests_list=INTERESTS_LIST,
        religions=RELIGIONS,
        ethnicities=ETHNICITIES
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
        if user.otp != token:
            flash("Invalid token.", "danger")
            return render_template("verify.html", email=email)

        # Token is correct → activate
        if user.otp_expires < datetime.utcnow():
            flash("Token expired. Please register again.", "danger")
            return redirect(url_for("auth.register"))

        user.is_active = True
        user.otp = None
        user.otp_expires = None
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
            flash("Please you need to verify your email address before we let you in.",  "warning")
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
from random import sample


# @auth.route('/user_dashboard')
# @login_required
# def user_dashboard():
#     posts = Post.query.order_by(Post.created_at.desc()).all()

#     # All other users
#     all_users = User.query.filter(User.id != current_user.id).all()

#     # Get list of friend IDs (not full User objects)
#     friend_ids = {friend.id for friend in current_user.friends}

#     # Non-friends = all_users except current_user and friends
#     non_friends = [u for u in all_users if u.id not in friend_ids]

#     # Pick 3 random non-friends
#     random_three = sample(non_friends, min(3, len(non_friends))) if non_friends else []

#     return render_template(
#         'user_dashboard.html',
#         posts=posts,
#         current_user=current_user,
#         all_users=all_users,          # for main "People You May Know"
#         random_three=random_three,    # for right sidebar
#         csrf_token=generate_csrf()
#     )

from datetime import datetime

def timeago(dt):
    now = datetime.utcnow()
    diff = now - dt
    if diff.days > 0:
        return f"{diff.days}d ago"
    hours = diff.seconds // 3600
    if hours > 0:
        return f"{hours}h ago"
    mins = diff.seconds // 60
    return f"{mins}m ago" if mins > 0 else "just now"

    app.jinja_env.filters['timeago'] = timeago




@auth.route('/user_dashboard', methods=['GET', 'POST'])
@login_required
def user_dashboard():
    if request.method == 'POST':
        # Handle post creation here
        post_content = request.form.get("post_content")
        media_file = request.files.get('media')
        
        if post_content or (media_file and media_file.filename != ''):
            image_url = None
            video_url = None

            if media_file and media_file.filename != '' and allowed_file(media_file.filename):
                try:
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
                    print(f"Media upload error: {e}")
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
        
        return redirect(url_for('auth.user_dashboard'))

    # GET request handling (your existing code)
    posts = Post.query.order_by(Post.created_at.desc()).all()
    # 1. Get ALL other users (no block filtering in SQL)
    all_users = User.query.filter(User.id != current_user.id).all()

    # 2. Filter in Python using your existing methods
    all_users = [
        u for u in all_users
        if not u.is_blocked_by(current_user)     # u did NOT block me
        and not current_user.is_blocked_by(u)    # I did NOT block u
    ]
    # FRIENDS (visible only)
    friends = [f for f in current_user.friends if f.is_visible_to(current_user)]

    # NON-FRIENDS for suggestions
    friend_ids = {f.id for f in friends}
    
    non_friends = [u for u in all_users if u.id not in friend_ids]
    friend_ids = {friend.id for friend in current_user.friends}
    non_friends = [u for u in all_users if u.id not in friend_ids]
    random_three = sample(non_friends, min(3, len(non_friends))) if non_friends else []

    return render_template(
        'user_dashboard.html',
        posts=posts,
        current_user=current_user,
        all_users=all_users,
        friends=friends, 
        random_three=random_three,
        csrf_token=generate_csrf()
    )






# Like Post
# @auth.route("/like_post/<int:post_id>", methods=["POST"])
# @login_required
# def like_post(post_id):
#     post = Post.query.get_or_404(post_id)
#     if current_user in post.likes:
#         post.likes.remove(current_user)
#         liked = False
#     else:
#         post.likes.append(current_user)
#         liked = True
#     db.session.commit()
#     return jsonify(likes=len(post.likes), liked=liked)



@auth.route("/like_post/<int:post_id>", methods=["POST"])
@login_required
def like_post(post_id):
    post = Post.query.get_or_404(post_id)
    
    existing_like = Like.query.filter_by(user_id=current_user.id, post_id=post_id).first()
    
    if existing_like:
        db.session.delete(existing_like)
        liked = False
    else:
        new_like = Like(user_id=current_user.id, post_id=post_id)
        db.session.add(new_like)
        liked = True
        
        # Create notification for post owner (if not liking own post)
        if post.author_id != current_user.id:
            post.author.create_notification(
                actor=current_user,
                notification_type=NotificationType.POST_LIKE,
                entity_id=post_id,
                entity_type='post'
            )
    
    db.session.commit()
    like_count = Like.query.filter_by(post_id=post_id).count()
    return jsonify(likes=like_count, liked=liked)



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
# In your add_comment route
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
    
    # Create notification for post owner (if not commenting on own post)
    if post.author_id != current_user.id:
        post.author.create_notification(
            actor=current_user,
            notification_type=NotificationType.NEW_COMMENT,
            entity_id=post_id,
            entity_type='post'
        )
    
    return jsonify(
        id=comment.id,
        name=f"{current_user.first_name} {current_user.last_name}",
        avatar=current_user.profile_pic or url_for('static', filename='assets/img/default-avatar.png'),
        content=content
    )


import cloudinary.uploader
import cloudinary.utils

# @auth.route("/<int:user_id>", methods=["GET", "POST"])
# @login_required
# def profile(user_id):
#     user = User.query.get_or_404(user_id)

#     # Only allow users to edit their own profile
#     if user.id != current_user.id:
#         flash("You can only edit your own profile.", "warning")
#         return redirect(url_for('auth.profile', user_id=current_user.id))

#     if request.method == "POST":
#         try:
#             # === 1. PROFILE PICTURE ===
#             if 'profile_pic' in request.files:
#                 file = request.files['profile_pic']
#                 if file and file.filename != '' and allowed_file(file.filename):
#                     print(f"Uploading profile picture: {file.filename}")  # Debug
#                     result = cloudinary.uploader.upload(
#                         file,
#                         folder="kimbela/profiles",
#                         transformation=[
#                             {'width': 400, 'height': 400, 'crop': 'fill', 'gravity': 'face'},
#                             {'quality': 'auto', 'fetch_format': 'auto'}
#                         ]
#                     )
#                     current_user.profile_pic = result['secure_url']
#                     db.session.commit()
#                     flash("Profile picture updated!", "success")
#                 elif file and file.filename != '':
#                     flash("Invalid file type for profile picture.", "danger")

#             # === 2. COVER PHOTO ===
#             if 'cover_pic' in request.files:
#                 file = request.files['cover_pic']
#                 if file and file.filename != '' and allowed_file(file.filename):
#                     print(f"Uploading cover photo: {file.filename}")  # Debug
#                     result = cloudinary.uploader.upload(
#                         file,
#                         folder="kimbela/covers",
#                         transformation=[
#                             {'width': 1200, 'height': 400, 'crop': 'fill'},
#                             {'quality': 'auto', 'fetch_format': 'auto'}
#                         ]
#                     )
#                     current_user.cover_pic = result['secure_url']
#                     db.session.commit()
#                     flash("Cover photo updated!", "success")
#                 elif file and file.filename != '':
#                     flash("Invalid file type for cover photo.", "danger")

#             # === 3. BIO UPDATE ===
#             bio = request.form.get("bio")
#             if bio is not None:
#                 current_user.bio = bio.strip()
#                 db.session.commit()
#                 flash("Bio updated!", "success")

#             # === 4. CREATE NEW POST (TEXT + MEDIA) ===
#             post_content = request.form.get("post_content")
#             media_file = request.files.get('media')
            
#             if post_content or (media_file and media_file.filename != ''):
#                 image_url = None
#                 video_url = None

#                 if media_file and media_file.filename != '' and allowed_file(media_file.filename):
#                     try:
#                         # Determine resource type based on content type
#                         resource_type = "auto"
#                         if media_file.content_type.startswith('video'):
#                             resource_type = "video"
                        
#                         result = cloudinary.uploader.upload(
#                             media_file,
#                             folder="kimbela/posts",
#                             resource_type=resource_type,
#                             transformation=[
#                                 {'width': 800, 'crop': 'limit'},
#                                 {'quality': 'auto', 'fetch_format': 'auto'}
#                             ]
#                         )
                        
#                         if media_file.content_type.startswith('video'):
#                             video_url = result['secure_url']
#                         else:
#                             image_url = result['secure_url']
                            
#                     except Exception as e:
#                         print(f"Media upload error: {e}")  # Debug
#                         flash("Failed to upload media.", "danger")
                        
#                 # Notify friends about profile update
#                 if any([request.files.get('profile_pic'), request.files.get('cover_pic'), request.form.get('bio')]):
#                     for friend in current_user.friends:
#                         friend.create_notification(
#                             actor=current_user,
#                             notification_type=NotificationType.PROFILE_UPDATE,
#                             entity_id=current_user.id,
#                             entity_type='user',
#                             custom_message=f"{current_user.full_name} updated their profile"
#                         )

#                 # Create post
#                 new_post = Post(
#                     content=post_content or "",
#                     image=image_url,
#                     video=video_url,
#                     author_id=current_user.id,
#                     created_at=datetime.utcnow()
#                 )
#                 db.session.add(new_post)
#                 db.session.commit()
#                 flash("Post created!", "success")

#             return redirect(url_for('auth.profile', user_id=current_user.id))

#         except Exception as e:
#             print(f"Error in profile update: {e}")  # Debug
#             flash("An error occurred while updating your profile.", "danger")
#             return redirect(url_for('auth.profile', user_id=current_user.id))

#     # === GET REQUEST: Load profile data ===
#     posts = Post.query.filter_by(author_id=current_user.id)\
#                       .order_by(Post.created_at.desc()).all()

#     # Mock friends (replace with real Friend model later)
#     friends = User.query.filter(User.id != current_user.id).limit(9).all()

#     return render_template(
#         "profile.html",
#         user=current_user,
#         posts=posts,
#         friends=friends
#     )
    
    
@auth.route("/get_comments/<int:post_id>")
def get_comments(post_id):
    post = Post.query.get_or_404(post_id)
    # Order comments by created_at DESCENDING (newest first)
    comments = Comment.query.filter_by(post_id=post_id)\
                           .order_by(Comment.created_at.desc())\
                           .all()
    result = []
    for c in comments:
        result.append({
            'id': c.id,
            'name': f"{c.author.first_name} {c.author.last_name}",
            'avatar': c.author.profile_pic or url_for('static', filename='assets/img/default-avatar.png'),
            'content': c.content,
            'created_at': c.created_at.isoformat(),
            'replies': []  # handle replies later
        })
    return jsonify(result)


@auth.route("/debug/notification_status")
@login_required
def debug_notification_status():
    """Check read status of notifications"""
    notifications = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).all()
    result = []
    for n in notifications:
        result.append({
            'id': n.id,
            'type': n.type,
            'message': n.message,
            'is_read': n.is_read,
            'created_at': n.created_at.isoformat()
        })
    return jsonify({
        'total': len(notifications),
        'unread': len([n for n in notifications if not n.is_read]),
        'read': len([n for n in notifications if n.is_read]),
        'notifications': result
    })



def allowed_file(filename):
    """Check if file extension is allowed"""
    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'mov', 'avi'}
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions
           
           
def create_notification(user_id, actor_id, type_, message, entity_id=None):
    """Helper to create a notification safely"""
    notification = Notification(
        user_id=user_id,
        actor_id=actor_id,
        type=type_,
        message=message,
        entity_id=entity_id
    )
    db.session.add(notification)
    db.session.commit()  
           
           

# In your add_friend route
@auth.route('/add_friend/<int:user_id>', methods=['POST'])
@login_required
def add_friend(user_id):
    if user_id == current_user.id:
        return jsonify(error="Can't add yourself"), 400

    # Prevent duplicate DB rows
    existing = FriendRequest.query.filter_by(
        sender_id=current_user.id,
        receiver_id=user_id
    ).first()
    if existing:
        return jsonify(error="Request already sent"), 400

    req = FriendRequest(sender_id=current_user.id, receiver_id=user_id)
    # **FLAG** so the signal knows we already handled it
    req._skip_notification = True
    db.session.add(req)

    # ---- CREATE NOTIFICATION MANUALLY (only once) ----
    create_notification(
        actor_id=current_user.id,
        user_id=user_id,
        type_='friend_request',
        message=f"{current_user.full_name} sent you a friend request",
        entity_id=req.id
    )
    db.session.commit()
    return jsonify(success=True)





@auth.route("/cancel_friend_request/<int:user_id>", methods=["POST"])
@login_required
def cancel_friend_request(user_id):
    user = User.query.get_or_404(user_id)
    # You'll need to implement this method in your User model
    return jsonify(success=True)

@auth.route("/get_user_profile/<int:user_id>")
@login_required
def get_user_profile(user_id):
    user = User.query.get_or_404(user_id)
    return jsonify({
        'first_name': user.first_name,
        'last_name': user.last_name,
        'email': user.email,
        'profile_pic': user.profile_pic or url_for('static', filename='assets/img/default-avatar.png'),
        'cover_pic': user.cover_pic,
        'bio': user.bio,
        'city': user.city,
        'country': user.country,
        'gender': user.gender,
        'dob': user.dob.isoformat() if user.dob else None,
        'phone_number': user.phone_number,
        'marital_status': user.marital_status,
        'interests': user.interests,
        'profile_url': url_for('auth.profile', user_id=user.id),
        'friends_count': user.friends.count(),
    })   
    
    


@auth.route("/notifications")
@login_required
def get_notifications():
    notifications = current_user.recent_notifications
    return jsonify([notification.to_dict() for notification in notifications])

@auth.route("/notifications/read", methods=["POST"])
@login_required
def mark_notifications_read():
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    return jsonify(success=True)

@auth.route("/notifications/<int:notification_id>/read", methods=["POST"])
@login_required
def mark_notification_read(notification_id):
    notification = Notification.query.filter_by(id=notification_id, user_id=current_user.id).first_or_404()
    notification.is_read = True
    db.session.commit()
    return jsonify(success=True)

@auth.route("/notifications/count")
@login_required
def get_unread_count():
    count = current_user.unread_notifications_count
    return jsonify(count=count)



@auth.route("/accept_friend_request/<int:user_id>", methods=["POST"])
@login_required
def accept_friend_request_route(user_id):
    data = request.get_json() or {}
    notification_id = data.get('notification_id')

    user = User.query.get_or_404(user_id)

    if current_user.accept_friend_request(user):
        # mark the notification as read
        if notification_id:
            noti = Notification.query.get(notification_id)
            if noti and noti.user_id == current_user.id:
                noti.is_read = True
                db.session.commit()
        return jsonify(success=True)

    return jsonify(success=False, error="Could not accept request")




@auth.route("/decline_friend_request/<int:user_id>", methods=["POST"])
@login_required
def decline_friend_request_route(user_id):
    data = request.get_json() or {}
    notification_id = data.get('notification_id')

    user = User.query.get_or_404(user_id)

    if current_user.decline_friend_request(user):
        if notification_id:
            noti = Notification.query.get(notification_id)
            if noti and noti.user_id == current_user.id:
                noti.is_read = True
                db.session.commit()
        return jsonify(success=True)

    return jsonify(success=False, error="Could not decline request")
           
           

# Add this to your Flask routes
@auth.route('/search')
def search():
    query = request.args.get('q', '').strip()
    if not query or len(query) < 2:
        return jsonify({'users': [], 'posts': []})
    
    # Search users (exclude current user)
    users = User.query.filter(
        db.and_(
            User.id != current_user.id,  # Exclude current user
            db.or_(
                User.first_name.ilike(f'%{query}%'),
                User.last_name.ilike(f'%{query}%'),
                User.email.ilike(f'%{query}%')
            )
        )
    ).limit(10).all()
    
    # Search posts (you can also exclude current user's posts if desired)
    posts = Post.query.filter(
        Post.content.ilike(f'%{query}%')
    ).join(User).limit(10).all()
    
    users_data = [{
        'id': user.id,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'profile_pic': user.profile_pic,
        'email': user.email
    } for user in users]
    
    posts_data = [{
        'id': post.id,
        'content': post.content,
        'author_first_name': post.author.first_name,
        'author_last_name': post.author.last_name,
        'author_id': post.author.id,  # Add author ID for client-side filtering
        'created_at': post.created_at.isoformat()
    } for post in posts]
    
    return jsonify({
        'users': users_data,
        'posts': posts_data
    })        
        
@auth.route('/get_post/<int:post_id>')
def get_post(post_id):
    post = Post.query.get_or_404(post_id)
    return jsonify({
        'id': post.id,
        'content': post.content,
        'image': post.image,
        'video': post.video,
        'author_first_name': post.author.first_name,
        'author_last_name': post.author.last_name,
        'author_profile_pic': post.author.profile_pic or url_for('static', filename='assets/img/default-avatar.png'),
        'created_at': post.created_at.isoformat()
    })





# auth.py  (add these routes)

# @auth.route("/block_user/<int:user_id>", methods=["POST"])
# @login_required
# def block_user(user_id):
#     user = User.query.get_or_404(user_id)
#     if user.id == current_user.id:
#         return jsonify(success=False, error="Cannot block yourself")
#     current_user.block(user)
#     return jsonify(success=True)

# @auth.route("/unblock_user/<int:user_id>", methods=["POST"])
# @login_required
# def unblock_user(user_id):
#     user = User.query.get_or_404(user_id)
#     current_user.unblock(user)
#     return jsonify(success=True)

# Update last_seen on every request
@auth.before_request
def update_last_seen():
    if current_user.is_authenticated:
        current_user.last_seen = datetime.utcnow()
        # Consider user online if seen < 5 min ago
        current_user.is_online = (datetime.utcnow() - current_user.last_seen) < timedelta(minutes=5)
        db.session.commit()




# Add these routes to your auth.py

# @auth.route("/block_user/<int:user_id>", methods=["POST"])
# @login_required
# def block_user(user_id):
#     """Block a user"""
#     user = User.query.get_or_404(user_id)
    
#     if user.id == current_user.id:
#         return jsonify(success=False, error="Cannot block yourself")
    
#     if current_user.is_blocking(user):
#         return jsonify(success=False, error="User already blocked")
    
#     try:
#         current_user.block(user)
        
#         # Remove friendship if exists
#         if user in current_user.friends:
#             current_user.remove_friend(user)
            
#         # Remove any pending friend requests
#         FriendRequest.query.filter(
#             ((FriendRequest.sender_id == current_user.id) & (FriendRequest.receiver_id == user_id)) |
#             ((FriendRequest.sender_id == user_id) & (FriendRequest.receiver_id == current_user.id))
#         ).delete()
        
#         db.session.commit()
        
#         return jsonify(success=True, message=f"{user.first_name} has been blocked")
        
#     except Exception as e:
#         db.session.rollback()
#         return jsonify(success=False, error=str(e))




# Add these routes to your auth.py

@auth.route("/block_user/<int:user_id>", methods=["POST"])
@login_required
def block_user(user_id):
    """Block a user"""
    user = User.query.get_or_404(user_id)
    
    if user.id == current_user.id:
        return jsonify(success=False, error="Cannot block yourself")
    
    if current_user.is_blocking(user):
        return jsonify(success=False, error="User already blocked")
    
    try:
        current_user.block(user)
        
        # Remove friendship if exists
        if user in current_user.friends:
            current_user.remove_friend(user)
            
        # Remove any pending friend requests
        FriendRequest.query.filter(
            ((FriendRequest.sender_id == current_user.id) & (FriendRequest.receiver_id == user_id)) |
            ((FriendRequest.sender_id == user_id) & (FriendRequest.receiver_id == current_user.id))
        ).delete()
        
        db.session.commit()
        
        return jsonify(success=True, message=f"{user.first_name} has been blocked")
        
    except Exception as e:
        db.session.rollback()
        return jsonify(success=False, error=str(e))

@auth.route("/unblock_user/<int:user_id>", methods=["POST"])
@login_required
def unblock_user(user_id):
    """Unblock a user"""
    user = User.query.get_or_404(user_id)
    
    if not current_user.is_blocking(user):
        return jsonify(success=False, error="User is not blocked")
    
    try:
        current_user.unblock(user)
        db.session.commit()
        
        return jsonify(success=True, message=f"{user.first_name} has been unblocked")
        
    except Exception as e:
        db.session.rollback()
        return jsonify(success=False, error=str(e))

@auth.route("/get_blocked_users", methods=["GET"])
@login_required
def get_blocked_users():
    """Get list of blocked users"""
    blocked_users = current_user.get_blocked_users()
    
    blocked_data = []
    for user in blocked_users:
        blocked_data.append({
            'id': user.id,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'profile_pic': user.profile_pic or url_for('static', filename='assets/img/default-avatar.png'),
            'email': user.email
        })
    
    return jsonify(blocked_users=blocked_data)



# @auth.route("/unblock_user/<int:user_id>", methods=["POST"])
# @login_required
# def unblock_user(user_id):
#     """Unblock a user"""
#     user = User.query.get_or_404(user_id)
    
#     if not current_user.is_blocking(user):
#         return jsonify(success=False, error="User is not blocked")
    
#     try:
#         current_user.unblock(user)
#         db.session.commit()
        
#         return jsonify(success=True, message=f"{user.first_name} has been unblocked")
        
#     except Exception as e:
#         db.session.rollback()
#         return jsonify(success=False, error=str(e))

# @auth.route("/get_blocked_users", methods=["GET"])
# @login_required
# def get_blocked_users():
#     """Get list of blocked users"""
#     blocked_users = current_user.get_blocked_users()
    
#     blocked_data = []
#     for user in blocked_users:
#         blocked_data.append({
#             'id': user.id,
#             'first_name': user.first_name,
#             'last_name': user.last_name,
#             'profile_pic': user.profile_pic or url_for('static', filename='assets/img/default-avatar.png'),
#             'email': user.email
#         })
    
#     return jsonify(blocked_users=blocked_data)






# Update the existing profile route to handle new fields
# @auth.route("/<int:user_id>", methods=["GET", "POST"])
# @login_required
# def profile(user_id):
#     user = User.query.get_or_404(user_id)

#     # Only allow users to edit their own profile
#     if user.id != current_user.id:
#         flash("You can only edit your own profile.", "warning")
#         return redirect(url_for('auth.profile', user_id=current_user.id))

#     if request.method == "POST":
#         try:
#             # Handle profile fields from registration form
#             current_user.first_name = request.form.get('first_name', current_user.first_name)
#             current_user.last_name = request.form.get('last_name', current_user.last_name)
#             current_user.email = request.form.get('email', current_user.email)
#             current_user.phone_number = request.form.get('phone_number', current_user.phone_number)
#             current_user.city = request.form.get('city', current_user.city)
#             current_user.country = request.form.get('country', current_user.country)
#             current_user.gender = request.form.get('gender', current_user.gender)
#             current_user.marital_status = request.form.get('marital_status', current_user.marital_status)
#             current_user.interests = request.form.get('interests', current_user.interests)
#             current_user.bio = request.form.get('bio', current_user.bio)

#             # Handle date of birth
#             dob_str = request.form.get('dob')
#             if dob_str:
#                 try:
#                     current_user.dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
#                 except ValueError:
#                     flash("Invalid date format for date of birth.", "warning")

#             # Handle profile picture
#             if 'profile_pic' in request.files:
#                 file = request.files['profile_pic']
#                 if file and file.filename != '' and allowed_file(file.filename):
#                     try:
#                         result = cloudinary.uploader.upload(
#                             file,
#                             folder="kimbela/profiles",
#                             transformation=[
#                                 {'width': 400, 'height': 400, 'crop': 'fill', 'gravity': 'face'},
#                                 {'quality': 'auto', 'fetch_format': 'auto'}
#                             ]
#                         )
#                         current_user.profile_pic = result['secure_url']
#                         flash("Profile picture updated successfully!", "success")
#                     except Exception as e:
#                         print(f"Profile picture upload error: {e}")
#                         flash("Failed to upload profile picture.", "danger")

#             # Handle cover photo
#             if 'cover_pic' in request.files:
#                 file = request.files['cover_pic']
#                 if file and file.filename != '' and allowed_file(file.filename):
#                     try:
#                         result = cloudinary.uploader.upload(
#                             file,
#                             folder="kimbela/covers",
#                             transformation=[
#                                 {'width': 1200, 'height': 400, 'crop': 'fill'},
#                                 {'quality': 'auto', 'fetch_format': 'auto'}
#                             ]
#                         )
#                         current_user.cover_pic = result['secure_url']
#                         flash("Cover photo updated successfully!", "success")
#                     except Exception as e:
#                         print(f"Cover photo upload error: {e}")
#                         flash("Failed to upload cover photo.", "danger")

#             db.session.commit()
#             flash("Profile updated successfully!", "success")

#         except Exception as e:
#             db.session.rollback()
#             flash("An error occurred while updating your profile.", "danger")
#             print(f"Profile update error: {e}")

#         return redirect(url_for('auth.profile', user_id=current_user.id))

#     # GET request - load profile data
#     posts = Post.query.filter_by(author_id=current_user.id)\
#                       .order_by(Post.created_at.desc()).all()

#     # Get friends (excluding blocked users)
#     friends = [f for f in current_user.friends if not current_user.is_blocking(f)]

#     # Get blocked users
#     blocked_users = current_user.get_blocked_users()

#     return render_template(
#         "profile.html",
#         user=current_user,
#         posts=posts,
#         friends=friends,
#         blocked_users=blocked_users
#     )






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
            # Handle profile fields from registration form
            current_user.first_name = request.form.get('first_name', current_user.first_name)
            current_user.last_name = request.form.get('last_name', current_user.last_name)
            current_user.email = request.form.get('email', current_user.email)
            current_user.phone_number = request.form.get('phone_number', current_user.phone_number)
            current_user.city = request.form.get('city', current_user.city)
            current_user.country = request.form.get('country', current_user.country)
            current_user.gender = request.form.get('gender', current_user.gender)
            current_user.marital_status = request.form.get('marital_status', current_user.marital_status)
            current_user.interests = request.form.get('interests', current_user.interests)
            current_user.bio = request.form.get('bio', current_user.bio)

            # Handle date of birth
            dob_str = request.form.get('dob')
            if dob_str:
                try:
                    current_user.dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
                except ValueError:
                    flash("Invalid date format for date of birth.", "warning")

            # Handle profile picture
            if 'profile_pic' in request.files:
                file = request.files['profile_pic']
                if file and file.filename != '' and allowed_file(file.filename):
                    try:
                        result = cloudinary.uploader.upload(
                            file,
                            folder="kimbela/profiles",
                            transformation=[
                                {'width': 400, 'height': 400, 'crop': 'fill', 'gravity': 'face'},
                                {'quality': 'auto', 'fetch_format': 'auto'}
                            ]
                        )
                        current_user.profile_pic = result['secure_url']
                        flash("Profile picture updated successfully!", "success")
                    except Exception as e:
                        print(f"Profile picture upload error: {e}")
                        flash("Failed to upload profile picture.", "danger")

            # Handle cover photo
            if 'cover_pic' in request.files:
                file = request.files['cover_pic']
                if file and file.filename != '' and allowed_file(file.filename):
                    try:
                        result = cloudinary.uploader.upload(
                            file,
                            folder="kimbela/covers",
                            transformation=[
                                {'width': 1200, 'height': 400, 'crop': 'fill'},
                                {'quality': 'auto', 'fetch_format': 'auto'}
                            ]
                        )
                        current_user.cover_pic = result['secure_url']
                        flash("Cover photo updated successfully!", "success")
                    except Exception as e:
                        print(f"Cover photo upload error: {e}")
                        flash("Failed to upload cover photo.", "danger")

            db.session.commit()
            flash("Profile updated successfully!", "success")

        except Exception as e:
            db.session.rollback()
            flash("An error occurred while updating your profile.", "danger")
            print(f"Profile update error: {e}")

        return redirect(url_for('auth.profile', user_id=current_user.id))

    # GET request - load profile data
    posts = Post.query.filter_by(author_id=current_user.id)\
                      .order_by(Post.created_at.desc()).all()

    # Get friends (excluding blocked users)
    friends = [f for f in current_user.friends if not current_user.is_blocking(f)]

    # Get blocked users
    blocked_users = current_user.get_blocked_users()

    return render_template(
        "profile.html",
        user=current_user,
        posts=posts,
        friends=friends,
        blocked_users=blocked_users,
        datetime=datetime
        )





           
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