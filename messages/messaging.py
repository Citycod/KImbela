from flask import Blueprint, jsonify, request, url_for, current_app
from flask_login import login_required, current_user
from flask_socketio import emit, join_room, leave_room
from models import Message, User
from extensions import db, socketio
from sqlalchemy import or_, and_, desc, func
from datetime import datetime, timedelta
import os, json, pytz, uuid
from werkzeug.utils import secure_filename
import mimetypes
from PIL import Image
import io
import requests
import os
from dotenv import load_dotenv
from flask import send_from_directory
import os
from PIL import Image


from time_utils import utcnow
messaging = Blueprint("messaging", __name__)

# Configuration
ALLOWED_EXTENSIONS = {
    "image": {"jpg", "jpeg", "png", "gif", "webp", "bmp"},
    "video": {"mp4", "webm", "ogg", "mov", "avi"},
    "audio": {"mp3", "wav", "ogg", "m4a", "webm"},
    "document": {"pdf", "doc", "docx", "txt", "xls", "xlsx", "ppt", "pptx"},
}

MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
MESSAGES_PER_PAGE = 50


load_dotenv()

# GIPHY API Configuration
GIPHY_API_KEY = os.getenv("GIPHY_API_KEY")


# ========== HELPER FUNCTIONS ==========
def allowed_file(filename, file_type="image"):
    """Check if file extension is allowed"""
    if "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in ALLOWED_EXTENSIONS.get(file_type, set())


def generate_unique_filename(filename):
    """Generate a unique filename to prevent collisions"""
    ext = filename.rsplit(".", 1)[1].lower() if "." in filename else ""
    unique_id = uuid.uuid4().hex
    return f"{unique_id}.{ext}" if ext else unique_id


def save_file(file, file_type="image"):
    """Save uploaded file and return URL"""
    if not file or file.filename == "":
        return None

    if file_type not in ALLOWED_EXTENSIONS:
        raise ValueError("Invalid file type")

    # Validate file size
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)

    if file_size > MAX_FILE_SIZE:
        raise ValueError(
            f"File too large. Maximum size is {MAX_FILE_SIZE // (1024 * 1024)}MB"
        )

    # Generate secure filename and validate extension
    original_filename = secure_filename(file.filename)
    if not allowed_file(original_filename, file_type):
        raise ValueError("Invalid file extension")
    unique_filename = generate_unique_filename(original_filename)

    # Create directory if it doesn't exist
    upload_dir = os.path.join(current_app.config["UPLOAD_FOLDER"], file_type)
    os.makedirs(upload_dir, exist_ok=True)

    # Save file
    file_path = os.path.join(upload_dir, unique_filename)
    file.save(file_path)

    # Process image if needed (resize, compress)
    if file_type == "image":
        process_image(file_path)

    # Return URL
    # return url_for('messaging.uploaded_file', file_type=file_type, filename=unique_filename, _external=True)
    return f"/uploads/{file_type}/{unique_filename}"


def process_image(file_path):
    """Process image for web optimization (keeps correct format)"""
    try:
        ext = os.path.splitext(file_path)[1].lower()  # .jpg, .jpeg, .png, .webp, etc.

        with Image.open(file_path) as img:
            # Resize if too large
            max_size = (1920, 1080)
            if img.width > max_size[0] or img.height > max_size[1]:
                img.thumbnail(max_size, Image.Resampling.LANCZOS)

            # Decide output format based on extension
            if ext in (".jpg", ".jpeg"):
                if img.mode in ("RGBA", "LA", "P"):
                    img = img.convert("RGB")
                img.save(file_path, format="JPEG", quality=85, optimize=True)

            elif ext == ".png":
                img.save(file_path, format="PNG", optimize=True)

            elif ext == ".webp":
                img.save(file_path, format="WEBP", quality=85, method=6)

            else:
                # Unknown ext: don't rewrite the file
                pass

    except Exception as e:
        print(f"Error processing image: {e}")


# ========== API ROUTES ==========
@messaging.route("/api/messaging/friends")
@login_required
def get_friends_for_messaging():
    """Get friends list for messaging with last message and unread count"""
    try:
        friends = []
        for friend in current_user.friends:
            if not current_user.can_interact_with(friend):
                continue

            # Get last message
            last_message = (
                Message.query.filter(
                    or_(
                        and_(
                            Message.sender_id == current_user.id,
                            Message.receiver_id == friend.id,
                        ),
                        and_(
                            Message.sender_id == friend.id,
                            Message.receiver_id == current_user.id,
                        ),
                    )
                )
                .order_by(Message.timestamp.desc())
                .first()
            )

            # Get unread message count
            unread_count = Message.query.filter(
                Message.sender_id == friend.id,
                Message.receiver_id == current_user.id,
                Message.status == "delivered",
            ).count()

            # Get friend's online status
            is_online = friend.is_online

            # Get last seen
            last_seen = friend.last_seen.isoformat() if friend.last_seen else None

            # Get last message time
            last_message_time = (
                last_message.timestamp.isoformat() if last_message else None
            )
            last_message_text = (
                last_message.content[:50] + "..."
                if last_message and len(last_message.content) > 50
                else last_message.content if last_message else None
            )

            friends.append(
                {
                    "id": friend.id,
                    "name": friend.full_name,
                    "avatar": friend.profile_pic
                    or url_for("static", filename="assets/img/default-avatar.png"),
                    "online": is_online,
                    "last_seen": last_seen,
                    "last_message": last_message_text,
                    "last_message_time": last_message_time,
                    "unread_count": unread_count,
                }
            )

        # Sort by last message time (most recent first)
        friends.sort(key=lambda x: x["last_message_time"] or "", reverse=True)

        return jsonify({"success": True, "friends": friends})
    except Exception as e:
        print(f"❌ Error getting friends: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@messaging.route("/api/messaging/messages/<int:friend_id>")
@login_required
def get_messages_with_friend(friend_id):
    """Get messages between current user and friend with pagination"""
    try:
        friend = User.query.get_or_404(friend_id)

        # Check permissions
        if not current_user.can_interact_with(friend):
            return jsonify({"success": False, "error": "Cannot message this user"}), 403

        if not current_user.is_friend_with(friend):
            return (
                jsonify({"success": False, "error": "You must be friends to message"}),
                403,
            )

        # Get pagination parameters
        page = request.args.get("page", 1, type=int)
        limit = request.args.get("limit", MESSAGES_PER_PAGE, type=int)
        before = request.args.get("before", None)

        # Build query
        query = Message.query.filter(
            or_(
                and_(
                    Message.sender_id == current_user.id,
                    Message.receiver_id == friend_id,
                ),
                and_(
                    Message.sender_id == friend_id,
                    Message.receiver_id == current_user.id,
                ),
            )
        )

        # If before is specified, get messages before this ID
        if before:
            query = query.filter(Message.id < before)

        # Order and paginate
        messages = query.order_by(Message.timestamp.desc()).paginate(
            page=page, per_page=limit, error_out=False
        )

        # Mark unread messages as read
        if page == 1:  # Only mark as read when viewing latest messages
            Message.query.filter_by(
                sender_id=friend_id, receiver_id=current_user.id, status="delivered"
            ).update({"status": "read"})
            db.session.commit()

        # Prepare response - FIXED: Handle metadata properly
        messages_data = []
        for msg in messages.items:
            message_data = {
                "id": msg.id,
                "sender_id": msg.sender_id,
                "receiver_id": msg.receiver_id,
                "content": msg.content,
                "message_type": msg.message_type,
                "timestamp": msg.timestamp.isoformat() if msg.timestamp else None,
                "status": msg.status,
                "sender_name": msg.sender.full_name if msg.sender else None,
                "sender_avatar": (
                    msg.sender.profile_pic
                    or url_for("static", filename="assets/img/default-avatar.png")
                    if msg.sender
                    else url_for("static", filename="assets/img/default-avatar.png")
                ),
            }

            # Handle metadata carefully
            if msg.message_data:  # CHANGED FROM msg.metadata
                if isinstance(msg.message_data, dict):
                    message_data["metadata"] = msg.message_data
                elif hasattr(msg.message_data, "copy"):
                    message_data["metadata"] = msg.message_data.copy()
                else:
                    try:
                        if isinstance(msg.message_data, str):
                            message_data["metadata"] = json.loads(msg.message_data)
                        else:
                            message_data["metadata"] = {}
                    except:
                        message_data["metadata"] = {}
            else:
                message_data["metadata"] = {}

            messages_data.append(message_data)

        return jsonify(
            {
                "success": True,
                "messages": messages_data,
                "has_more": messages.has_next,
                "next_page": messages.next_num if messages.has_next else None,
                "total": messages.total,
            }
        )

    except Exception as e:
        print(f"❌ Error getting messages: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@messaging.route("/api/messaging/mark-read/<int:friend_id>", methods=["POST"])
@login_required
def mark_messages_as_read(friend_id):
    """Mark all messages from friend as read"""
    try:
        updated = Message.query.filter_by(
            sender_id=friend_id, receiver_id=current_user.id, status="delivered"
        ).update({"status": "read"})

        db.session.commit()

        # Emit read receipt
        socketio.emit(
            "messages_read",
            {
                "friend_id": current_user.id,
                "message_ids": [],  # You can pass specific message IDs if needed
            },
            room=f"user_{friend_id}",
        )

        return jsonify({"success": True, "marked_read": updated})
    except Exception as e:
        print(f"❌ Error marking messages as read: {e}")
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@messaging.route("/api/messaging/send", methods=["POST"])
@login_required
def send_message():
    """Send a new message"""
    try:
        data = request.get_json()

        if not data:
            return jsonify({"success": False, "error": "No data provided"}), 400

        friend_id = data.get("friend_id") or data.get("receiver_id")
        content = data.get("content", "").strip()
        message_type = data.get("type", "text")
        metadata = data.get("metadata", {})

        if not friend_id:
            return (
                jsonify({"success": False, "error": "No recipient specified"}),
                400,
            )

        if not content and message_type == "text":
            return (
                jsonify({"success": False, "error": "Message content is required"}),
                400,
            )

        friend = User.query.get(friend_id)
        if not friend:
            return jsonify({"success": False, "error": "User not found"}), 404

        # Check permissions
        if not current_user.can_interact_with(friend):
            return (
                jsonify({"success": False, "error": "Cannot message this user"}),
                403,
            )

        if not current_user.is_friend_with(friend):
            return (
                jsonify(
                    {"success": False, "error": "You must be friends to message"}
                ),
                403,
            )

        message = Message(
            sender_id=current_user.id,
            receiver_id=friend_id,
            content=content,
            message_type=message_type,
            message_data=metadata if metadata else None,
            status="delivered" if friend.is_online else "sent",
        )

        try:
            db.session.add(message)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            current_app.logger.exception("Failed to persist HTTP message")
            return jsonify({"success": False, "error": str(e)}), 500

        message_data = {
            "id": message.id,
            "sender_id": message.sender_id,
            "receiver_id": message.receiver_id,
            "content": message.content,
            "type": message.message_type,
            "timestamp": message.timestamp.isoformat() if message.timestamp else None,
            "status": message.status,
            "sender_name": current_user.full_name,
            "sender_avatar": current_user.profile_pic
            or url_for("static", filename="assets/img/default-avatar.png"),
        }

        if message.message_data:
            if isinstance(message.message_data, dict):
                message_data["metadata"] = message.message_data
            else:
                try:
                    message_data["metadata"] = json.loads(str(message.message_data))
                except (TypeError, ValueError):
                    message_data["metadata"] = {}
        else:
            message_data["metadata"] = {}

        try:
            socketio.emit("new_message", message_data, room=f"user_{friend_id}")
            socketio.emit(
                "new_message", message_data, room=f"user_{current_user.id}"
            )
        except Exception:
            current_app.logger.exception("Failed to emit persisted HTTP message")

        # The account-level is_online flag cannot identify which device or
        # conversation is active. Suppressing here can silence every subscribed
        # device after any one Socket.IO connection comes online.
        try:
            from utils.push_service import send_push_notification

            push_payload = {
                "title": f"New Message from {current_user.first_name}",
                "body": (
                    content
                    if message_type == "text"
                    else f"Sent you a {message_type}"
                ),
                "url": url_for("user.user_dashboard", chat=current_user.id),
            }
            send_push_notification(friend_id, push_payload)
        except Exception:
            current_app.logger.exception(
                "Failed to send push for persisted HTTP message"
            )

        return jsonify({"success": True, "message": message_data})

    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Error sending HTTP message")
        return jsonify({"success": False, "error": str(e)}), 500


# @messaging.route('/uploads/<file_type>/<filename>')
# @login_required
# def uploaded_file(file_type, filename):
#     try:
#         upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], file_type)
#         return send_from_directory(upload_dir, filename)
#     except NotFound:
#         abort(404)
#     except Exception as e:
#         print(f"Error serving uploaded file: {e}")
#         abort(404)


@messaging.route("/api/messaging/upload", methods=["POST"])
@login_required
def upload_file():
    """Upload a file and return clean URL"""
    try:
        if "file" not in request.files:
            return jsonify({"success": False, "error": "No file provided"}), 400

        file = request.files["file"]
        to_id = request.form.get("to_id", type=int)
        file_type = request.form.get(
            "type", "document"
        )  # image, video, audio, document

        if not to_id:
            return jsonify({"success": False, "error": "No recipient specified"}), 400

        if not file or file.filename == "":
            return jsonify({"success": False, "error": "No file selected"}), 400

        # Save file and get URL
        file_url = save_file(file, file_type)
        if not file_url:
            return jsonify({"success": False, "error": "Failed to save file"}), 500

        return jsonify(
            {
                "success": True,
                "url": file_url,
                "filename": file.filename,
                "type": file_type,
            }
        )

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        print(f"❌ Error uploading file: {e}")
        return jsonify({"success": False, "error": "Upload failed"}), 500


@messaging.route("/api/messaging/unread_count")
@login_required
def get_unread_message_count():
    """Get total unread message count"""
    try:
        unread_count = Message.query.filter_by(
            receiver_id=current_user.id, status="delivered"
        ).count()

        return jsonify({"success": True, "unread_count": unread_count})
    except Exception as e:
        print(f"❌ Error getting unread count: {e}")
        return jsonify({"success": False, "unread_count": 0})


# @messaging.route("/api/messaging/search")
# @login_required
# def search_messages():
#     """Search messages with a friend"""
#     try:
#         friend_id = request.args.get('friend_id', type=int)
#         query = request.args.get('q', '').strip()
#
#         if not friend_id or not query:
#             return jsonify({"success": False, "error": "Missing parameters"}), 400
#
#         # Search messages containing the query
#         messages = Message.query.filter(
#             or_(
#                 and_(Message.sender_id == current_user.id, Message.receiver_id == friend_id),
#                 and_(Message.sender_id == friend_id, Message.receiver_id == current_user.id)
#             ),
#             Message.content.ilike(f'%{query}%')
#         ).order_by(Message.timestamp.desc()).limit(50).all()
#
#         messages_data = []
#         for msg in messages:
#             messages_data.append({
#                 "id": msg.id,
#                 "content": msg.content,
#                 "type": msg.type,
#                 "timestamp": msg.timestamp.isoformat(),
#                 "is_mine": msg.sender_id == current_user.id
#             })
#
#         return jsonify({"success": True, "messages": messages_data})
#
#     except Exception as e:
#         print(f"❌ Error searching messages: {e}")
#         return jsonify({"success": False, "error": str(e)}), 500


# @messaging.route("/api/messaging/delete/<int:message_id>", methods=["DELETE"])
# @login_required
# def delete_message(message_id):
#     """Delete a message (soft delete)"""
#     try:
#         message = Message.query.get_or_404(message_id)
#
#         # Check permissions
#         if message.sender_id != current_user.id:
#             return jsonify({"success": False, "error": "Cannot delete other's messages"}), 403
#
#         # Soft delete (mark as deleted)
#         message.is_deleted = True
#         db.session.commit()
#
#         # Notify the other user
#         other_user_id = message.receiver_id if message.sender_id == current_user.id else message.sender_id
#         socketio.emit('message_deleted', {
#             'message_id': message_id,
#             'deleted_by': current_user.id
#         }, room=f'user_{other_user_id}')
#
#         return jsonify({"success": True})
#
#     except Exception as e:
#         print(f"❌ Error deleting message: {e}")
#         db.session.rollback()
#         return jsonify({"success": False, "error": str(e)}), 500


# ========== HELPER FUNCTIONS ==========
def notify_friends_online(user_id):
    """Notify user's friends that they're online"""
    try:
        user = User.query.get(user_id)
        if not user:
            return

        for friend in user.friends:
            if user.can_interact_with(friend):
                socketio.emit(
                    "friend_online",
                    {
                        "user_id": user_id,
                        "user_name": user.full_name,
                        "timestamp": utcnow().isoformat(),
                    },
                    room=f"user_{friend.id}",
                )

    except Exception as e:
        print(f"❌ Error notifying friends online: {e}")


def notify_friends_offline(user_id):
    """Notify user's friends that they're offline"""
    try:
        user = User.query.get(user_id)
        if not user:
            return

        for friend in user.friends:
            if user.can_interact_with(friend):
                socketio.emit(
                    "friend_offline",
                    {
                        "user_id": user_id,
                        "user_name": user.full_name,
                        "timestamp": utcnow().isoformat(),
                    },
                    room=f"user_{friend.id}",
                )

    except Exception as e:
        print(f"❌ Error notifying friends offline: {e}")


@messaging.route("/api/gifs")
@login_required
def get_gifs():
    """Get GIFs from GIPHY API"""
    try:
        query = request.args.get("q", "trending")
        limit = request.args.get("limit", 20)
        offset = request.args.get("offset", 0)

        if query == "trending":
            url = f"https://api.giphy.com/v1/gifs/trending"
        else:
            url = f"https://api.giphy.com/v1/gifs/search"

        params = {
            "api_key": GIPHY_API_KEY,
            "limit": limit,
            "offset": offset,
            "rating": "g",
            "lang": "en",
        }

        if query != "trending":
            params["q"] = query

        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        gifs = []
        for gif in data.get("data", []):
            gifs.append(
                {
                    "id": gif.get("id"),
                    "title": gif.get("title"),
                    "url": gif.get("images", {}).get("original", {}).get("url"),
                    "preview_url": gif.get("images", {})
                    .get("fixed_height_small", {})
                    .get("url"),
                    "width": gif.get("images", {}).get("original", {}).get("width"),
                    "height": gif.get("images", {}).get("original", {}).get("height"),
                }
            )

        return jsonify(
            {"success": True, "gifs": gifs, "pagination": data.get("pagination", {})}
        )

    except Exception as e:
        print(f"❌ Error fetching GIFs: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@messaging.route("/api/messaging/search")
@login_required
def search_messages():
    """Search messages"""
    try:
        query = request.args.get("q", "").strip()
        friend_id = request.args.get("friend_id")

        if not query or len(query) < 2:
            return jsonify({"success": False, "error": "Query too short"}), 400

        # Build query
        search_query = Message.query.filter(
            (
                (Message.sender_id == current_user.id)
                & (Message.receiver_id == friend_id)
            )
            | (
                (Message.sender_id == friend_id)
                & (Message.receiver_id == current_user.id)
            )
        ).filter(Message.content.ilike(f"%{query}%"))

        if friend_id:
            search_query = search_query.filter(
                (Message.sender_id == friend_id) | (Message.receiver_id == friend_id)
            )

        messages = search_query.order_by(Message.timestamp.desc()).limit(50).all()

        results = []
        for msg in messages:
            results.append(
                {
                    "id": msg.id,
                    "content": msg.content,
                    "timestamp": msg.timestamp.isoformat(),
                    "sender_id": msg.sender_id,
                    "receiver_id": msg.receiver_id,
                    "is_mine": msg.sender_id == current_user.id,
                }
            )

        return jsonify({"success": True, "results": results})

    except Exception as e:
        print(f"❌ Error searching messages: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@messaging.route("/api/messaging/delete/<int:message_id>", methods=["DELETE"])
@login_required
def delete_message(message_id):
    """Delete a message"""
    try:
        message = Message.query.get_or_404(message_id)

        # Check permission
        if message.sender_id != current_user.id:
            return jsonify({"success": False, "error": "Unauthorized"}), 403

        # Soft delete (update content)
        message.content = "[Message deleted]"
        message.is_deleted = True
        db.session.commit()

        # Notify recipient via socket
        socketio.emit(
            "message_deleted",
            {"message_id": message_id, "timestamp": utcnow().isoformat()},
            room=f"user_{message.receiver_id}",
        )

        return jsonify({"success": True})

    except Exception as e:
        print(f"❌ Error deleting message: {e}")
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


# Add to your Flask app
@messaging.route("/api/messaging/unread-count")
@login_required
def get_unread_count():
    try:
        # Use receiver_id and status != 'read'
        unread_count = Message.query.filter_by(
            receiver_id=current_user.id,
            status="sent",  # or whatever status indicates "unread"
        ).count()
        return jsonify({"unread_count": unread_count})
    except Exception as e:
        print(f"Error in get_unread_count: {str(e)}")
        return jsonify({"error": str(e)}), 500


@messaging.route("/api/messaging/mark-read/<int:message_id>", methods=["POST"])
@login_required
def mark_message_read(message_id):
    try:
        message = Message.query.get_or_404(message_id)

        # Check if current user is the receiver
        if message.receiver_id == current_user.id:
            message.status = "read"  # or 'delivered' depending on your logic
            db.session.commit()
            return jsonify({"success": True})
        return jsonify({"error": "Unauthorized"}), 403

    except Exception as e:
        print(f"Error in mark_message_read: {str(e)}")
        return jsonify({"error": str(e)}), 500


@messaging.route(
    "/api/messaging/mark-conversation-read/<int:sender_id>", methods=["POST"]
)
@login_required
def mark_conversation_read(sender_id):
    try:
        # Mark all unread messages from this sender as read
        messages = Message.query.filter_by(
            sender_id=sender_id,
            receiver_id=current_user.id,
            status="sent",  # assuming 'sent' means unread
        ).all()

        for message in messages:
            message.status = "read"

        db.session.commit()
        return jsonify({"success": True, "marked": len(messages)})
    except Exception as e:
        print(f"Error marking conversation as read: {str(e)}")
        return jsonify({"error": str(e)}), 500
