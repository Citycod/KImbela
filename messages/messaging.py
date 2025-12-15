# messaging.py - Routes only, no Socket.IO handlers
from flask import Blueprint, jsonify, request, url_for
from flask_login import login_required, current_user
from extensions import db
from models import Message, User

messaging = Blueprint("messaging", __name__)

# ========== ROUTES ONLY ==========
@messaging.route("/api/messaging/friends")
@login_required
def get_friends_for_messaging():
    """Get friends list for messaging"""
    try:
        friends = []
        for friend in current_user.friends:
            if current_user.can_interact_with(friend):
                # Get unread message count
                unread_count = Message.query.filter(
                    Message.sender_id == friend.id,
                    Message.receiver_id == current_user.id,
                    Message.status == "delivered"
                ).count()

                friends.append({
                    "id": friend.id,
                    "name": friend.full_name,
                    "avatar": friend.profile_pic or url_for("static", filename="assets/img/default-avatar.png"),
                    "online": friend.is_online,
                    "unread_count": unread_count
                })
        
        return jsonify({"success": True, "friends": friends})
    except Exception as e:
        print(f"❌ Error getting friends: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@messaging.route("/api/messaging/messages/<int:friend_id>")
@login_required
def get_messages_with_friend(friend_id):
    """Get messages between current user and friend"""
    try:
        friend = User.query.get_or_404(friend_id)
        
        # Check permissions
        if not current_user.can_interact_with(friend):
            return jsonify({"success": False, "error": "Cannot message this user"}), 403
        
        if not current_user.is_friend_with(friend):
            return jsonify({"success": False, "error": "You must be friends to message"}), 403

        # Get messages
        messages = Message.query.filter(
            ((Message.sender_id == current_user.id) & (Message.receiver_id == friend_id)) |
            ((Message.sender_id == friend_id) & (Message.receiver_id == current_user.id))
        ).order_by(Message.timestamp.asc()).all()

        # Mark unread messages as read
        unread_messages = Message.query.filter(
            Message.sender_id == friend_id,
            Message.receiver_id == current_user.id,
            Message.status == "delivered"
        ).all()

        for msg in unread_messages:
            msg.status = "read"
        
        db.session.commit()

        # Prepare response
        messages_data = []
        for msg in messages:
            messages_data.append({
                "id": msg.id,
                "sender_id": msg.sender_id,
                "receiver_id": msg.receiver_id,
                "content": msg.content,
                "timestamp": msg.timestamp.isoformat(),
                "status": msg.status,
                "is_mine": msg.sender_id == current_user.id,
                "sender_name": msg.sender.full_name,
                "sender_avatar": msg.sender.profile_pic or url_for("static", filename="assets/img/default-avatar.png")
            })

        return jsonify({"success": True, "messages": messages_data})
        
    except Exception as e:
        print(f"❌ Error getting messages: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@messaging.route("/api/messaging/send", methods=["POST"])
@login_required
def send_message():
    """Send a new message"""
    try:
        data = request.get_json()
        friend_id = data.get("friend_id")
        content = data.get("content", "").strip()

        if not friend_id or not content:
            return jsonify({"success": False, "error": "Missing data"}), 400

        friend = User.query.get(friend_id)
        if not friend:
            return jsonify({"success": False, "error": "User not found"}), 404

        # Check permissions
        if not current_user.can_interact_with(friend):
            return jsonify({"success": False, "error": "Cannot message this user"}), 403
        
        if not current_user.is_friend_with(friend):
            return jsonify({"success": False, "error": "You must be friends to message"}), 403

        # Create message
        message = Message(
            sender_id=current_user.id,
            receiver_id=friend_id,
            content=content,
            status="sent"
        )

        db.session.add(message)
        db.session.commit()

        # Update status
        if friend.is_online:
            message.status = "delivered"
            db.session.commit()

        # Prepare response
        message_data = {
            "id": message.id,
            "sender_id": message.sender_id,
            "receiver_id": message.receiver_id,
            "content": message.content,
            "timestamp": message.timestamp.isoformat(),
            "status": message.status,
            "is_mine": True,
            "sender_name": current_user.full_name,
            "sender_avatar": current_user.profile_pic or url_for("static", filename="assets/img/default-avatar.png")
        }

        return jsonify({"success": True, "message": message_data})

    except Exception as e:
        print(f"❌ Error sending message: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@messaging.route("/api/messaging/unread_count")
@login_required
def get_unread_message_count():
    """Get total unread message count"""
    try:
        unread_count = Message.query.filter_by(
            receiver_id=current_user.id,
            status="delivered"
        ).count()
        
        return jsonify({"success": True, "unread_count": unread_count})
    except Exception as e:
        print(f"❌ Error getting unread count: {e}")
        return jsonify({"success": False, "unread_count": 0})


# Simple test endpoint
@messaging.route("/api/messaging/test")
@login_required
def test_messaging():
    """Test messaging endpoint"""
    return jsonify({
        "success": True,
        "message": "Messaging system is working",
        "user_id": current_user.id
    })