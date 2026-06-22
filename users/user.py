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
    abort,
)
from datetime import date
from urllib.parse import urlparse, urljoin
from sqlalchemy.orm import joinedload
from sqlalchemy import func, or_

from models import (
    MatchmakingPackage,
    MatchmakingRequest,
    MatchmakingLike,
    MatchmakingView,
    User,
    Message as ChatMessage,
    SponsoredAd,
    AdCampaign,
    BirthdayNotification,
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

from time_utils import utcnow
# from scheduler import (
#     manual_trigger_matchmaking_expiry_check,
#     manual_trigger_expired_matchmaking_check,
# )
from extensions import db, bcrypt, mail, socketio

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
    Country,
    State,
    City,
    # ReportedPost,
)

from flask_login import login_user, logout_user, login_required, current_user

from extensions import db
from extensions import cache as app_cache
from extensions import cache as app_cache
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from io import BytesIO
import mimetypes

import random
from extensions import db, login_manager, mail
import string
from dotenv import load_dotenv

from flask import jsonify, request
from random import sample
from datetime import datetime
from payments.payment_service import PaymentService
from flask_caching import Cache
from extensions import csrf

cache = Cache()


def safe_cache_delete(cache_key):
    try:
        app_cache.delete(cache_key)
    except Exception as exc:
        try:
            current_app.logger.warning(
                "Cache delete skipped for %s: %s", cache_key, exc
            )
        except Exception:
            pass


def safe_cache_get(cache_key):
    try:
        return app_cache.get(cache_key)
    except Exception as exc:
        try:
            current_app.logger.warning(
                "Cache get skipped for %s: %s", cache_key, exc
            )
        except Exception:
            pass
        return None


def safe_cache_set(cache_key, value, timeout=300):
    try:
        app_cache.set(cache_key, value, timeout=timeout)
    except Exception as exc:
        try:
            current_app.logger.warning(
                "Cache set skipped for %s: %s", cache_key, exc
            )
        except Exception:
            pass


def resolve_user_by_identifier(user_identifier):
    user = User.query.filter_by(public_id=user_identifier).first()
    if user:
        return user

    if str(user_identifier).isdigit():
        return User.query.get_or_404(int(user_identifier))

    abort(404)


def resolve_post_by_identifier(post_identifier):
    post = Post.query.filter_by(public_id=post_identifier).first()
    if post:
        return post

    if str(post_identifier).isdigit():
        return Post.query.get_or_404(int(post_identifier))

    abort(404)


def _absolute_share_url(raw_url):
    if not raw_url:
        return None

    base_url = (current_app.config.get("BASE_URL") or "").rstrip("/")

    if raw_url.startswith(("http://", "https://")):
        return raw_url

    if raw_url.startswith("/uploads/"):
        raw_url = raw_url.replace("/uploads/", "/public/uploads/", 1)

    root_url = f"{base_url}/" if base_url else request.url_root
    return urljoin(root_url, raw_url.lstrip("/"))


def _social_preview_image_url(raw_url):
    absolute_url = _absolute_share_url(raw_url)
    if not absolute_url:
        return None

    cloudinary_marker = "/image/upload/"
    if "res.cloudinary.com" in absolute_url and cloudinary_marker in absolute_url:
        return absolute_url.replace(
            cloudinary_marker,
            "/image/upload/f_jpg,q_auto,w_1200,c_limit/",
            1,
        )

    return absolute_url


def build_post_share_meta(post):
    preview_post = post.shared_post or post
    fallback_image = url_for("static", filename="assets/img/kim.png")
    image_url = (
        preview_post.image
        or preview_post.gif
        or post.image
        or post.gif
        or fallback_image
    )

    title_author = preview_post.author if preview_post.author else post.author
    description_source = (
        post.content
        or preview_post.content
        or f"See {title_author.full_name}'s post on Kimbela."
    ).strip()
    description = description_source[:197].rstrip() + "..." if len(description_source) > 200 else description_source
    absolute_image_url = _social_preview_image_url(image_url)
    image_type, _ = mimetypes.guess_type(absolute_image_url or "")

    return {
        "title": f"Post by {title_author.full_name} - Kimbela",
        "description": description,
        "url": _absolute_share_url(url_for("user.view_shared_post", post_identifier=post.public_id)),
        "image": absolute_image_url,
        "image_type": image_type or "image/jpeg",
        "image_width": "1200",
        "image_height": "630",
    }


def get_groups_data_for_user(user_id):
    cache_key = f"user_groups_v2:{user_id}"
    cached = safe_cache_get(cache_key)
    if cached is not None:
        return cached

    def is_alumni_married_group(name):
        normalized = (name or "").strip().lower()
        return "alumni" in normalized and "married" in normalized

    groups = Group.query.filter_by(is_active=True).all()
    groups = sorted(
        groups,
        key=lambda group: (
            is_alumni_married_group(group.name),
            group.name.lower(),
        ),
    )
    if not groups:
        safe_cache_set(cache_key, [], timeout=60)
        return []

    member_group_ids = {
        row[0]
        for row in db.session.query(group_members.c.group_id)
        .filter(group_members.c.user_id == user_id)
        .all()
    }

    groups_data = []
    for group in groups:
        groups_data.append(
            {
                "id": group.id,
                "name": group.name,
                "cover_pic": group.image
                or "https://via.placeholder.com/100x100/3B82F6/FFFFFF?text=Group",
                "member_count": group.member_count or 0,
                "is_member": group.id in member_group_ids,
                "unread_count": 0,
            }
        )

    safe_cache_set(cache_key, groups_data, timeout=60)
    return groups_data


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


@user.get("/api/locations/countries")
def get_countries():
    rows = Country.query.with_entities(Country.id, Country.name).order_by(
        Country.name
    )
    return jsonify([{"id": r.id, "name": r.name} for r in rows])


@user.get("/api/locations/states")
def get_states():
    country_id = request.args.get("country_id", type=int)
    if not country_id:
        return jsonify([])
    rows = (
        State.query.with_entities(State.id, State.name)
        .filter_by(country_id=country_id)
        .order_by(State.name)
    )
    return jsonify([{"id": r.id, "name": r.name} for r in rows])


@user.get("/api/locations/cities")
def get_cities():
    state_id = request.args.get("state_id", type=int)
    if not state_id:
        return jsonify([])
    rows = (
        City.query.with_entities(City.id, City.name)
        .filter_by(state_id=state_id)
        .order_by(City.name)
    )
    return jsonify([{"id": r.id, "name": r.name} for r in rows])


def _require_debug_access():
    """Restrict debug endpoints to admins when explicitly enabled."""
    if not current_user.is_authenticated:
        abort(404)
    if not current_user.is_super_admin:
        abort(404)
    if not current_app.config.get("ENABLE_DEBUG_ROUTES"):
        abort(404)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


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

def get_banner_ad_by_placement(placement):
    current_time = utcnow()
    banner_ad = (
        AdCampaign.query.filter(
            AdCampaign.status == "active",
            AdCampaign.start_date <= current_time,
            AdCampaign.end_date >= current_time,
            AdCampaign.placement == placement,
        )
        .order_by(AdCampaign.budget.desc())
        .first()
    )
    if not banner_ad:
        return None

    media_url = (
        banner_ad.image
        or "https://via.placeholder.com/1600x400/0f172a/ffffff?text=Kimbela+Ad"
    )
    return {
        "id": banner_ad.id,
        "title": banner_ad.title or "Featured Offer",
        "image_url": media_url,
        "target_url": banner_ad.target_url or "#",
    }



@user.route("/")
@user.route("/index", methods=["GET", "POST"])
def index():
    return render_template("index.html")


def timeago(dt):
    now = utcnow()
    diff = now - dt
    if diff.days > 0:
        return f"{diff.days}d ago"
    hours = diff.seconds // 3600
    if hours > 0:
        return f"{hours}h ago"
    mins = diff.seconds // 60
    return f"{mins}m ago" if mins > 0 else "just now"

    app.jinja_env.filters["timeago"] = timeago


# Run this once to create sample packages
def create_sample_packages():
    packages = [
        MatchmakingPackage(
            name="Basic",
            description="Perfect for casual matchmaking",
            price=9.99,
            duration_days=7,
            features="Basic Profile Listing,7 Days Duration,Basic Matching,Limited Visibility",
        ),
        MatchmakingPackage(
            name="Standard",
            description="Great for serious connections",
            price=24.99,
            duration_days=14,
            features="Enhanced Profile Listing,14 Days Duration,Advanced Matching,Priority Placement,Message Responses",
        ),
        MatchmakingPackage(
            name="Premium",
            description="Maximum visibility and matches",
            price=49.99,
            duration_days=30,
            features="Premium Profile Listing,30 Days Duration,Advanced Matching,Top Placement,Unlimited Messages,Personal Matchmaker",
        ),
        MatchmakingPackage(
            name="Elite",
            description="For exclusive matchmaking",
            price=99.99,
            duration_days=60,
            features="Elite Profile Listing,60 Days Duration,VIP Matching,Featured Placement,Unlimited Messages,Dedicated Matchmaker,Background Verification",
        ),
    ]

    for package in packages:
        db.session.add(package)

    db.session.commit()


from sqlalchemy import select, func, exists, and_
from sqlalchemy.orm import joinedload, contains_eager
from flask_caching import Cache

from werkzeug.exceptions import RequestEntityTooLarge

from werkzeug.exceptions import RequestEntityTooLarge


@user.route("/api/birthdays/today")
@login_required
def get_today_birthdays():
    """Get friends with birthdays today"""
    today = date.today()

    birthday_friends = []
    for friend in current_user.friends:
        if (
            friend.dob
            and friend.dob.month == today.month
            and friend.dob.day == today.day
        ):
            birthday_friends.append(
                {
                    "id": friend.id,
                    "name": friend.full_name,
                    "avatar": friend.profile_pic
                    or url_for("static", filename="assets/img/default-avatar.png"),
                    "age": today.year - friend.dob.year,
                }
            )

    return jsonify(
        {"success": True, "birthdays": birthday_friends, "count": len(birthday_friends)}
    )


@user.route("/api/birthdays/upcoming")
@login_required
def get_upcoming_birthdays_api():
    """Get upcoming birthdays (next 7 days)"""
    upcoming = get_upcoming_birthdays(current_user.id, days_ahead=7)

    birthdays_data = []
    for item in upcoming:
        birthdays_data.append(
            {
                "id": item["friend"].id,
                "name": item["friend"].full_name,
                "avatar": item["friend"].profile_pic
                or url_for("static", filename="assets/img/default-avatar.png"),
                "days_until": item["days_until"],
                "birthday_date": item["birthday_date"].isoformat(),
                "age": item["age"],
            }
        )

    return jsonify({"success": True, "birthdays": birthdays_data})


@user.route("/api/birthday/wish", methods=["POST"])
@login_required
def send_birthday_wish():
    """Send a birthday wish with comprehensive error logging"""
    import traceback
    import sys

    # Log start of request
    print(
        f"\n🎂 [BIRTHDAY WISH] Request received from user {current_user.id} ({current_user.full_name})"
    )
    print(f"📦 Request method: {request.method}")

    try:
        # Get and validate JSON data
        if not request.is_json:
            print("❌ [ERROR] Request is not JSON")
            return (
                jsonify(
                    {"success": False, "error": "Content-Type must be application/json"}
                ),
                400,
            )

        data = request.get_json()
        print(f"📦 Raw request data: {data}")

        if not data:
            print("❌ [ERROR] No data provided in request")
            return jsonify({"success": False, "error": "No data provided"}), 400

        # Extract and validate parameters
        friend_id = data.get("friend_id")
        message = data.get("message", "Happy Birthday! 🎉").strip()

        print(f"🎯 Processing birthday wish:")
        print(f"   → Friend ID: {friend_id}")
        print(f"   → Message: '{message}'")
        print(f"   → Current user ID: {current_user.id}")

        if not friend_id:
            print("❌ [ERROR] Friend ID is required")
            return jsonify({"success": False, "error": "Friend ID is required"}), 400

        try:
            friend_id = int(friend_id)
        except (ValueError, TypeError):
            print(f"❌ [ERROR] Invalid friend ID type: {type(friend_id)}")
            return jsonify({"success": False, "error": "Invalid friend ID format"}), 400

        # Find friend
        print(f"🔍 Looking up friend with ID: {friend_id}")
        friend = User.query.get(friend_id)

        if not friend:
            print(f"❌ [ERROR] Friend not found with ID: {friend_id}")
            return jsonify({"success": False, "error": "Friend not found"}), 404

        print(f"✅ Friend found: {friend.full_name} (ID: {friend.id})")

        # Check friendship status
        print(f"🤝 Checking friendship between {current_user.id} and {friend.id}")
        are_friends = current_user.is_friend_with(friend)
        print(f"   → Are friends: {are_friends}")

        if not are_friends:
            print(f"❌ [ERROR] Users are not friends")
            return jsonify({"success": False, "error": "Not friends"}), 403

        # Check if friend has birthday today
        today = date.today()
        print(f"📅 Today's date: {today}")

        if friend.dob:
            friend_birthday = friend.dob.replace(year=today.year)
            is_birthday = (
                friend.dob.month == today.month and friend.dob.day == today.day
            )
            print(f"🎁 Friend's DOB: {friend.dob}")
            print(f"🎁 Birthday this year: {friend_birthday}")
            print(f"🎁 Is birthday today: {is_birthday}")

            if not is_birthday:
                print("⚠️ [WARNING] Friend's birthday is not today")
                # We'll still allow sending the wish, but log it
        else:
            print("⚠️ [WARNING] Friend does not have DOB set")

        # Start database transaction
        print(f"💾 Starting database transaction...")

        # Create or update birthday notification
        notification = BirthdayNotification.query.filter_by(
            user_id=current_user.id, birthday_user_id=friend.id, birthday_date=today
        ).first()

        if notification:
            print(f"📝 Updating existing birthday notification ID: {notification.id}")
            notification.is_wished = True
            notification.wish_message = message
            notification.wished_at = utcnow()
            print(f"   → Updated wish status to: {notification.is_wished}")
            print(f"   → Wish message: {notification.wish_message[:50]}...")
        else:
            print(f"📝 Creating new birthday notification")
            notification = BirthdayNotification(
                user_id=current_user.id,
                birthday_user_id=friend.id,
                birthday_date=today,
                is_wished=True,
                wish_message=message,
                wished_at=utcnow(),
            )
            db.session.add(notification)
            print(f"   → Created notification with wished_at: {notification.wished_at}")

        # Mark notification as seen
        notification.is_seen = True
        print(f"   → Marked notification as seen: {notification.is_seen}")

        # Create birthday message - FIXED: Use sender and receiver objects, not IDs

        birthday_message = ChatMessage()

        birthday_message.sender_id = current_user.id
        birthday_message.receiver_id = friend.id
        birthday_message.content = f"🎂 {message}"
        birthday_message.timestamp = utcnow()
        birthday_message.status = "sent"
        birthday_message.message_type = "birthday_wish"
        birthday_message.message_data = {
            "is_birthday_wish": True,
            "original_message": message,
            "wish_sent_at": utcnow().isoformat(),
            "friend_name": friend.full_name,
            "wisher_name": current_user.full_name,
        }

        db.session.add(birthday_message)
        db.session.flush()  # ensures birthday_message.id exists
        print(f"✅ ChatMessage created with ID: {birthday_message.id}")
        # so birthday_message.id exists BEFORE commit
        print(f"✅ ChatMessage created with ID: {birthday_message.id}")

        print(f"✅ ChatMessage created with ID: {birthday_message.id}")
        print(f"   → Sender: {current_user.full_name} (ID: {current_user.id})")
        print(f"   → Receiver: {friend.full_name} (ID: {friend.id})")
        print(f"   → Content preview: {birthday_message.content[:50]}...")

        # Debug: Print all ChatMessage object attributes
        print(f"🔍 ChatMessage object attributes:")
        for attr in ["sender_id", "receiver_id", "sender", "receiver"]:
            if hasattr(birthday_message, attr):
                value = getattr(birthday_message, attr)
                print(f"   → {attr}: {value} (type: {type(value).__name__})")
            else:
                print(f"   → {attr}: Not found")

        # Commit all changes
        print(f"💾 Committing database changes...")
        db.session.commit()
        print(f"✅ Database commit successful!")

        # Verify the message was saved correctly
        saved_message = ChatMessage.query.get(birthday_message.id)
        if saved_message:
            print(f"✅ Message saved successfully in database")
            print(f"   → Saved sender_id: {saved_message.sender_id}")
            print(f"   → Saved receiver_id: {saved_message.receiver_id}")
            print(f"   → Saved content: {saved_message.content[:50]}...")
        else:
            print(f"⚠️ Could not retrieve saved message from database")

        # Log success
        print(f"🎉 Birthday wish sent successfully!")
        print(f"   → Message ID: {birthday_message.id}")
        print(f"   → Notification ID: {notification.id}")
        print(f"   → Sent at: {utcnow().isoformat()}")

        return jsonify(
            {
                "success": True,
                "message": "Birthday wish sent! 🎉",
                "message_id": birthday_message.id,
                "notification_id": notification.id,
                "timestamp": utcnow().isoformat(),
                "friend_name": friend.full_name,
            }
        )

    except Exception as e:
        # Rollback on error
        print(f"\n❌ [ERROR] Exception occurred:")
        print(f"   → Error type: {type(e).__name__}")
        print(f"   → Error message: {str(e)}")
        print(f"\n🔍 Stack trace:")
        traceback.print_exc(file=sys.stdout)

        # Attempt to get more context about the error
        print(f"\n📊 Error context:")
        print(f"   → Current user: {current_user.id if current_user else 'None'}")
        print(f"   → Request method: {request.method}")
        print(f"   → Request path: {request.path}")

        # Database rollback
        try:
            db.session.rollback()
            print(f"   → Database rollback completed")
        except Exception as rollback_error:
            print(f"   → Failed to rollback: {rollback_error}")

        # Check for specific common errors
        error_msg = str(e)
        if "sender" in error_msg.lower() or "receiver" in error_msg.lower():
            print(f"   → Detected sender/receiver related error")
            print(f"   → Message model expects sender and receiver objects")

        return (
            jsonify(
                {
                    "success": False,
                    "error": "Failed to send birthday wish",
                    "details": str(e),
                    "error_type": type(e).__name__,
                }
            ),
            500,
        )


@user.route("/api/birthday/notifications/mark_seen", methods=["POST"])
@login_required
def mark_birthday_notifications_seen():
    """Mark birthday notifications as seen"""
    try:
        BirthdayNotification.query.filter_by(
            user_id=current_user.id, is_seen=False
        ).update({"is_seen": True})

        db.session.commit()
        return jsonify({"success": True})

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@user.route("/user_dashboard", methods=["GET", "POST"])
@login_required
def user_dashboard():
    """Main dashboard route with full support for images, videos, and GIPHY GIFs"""

    # ===== POST REQUEST =====
    if request.method == "POST":
        # Optional: Handle AJAX file upload progress (if you have it)
        if (
            request.headers.get("X-Requested-With") == "XMLHttpRequest"
            and request.headers.get("X-File-Upload") == "true"
        ):
            return handle_ajax_post_upload()  # Your existing handler, if any

        try:
            post_content = request.form.get("post_content", "").strip()
            media_file = request.files.get("media")
            gif_url = request.form.get("gif_url", "").strip()  # From hidden input
            post_location = request.form.get("post_location", "").strip()

            image_url = None
            video_url = None
            gif_url_saved = None

            # Validation: require at least one of text, media, or GIF
            has_content = bool(post_content)
            has_media = bool(media_file and media_file.filename)
            has_gif = bool(gif_url)

            if not (has_content or has_media or has_gif):
                flash(
                    "Please add text, a photo, or a GIF to your post.", "warning"
                )
                return redirect(url_for("user.user_dashboard"))

            if has_media:
                filename_lower = media_file.filename.lower()
                if media_file.content_type.startswith("video/") or filename_lower.endswith(
                    (".mp4", ".mov", ".avi", ".mkv", ".webm")
                ):
                    flash("Video uploads are not allowed.", "danger")
                    return redirect(url_for("user.user_dashboard"))

                if not allowed_file(media_file.filename):
                    flash("Unsupported file type. Please upload an image or GIF.", "danger")
                    return redirect(url_for("user.user_dashboard"))

            # === HANDLE UPLOADED MEDIA (Photo / Video / Uploaded GIF) ===
            if has_media and allowed_file(media_file.filename):
                try:
                    # Check file size
                    media_file.seek(0, 2)
                    file_size = media_file.tell()
                    media_file.seek(0)

                    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
                    if file_size > MAX_FILE_SIZE:
                        flash("File too large! Maximum size is 100MB.", "danger")
                        return redirect(url_for("user.user_dashboard"))

                    # Determine resource type (images only)
                    filename_lower = media_file.filename.lower()
                    if filename_lower.endswith((".gif", ".png", ".jpg", ".jpeg", ".webp", ".bmp")):
                        resource_type = "image"
                    else:
                        resource_type = "auto"

                    upload_options = {
                        "folder": "kimbela/posts",
                        "resource_type": resource_type,
                        "transformation": [
                            {"width": 1000, "crop": "limit"},
                            {"quality": "auto", "fetch_format": "auto"},
                        ],
                    }

                    # Preserve animation for uploaded GIFs
                    if filename_lower.endswith(".gif"):
                        upload_options["transformation"] = [
                            {"quality": "auto", "fetch_format": "gif"}
                        ]

                    result = cloudinary.uploader.upload(media_file, **upload_options)

                    image_url = result["secure_url"]

                except Exception as e:
                    print(f"Media upload error: {e}")
                    flash("Failed to upload media. Please try again.", "danger")
                    return redirect(url_for("user.user_dashboard"))

            # === HANDLE GIPHY GIF (only if no uploaded media was processed) ===
            elif has_gif:
                gif_url = gif_url.strip()

                if not gif_url.startswith("https://"):
                    flash("GIF URL must use HTTPS.", "danger")
                    return redirect(url_for("user.user_dashboard"))

                if ".giphy.com/" not in gif_url:
                    print(f"Blocked non-GIPHY URL: {gif_url}")
                    flash("Only GIPHY GIFs are allowed.", "danger")
                    return redirect(url_for("user.user_dashboard"))

                # It's a valid GIPHY URL
                gif_url_saved = gif_url

            # === CREATE THE POST ===
            new_post = Post(
                content=post_content or "",  # Allow empty text if media/GIF present
                image=image_url,
                video=video_url,
                gif=gif_url_saved,
                location=post_location or None,
                author_id=current_user.id,
                created_at=utcnow(),
            )

            db.session.add(new_post)
            db.session.commit()

            print(f"Post created successfully! ID: {new_post.id}")
            if image_url:
                print(f"→ Image: {image_url}")
            if video_url:
                print(f"→ Video: {video_url}")
            if gif_url_saved:
                print(f"→ GIF: {gif_url_saved}")

            # Clear any relevant cache
            try:
                safe_cache_delete(f"user_dashboard_{current_user.id}")
                safe_cache_delete(f"posts_feed_{current_user.id}")
            except:
                pass

            flash("Your post was created successfully!", "success")
            return redirect(url_for("user.user_dashboard"))

        except RequestEntityTooLarge:
            flash("File is too large! Maximum size is 100MB.", "danger")
            return redirect(url_for("user.user_dashboard"))
        except Exception as e:
            db.session.rollback()
            print(f"Error creating post: {e}")
            flash("An error occurred. Please try again.", "danger")
            return redirect(url_for("user.user_dashboard"))

    # ===== GET REQUEST =====
    user_id = current_user.id
    cursor = request.args.get("cursor", type=int)
    limit = request.args.get("limit", 10, type=int)

    posts, next_cursor, has_more = get_visible_posts_optimized(
        user_id, cursor=cursor, limit=limit
    )

    # Friends
    friend_query = text(
        """
        SELECT friend_id FROM friendship WHERE user_id = :user_id
        UNION
        SELECT user_id FROM friendship WHERE friend_id = :user_id
    """
    )
    friend_ids_result = db.session.execute(friend_query, {"user_id": user_id})
    friend_ids = {row[0] for row in friend_ids_result}

    blocked_query = text(
        """
        SELECT blocked_id FROM user_blocks WHERE blocker_id = :user_id
        UNION
        SELECT blocker_id FROM user_blocks WHERE blocked_id = :user_id
    """
    )
    blocked_ids_result = db.session.execute(blocked_query, {"user_id": user_id})
    blocked_ids = {row[0] for row in blocked_ids_result}

    friends = []
    if friend_ids:
        friends = (
            User.query.filter(User.id.in_(friend_ids), ~User.id.in_(blocked_ids))
            .order_by(User.last_seen.desc())
            .limit(20)
            .all()
        )

    # People you may know (suggestions)
    suggestions_query = User.query.filter(
        User.id != user_id,
        ~User.id.in_(friend_ids),
        ~User.id.in_(blocked_ids),
        User.is_active == True,
    )
    eligible_count = suggestions_query.count()
    random_five = []
    if eligible_count > 0:
        offset = random.randint(0, max(eligible_count - 5, 0))
        random_five = suggestions_query.offset(offset).limit(5).all()
        for user in random_five:
            user.friend_request_status = current_user.get_friend_request_status(user.id)

    # Groups (cached, for initial HTML render)
    groups_data = get_groups_data_for_user(current_user.id)

    # Sponsored ads (example)
    current_time = utcnow()
    sponsored_ads = (
        AdCampaign.query.filter(
            AdCampaign.status == "active",
            AdCampaign.start_date <= current_time,
            AdCampaign.end_date >= current_time,
        )
        .filter(or_(AdCampaign.placement == None, AdCampaign.placement == "sponsored"))
        .order_by(AdCampaign.budget.desc())
        .limit(3)
        .all()
    )

    def get_video_mime(url):
        if not url:
            return ""
        lower = url.split("?")[0].lower()
        if lower.endswith(".webm"):
            return "video/webm"
        if lower.endswith(".mov"):
            return "video/quicktime"
        if lower.endswith(".m4v"):
            return "video/mp4"
        if lower.endswith(".mp4"):
            return "video/mp4"
        return ""

    placement_map = {
        "top_banner": "dashboard-top",
        "sidebar_banner": "dashboard-sidebar",
        "vertical_banner": "dashboard-vertical",
        "spotlight_banner": "dashboard-spotlight",
        "bottom_banner": "dashboard-bottom",
    }
    dashboard_ads = {}
    for key, placement in placement_map.items():
        banner_ad = (
            AdCampaign.query.filter(
                AdCampaign.status == "active",
                AdCampaign.start_date <= current_time,
                AdCampaign.end_date >= current_time,
                AdCampaign.placement == placement,
            )
            .order_by(AdCampaign.budget.desc())
            .first()
        )
        if banner_ad:
            media_url = (
                banner_ad.image
                or "https://via.placeholder.com/1200x600/0f172a/ffffff?text=Kimbela+Ad"
            )
            video_mime = get_video_mime(media_url)
            media_type = (
                "video"
                if placement
                in ["dashboard-sidebar", "dashboard-vertical", "dashboard-spotlight"]
                and video_mime
                else "image"
            )
            dashboard_ads[key] = {
                "id": banner_ad.id,
                "title": banner_ad.title or "Featured Offer",
                "description": banner_ad.description or "",
                "call_to_action": banner_ad.call_to_action or "Learn More",
                "image_url": media_url,
                "media_type": media_type,
                "video_mime": video_mime,
                "target_url": banner_ad.target_url or "#",
            }

    ads_data = [
        {
            "id": ad.id,
            "title": ad.title,
            "description": ad.description,
            "image_url": ad.image
            or "https://via.placeholder.com/600x300/4F46E5/FFFFFF?text=Sponsored+Ad",
            "target_url": ad.target_url or "#",
            "call_to_action": ad.call_to_action or "Learn More",
            "advertiser_name": ad.user.full_name if ad.user else "Sponsor",
        }
        for ad in sponsored_ads
    ]

    # AJAX partial posts
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        posts_html = render_template(
            "_posts_partial.html",
            posts=posts,
            current_user=current_user,
            default_avatar=url_for("static", filename="assets/img/default-avatar.png"),
        )
        return jsonify(
            {
                "success": True,
                "posts": posts_html,
                "next_cursor": next_cursor,
                "has_more": has_more,
                "count": len(posts),
                "sponsored_ads": ads_data[:1],
            }
        )

    # Add birthday notifications to the context
    today = date.today()
    birthday_notifications = BirthdayNotification.query.filter(
        BirthdayNotification.user_id == current_user.id,
        BirthdayNotification.is_seen == False,
    ).all()

    # Get friends with birthdays today
    birthday_friends_today = []
    for friend in friends:
        if (
            friend.dob
            and friend.dob.month == today.month
            and friend.dob.day == today.day
        ):
            birthday_friends_today.append(friend)

    # Get upcoming birthdays (next 7 days)
    upcoming_birthdays = get_upcoming_birthdays(current_user.id, days_ahead=7)

    # Full page render
    return render_template(
        "user_dashboard.html",
        initial_posts=posts,
        next_cursor=next_cursor,
        birthday_notifications=birthday_notifications,
        birthday_friends_today=birthday_friends_today,
        upcoming_birthdays=upcoming_birthdays,
        has_more=has_more,
        current_user=current_user,
        friends=friends,
        random_five=random_five,
        groups_data=groups_data,
        sponsored_ads=ads_data,
        dashboard_ads=dashboard_ads,
        csrf_token=generate_csrf(),
        default_avatar=url_for("static", filename="assets/img/default-avatar.png"),
    )


def handle_ajax_post_upload():
    """Handle AJAX post upload with progress simulation"""
    try:
        post_content = request.form.get("post_content", "").strip()
        media_file = request.files.get("media")
        emoji_data = request.form.get("emoji_data", "{}")

        # Validate content
        if not post_content and not (media_file and media_file.filename):
            return jsonify(
                {
                    "success": False,
                    "error": "Please add some content or media to your post.",
                }
            )

        image_url = None
        video_url = None
        gif_url = None

        if media_file and media_file.filename:
            filename = media_file.filename.lower()
            if media_file.content_type.lower().startswith("video") or filename.endswith(
                (".mp4", ".mov", ".avi", ".mkv", ".webm")
            ):
                return jsonify(
                    {"success": False, "error": "Video uploads are not allowed."}
                )
            if not allowed_file(media_file.filename):
                return jsonify(
                    {
                        "success": False,
                        "error": "Unsupported file type. Please upload an image or GIF.",
                    }
                )

        # Upload media if present
        if (
            media_file
            and media_file.filename != ""
            and allowed_file(media_file.filename)
        ):
            # Check file size
            media_file.seek(0, 2)
            file_size = media_file.tell()
            media_file.seek(0)

            MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB

            if file_size > MAX_FILE_SIZE:
                return jsonify(
                    {
                        "success": False,
                        "error": f"File too large! Maximum size is {MAX_FILE_SIZE // (1024 * 1024)}MB",
                    }
                )

            try:
                # Determine resource type (images only)
                resource_type = "auto"
                content_type = media_file.content_type.lower()
                filename = media_file.filename.lower()

                if content_type.startswith("image") or filename.endswith(
                    (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp")
                ):
                    resource_type = "image"

                # Special handling for GIFs
                is_gif = filename.endswith(".gif")

                upload_options = {
                    "folder": "kimbela/posts",
                    "resource_type": resource_type,
                    "transformation": [
                        {"width": 800, "crop": "limit"},
                        {"quality": "auto", "fetch_format": "auto"},
                    ],
                }

                if is_gif:
                    upload_options["transformation"] = [
                        {"width": 800, "crop": "limit"},
                        {"quality": "auto", "fetch_format": "gif"},
                    ]

                # Upload to Cloudinary
                result = cloudinary.uploader.upload(media_file, **upload_options)

                # Store URL
                image_url = result["secure_url"]

                if is_gif:
                    gif_url = result["secure_url"]
                    image_url = gif_url  # Store GIF as image URL

            except Exception as e:
                print(f"Media upload error: {e}")
                return jsonify(
                    {
                        "success": False,
                        "error": "Failed to upload media. The file might be corrupted.",
                    }
                )

        # Parse emoji data
        try:
            emoji_info = json.loads(emoji_data)
        except:
            emoji_info = {}

        # Create the post
        new_post = Post(
            content=post_content,
            image=image_url,
            video=video_url,
            author_id=current_user.id,
            created_at=utcnow(),
            emoji_data=emoji_info,
            # likes_count=0,
            # comments_count=0
        )

        db.session.add(new_post)
        db.session.commit()

        # Clear cache
        try:
            safe_cache_delete(f"user_dashboard_{current_user.id}")
            safe_cache_delete(f"posts_feed_{current_user.id}")
        except:
            pass

        # Process content for display
        processed_content = process_emoji_content(post_content, emoji_data)

        # Prepare response data
        response_data = {
            "success": True,
            "message": "Post created successfully!",
            "post_id": new_post.id,
            "post_public_id": new_post.public_id,
            "post_content": processed_content,
            "image_url": image_url,
            "video_url": video_url,
            "author_name": current_user.full_name,
            "author_avatar": current_user.profile_pic
            or url_for("static", filename="assets/img/default-avatar.png"),
            "created_at": new_post.created_at.isoformat(),
            "created_at_formatted": new_post.created_at.strftime("%b %d at %I:%M %p"),
        }

        return jsonify(response_data)

    except Exception as e:
        print(f"Error in AJAX post upload: {e}")
        db.session.rollback()

        # Check if it's a request entity too large error
        import werkzeug

        if isinstance(e, werkzeug.exceptions.RequestEntityTooLarge):
            return jsonify(
                {"success": False, "error": "File is too large! Maximum size is 100MB."}
            )

        return jsonify(
            {"success": False, "error": "An error occurred while creating the post."}
        )


def process_emoji_content(content, emoji_data):
    """
    Process post content to replace emoji/sticker/GIF placeholders with HTML
    """
    if not content or not emoji_data:
        return content

    try:
        emoji_info = json.loads(emoji_data)

        # Process stickers
        stickers = emoji_info.get("stickers", [])
        for sticker in stickers:
            placeholder = f"[sticker:{sticker.get('name', 'sticker')}]"
            replacement = f'<img src="{sticker.get("value", "")}" alt="{sticker.get("name", "sticker")}" class="inline-sticker h-6 w-6 align-middle" data-sticker-name="{sticker.get("name", "sticker")}">'
            content = content.replace(placeholder, replacement)

        # Process GIFs
        gifs = emoji_info.get("gifs", [])
        for gif in gifs:
            placeholder = f"[gif:{gif.get('name', 'gif')}]"
            replacement = f'<img src="{gif.get("value", "")}" alt="{gif.get("name", "gif")}" class="inline-gif max-h-60 rounded-lg my-2 mx-auto" data-gif-name="{gif.get("name", "gif")}">'
            content = content.replace(placeholder, replacement)

        # Process emojis (they're already in the text as Unicode)
        emojis = emoji_info.get("emojis", [])
        for emoji in emojis:
            # Emojis are already inserted as Unicode characters
            # We can add a data attribute for tracking
            emoji_char = emoji.get("value", "")
            emoji_name = emoji.get("name", "emoji")
            if emoji_char in content:
                # Wrap emoji with span for styling if needed
                content = content.replace(
                    emoji_char,
                    f'<span class="inline-emoji" data-emoji-name="{emoji_name}" title="{emoji_name}">{emoji_char}</span>',
                )

    except Exception as e:
        print(f"Error processing emoji content: {e}")

    return content


@user.route("/api/emojis/popular", methods=["GET"])
@login_required
def get_popular_emojis():
    """Get popular emojis for the picker"""
    popular_emojis = [
        {"emoji": "😂", "name": "Face with Tears of Joy"},
        {"emoji": "❤️", "name": "Red Heart"},
        {"emoji": "😍", "name": "Smiling Face with Heart-Eyes"},
        {"emoji": "🤣", "name": "Rolling on the Floor Laughing"},
        {"emoji": "😊", "name": "Smiling Face with Smiling Eyes"},
        {"emoji": "🙏", "name": "Folded Hands"},
        {"emoji": "😘", "name": "Face Blowing a Kiss"},
        {"emoji": "🥰", "name": "Smiling Face with Hearts"},
        {"emoji": "😭", "name": "Loudly Crying Face"},
        {"emoji": "😁", "name": "Beaming Face with Smiling Eyes"},
        {"emoji": "👍", "name": "Thumbs Up"},
        {"emoji": "😅", "name": "Grinning Face with Sweat"},
        {"emoji": "👏", "name": "Clapping Hands"},
        {"emoji": "😎", "name": "Smiling Face with Sunglasses"},
        {"emoji": "🎉", "name": "Party Popper"},
        {"emoji": "🔥", "name": "Fire"},
        {"emoji": "💯", "name": "Hundred Points"},
        {"emoji": "✨", "name": "Sparkles"},
        {"emoji": "🌟", "name": "Glowing Star"},
        {"emoji": "🎈", "name": "Balloon"},
    ]

    return jsonify({"success": True, "emojis": popular_emojis})


@user.route("/api/stickers", methods=["GET"])
@login_required
def get_stickers():
    """Get available stickers"""
    # In production, you'd fetch these from your database
    stickers = [
        {
            "id": 1,
            "name": "Happy Face",
            "url": "https://cdn.jsdelivr.net/npm/twemoji@14.0.2/assets/svg/1f600.svg",
            "category": "smileys",
        },
        {
            "id": 2,
            "name": "Heart Eyes",
            "url": "https://cdn.jsdelivr.net/npm/twemoji@14.0.2/assets/svg/1f60d.svg",
            "category": "smileys",
        },
        {
            "id": 3,
            "name": "Thumbs Up",
            "url": "https://cdn.jsdelivr.net/npm/twemoji@14.0.2/assets/svg/1f44d.svg",
            "category": "gestures",
        },
        {
            "id": 4,
            "name": "Red Heart",
            "url": "https://cdn.jsdelivr.net/npm/twemoji@14.0.2/assets/svg/2764.svg",
            "category": "hearts",
        },
        {
            "id": 5,
            "name": "Fire",
            "url": "https://cdn.jsdelivr.net/npm/twemoji@14.0.2/assets/svg/1f525.svg",
            "category": "objects",
        },
    ]

    return jsonify({"success": True, "stickers": stickers})


@user.route("/api/gifs/trending", methods=["GET"])
@login_required
def get_trending_gifs():
    """Get trending GIFs (using GIPHY proxy)"""
    try:
        # Use GIPHY API (you need to add your API key to .env)
        giphy_api_key = os.getenv(
            "GIPHY_API_KEY", "dc6zaTOxFJmzC"
        )  # Default public beta key

        response = requests.get(
            f"https://api.giphy.com/v1/gifs/trending",
            params={"api_key": giphy_api_key, "limit": 20, "rating": "g"},
        )

        if response.status_code == 200:
            data = response.json()
            gifs = []

            for gif in data.get("data", []):
                gifs.append(
                    {
                        "id": gif.get("id"),
                        "title": gif.get("title", "GIF"),
                        "url": gif.get("images", {}).get("fixed_height", {}).get("url"),
                        "preview_url": gif.get("images", {})
                        .get("fixed_height_small", {})
                        .get("url"),
                        "width": gif.get("images", {})
                        .get("fixed_height", {})
                        .get("width"),
                        "height": gif.get("images", {})
                        .get("fixed_height", {})
                        .get("height"),
                    }
                )

            return jsonify({"success": True, "gifs": gifs})
        else:
            return jsonify({"success": False, "error": "Failed to fetch GIFs"})

    except Exception as e:
        print(f"Error fetching GIFs: {e}")
        return jsonify({"success": False, "error": str(e)})


@user.route("/api/gifs/search", methods=["GET"])
@login_required
def search_gifs():
    """Search for GIFs"""
    try:
        query = request.args.get("q", "")
        if not query:
            return jsonify({"success": False, "error": "Search query required"})

        giphy_api_key = os.getenv("GIPHY_API_KEY", "dc6zaTOxFJmzC")

        response = requests.get(
            f"https://api.giphy.com/v1/gifs/search",
            params={"api_key": giphy_api_key, "q": query, "limit": 20, "rating": "g"},
        )

        if response.status_code == 200:
            data = response.json()
            gifs = []

            for gif in data.get("data", []):
                gifs.append(
                    {
                        "id": gif.get("id"),
                        "title": gif.get("title", query),
                        "url": gif.get("images", {}).get("fixed_height", {}).get("url"),
                        "preview_url": gif.get("images", {})
                        .get("fixed_height_small", {})
                        .get("url"),
                    }
                )

            return jsonify({"success": True, "gifs": gifs})
        else:
            return jsonify({"success": False, "error": "Failed to search GIFs"})

    except Exception as e:
        print(f"Error searching GIFs: {e}")
        return jsonify({"success": False, "error": str(e)})


def get_visible_posts_optimized(user_id, cursor=None, limit=10):
    """Get posts visible to the user with pagination support"""
    from sqlalchemy import text

    # Simple query to get post IDs with pagination
    # Get limit+1 to check if there are more posts
    query = text(
        """
        SELECT p.id 
        FROM posts p
        WHERE p.author_id NOT IN (
            -- Users blocked by current user
            SELECT blocked_id 
            FROM user_blocks 
            WHERE blocker_id = :user_id
            UNION
            -- Users who blocked current user
            SELECT blocker_id 
            FROM user_blocks 
            WHERE blocked_id = :user_id
        )
        {cursor_clause}
        ORDER BY p.created_at DESC
        LIMIT :limit + 1  -- Get one extra to check if there are more
    """.format(
            cursor_clause="AND p.id < :cursor" if cursor else ""
        )
    )

    params = {"user_id": user_id, "limit": limit}
    if cursor:
        params["cursor"] = cursor

    result = db.session.execute(query, params)
    rows = result.fetchall()

    # Check if we have more posts than requested
    has_more = len(rows) > limit

    # Take only the requested limit (slice the results)
    post_ids = [row[0] for row in rows[:limit]]

    # Get next cursor (ID of the last post for next page)
    next_cursor = post_ids[-1] if post_ids else None

    # Fetch posts with relationships
    posts = []
    if post_ids:
        posts = (
            Post.query.options(
                joinedload(Post.author),
                joinedload(Post.comments).joinedload(Comment.author),
                joinedload(Post.likes),
                joinedload(Post.shared_post).joinedload(Post.author),
            )
            .filter(Post.id.in_(post_ids))
            .order_by(Post.created_at.desc())
            .all()
        )

    return posts, next_cursor, has_more


# Add this temporarily to see query performance

# ===== OPTIMIZED HELPER FUNCTIONS =====


def get_posts_with_pagination(user_id, cursor=None, limit=10):
    """
    Optimized function to get posts with pagination
    """
    # Get blocked users in a separate query
    user = User.query.options(
        joinedload(User.blocked_users), joinedload(User.blocked_by)
    ).get(user_id)

    blocked_ids = {u.id for u in user.blocked_users}
    blocked_ids.update(u.id for u in user.blocked_by)

    # Build posts query
    query = Post.query.options(
        joinedload(Post.author),
        joinedload(Post.comments).joinedload(Comment.author),
        joinedload(Post.shared_post).joinedload(Post.author),
    ).filter(
        ~Post.author_id.in_(list(blocked_ids))
    )  # Convert to list for IN clause

    if cursor:
        query = query.filter(Post.id < cursor)

    # Get posts and count likes efficiently
    posts = query.order_by(Post.created_at.desc()).limit(limit + 1).all()

    # Prefetch likes count in batch
    if posts:
        post_ids = [p.id for p in posts]

        # Single query to get all likes counts
        from sqlalchemy import select, func

        likes_query = (
            select(Like.post_id, func.count(Like.id).label("likes_count"))
            .where(Like.post_id.in_(post_ids))
            .group_by(Like.post_id)
        )

        likes_counts = {
            row[0]: row[1] for row in db.session.execute(likes_query).fetchall()
        }

        # Attach likes count to each post
        for post in posts:
            post.likes_count = likes_counts.get(post.id, 0)

    # Check if there are more posts
    has_more = len(posts) > limit
    posts = posts[:limit]
    next_cursor = posts[-1].id if posts else None

    return posts, next_cursor, has_more


def get_user_friends(user_id):
    """
    Optimized function to get user's friends without the warning
    """
    # Get blocked users
    user = User.query.get(user_id)
    blocked_ids = {u.id for u in user.blocked_users}
    blocked_ids.update(u.id for u in user.blocked_by)

    # Fix the SQLAlchemy warning by using explicit select
    from sqlalchemy import select

    # Create explicit subqueries instead of using .subquery() directly
    friends_as_user = select(friendship.c.friend_id).where(
        friendship.c.user_id == user_id
    )

    friends_as_friend = select(friendship.c.user_id).where(
        friendship.c.friend_id == user_id
    )

    # Combine using union_all with scalar_subquery
    friend_ids_query = friends_as_user.union_all(friends_as_friend).scalar_subquery()

    # Main query
    friends = (
        User.query.filter(User.id.in_(friend_ids_query))
        .filter(~User.id.in_(list(blocked_ids)))
        .all()
    )

    return friends


def get_friend_suggestions(user_id):
    """
    Optimized function to get friend suggestions
    """
    # Get blocked users
    user = User.query.get(user_id)
    blocked_ids = {u.id for u in user.blocked_users}
    blocked_ids.update(u.id for u in user.blocked_by)

    # Get friend IDs using explicit select
    from sqlalchemy import select

    friends_as_user = select(friendship.c.friend_id).where(
        friendship.c.user_id == user_id
    )

    friends_as_friend = select(friendship.c.user_id).where(
        friendship.c.friend_id == user_id
    )

    friend_ids_query = friends_as_user.union_all(friends_as_friend).scalar_subquery()

    # Get suggestions (not friends, not blocked, not self)
    eligible_users = (
        User.query.filter(User.id != user_id)
        .filter(~User.id.in_(friend_ids_query))
        .filter(~User.id.in_(list(blocked_ids)))
    )

    # Get count and random suggestions efficiently
    count = eligible_users.count()

    if count <= 3:
        return eligible_users.all()

    # Get 3 random users using OFFSET method (more efficient than ORDER BY RANDOM())
    offset = random.randint(0, count - 3)
    return eligible_users.offset(offset).limit(3).all()


# ===== CACHE CLEARING ON POST CREATION =====


@user.route("/clear_dashboard_cache", methods=["POST"])
@login_required
def clear_dashboard_cache():
    """Clear dashboard cache when user creates a new post"""
    safe_cache_delete(f"user_dashboard_{current_user.id}")
    return jsonify({"success": True})


# @user.route("/user_dashboard", methods=["GET", "POST"])
# @login_required
# def user_dashboard():
#     if request.method == "POST":
#         # Handle post creation here
#         post_content = request.form.get("post_content")
#         media_file = request.files.get("media")

#         if post_content or (media_file and media_file.filename != ""):
#             image_url = None
#             video_url = None

#             if (
#                 media_file
#                 and media_file.filename != ""
#                 and allowed_file(media_file.filename)
#             ):
#                 try:
#                     resource_type = "auto"
#                     if media_file.content_type.startswith("video"):
#                         resource_type = "video"

#                     result = cloudinary.uploader.upload(
#                         media_file,
#                         folder="kimbela/posts",
#                         resource_type=resource_type,
#                         transformation=[
#                             {"width": 800, "crop": "limit"},
#                             {"quality": "auto", "fetch_format": "auto"},
#                         ],
#                     )

#                     if media_file.content_type.startswith("video"):
#                         video_url = result["secure_url"]
#                     else:
#                         image_url = result["secure_url"]

#                 except Exception as e:
#                     print(f"Media upload error: {e}")
#                     flash("Failed to upload media.", "danger")

#             # Create post
#             new_post = Post(
#                 content=post_content or "",
#                 image=image_url,
#                 video=video_url,
#                 author_id=current_user.id,
#                 created_at=utcnow(),
#             )
#             db.session.add(new_post)
#             db.session.commit()
#             flash("Post created!", "success")

#         return redirect(url_for("user.user_dashboard"))

#     # ====== OPTIMIZED GET REQUEST ======

#     # Get cursor for infinite scroll (last post ID)
#     cursor = request.args.get("cursor", type=int)
#     limit = request.args.get("limit", 10, type=int)

#     # Get current user's blocked users IDs
#     blocked_user_ids = [user.id for user in current_user.blocked_users]
#     blocker_ids = [user.id for user in current_user.blocked_by]

#     # Build posts query with proper relationships eager loaded
#     # Only load relationships that actually exist in your Post model
#     posts_query = Post.query.options(
#         joinedload(Post.author),  # Eager load author
#         joinedload(Post.comments).joinedload(
#             Comment.author
#         ),  # Eager load comments with their authors
#         # Remove joinedload(Post.likes) if it's not a relationship
#         # Remove joinedload(Post.post_reactions) if it's not a relationship
#     )

#     # Filter out posts from blocked users and users who blocked current user
#     posts_query = posts_query.filter(
#         ~Post.author_id.in_(blocked_user_ids), ~Post.author_id.in_(blocker_ids)
#     )

#     # Apply cursor-based pagination
#     if cursor:
#         # For infinite scroll: get posts older than the cursor
#         posts_query = posts_query.filter(Post.id < cursor)

#     # Order and limit
#     posts = posts_query.order_by(Post.created_at.desc()).limit(limit).all()

#     # Get next cursor (ID of the last post for next page)
#     next_cursor = posts[-1].id if posts else None

#     # Check if there are more posts
#     if posts:
#         has_more = (
#             Post.query.filter(
#                 Post.id < posts[-1].id,
#                 ~Post.author_id.in_(blocked_user_ids),
#                 ~Post.author_id.in_(blocker_ids),
#             ).count()
#             > 0
#         )
#     else:
#         has_more = False

#     # 2. OPTIMIZED FRIENDS QUERY
#     # Get IDs of current user's friends
#     friend_ids = (
#         db.session.query(friendship.c.friend_id)
#         .filter(friendship.c.user_id == current_user.id)
#         .union_all(
#             db.session.query(friendship.c.user_id).filter(
#                 friendship.c.friend_id == current_user.id
#             )
#         )
#         .all()
#     )

#     friend_ids = [fid[0] for fid in friend_ids] if friend_ids else []

#     # Get actual friend objects (excluding blocked users)
#     if friend_ids:
#         friends = User.query.filter(
#             User.id.in_(friend_ids),
#             ~User.id.in_(blocked_user_ids),
#             ~User.id.in_(blocker_ids),
#         ).all()
#     else:
#         friends = []

#     # 3. OPTIMIZED SUGGESTIONS (Non-friends)
#     # Get users who are not friends, not blocked, and not blocking
#     non_friend_query = User.query.filter(
#         User.id != current_user.id,
#         ~User.id.in_(friend_ids) if friend_ids else True,
#         ~User.id.in_(blocked_user_ids),
#         ~User.id.in_(blocker_ids),
#     )

#     # Get only 3 random suggestions
#     random_five = non_friend_query.order_by(db.func.random()).limit(3).all()

#     # If this is an AJAX request for infinite scroll, return JSON
#     if request.headers.get("X-Requested-With") == "XMLHttpRequest":
#         # Render posts as HTML
#         posts_html = render_template(
#             "_posts_partial.html", posts=posts, current_user=current_user
#         )

#         return jsonify(
#             {
#                 "success": True,
#                 "posts": posts_html,
#                 "next_cursor": next_cursor,
#                 "has_more": has_more,
#                 "count": len(posts),
#             }
#         )

#     # Regular request - render full page
#     return render_template(
#         "user_dashboard.html",
#         initial_posts=posts,  # Initial batch of posts
#         next_cursor=next_cursor,
#         has_more=has_more,
#         current_user=current_user,
#         friends=friends,
#         random_five=random_five,
#         csrf_token=generate_csrf(),
#     )


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


@user.route("/repost/<post_identifier>", methods=["POST"])
@login_required
def repost_post(post_identifier):
    original_post = resolve_post_by_identifier(post_identifier)

    existing_repost = Post.query.filter_by(
        author_id=current_user.id,
        shared_post_id=original_post.id,
        share_type="repost",
    ).first()
    if existing_repost:
        return jsonify(success=False, error="You already reposted this post."), 400

    new_post = Post(
        content="",
        author_id=current_user.id,
        shared_post_id=original_post.id,
        share_type="repost",
    )
    db.session.add(new_post)

    if original_post.author_id != current_user.id:
        original_post.author.create_notification(
            actor=current_user,
            notification_type=NotificationType.POST_SHARE,
            entity_id=original_post.id,
            entity_type="post",
        )

    db.session.commit()
    safe_cache_delete(f"user_dashboard_{current_user.id}")
    safe_cache_delete(f"posts_feed_{current_user.id}")
    return jsonify(success=True, post_id=new_post.id, post_public_id=new_post.public_id)


@user.route("/share_post/<post_identifier>", methods=["POST"])
@login_required
def share_post(post_identifier):
    original_post = resolve_post_by_identifier(post_identifier)
    payload = request.get_json(silent=True) or request.form
    content = (payload.get("content") or "").strip()

    existing_share = Post.query.filter_by(
        author_id=current_user.id,
        shared_post_id=original_post.id,
        share_type="share",
    ).first()
    if existing_share:
        return jsonify(success=False, error="You already shared this post."), 400

    new_post = Post(
        content=content,
        author_id=current_user.id,
        shared_post_id=original_post.id,
        share_type="share",
    )
    db.session.add(new_post)

    if original_post.author_id != current_user.id:
        original_post.author.create_notification(
            actor=current_user,
            notification_type=NotificationType.POST_SHARE,
            entity_id=original_post.id,
            entity_type="post",
        )

    db.session.commit()
    safe_cache_delete(f"user_dashboard_{current_user.id}")
    safe_cache_delete(f"posts_feed_{current_user.id}")
    return jsonify(success=True, post_id=new_post.id, post_public_id=new_post.public_id)


# Delete Post
@user.route("/delete_post/<int:post_id>", methods=["POST"])
@login_required
@csrf.exempt
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
        return jsonify(success=False, error="Comment cannot be empty"), 400

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
        success=True,
        comment={
            "id": comment.id,
            "name": f"{current_user.first_name} {current_user.last_name}",
            "avatar": current_user.profile_pic
            or url_for("static", filename="assets/img/default-avatar.png"),
            "content": content,
            "created_at": comment.created_at.isoformat(),
            "created_at_formatted": comment.created_at.strftime(
                "%b %d, %Y at %I:%M %p"
            ),
            "created_at_short": comment.created_at.strftime("%b %d, %H:%M"),
        },
    )


@user.route("/get_comments/<int:post_id>")
@login_required
def get_comments(post_id):
    try:
        limit = request.args.get("limit", 20, type=int)

        # Get all comments or limit based on request
        if limit == 0:  # 0 means get all
            comments = (
                Comment.query.filter_by(post_id=post_id)
                .order_by(Comment.created_at.desc())
                .all()
            )
        else:
            comments = (
                Comment.query.filter_by(post_id=post_id)
                .order_by(Comment.created_at.desc())
                .limit(limit)
                .all()
            )

        comments_data = []
        for comment in comments:
            author = comment.author
            comments_data.append(
                {
                    "id": comment.id,
                    "content": comment.content,
                    "created_at": comment.created_at.strftime("%I:%M %p"),
                    "author_id": author.id,
                    "author_name": author.full_name,
                    "avatar": author.profile_pic
                    or url_for("static", filename="assets/img/default-avatar.png"),
                }
            )

        return jsonify({"comments": comments_data})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@user.route("/debug/notification_status")
@login_required
def debug_notification_status():
    """Check read status of notifications"""
    _require_debug_access()
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
    allowed_extensions = {"png", "jpg", "jpeg", "gif", "webp", "bmp"}
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
# In your user.py, update the add_friend route:


@user.route("/add_friend/<int:user_id>", methods=["POST"])
@login_required
def add_friend(user_id):
    """Add a friend"""
    try:
        target_user = User.query.get(user_id)

        if not target_user:
            return jsonify({"success": False, "error": "User not found"}), 404

        if target_user.id == current_user.id:
            return jsonify(
                {"success": False, "error": "You cannot add yourself as a friend"}
            )

        if current_user.is_friend_with(target_user):
            return jsonify({"success": False, "error": "Already friends"})

        existing_request = FriendRequest.query.filter(
            (
                (FriendRequest.sender_id == current_user.id)
                & (FriendRequest.receiver_id == target_user.id)
            )
            | (
                (FriendRequest.sender_id == target_user.id)
                & (FriendRequest.receiver_id == current_user.id)
            )
        ).first()

        if existing_request:
            return jsonify({"success": False, "error": "Friend request already sent"})

        # Create friend request
        friend_request = FriendRequest(
            sender_id=current_user.id,
            receiver_id=target_user.id,
            status="pending",
            created_at=utcnow(),
        )

        db.session.add(friend_request)

        # IMPORTANT: Commit FIRST to get the friend_request.id
        db.session.commit()

        # NOW create notification
        notification = Notification(
            user_id=target_user.id,
            actor_id=current_user.id,
            type="friend_request",
            message=f"{current_user.full_name} sent you a friend request",
            entity_id=friend_request.id,  # Now this has a value
            created_at=utcnow(),
            is_read=False,
        )

        db.session.add(notification)
        db.session.commit()

        return jsonify({"success": True, "message": "Friend request sent successfully"})

    except Exception as e:
        db.session.rollback()
        print(f"Error adding friend: {e}")
        import traceback

        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@user.route("/cancel_friend_request/<int:user_id>", methods=["POST"])
@login_required
def cancel_friend_request(user_id):
    """Cancel a pending friend request"""
    try:
        target_user = User.query.get(user_id)

        if not target_user:
            return jsonify({"success": False, "error": "User not found"}), 404

        # Find the pending friend request
        friend_request = FriendRequest.query.filter(
            (FriendRequest.sender_id == current_user.id)
            & (FriendRequest.receiver_id == target_user.id)
            & (FriendRequest.status == "pending")
        ).first()

        if not friend_request:
            return jsonify(
                {"success": False, "error": "No pending friend request found"}
            )

        # Delete the friend request
        db.session.delete(friend_request)

        # Also delete the notification if it exists
        notification = Notification.query.filter(
            Notification.actor_id == current_user.id,
            Notification.user_id == target_user.id,
            Notification.type == "friend_request",
            Notification.entity_id == friend_request.id,
        ).first()

        if notification:
            db.session.delete(notification)

        db.session.commit()

        return jsonify({"success": True, "message": "Friend request cancelled"})

    except Exception as e:
        db.session.rollback()
        print(f"Error cancelling friend request: {e}")
        import traceback

        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@user.route("/api/ads/sponsored")
def get_sponsored_ads():
    try:
        from datetime import datetime

        current_time = utcnow()

        print(f"🔍 [DEBUG] Loading sponsored ads at: {current_time}")

        # Query for active ads within date range
        active_ads = (
            AdCampaign.query.filter(
                AdCampaign.status == "active",
                AdCampaign.start_date <= current_time,
                AdCampaign.end_date >= current_time,
            )
            .filter(
                or_(
                    AdCampaign.placement == None,
                    AdCampaign.placement == "sponsored",
                )
            )
            .all()
        )

        print(f"🔍 [DEBUG] Found {len(active_ads)} active ads")

        # Log each ad for debugging
        for ad in active_ads:
            print(f"  - ID: {ad.id}, Title: '{ad.title}'")
            print(f"    Status: {ad.status}, Budget: {ad.budget}")
            print(f"    Start: {ad.start_date}, End: {ad.end_date}")
            print(f"    Image field exists: {hasattr(ad, 'image')}")
            print(f"    User ID: {ad.user_id}")

        ads_data = []
        for ad in active_ads:
            # Get advertiser name from user relationship
            advertiser_name = "Sponsored Partner"

            # Try to get user info
            if hasattr(ad, "user"):
                user = ad.user
                if user:
                    if hasattr(user, "business_name") and user.business_name:
                        advertiser_name = user.business_name
                    elif hasattr(user, "full_name") and user.full_name:
                        advertiser_name = user.full_name
                    elif hasattr(user, "username"):
                        advertiser_name = user.username

            # Get image URL - your field is called 'image', not 'image_url'
            image_url = (
                ad.image
                if hasattr(ad, "image") and ad.image
                else "https://via.placeholder.com/600x300/4F46E5/FFFFFF?text=Sponsored+Ad"
            )

            # Get CTA URL - your field is called 'target_url'
            cta_url = (
                ad.target_url if hasattr(ad, "target_url") and ad.target_url else "#"
            )

            # Get CTA text - your field is called 'call_to_action'
            cta_text = (
                ad.call_to_action
                if hasattr(ad, "call_to_action") and ad.call_to_action
                else "Learn More"
            )

            ads_data.append(
                {
                    "id": ad.id,
                    "title": ad.title or "Special Offer",
                    "description": ad.description or "Discover amazing opportunities!",
                    "image_url": image_url,
                    "advertiser_name": advertiser_name,
                    "cta_url": cta_url,
                    "cta_text": cta_text,
                    "budget": float(ad.budget or 0),
                    "clicks": ad.clicks or 0,
                    "impressions": ad.impressions or 0,
                    "start_date": ad.start_date.isoformat() if ad.start_date else None,
                    "end_date": ad.end_date.isoformat() if ad.end_date else None,
                }
            )

        print(f"✅ [DEBUG] Returning {len(ads_data)} ads")

        return jsonify(
            {
                "success": True,
                "ads": ads_data,
                "count": len(ads_data),
                "timestamp": current_time.isoformat(),
            }
        )

    except Exception as e:
        print(f"❌ [ERROR] in get_sponsored_ads: {str(e)}")
        import traceback

        traceback.print_exc()
        return jsonify({"success": False, "error": str(e), "ads": []}), 500


@user.route("/api/ads/<int:ad_id>/impression", methods=["POST"])
def track_ad_impression(ad_id):
    try:
        ad = AdCampaign.query.get(ad_id)
        if ad:
            # Initialize if None
            if ad.impressions is None:
                ad.impressions = 0
            ad.impressions += 1
            db.session.commit()
            print(f"📊 Tracked impression for ad {ad_id}. Total: {ad.impressions}")
            return jsonify({"success": True})
        return jsonify({"success": False, "error": "Ad not found"}), 404
    except Exception as e:
        print(f"❌ Error tracking impression: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@user.route("/api/ads/<int:ad_id>/click", methods=["POST"])
def track_ad_click(ad_id):
    try:
        ad = AdCampaign.query.get(ad_id)
        if ad:
            # Initialize if None
            if ad.clicks is None:
                ad.clicks = 0
            ad.clicks += 1
            db.session.commit()
            print(f"📊 Tracked click for ad {ad_id}. Total: {ad.clicks}")
            return jsonify({"success": True})
        return jsonify({"success": False, "error": "Ad not found"}), 404
    except Exception as e:
        print(f"❌ Error tracking click: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@user.route("/get_user_profile/<int:user_id>")
@login_required
def get_user_profile(user_id):
    user = User.query.get_or_404(user_id)

    # DEBUG: Print everything about religion
    print(f"=== DEBUG for user_id: {user_id} ===")
    print(f"User religion value from DB: {user.religion}")
    print(f"User religion type: {type(user.religion)}")
    print(f"Religion is None: {user.religion is None}")
    print(f"Religion == '': {user.religion == ''}")

    # FIXED: Use the User model's existing method
    friend_status = current_user.get_friend_request_status(
        user_id
    )  # 'none', 'sent', 'received', or 'friends'

    # Create the response dictionary
    response_data = {
        "first_name": user.first_name,
        "last_name": user.last_name,
        # "email": user.email,
        "profile_pic": user.profile_pic
        or url_for("static", filename="assets/img/default-avatar.png"),
        "cover_pic": user.cover_pic,
        "bio": user.bio,
        "city": user.city,
        "country": user.country,
        "state": user.state,
        "gender": user.gender,
        "religion": user.religion,  # This should be included even if None
        "dob": user.dob.isoformat() if user.dob else None,
        # "phone_number": user.phone_number,
        "marital_status": user.marital_status,
        "occupation": user.occupation,
        "educational_level": user.educational_level,
        "ethnicity": user.ethnicity,
        "interests": user.interests,
        "profile_url": url_for("user.view_profile", user_identifier=user.public_id),
        "friends_count": user.friends.count(),
        "friend_status": friend_status,  # 'none', 'sent', 'received', or 'friends'
    }

    # DEBUG: Print the response data
    print(f"Response data keys: {response_data.keys()}")
    print(f"Response data religion value: {response_data.get('religion')}")
    print("=== END DEBUG ===\n")

    return jsonify(response_data)


@user.route("/notifications")
@login_required
def get_notifications():
    # get 5 notifications
    notifications = (
        Notification.query.filter_by(user_id=current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(10)
        .all()
    )

    result = []
    for n in notifications:
        notification_data = {
            "id": n.id,
            "type": n.type,
            "message": n.message,
            "is_read": n.is_read,
            "created_at": n.created_at.isoformat(),
            "entity_id": n.entity_id,
            "actor_id": n.actor_id,  # Add actor_id (the sender's ID)
        }

        # Add actor information if it exists
        if n.actor_id:
            actor = User.query.get(n.actor_id)
            if actor:
                notification_data["actor"] = {
                    "id": actor.id,
                    "name": f"{actor.first_name} {actor.last_name}",
                    "avatar": actor.profile_pic
                    or url_for("static", filename="assets/img/default-avatar.png"),
                }

        result.append(notification_data)

    return jsonify(result)


@user.route("/check_friend_status/<int:user_id>")
@login_required
def check_friend_status(user_id):
    """Check the friend request status between current user and target user"""
    friend_status = current_user.get_friend_request_status(user_id)
    return jsonify({"status": friend_status})


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


from flask_caching import Cache
from datetime import datetime, timedelta
from flask import current_app
from sqlalchemy import text

# Initialize cache (if not already done in extensions.py)
cache = Cache()


@user.route("/notifications/count")
@login_required
def get_unread_count():
    """Get unread notification count - OPTIMIZED"""
    try:
        # Use raw SQL for maximum performance
        from sqlalchemy import text

        query = text(
            """
            SELECT COUNT(*) as count 
            FROM notifications 
            WHERE user_id = :user_id 
            AND is_read = FALSE
            AND created_at > NOW() - INTERVAL '30 days'
        """
        )

        result = db.session.execute(query, {"user_id": current_user.id})
        count = result.fetchone()[0] or 0

        return jsonify({"count": count})

    except Exception as e:
        print(f"Error in get_unread_count: {e}")
        return jsonify({"count": 0})


@user.route("/debug/notifications")
@login_required
def debug_notifications():
    """Debug notifications to see what's wrong"""
    _require_debug_access()
    from sqlalchemy import text

    user_id = current_user.id

    # Check database structure
    query = text(
        """
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'notifications'
    """
    )

    columns = db.session.execute(query).fetchall()

    # Check actual notifications
    notifications = (
        Notification.query.filter_by(user_id=user_id)
        .order_by(Notification.created_at.desc())
        .limit(10)
        .all()
    )

    # Check if any are unread
    unread = Notification.query.filter_by(user_id=user_id, is_read=False).count()

    return jsonify(
        {
            "user_id": user_id,
            "notification_columns": [dict(c) for c in columns],
            "total_notifications": Notification.query.filter_by(
                user_id=user_id
            ).count(),
            "unread_notifications": unread,
            "recent_notifications": [
                {
                    "id": n.id,
                    "type": n.type,
                    "message": n.message,
                    "is_read": n.is_read,
                    "created_at": n.created_at.isoformat(),
                    "actor_id": n.actor_id,
                }
                for n in notifications
            ],
            "has_is_read_column": any(c[0] == "is_read" for c in columns),
            "has_read_column": any(c[0] == "read" for c in columns),
        }
    )


@user.route("/debug/posts")
@login_required
def debug_posts():
    """Debug posts to see why they're not appearing"""
    _require_debug_access()

    # Check your Post model structure
    from sqlalchemy import text

    query = text(
        """
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'posts'
        ORDER BY ordinal_position
    """
    )

    columns = db.session.execute(query).fetchall()

    # Check recent posts
    recent_posts = Post.query.order_by(Post.created_at.desc()).limit(5).all()

    # Check YOUR recent posts
    my_posts = (
        Post.query.filter_by(author_id=current_user.id)
        .order_by(Post.created_at.desc())
        .limit(5)
        .all()
    )

    # Check blocked users
    blocked_ids = [u.id for u in current_user.blocked_users]
    blocker_ids = [u.id for u in current_user.blocked_by]

    return jsonify(
        {
            "post_columns": [dict(c) for c in columns],
            "my_recent_posts": [
                {
                    "id": p.id,
                    "content": (
                        p.content[:50] + "..."
                        if p.content and len(p.content) > 50
                        else p.content
                    ),
                    "author_id": p.author_id,
                    "created_at": p.created_at.isoformat(),
                    "has_image": bool(p.image),
                    "has_video": bool(p.video),
                }
                for p in my_posts
            ],
            "recent_global_posts": [
                {
                    "id": p.id,
                    "content": (
                        p.content[:50] + "..."
                        if p.content and len(p.content) > 50
                        else p.content
                    ),
                    "author_id": p.author_id,
                    "author_name": p.author.full_name if p.author else "Unknown",
                    "created_at": p.created_at.isoformat(),
                }
                for p in recent_posts
            ],
            "blocked_users": blocked_ids,
            "blocked_by": blocker_ids,
            "post_count": Post.query.count(),
            "my_post_count": Post.query.filter_by(author_id=current_user.id).count(),
        }
    )


@user.route("/get_blocked_users")
@login_required
def get_blocked_users():
    """Return blocked users with display details"""
    try:
        return jsonify(current_user.get_blocked_users_with_details())
    except Exception as e:
        print(f"Error fetching blocked users: {e}")
        return jsonify([]), 500


@user.route("/block_user/<int:user_id>", methods=["POST"])
@login_required
def block_user(user_id):
    """Block a user from interacting/seeing content"""
    if user_id == current_user.id:
        return jsonify({"success": False, "error": "You cannot block yourself"}), 400

    target_user = User.query.get_or_404(user_id)

    try:
        current_user.block(target_user)
        safe_cache_delete(f"user_dashboard_{current_user.id}")
        safe_cache_delete(f"user_dashboard_{target_user.id}")
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        print(f"Error blocking user {user_id}: {e}")
        return jsonify({"success": False, "error": "Failed to block user"}), 500


@user.route("/unblock_user/<int:user_id>", methods=["POST"])
@login_required
def unblock_user(user_id):
    """Unblock a previously blocked user"""
    if user_id == current_user.id:
        return jsonify({"success": False, "error": "Invalid user"}), 400

    target_user = User.query.get_or_404(user_id)

    try:
        current_user.unblock(target_user)
        safe_cache_delete(f"user_dashboard_{current_user.id}")
        safe_cache_delete(f"user_dashboard_{target_user.id}")
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        print(f"Error unblocking user {user_id}: {e}")
        return jsonify({"success": False, "error": "Failed to unblock user"}), 500


def compute_notification_count(user_id):
    """
    Efficiently compute unread notification count
    """
    from models import Notification  # Import here to avoid circular imports

    # Use direct SQL count for maximum performance
    count = (
        db.session.query(db.func.count(Notification.id))
        .filter(
            Notification.user_id == user_id,
            Notification.is_read == False,
            # Add time filter if you want to limit to recent notifications
            # Notification.created_at >= utcnow() - timedelta(days=30)
        )
        .scalar()
    )

    return count or 0


# ===== REAL-TIME UPDATES WITH SOCKET.IO =====
@user.route("/notifications")
@login_required
def notifications():
    """
    Get actual notifications (not just count) with pagination
    """
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    notifications = (
        Notification.query.filter_by(user_id=current_user.id)
        .order_by(Notification.created_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    # Mark as read when viewed (optional)
    if page == 1:  # Only mark as read when viewing first page
        unread_ids = [n.id for n in notifications.items if not n.read]
        if unread_ids:
            Notification.query.filter(Notification.id.in_(unread_ids)).update(
                {"read": True}, synchronize_session=False
            )
            db.session.commit()

            # Clear the cached count
            safe_cache_delete(f"notification_count_{current_user.id}")

    # Return HTML or JSON based on request
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify(
            {
                "notifications": [n.to_dict() for n in notifications.items],
                "total": notifications.total,
                "pages": notifications.pages,
                "current_page": page,
            }
        )

    return render_template("notifications.html", notifications=notifications)


# ===== SOCKET.IO EVENT FOR REAL-TIME UPDATES =====
@socketio.on("request_notification_count")
def handle_notification_count_request(data):
    """
    Handle real-time notification count requests via WebSocket
    """
    if not current_user.is_authenticated:
        return

    user_id = current_user.id
    cache_key = f"notification_count_{user_id}"

    # Get count (from cache or fresh)
    count = cache.get(cache_key)
    if count is None:
        count = compute_notification_count(user_id)
        cache.set(cache_key, count, timeout=30)

    # Send count to the specific user
    emit("notification_count_update", {"count": count}, room=f"user_{user_id}")


# ===== CACHE INVALIDATION TRIGGERS =====
def invalidate_notification_cache(user_id):
    """
    Call this whenever a new notification is created or marked read
    """
    cache_key = f"notification_count_{user_id}"
    safe_cache_delete(cache_key)

    # Also emit real-time update via Socket.IO
    socketio.emit(
        "notification_count_update",
        {"count": compute_notification_count(user_id)},
        room=f"user_{user_id}",
    )


# ===== EXAMPLE: TRIGGER CACHE INVALIDATION =====
# Add these to places where notifications change:


# 1. When creating a new notification:
def create_notification(user_id, message, type="info"):
    from models import Notification

    notification = Notification(
        user_id=user_id,
        message=message,
        type=type,
        read=False,
        created_at=utcnow(),
    )
    db.session.add(notification)
    db.session.commit()

    # Invalidate cache
    invalidate_notification_cache(user_id)

    return notification


# 2. When marking all notifications as read:
@user.route("/notifications/mark_all_read", methods=["POST"])
@login_required
def mark_all_read():
    updated = Notification.query.filter_by(user_id=current_user.id, read=False).update(
        {"read": True}, synchronize_session=False
    )

    if updated:
        db.session.commit()
        invalidate_notification_cache(current_user.id)

    return jsonify({"success": True, "marked_read": updated})


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
@login_required
def search():
    query = request.args.get("q", "").strip()
    if not query or len(query) < 2:
        return jsonify({"users": [], "posts": []})

    blocked_ids = {u.id for u in current_user.blocked_users}
    blocked_ids.update(u.id for u in current_user.blocked_by)

    # Search users (exclude current user)
    users = (
        User.query.filter(
            db.and_(
                User.id != current_user.id,  # Exclude current user
                ~User.id.in_(list(blocked_ids)),
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
        Post.query.filter(
            Post.content.ilike(f"%{query}%"),
            ~Post.author_id.in_(list(blocked_ids)),
        )
        .join(User)
        .limit(10)
        .all()
    )

    users_data = [
        {
            "id": user.id,
            "public_id": user.public_id,
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
            "public_id": post.public_id,
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
            "public_id": post.public_id,
            "content": post.content,
            "image": post.image,
            "video": post.video,
            "location": post.location,
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
        current_user.last_seen = utcnow()
        # Consider user online if seen < 5 min ago
        current_user.is_online = (
            utcnow() - current_user.last_seen
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
        "Seventh-day Adventist",
        "Jehovah's Witness",
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
            current_user.state = request.form.get("state", current_user.state)
            current_user.gender = request.form.get("gender", current_user.gender)
            current_user.marital_status = request.form.get(
                "marital_status", current_user.marital_status
            )
            current_user.interests = request.form.get(
                "interests", current_user.interests
            )
            current_user.bio = request.form.get("bio", current_user.bio)
            current_user.religion = request.form.get("religion", current_user.religion)
            current_user.educational_level = request.form.get(
                "educational_level", current_user.educational_level
            )
            current_user.ethnicity = request.form.get(
                "ethnicity", current_user.ethnicity
            )

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
        Post.query.options(
            joinedload(Post.author),
            joinedload(Post.shared_post).joinedload(Post.author),
            joinedload(Post.comments).joinedload(Comment.author),
            joinedload(Post.likes),
        )
        .filter_by(author_id=current_user.id)
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
        educational_levels=EDUCATIONAL_LEVELS,
        religions=RELIGIONS,
        ethnicities=ETHNICITIES,
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
    return render_template("terms-of-service.html")


@user.route("/privacy", methods=["GET", "POST"])
def privacy():
    return render_template("privacy.html")


@user.route("/community-guidelines", methods=["GET", "POST"])
def community_guidelines():
    return render_template("community-guidelines.html")


@user.route("/acceptable-use-policy", methods=["GET", "POST"])
def acceptable_use_policy():
    return render_template("acceptable-use-policy.html")


@user.route("/marketplace-seller-terms", methods=["GET", "POST"])
def marketplace_seller_terms():
    return render_template("marketplace-seller-terms.html")


@user.route("/refund-billing-policy", methods=["GET", "POST"])
def refund_billing_policy():
    return render_template("refund-billing-policy.html")


@user.route("/cookie-policy", methods=["GET", "POST"])
def cookie_policy():
    return render_template("cookie-policy.html")


@user.route("/safety-tips", methods=["GET", "POST"])
def safety_tips():
    return render_template("safety-tips.html")


@user.route("/dispute-reporting", methods=["GET", "POST"])
def dispute_reporting():
    return render_template("dispute-reporting.html")


@user.route("/disclaimer", methods=["GET", "POST"])
def disclaimer():
    return render_template("disclaimer.html")


@user.route("/faq", methods=["GET", "POST"])
def faq():
    return render_template("faq.html")


@user.route("/get_user_groups")
@login_required
def get_user_groups():
    """Get all groups for the dropdown with membership status"""
    try:
        print(f"🔍 Fetching groups for user: {current_user.id}")
        groups_data = get_groups_data_for_user(current_user.id)
        print(f"🔍 Returning {len(groups_data)} groups")
        return jsonify(groups_data)

    except Exception as e:
        print(f"❌ ERROR in get_user_groups: {str(e)}")
        import traceback

        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ===== MESSAGING ROUTES =====


@user.route("/api/friends")
@login_required
def get_friends_api():
    """Get friends list for messaging"""
    try:
        friends = []
        for friend in current_user.friends:
            if current_user.can_interact_with(friend):
                friends.append(
                    {
                        "id": friend.id,
                        "name": friend.full_name,
                        "avatar": friend.profile_pic
                        or url_for("static", filename="assets/img/default-avatar.png"),
                        "online": friend.is_online,
                        "unread_count": 0,  # You can implement this later
                    }
                )

        return jsonify(friends)
    except Exception as e:
        print(f"❌ Error getting friends: {e}")
        return jsonify({"error": str(e)}), 500


@user.route("/api/messages/<int:friend_id>")
@login_required
def get_messages_api(friend_id):
    """Get messages between current user and friend"""
    try:
        friend = User.query.get_or_404(friend_id)

        # Check if users are friends
        if not current_user.is_friend_with(friend):
            return jsonify({"error": "You must be friends to message"}), 403

        # Get messages
        messages = (
            Message.query.filter(
                (
                    (Message.sender_id == current_user.id)
                    & (Message.receiver_id == friend_id)
                )
                | (
                    (Message.sender_id == friend_id)
                    & (Message.receiver_id == current_user.id)
                )
            )
            .order_by(Message.timestamp.asc())
            .all()
        )

        # Prepare response
        messages_data = []
        for msg in messages:
            messages_data.append(
                {
                    "id": msg.id,
                    "sender_id": msg.sender_id,
                    "receiver_id": msg.receiver_id,
                    "content": msg.content,
                    "timestamp": msg.timestamp.isoformat(),
                    "status": msg.status,
                    "sender_name": msg.sender.full_name,
                    "sender_avatar": msg.sender.profile_pic
                    or url_for("static", filename="assets/img/default-avatar.png"),
                }
            )

        return jsonify(messages_data)

    except Exception as e:
        print(f"❌ Error getting messages: {e}")
        return jsonify({"error": str(e)}), 500


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
                    "image": group.image
                    or "https://images.unsplash.com/photo-1611262588024-d12430b98920?w=100&h=100&fit=crop",
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
                Group.name.ilike(f"%{search}%"), Group.description.ilike(f"%{search}%")
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
                "is_member": group.members.filter_by(id=current_user.id).first()
                is not None,  # Proper membership check
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

    default_avatar = url_for("static", filename="assets/img/default-avatar.png")

    # Get group posts
    posts = (
        Post.query.filter_by(group_id=group_id)
        .options(
            db.joinedload(Post.author),
            db.joinedload(Post.comments).joinedload(Comment.author),
        )
        .order_by(Post.created_at.desc())
        .all()
    )

    return render_template(
        "group_detail.html",
        group=group,
        is_member=is_member,
        posts=posts,
        current_user=current_user,
        default_avatar=default_avatar,
    )


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


@user.route("/groups")
@login_required
def groups_page():
    """Main groups discovery page"""
    return render_template("groups.html")


@user.route("/groups/<int:group_id>")
@login_required
def group_detail(group_id):
    """Individual group page with posts and interactions"""
    group = Group.query.get_or_404(group_id)
    is_member = current_user in group.members

    default_avatar = url_for("static", filename="assets/img/default-avatar.png")

    # Get posts for this group
    posts = (
        Post.query.filter_by(group_id=group_id).order_by(Post.created_at.desc()).all()
    )

    return render_template(
        "group_detail.html",
        group=group,
        is_member=is_member,
        posts=posts,
        current_user=current_user,
        default_avatar=default_avatar,
    )


@user.route("/groups/create", methods=["GET", "POST"])
@login_required
def create_group():
    """Create a new group"""
    if request.method == "POST":
        try:
            name = request.form.get("name", "").strip()
            description = request.form.get("description", "").strip()
            category = request.form.get("category", "social")
            is_private = request.form.get("is_private") == "true"

            if not name:
                return jsonify({"success": False, "error": "Group name is required"})

            group = Group(
                name=name,
                description=description,
                category=category,
                is_private=is_private,
                created_by=current_user.id,
                member_count=1,
            )

            # Handle group image
            if "image" in request.files:
                file = request.files["image"]
                if file and file.filename and allowed_file(file.filename):
                    try:
                        result = cloudinary.uploader.upload(
                            file,
                            folder="kimbela/groups",
                            transformation=[
                                {"width": 800, "height": 600, "crop": "limit"},
                                {"quality": "auto", "fetch_format": "auto"},
                            ],
                        )
                        group.image = result["secure_url"]
                    except Exception as e:
                        print("Group image upload failed:", e)

            db.session.add(group)

            # Add creator as first member
            group.members.append(current_user)
            db.session.commit()

            return jsonify({"success": True, "group_id": group.id})

        except Exception as e:
            db.session.rollback()
            print("Create group error:", e)
            return jsonify({"success": False, "error": "Failed to create group"})

    return render_template("create_group.html")


@user.route("/groups/<int:group_id>/join", methods=["POST"])
@login_required
def join_group(group_id):
    """Join a group"""
    group = Group.query.get_or_404(group_id)

    if current_user in group.members.all():  # Use .all() to check membership
        return jsonify({"success": False, "error": "Already a member"})

    group.members.append(current_user)
    group.member_count = group.members.count()  # Use .count() instead of len()
    db.session.commit()

    return jsonify({"success": True})


# Fix the leave_group rout
@user.route("/groups/<int:group_id>/leave", methods=["POST"])
@login_required
def leave_group(group_id):
    """Leave a group"""
    group = Group.query.get_or_404(group_id)

    if current_user not in group.members.all():  # Use .all() to check membership
        return jsonify({"success": False, "error": "Not a member"})

    group.members.remove(current_user)
    group.member_count = group.members.count()  # Use .count() instead of len()
    db.session.commit()

    return jsonify({"success": True})


@user.route("/groups/<int:group_id>/post", methods=["POST"])
@login_required
def create_group_post(group_id):
    """Create a post in a group"""
    group = Group.query.get_or_404(group_id)

    if current_user not in group.members:
        return jsonify({"success": False, "error": "Must be a member to post"})

    post_content = request.form.get("post_content", "").strip()
    media_file = request.files.get("media")

    if not post_content and not (media_file and media_file.filename):
        return jsonify({"success": False, "error": "Post content or media is required"})

    if media_file and media_file.filename and not allowed_file(media_file.filename):
        return jsonify(
            {
                "success": False,
                "error": "Unsupported file type. Please upload an image or GIF.",
            }
        )

    try:
        image_url = None
        video_url = None

        if media_file and media_file.filename and allowed_file(media_file.filename):
            filename = media_file.filename.lower()
            if media_file.content_type.startswith("video") or filename.endswith(
                (".mp4", ".mov", ".avi", ".mkv", ".webm")
            ):
                return jsonify(
                    {"success": False, "error": "Video uploads are not allowed."}
                )

            resource_type = "image"

            result = cloudinary.uploader.upload(
                media_file,
                folder="kimbela/groups/posts",
                resource_type=resource_type,
                transformation=[
                    {"width": 800, "crop": "limit"},
                    {"quality": "auto", "fetch_format": "auto"},
                ],
            )

            image_url = result["secure_url"]

        post = Post(
            content=post_content,
            image=image_url,
            video=video_url,
            author_id=current_user.id,
            group_id=group_id,  # Now this will work!
            created_at=utcnow(),
        )

        db.session.add(post)
        db.session.commit()

        return jsonify(
            {
                "success": True,
                "post_id": post.id,
                "message": "Post created successfully!",
            }
        )

    except Exception as e:
        db.session.rollback()
        print("Group post creation error:", e)
        return jsonify({"success": False, "error": "Failed to create post"})


@user.route("/groups/<int:group_id>/posts")
@login_required
def get_group_posts(group_id):
    """Get posts for a group with pagination"""
    page = request.args.get("page", 1, type=int)
    per_page = 10

    posts = (
        Post.query.filter_by(group_id=group_id)
        .order_by(Post.created_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    posts_data = []
    for post in posts.items:
        posts_data.append(
            {
                "id": post.id,
                "content": post.content,
                "image": post.image,
                "video": post.video,
                "created_at": post.created_at.isoformat(),
                "author": {
                    "id": post.author.id,
                    "name": post.author.full_name,
                    "avatar": post.author.profile_pic
                    or url_for("static", filename="assets/img/default-avatar.png"),
                },
                "likes_count": post.likes.count(),
                "comments_count": post.comments.count(),
                "user_has_liked": (
                    current_user.has_liked_post(post.id)
                    if current_user.is_authenticated
                    else False
                ),
            }
        )

    return jsonify(
        {
            "posts": posts_data,
            "has_next": posts.has_next,
            "next_page": posts.next_num if posts.has_next else None,
        }
    )


@user.route("/report_content", methods=["POST"])
@login_required
def report_content():
    """Report a post or comment"""
    data = request.get_json()

    content_type = data.get("content_type")  # 'post' or 'comment'
    content_id = data.get("content_id")
    reason = data.get("reason")
    additional_info = data.get("additional_info", "")

    if not all([content_type, content_id, reason]):
        return jsonify({"success": False, "error": "Missing required fields"})

    # Determine the reported user based on content type
    reported_user_id = None
    if content_type == "post":
        post = Post.query.get(content_id)
        if post:
            reported_user_id = post.author_id
    elif content_type == "comment":
        comment = Comment.query.get(content_id)
        if comment:
            reported_user_id = comment.author_id

    report = ReportedContent(
        reporter_id=current_user.id,
        reported_user_id=reported_user_id,
        content_type=content_type,
        content_id=content_id,
        reason=f"{reason}: {additional_info}".strip() if additional_info else reason,
        status="pending",
    )

    db.session.add(report)
    db.session.commit()

    return jsonify({"success": True, "message": "Content reported successfully"})


@user.route("/groups/all")
@login_required
def get_all_groups():
    """API endpoint to get all groups with filtering"""
    page = request.args.get("page", 1, type=int)
    search = request.args.get("search", "")
    category = request.args.get("category", "")
    privacy = request.args.get("privacy", "")

    query = Group.query.filter_by(is_active=True)

    if search:
        query = query.filter(
            db.or_(
                Group.name.ilike(f"%{search}%"), Group.description.ilike(f"%{search}%")
            )
        )

    if category and category != "all":
        query = query.filter_by(category=category)

    if privacy == "public":
        query = query.filter_by(is_private=False)
    elif privacy == "private":
        query = query.filter_by(is_private=True)

    groups = query.order_by(Group.member_count.desc()).paginate(
        page=page, per_page=20, error_out=False
    )

    groups_data = []
    for group in groups.items:
        groups_data.append(
            {
                "id": group.id,
                "name": group.name,
                "description": group.description,
                "image": group.image,
                "category": group.category,
                "is_private": group.is_private,
                "member_count": group.member_count,
                "created_at": group.created_at.isoformat(),
                "is_member": current_user in group.members,
            }
        )

    return jsonify(groups_data)


@user.route("/groups/<int:group_id>/members")
@login_required
def get_group_members(group_id):
    """Get group members"""
    group = Group.query.get_or_404(group_id)
    page = request.args.get("page", 1, type=int)

    members = group.members.paginate(page=page, per_page=50, error_out=False)

    members_data = []
    for member in members.items:
        members_data.append(
            {
                "id": member.id,
                "name": member.full_name,
                "avatar": member.profile_pic
                or url_for("static", filename="assets/img/default-avatar.png"),
                "is_online": member.is_online,
                "last_seen": member.last_seen.isoformat() if member.last_seen else None,
            }
        )

    return jsonify(
        {
            "members": members_data,
            "has_next": members.has_next,
            "next_page": members.next_num if members.has_next else None,
        }
    )


# Add these routes to your Flask application
@user.route("/edit_post/<int:post_id>", methods=["POST"])
@login_required
def edit_group_post(post_id):
    try:
        post = Post.query.get_or_404(post_id)

        # Check if the current user is the author
        if post.author_id != current_user.id:
            return jsonify({"success": False, "error": "Unauthorized"}), 403

        new_content = request.form.get("post_content")
        if new_content:
            post.content = new_content
            db.session.commit()
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "Content cannot be empty"})

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@user.route("/delete_post/<int:post_id>", methods=["POST"])
@login_required
def delete_group_post(post_id):
    try:
        post = Post.query.get_or_404(post_id)

        # Check if the current user is the author
        if post.author_id != current_user.id:
            return jsonify({"success": False, "error": "Unauthorized"}), 403

        db.session.delete(post)
        db.session.commit()
        return jsonify({"success": True})

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@user.route("/delete_comment/<int:comment_id>", methods=["POST"])
@login_required
def delete_group_comment(comment_id):
    try:
        comment = Comment.query.get_or_404(comment_id)

        # Check if the current user is the author
        if comment.author_id != current_user.id:
            return jsonify({"success": False, "error": "Unauthorized"}), 403

        db.session.delete(comment)
        db.session.commit()
        return jsonify({"success": True})

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@user.route("/get_comments/<int:post_id>")
@login_required
def get_group_comments(post_id):
    try:
        post = Post.query.get_or_404(post_id)
        comments = []

        for comment in post.comments_list:
            comments.append(
                {
                    "id": comment.id,
                    "content": comment.content,
                    "author_name": comment.author.full_name,
                    "author_id": comment.author_id,
                    "avatar": comment.author.profile_pic
                    or url_for("static", filename="assets/img/default-avatar.png"),
                    "created_at": comment.created_at.strftime("%I:%M %p"),
                }
            )

        return jsonify({"comments": comments})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@user.route("/like_post/<int:post_id>", methods=["POST"])
@login_required
def like_group_post(post_id):
    try:
        post = Post.query.get_or_404(post_id)
        liked = post.toggle_like(current_user.id)
        db.session.commit()

        return jsonify(
            {"success": True, "liked": liked, "like_count": len(post.likes_list)}
        )
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@user.route("/add_comment/<int:post_id>", methods=["POST"])
@login_required
def add_group_comment(post_id):
    try:
        data = request.get_json()
        content = data.get("content", "").strip()

        if not content:
            return jsonify({"success": False, "error": "Comment cannot be empty"})

        comment = Comment(content=content, author_id=current_user.id, post_id=post_id)

        db.session.add(comment)
        db.session.commit()

        return jsonify(
            {
                "success": True,
                "comment": {
                    "id": comment.id,
                    "content": comment.content,
                    "author_name": current_user.full_name,
                    "author_avatar": current_user.profile_pic
                    or url_for("static", filename="assets/img/default-avatar.png"),
                    "created_at": "Just now",
                },
            }
        )
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


from models import Reaction


@user.route("/react_post/<int:post_id>", methods=["POST"])
@login_required
def react_to_post(post_id):
    """Handle post reactions"""
    try:
        data = request.get_json()
        reaction_type = data.get("reaction_type", "like")

        # Validate reaction type
        valid_reactions = ["like", "love", "care", "haha", "wow", "sad", "angry"]
        if reaction_type not in valid_reactions:
            return jsonify({"success": False, "error": "Invalid reaction type"}), 400

        post = Post.query.get_or_404(post_id)

        # Check for existing reaction
        existing_reaction = Reaction.query.filter_by(
            user_id=current_user.id, post_id=post_id
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
                user_id=current_user.id, post_id=post_id, reaction_type=reaction_type
            )
            db.session.add(new_reaction)
            reacted = True

        db.session.commit()

        # Get updated reaction count
        reaction_count = Reaction.query.filter_by(post_id=post_id).count()
        user_reaction = Reaction.query.filter_by(
            user_id=current_user.id, post_id=post_id
        ).first()

        return jsonify(
            {
                "success": True,
                "reacted": reacted,
                "reaction_type": reaction_type,
                "total_reactions": reaction_count,
                "user_reaction": user_reaction.reaction_type if user_reaction else None,
            }
        )

    except Exception as e:
        db.session.rollback()
        print(f"Reaction error: {e}")
        return jsonify({"success": False, "error": "Failed to react to post"}), 500


import time

start = time.time()
# result = db.session.query(...).all()
print(f"Query took {time.time() - start:.2f} seconds")


@user.route("/post/<post_identifier>")
def view_shared_post(post_identifier):
    post = resolve_post_by_identifier(post_identifier)
    post = (
        Post.query.options(
            joinedload(Post.author),
            joinedload(Post.shared_post).joinedload(Post.author),
            joinedload(Post.comments).joinedload(Comment.author),
            joinedload(Post.likes),
        )
        .filter_by(id=post.id)
        .first_or_404()
    )
    return render_template("post_detail.html", post=post, share_meta=build_post_share_meta(post))


@user.route("/profile/<user_identifier>")
@login_required
def view_profile(user_identifier):
    target_user = resolve_user_by_identifier(user_identifier)

    friend_status = current_user.get_friend_request_status(target_user.id)

    # Check if current user has blocked or is blocked by target user
    is_blocked = current_user.is_blocked_by(target_user) or current_user.is_blocking(
        target_user
    )

    if is_blocked:
        flash("You cannot view this profile.", "danger")
        return redirect(url_for("user.user_dashboard"))

    # Get the user's recent posts (visible to the viewer)
    posts = (
        Post.query.options(
            joinedload(Post.author),
            joinedload(Post.shared_post).joinedload(Post.author),
            joinedload(Post.comments).joinedload(Comment.author),
            joinedload(Post.likes),
        )
        .filter_by(author_id=target_user.id)
        .order_by(Post.created_at.desc())
        .limit(20)  # Adjust as needed
        .all()
    )

    # Get friends count (excluding blocked users)
    friends_count = target_user.friends.count()

    # Calculate age if DOB is set
    age = calculate_age(target_user.dob) if target_user.dob else None

    # Pass everything to the template
    return render_template(
        "public_profile.html",
        profile_user=target_user,
        current_user=current_user,
        friend_status=friend_status,
        posts=posts,
        friends_count=friends_count,
        age=age,
        is_own_profile=(target_user.id == current_user.id),
    )


@user.route("/api/account/delete", methods=["DELETE"])
@login_required
def delete_account():
    if current_user.is_super_admin:
        return jsonify({"success": False, "error": "Super admin accounts cannot be deleted."}), 403

    user_record = User.query.get(current_user.id)
    if not user_record:
        return jsonify({"success": False, "error": "User not found."}), 404

    try:
        db.session.delete(user_record)
        db.session.commit()
        logout_user()
        return jsonify({"success": True})
    except Exception:
        db.session.rollback()
        # Fallback: soft delete to avoid FK constraint issues
        try:
            user_record = User.query.get(current_user.id)
            if not user_record:
                return jsonify({"success": False, "error": "User not found."}), 404
            user_record.is_active = False
            user_record.email = f"deleted_{user_record.id}@deleted.local"
            user_record.first_name = "Deleted"
            user_record.last_name = "User"
            user_record.phone_number = ""
            db.session.commit()
            logout_user()
            return jsonify({"success": True, "soft_deleted": True})
        except Exception:
            db.session.rollback()
            return jsonify({"success": False, "error": "Unable to delete account at this time."}), 500


def get_upcoming_birthdays(user_id, days_ahead=7):
    """
    Get friends with upcoming birthdays
    """
    today = date.today()

    # Get user's friends
    user = User.query.get(user_id)
    friends = user.friends.all()

    upcoming_birthdays = []

    for friend in friends:
        if friend.dob:
            # Get this year's birthday
            birthday_this_year = date(today.year, friend.dob.month, friend.dob.day)

            # Check if birthday is today or in next 7 days
            days_until = (birthday_this_year - today).days

            if 0 <= days_until <= days_ahead:
                upcoming_birthdays.append(
                    {
                        "friend": friend,
                        "days_until": days_until,
                        "birthday_date": birthday_this_year,
                        "age": today.year - friend.dob.year,
                    }
                )

    return upcoming_birthdays
