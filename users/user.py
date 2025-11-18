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
    secure=True,
)

user = Blueprint("user", __name__)


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)











# Add this function to create a timeago filter
def timeago_filter(dt):
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


@user.route("/")
@user.route("/index", methods=["GET", "POST"])
def index():
    return render_template("index.html")


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

    app.jinja_env.filters["timeago"] = timeago


@user.route("/user_dashboard", methods=["GET", "POST"])
@login_required
def user_dashboard():
    if request.method == "POST":
        # Handle post creation here
        post_content = request.form.get("post_content")
        media_file = request.files.get("media")

        if post_content or (media_file and media_file.filename != ""):
            image_url = None
            video_url = None

            if (
                media_file
                and media_file.filename != ""
                and allowed_file(media_file.filename)
            ):
                try:
                    resource_type = "auto"
                    if media_file.content_type.startswith("video"):
                        resource_type = "video"

                    result = cloudinary.uploader.upload(
                        media_file,
                        folder="kimbela/posts",
                        resource_type=resource_type,
                        transformation=[
                            {"width": 800, "crop": "limit"},
                            {"quality": "auto", "fetch_format": "auto"},
                        ],
                    )

                    if media_file.content_type.startswith("video"):
                        video_url = result["secure_url"]
                    else:
                        image_url = result["secure_url"]

                except Exception as e:
                    print(f"Media upload error: {e}")
                    flash("Failed to upload media.", "danger")

            # Create post
            new_post = Post(
                content=post_content or "",
                image=image_url,
                video=video_url,
                author_id=current_user.id,
                created_at=datetime.utcnow(),
            )
            db.session.add(new_post)
            db.session.commit()
            flash("Post created!", "success")

        return redirect(url_for("user.user_dashboard"))

    # GET request handling (your existing code)
    posts = Post.query.order_by(Post.created_at.desc()).all()
    # 1. Get ALL other users (no block filtering in SQL)
    all_users = User.query.filter(User.id != current_user.id).all()

    # 2. Filter in Python using your existing methods
    all_users = [
        u
        for u in all_users
        if not u.is_blocked_by(current_user)  # u did NOT block me
        and not current_user.is_blocked_by(u)  # I did NOT block u
    ]
    # FRIENDS (visible only)
    friends = [f for f in current_user.friends if f.is_visible_to(current_user)]

    # NON-FRIENDS for suggestions
    friend_ids = {f.id for f in friends}

    non_friends = [u for u in all_users if u.id not in friend_ids]
    friend_ids = {friend.id for friend in current_user.friends}
    non_friends = [u for u in all_users if u.id not in friend_ids]
    random_three = (
        sample(non_friends, min(1000, len(non_friends))) if non_friends else []
    )

    return render_template(
        "user_dashboard.html",
        posts=posts,
        current_user=current_user,
        all_users=all_users,
        friends=friends,
        random_three=random_three,
        csrf_token=generate_csrf(),
    )



@user.route("/like_post/<int:post_id>", methods=["POST"])
@login_required
def like_post(post_id):
    post = Post.query.get_or_404(post_id)

    existing_like = Like.query.filter_by(
        user_id=current_user.id, post_id=post_id
    ).first()

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
                entity_type="post",
            )

    db.session.commit()
    like_count = Like.query.filter_by(post_id=post_id).count()
    return jsonify(likes=like_count, liked=liked)




# Delete Post
@user.route("/delete_post/<int:post_id>", methods=["POST"])
@login_required
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.author_id != current_user.id:
        return jsonify(error="Unauthorized"), 403
    db.session.delete(post)
    db.session.commit()
    return jsonify(success=True)


# Edit Post
@user.route("/edit_post", methods=["POST"])
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
@user.route("/add_comment/<int:post_id>", methods=["POST"])
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
            entity_type="post",
        )

    return jsonify(
        id=comment.id,
        name=f"{current_user.first_name} {current_user.last_name}",
        avatar=current_user.profile_pic
        or url_for("static", filename="assets/img/default-avatar.png"),
        content=content,
    )




@user.route("/get_comments/<int:post_id>")
def get_comments(post_id):
    post = Post.query.get_or_404(post_id)
    # Order comments by created_at DESCENDING (newest first)
    comments = (
        Comment.query.filter_by(post_id=post_id)
        .order_by(Comment.created_at.desc())
        .all()
    )
    result = []
    for c in comments:
        result.append(
            {
                "id": c.id,
                "name": f"{c.author.first_name} {c.author.last_name}",
                "avatar": c.author.profile_pic
                or url_for("static", filename="assets/img/default-avatar.png"),
                "content": c.content,
                "created_at": c.created_at.isoformat(),
                "replies": [],  # handle replies later
            }
        )
    return jsonify(result)


@user.route("/debug/notification_status")
@login_required
def debug_notification_status():
    """Check read status of notifications"""
    notifications = (
        Notification.query.filter_by(user_id=current_user.id)
        .order_by(Notification.created_at.desc())
        .all()
    )
    result = []
    for n in notifications:
        result.append(
            {
                "id": n.id,
                "type": n.type,
                "message": n.message,
                "is_read": n.is_read,
                "created_at": n.created_at.isoformat(),
            }
        )
    return jsonify(
        {
            "total": len(notifications),
            "unread": len([n for n in notifications if not n.is_read]),
            "read": len([n for n in notifications if n.is_read]),
            "notifications": result,
        }
    )


def allowed_file(filename):
    """Check if file extension is allowed"""
    allowed_extensions = {"png", "jpg", "jpeg", "gif", "mp4", "mov", "avi"}
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed_extensions


def create_notification(user_id, actor_id, type_, message, entity_id=None):
    """Helper to create a notification safely"""
    notification = Notification(
        user_id=user_id,
        actor_id=actor_id,
        type=type_,
        message=message,
        entity_id=entity_id,
    )
    db.session.add(notification)
    db.session.commit()


# In your add_friend route
@user.route("/add_friend/<int:user_id>", methods=["POST"])
@login_required
def add_friend(user_id):
    if user_id == current_user.id:
        return jsonify(error="Can't add yourself"), 400

    # Prevent duplicate DB rows
    existing = FriendRequest.query.filter_by(
        sender_id=current_user.id, receiver_id=user_id
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
        type_="friend_request",
        message=f"{current_user.full_name} sent you a friend request",
        entity_id=req.id,
    )
    db.session.commit()
    return jsonify(success=True)


@user.route("/cancel_friend_request/<int:user_id>", methods=["POST"])
@login_required
def cancel_friend_request(user_id):
    user = User.query.get_or_404(user_id)
    # You'll need to implement this method in your User model
    return jsonify(success=True)


@user.route("/get_user_profile/<int:user_id>")
@login_required
def get_user_profile(user_id):
    user = User.query.get_or_404(user_id)
    return jsonify(
        {
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "profile_pic": user.profile_pic
            or url_for("static", filename="assets/img/default-avatar.png"),
            "cover_pic": user.cover_pic,
            "bio": user.bio,
            "city": user.city,
            "country": user.country,
            "gender": user.gender,
            "dob": user.dob.isoformat() if user.dob else None,
            "phone_number": user.phone_number,
            "marital_status": user.marital_status,
            "interests": user.interests,
            "profile_url": url_for("user.profile", user_id=user.id),
            "friends_count": user.friends.count(),
        }
    )


@user.route("/notifications")
@login_required
def get_notifications():
    notifications = current_user.recent_notifications
    return jsonify([notification.to_dict() for notification in notifications])


@user.route("/notifications/read", methods=["POST"])
@login_required
def mark_notifications_read():
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update(
        {"is_read": True}
    )
    db.session.commit()
    return jsonify(success=True)


@user.route("/notifications/<int:notification_id>/read", methods=["POST"])
@login_required
def mark_notification_read(notification_id):
    notification = Notification.query.filter_by(
        id=notification_id, user_id=current_user.id
    ).first_or_404()
    notification.is_read = True
    db.session.commit()
    return jsonify(success=True)


@user.route("/notifications/count")
@login_required
def get_unread_count():
    count = current_user.unread_notifications_count
    return jsonify(count=count)


@user.route("/accept_friend_request/<int:user_id>", methods=["POST"])
@login_required
def accept_friend_request_route(user_id):
    data = request.get_json() or {}
    notification_id = data.get("notification_id")

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


@user.route("/decline_friend_request/<int:user_id>", methods=["POST"])
@login_required
def decline_friend_request_route(user_id):
    data = request.get_json() or {}
    notification_id = data.get("notification_id")

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
@user.route("/search")
def search():
    query = request.args.get("q", "").strip()
    if not query or len(query) < 2:
        return jsonify({"users": [], "posts": []})

    # Search users (exclude current user)
    users = (
        User.query.filter(
            db.and_(
                User.id != current_user.id,  # Exclude current user
                db.or_(
                    User.first_name.ilike(f"%{query}%"),
                    User.last_name.ilike(f"%{query}%"),
                    User.email.ilike(f"%{query}%"),
                ),
            )
        )
        .limit(10)
        .all()
    )

    # Search posts (you can also exclude current user's posts if desired)
    posts = (
        Post.query.filter(Post.content.ilike(f"%{query}%")).join(User).limit(10).all()
    )

    users_data = [
        {
            "id": user.id,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "profile_pic": user.profile_pic,
            "email": user.email,
        }
        for user in users
    ]

    posts_data = [
        {
            "id": post.id,
            "content": post.content,
            "author_first_name": post.author.first_name,
            "author_last_name": post.author.last_name,
            "author_id": post.author.id,  # Add author ID for client-side filtering
            "created_at": post.created_at.isoformat(),
        }
        for post in posts
    ]

    return jsonify({"users": users_data, "posts": posts_data})


@user.route("/get_post/<int:post_id>")
def get_post(post_id):
    post = Post.query.get_or_404(post_id)
    return jsonify(
        {
            "id": post.id,
            "content": post.content,
            "image": post.image,
            "video": post.video,
            "author_first_name": post.author.first_name,
            "author_last_name": post.author.last_name,
            "author_profile_pic": post.author.profile_pic
            or url_for("static", filename="assets/img/default-avatar.png"),
            "created_at": post.created_at.isoformat(),
        }
    )


# Update last_seen on every request
@user.before_request
def update_last_seen():
    if current_user.is_authenticated:
        current_user.last_seen = datetime.utcnow()
        # Consider user online if seen < 5 min ago
        current_user.is_online = (
            datetime.utcnow() - current_user.last_seen
        ) < timedelta(minutes=5)
        db.session.commit()


@user.route("/<int:user_id>", methods=["GET", "POST"])
@login_required
def profile(user_id):
    user = User.query.get_or_404(user_id)

    # Only allow users to edit their own profile
    if user.id != current_user.id:
        flash("You can only edit your own profile.", "warning")
        return redirect(url_for("user.profile", user_id=current_user.id))

    if request.method == "POST":
        try:
            # Handle profile fields from registration form
            current_user.first_name = request.form.get(
                "first_name", current_user.first_name
            )
            current_user.last_name = request.form.get(
                "last_name", current_user.last_name
            )
            current_user.email = request.form.get("email", current_user.email)
            current_user.phone_number = request.form.get(
                "phone_number", current_user.phone_number
            )
            current_user.city = request.form.get("city", current_user.city)
            current_user.country = request.form.get("country", current_user.country)
            current_user.gender = request.form.get("gender", current_user.gender)
            current_user.marital_status = request.form.get(
                "marital_status", current_user.marital_status
            )
            current_user.interests = request.form.get(
                "interests", current_user.interests
            )
            current_user.bio = request.form.get("bio", current_user.bio)

            # Handle date of birth
            dob_str = request.form.get("dob")
            if dob_str:
                try:
                    current_user.dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
                except ValueError:
                    flash("Invalid date format for date of birth.", "warning")

            # Handle profile picture
            if "profile_pic" in request.files:
                file = request.files["profile_pic"]
                if file and file.filename != "" and allowed_file(file.filename):
                    try:
                        result = cloudinary.uploader.upload(
                            file,
                            folder="kimbela/profiles",
                            transformation=[
                                {
                                    "width": 400,
                                    "height": 400,
                                    "crop": "fill",
                                    "gravity": "face",
                                },
                                {"quality": "auto", "fetch_format": "auto"},
                            ],
                        )
                        current_user.profile_pic = result["secure_url"]
                        flash("Profile picture updated successfully!", "success")
                    except Exception as e:
                        print(f"Profile picture upload error: {e}")
                        flash("Failed to upload profile picture.", "danger")

            # Handle cover photo
            if "cover_pic" in request.files:
                file = request.files["cover_pic"]
                if file and file.filename != "" and allowed_file(file.filename):
                    try:
                        result = cloudinary.uploader.upload(
                            file,
                            folder="kimbela/covers",
                            transformation=[
                                {"width": 1200, "height": 400, "crop": "fill"},
                                {"quality": "auto", "fetch_format": "auto"},
                            ],
                        )
                        current_user.cover_pic = result["secure_url"]
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

        return redirect(url_for("user.profile", user_id=current_user.id))

    # GET request - load profile data
    posts = (
        Post.query.filter_by(author_id=current_user.id)
        .order_by(Post.created_at.desc())
        .all()
    )

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
        datetime=datetime,
    )


@user.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))


@user.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    return render_template("forgot_password.html")


@user.route("/about", methods=["GET", "POST"])
def about():
    return render_template("about.html")


@user.route("/features", methods=["GET", "POST"])
def features():
    return render_template("features.html")


@user.route("/contact", methods=["GET", "POST"])
def contact():
    return render_template("contact.html")


@user.route("/terms", methods=["GET", "POST"])
def terms():
    return render_template("terms.html")


@user.route("/privacy", methods=["GET", "POST"])
def privacy():
    return render_template("privacy.html")





@user.route("/get_user_groups")
@login_required
def get_user_groups():
    """Get all groups for the dropdown with membership status"""
    try:
        print(f"🔍 DEBUG: Fetching ALL groups for user: {current_user.id} ({current_user.email})")

        # Get all active groups
        all_groups = Group.query.filter_by(is_active=True).order_by(Group.name.asc()).all()
        print(f"🔍 DEBUG: Found {len(all_groups)} total active groups")

        groups_data = []
        for group in all_groups:
            # Check membership using the relationship
            is_member = group.members.filter_by(id=current_user.id).first() is not None

            print(f"🔍 DEBUG: Group '{group.name}' (ID: {group.id}) with {group.member_count} members. User is member: {is_member}")

            groups_data.append(
                {
                    "id": group.id,
                    "name": group.name,
                    "cover_pic": group.image or "https://via.placeholder.com/100x100/3B82F6/FFFFFF?text=Group",
                    "member_count": group.member_count,
                    "is_member": is_member,
                    "unread_count": 0,
                }
            )

        print(f"🔍 DEBUG: Returning {len(groups_data)} groups as JSON")
        return jsonify(groups_data)

    except Exception as e:
        print(f"❌ ERROR in get_user_groups: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify([])


# Add these routes to your auth blueprint


@user.route("/groups/user_groups")
@login_required
def user_groups():
    """Get user's groups for sidebar - alternative approach"""
    try:
        # Get user's groups using the relationship
        groups = current_user.user_groups.filter_by(is_active=True).limit(10).all()

        return jsonify(
            [
                {
                    "id": group.id,
                    "name": group.name,
                    "image": group.image or "https://images.unsplash.com/photo-1611262588024-d12430b98920?w=100&h=100&fit=crop",
                    "member_count": group.member_count,
                    "is_member": True,
                }
                for group in groups
            ]
        )
    except Exception as e:
        print(f"Error in user_groups: {e}")
        return jsonify([])



@user.route("/groups/all")
@login_required
def all_groups():
    """Get all groups for discovery"""
    search = request.args.get("search", "")
    category = request.args.get("category", "all")

    query = Group.query.filter_by(is_active=True)

    if search:
        query = query.filter(
            db.or_(
                Group.name.ilike(f"%{search}%"),
                Group.description.ilike(f"%{search}%")
            )
        )

    if category != "all":
        query = query.filter_by(category=category)

    groups = query.order_by(Group.member_count.desc()).limit(20).all()

    return jsonify(
        [
            {
                "id": group.id,
                "name": group.name,
                "description": group.description,
                "image": group.image,
                "category": group.category,
                "is_private": group.is_private,
                "member_count": group.member_count,
                "created_at": group.created_at.isoformat(),
                "is_member": group.members.filter_by(id=current_user.id).first() is not None,  # Proper membership check
            }
            for group in groups
        ]
    )




@user.route("/groups/<int:group_id>")
@login_required
def group_page(group_id):
    """Get group page HTML"""
    group = Group.query.get_or_404(group_id)
    
    # Check membership properly
    is_member = group.members.filter_by(id=current_user.id).first() is not None
    
    default_avatar = url_for('static', filename='assets/img/default-avatar.png')

    # Get group posts
    posts = Post.query.filter_by(group_id=group_id)\
        .options(
            db.joinedload(Post.author),
            db.joinedload(Post.comments).joinedload(Comment.author)
        )\
        .order_by(Post.created_at.desc())\
        .all()
    

    return render_template(
        "group_detail.html",
        group=group,
        is_member=is_member,
        posts=posts,
        current_user=current_user,
        default_avatar=default_avatar
    )
# @user.route("/groups/create", methods=["POST"])
# @login_required
# def create_group():
#     """Create a new group"""
#     try:
#         name = request.form.get("name", "").strip()
#         description = request.form.get("description", "").strip()
#         category = request.form.get("category", "social")
#         is_private = request.form.get("is_private") == "true"

#         if not name:
#             return jsonify({"success": False, "error": "Group name is required"})

#         group = Group(
#             name=name,
#             description=description,
#             category=category,
#             is_private=is_private,
#             created_by=current_user.id,
#         )

#         # Handle group image
#         if "image" in request.files:
#             file = request.files["image"]
#             if file and file.filename and allowed_file(file.filename):
#                 try:
#                     result = cloudinary.uploader.upload(
#                         file,
#                         folder="kimbela/groups",
#                         transformation=[
#                             {"width": 800, "height": 600, "crop": "limit"},
#                             {"quality": "auto", "fetch_format": "auto"},
#                         ],
#                     )
#                     group.image = result["secure_url"]
#                 except Exception as e:
#                     print("Group image upload failed:", e)

#         db.session.add(group)

#         # Add creator as first member
#         group.members.append(current_user)
#         group.member_count = 1

#         db.session.commit()

#         return jsonify({"success": True, "group_id": group.id})

#     except Exception as e:
#         db.session.rollback()
#         print("Create group error:", e)
#         return jsonify({"success": False, "error": "Failed to create group"})


# @user.route("/groups/<int:group_id>/join", methods=["POST"])
# @login_required
# def join_group(group_id):
#     """Join a group"""
#     group = Group.query.get_or_404(group_id)

#     if current_user in group.members:
#         return jsonify({"success": False, "error": "Already a member"})

#     group.members.append(current_user)
#     group.member_count = len(group.members)
#     db.session.commit()

#     return jsonify({"success": True})


# @user.route("/groups/<int:group_id>/leave", methods=["POST"])
# @login_required
# def leave_group(group_id):
#     """Leave a group"""
#     group = Group.query.get_or_404(group_id)

#     if current_user not in group.members:
#         return jsonify({"success": False, "error": "Not a member"})

#     group.members.remove(current_user)
#     group.member_count = len(group.members)
#     db.session.commit()

#     return jsonify({"success": True})


@user.route("/comments/<int:comment_id>/report", methods=["POST"])
@login_required
def report_comment(comment_id):
    """Report a comment"""
    comment = Comment.query.get_or_404(comment_id)
    reason = request.form.get("report_reason")
    other_reason = request.form.get("other_reason", "")

    if not reason:
        return jsonify({"success": False, "error": "Please select a reason"})

    # Create reported content entry
    report = ReportedContent(
        reporter_id=current_user.id,
        reported_user_id=comment.author_id,
        content_type="comment",
        content_id=comment_id,
        reason=f"{reason}: {other_reason}".strip() if other_reason else reason,
        status="pending",
    )

    db.session.add(report)
    db.session.commit()

    return jsonify({"success": True})




# Add these routes to your auth blueprint

@user.route('/groups')
@login_required
def groups_page():
    """Main groups discovery page"""
    return render_template('groups.html')

@user.route('/groups/<int:group_id>')
@login_required
def group_detail(group_id):
    """Individual group page with posts and interactions"""
    group = Group.query.get_or_404(group_id)
    is_member = current_user in group.members
    
    default_avatar = url_for('static', filename='assets/img/default-avatar.png')
    
    # Get posts for this group
    posts = Post.query.filter_by(group_id=group_id).order_by(Post.created_at.desc()).all()
    
    return render_template(
        'group_detail.html',
        group=group,
        is_member=is_member,
        posts=posts,
        current_user=current_user,
        default_avatar=default_avatar,
    )

@user.route("/groups/create", methods=['GET', 'POST'])
@login_required
def create_group():
    """Create a new group"""
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            category = request.form.get('category', 'social')
            is_private = request.form.get('is_private') == 'true'

            if not name:
                return jsonify({'success': False, 'error': 'Group name is required'})

            group = Group(
                name=name,
                description=description,
                category=category,
                is_private=is_private,
                created_by=current_user.id,
                member_count=1
            )

            # Handle group image
            if 'image' in request.files:
                file = request.files['image']
                if file and file.filename and allowed_file(file.filename):
                    try:
                        result = cloudinary.uploader.upload(
                            file,
                            folder='kimbela/groups',
                            transformation=[
                                {'width': 800, 'height': 600, 'crop': 'limit'},
                                {'quality': 'auto', 'fetch_format': 'auto'},
                            ],
                        )
                        group.image = result['secure_url']
                    except Exception as e:
                        print('Group image upload failed:', e)

            db.session.add(group)
            
            # Add creator as first member
            group.members.append(current_user)
            db.session.commit()

            return jsonify({'success': True, 'group_id': group.id})

        except Exception as e:
            db.session.rollback()
            print('Create group error:', e)
            return jsonify({'success': False, 'error': 'Failed to create group'})

    return render_template('create_group.html')





@user.route("/groups/<int:group_id>/join", methods=['POST'])
@login_required
def join_group(group_id):
    """Join a group"""
    group = Group.query.get_or_404(group_id)
    
    if current_user in group.members.all():  # Use .all() to check membership
        return jsonify({'success': False, 'error': 'Already a member'})

    group.members.append(current_user)
    group.member_count = group.members.count()  # Use .count() instead of len()
    db.session.commit()

    return jsonify({'success': True})





# Fix the leave_group rout
@user.route("/groups/<int:group_id>/leave", methods=['POST'])
@login_required
def leave_group(group_id):
    """Leave a group"""
    group = Group.query.get_or_404(group_id)
    
    if current_user not in group.members.all():  # Use .all() to check membership
        return jsonify({'success': False, 'error': 'Not a member'})

    group.members.remove(current_user)
    group.member_count = group.members.count()  # Use .count() instead of len()
    db.session.commit()

    return jsonify({'success': True})






@user.route('/groups/<int:group_id>/post', methods=['POST'])
@login_required
def create_group_post(group_id):
    """Create a post in a group"""
    group = Group.query.get_or_404(group_id)
    
    if current_user not in group.members:
        return jsonify({'success': False, 'error': 'Must be a member to post'})

    post_content = request.form.get('post_content', '').strip()
    media_file = request.files.get('media')

    if not post_content and not (media_file and media_file.filename):
        return jsonify({'success': False, 'error': 'Post content or media is required'})

    try:
        image_url = None
        video_url = None

        if media_file and media_file.filename and allowed_file(media_file.filename):
            resource_type = 'auto'
            if media_file.content_type.startswith('video'):
                resource_type = 'video'

            result = cloudinary.uploader.upload(
                media_file,
                folder='kimbela/groups/posts',
                resource_type=resource_type,
                transformation=[
                    {'width': 800, 'crop': 'limit'},
                    {'quality': 'auto', 'fetch_format': 'auto'},
                ],
            )

            if media_file.content_type.startswith('video'):
                video_url = result['secure_url']
            else:
                image_url = result['secure_url']

        post = Post(
            content=post_content,
            image=image_url,
            video=video_url,
            author_id=current_user.id,
            group_id=group_id,  # Now this will work!
            created_at=datetime.utcnow()
        )
        
        db.session.add(post)
        db.session.commit()

        return jsonify({
            'success': True, 
            'post_id': post.id,
            'message': 'Post created successfully!'
        })

    except Exception as e:
        db.session.rollback()
        print('Group post creation error:', e)
        return jsonify({'success': False, 'error': 'Failed to create post'})
    
    
    
    
    
    
    

@user.route('/groups/<int:group_id>/posts')
@login_required
def get_group_posts(group_id):
    """Get posts for a group with pagination"""
    page = request.args.get('page', 1, type=int)
    per_page = 10
    
    posts = Post.query.filter_by(group_id=group_id)\
        .order_by(Post.created_at.desc())\
        .paginate(page=page, per_page=per_page, error_out=False)
    
    posts_data = []
    for post in posts.items:
        posts_data.append({
            'id': post.id,
            'content': post.content,
            'image': post.image,
            'video': post.video,
            'created_at': post.created_at.isoformat(),
            'author': {
                'id': post.author.id,
                'name': post.author.full_name,
                'avatar': post.author.profile_pic or url_for('static', filename='assets/img/default-avatar.png')
            },
            'likes_count': post.likes.count(),
            'comments_count': post.comments.count(),
            'user_has_liked': current_user.has_liked_post(post.id) if current_user.is_authenticated else False
        })
    
    return jsonify({
        'posts': posts_data,
        'has_next': posts.has_next,
        'next_page': posts.next_num if posts.has_next else None     
    })
    
    
    
    
    

@user.route('/report_content', methods=['POST'])
@login_required
def report_content():
    """Report a post or comment"""
    data = request.get_json()
    
    content_type = data.get('content_type')  # 'post' or 'comment'
    content_id = data.get('content_id')
    reason = data.get('reason')
    additional_info = data.get('additional_info', '')
    
    if not all([content_type, content_id, reason]):
        return jsonify({'success': False, 'error': 'Missing required fields'})
    
    # Determine the reported user based on content type
    reported_user_id = None
    if content_type == 'post':
        post = Post.query.get(content_id)
        if post:
            reported_user_id = post.author_id
    elif content_type == 'comment':
        comment = Comment.query.get(content_id)
        if comment:
            reported_user_id = comment.author_id
    
    report = ReportedContent(
        reporter_id=current_user.id,
        reported_user_id=reported_user_id,
        content_type=content_type,
        content_id=content_id,
        reason=f"{reason}: {additional_info}".strip() if additional_info else reason,
        status='pending'
    )
    
    db.session.add(report)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Content reported successfully'})





@user.route('/groups/all')
@login_required
def get_all_groups():
    """API endpoint to get all groups with filtering"""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    category = request.args.get('category', '')
    privacy = request.args.get('privacy', '')
    
    query = Group.query.filter_by(is_active=True)
    
    if search:
        query = query.filter(
            db.or_(
                Group.name.ilike(f'%{search}%'),
                Group.description.ilike(f'%{search}%')
            )
        )
    
    if category and category != 'all':
        query = query.filter_by(category=category)
    
    if privacy == 'public':
        query = query.filter_by(is_private=False)
    elif privacy == 'private':
        query = query.filter_by(is_private=True)
    
    groups = query.order_by(Group.member_count.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    
    groups_data = []
    for group in groups.items:
        groups_data.append({
            'id': group.id,
            'name': group.name,
            'description': group.description,
            'image': group.image,
            'category': group.category,
            'is_private': group.is_private,
            'member_count': group.member_count,
            'created_at': group.created_at.isoformat(),
            'is_member': current_user in group.members
        })
    
    return jsonify(groups_data)




@user.route('/groups/<int:group_id>/members')
@login_required
def get_group_members(group_id):
    """Get group members"""
    group = Group.query.get_or_404(group_id)
    page = request.args.get('page', 1, type=int)
    
    members = group.members.paginate(page=page, per_page=50, error_out=False)
    
    members_data = []
    for member in members.items:
        members_data.append({
            'id': member.id,
            'name': member.full_name,
            'avatar': member.profile_pic or url_for('static', filename='assets/img/default-avatar.png'),
            'is_online': member.is_online,
            'last_seen': member.last_seen.isoformat() if member.last_seen else None
        })
    
    return jsonify({
        'members': members_data,
        'has_next': members.has_next,
        'next_page': members.next_num if members.has_next else None
    })
    
    
    


# Add these routes to your Flask application
@user.route('/edit_post/<int:post_id>', methods=['POST'])
@login_required
def edit_group_post(post_id):
    try:
        post = Post.query.get_or_404(post_id)
        
        # Check if the current user is the author
        if post.author_id != current_user.id:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
        new_content = request.form.get('post_content')
        if new_content:
            post.content = new_content
            db.session.commit()
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Content cannot be empty'})
            
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    
    
    
    

@user.route('/delete_post/<int:post_id>', methods=['POST'])
@login_required
def delete_group_post(post_id):
    try:
        post = Post.query.get_or_404(post_id)
        
        # Check if the current user is the author
        if post.author_id != current_user.id:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
        db.session.delete(post)
        db.session.commit()
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    
    
    
    
    
    

@user.route('/delete_comment/<int:comment_id>', methods=['POST'])
@login_required
def delete_group_comment(comment_id):
    try:
        comment = Comment.query.get_or_404(comment_id)
        
        # Check if the current user is the author
        if comment.author_id != current_user.id:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
        db.session.delete(comment)
        db.session.commit()
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@user.route('/get_comments/<int:post_id>')
@login_required
def get_group_comments(post_id):
    try:
        post = Post.query.get_or_404(post_id)
        comments = []
        
        for comment in post.comments_list:
            comments.append({
                'id': comment.id,
                'content': comment.content,
                'author_name': comment.author.full_name,
                'author_id': comment.author_id,
                'avatar': comment.author.profile_pic or url_for('static', filename='assets/img/default-avatar.png'),
                'created_at': comment.created_at.strftime('%I:%M %p')
            })
        
        return jsonify({'comments': comments})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
    


@user.route('/like_post/<int:post_id>', methods=['POST'])
@login_required
def like_group_post(post_id):
    try:
        post = Post.query.get_or_404(post_id)
        liked = post.toggle_like(current_user.id)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'liked': liked,
            'like_count': len(post.likes_list)
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@user.route('/add_comment/<int:post_id>', methods=['POST'])
@login_required
def add_group_comment(post_id):
    try:
        data = request.get_json()
        content = data.get('content', '').strip()
        
        if not content:
            return jsonify({'success': False, 'error': 'Comment cannot be empty'})
        
        comment = Comment(
            content=content,
            author_id=current_user.id,
            post_id=post_id
        )
        
        db.session.add(comment)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'comment': {
                'id': comment.id,
                'content': comment.content,
                'author_name': current_user.full_name,
                'author_avatar': current_user.profile_pic or url_for('static', filename='assets/img/default-avatar.png'),
                'created_at': 'Just now'
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    
    
    
    
from models import Reaction
    
    
@user.route('/react_post/<int:post_id>', methods=['POST'])
@login_required
def react_to_post(post_id):
    """Handle post reactions"""
    try:
        data = request.get_json()
        reaction_type = data.get('reaction_type', 'like')
        
        # Validate reaction type
        valid_reactions = ['like', 'love', 'care', 'haha', 'wow', 'sad', 'angry']
        if reaction_type not in valid_reactions:
            return jsonify({'success': False, 'error': 'Invalid reaction type'}), 400
        
        post = Post.query.get_or_404(post_id)
        
        # Check for existing reaction
        existing_reaction = Reaction.query.filter_by(
            user_id=current_user.id, 
            post_id=post_id
        ).first()
        
        if existing_reaction:
            if existing_reaction.reaction_type == reaction_type:
                # Remove reaction if same type clicked again
                db.session.delete(existing_reaction)
                reacted = False
            else:
                # Update reaction type
                existing_reaction.reaction_type = reaction_type
                reacted = True
        else:
            # Add new reaction
            new_reaction = Reaction(
                user_id=current_user.id,
                post_id=post_id,
                reaction_type=reaction_type
            )
            db.session.add(new_reaction)
            reacted = True
        
        db.session.commit()
        
        # Get updated reaction count
        reaction_count = Reaction.query.filter_by(post_id=post_id).count()
        user_reaction = Reaction.query.filter_by(
            user_id=current_user.id, 
            post_id=post_id
        ).first()
        
        return jsonify({
            'success': True,
            'reacted': reacted,
            'reaction_type': reaction_type,
            'total_reactions': reaction_count,
            'user_reaction': user_reaction.reaction_type if user_reaction else None
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Reaction error: {e}")
        return jsonify({'success': False, 'error': 'Failed to react to post'}), 500