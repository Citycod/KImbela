# socketio_handlers.py - Separate file for Socket.IO handlers
from flask_socketio import emit, join_room, leave_room
from flask_login import current_user
from datetime import datetime
from models import User, Message
from extensions import db, socketio

# Initialize socketio in this module too
from extensions import socketio


@socketio.on("connect")
def handle_connect():
    """Handle user connection"""
    try:
        print(f"🔗 Socket.IO connect attempt")

        if current_user.is_authenticated:
            user_id = current_user.id

            # Join user's personal room
            join_room(f"user_{user_id}")
            print(f"✅ User {user_id} joined room user_{user_id}")

            # Mark user as online
            current_user.is_online = True
            current_user.last_seen = datetime.utcnow()
            db.session.commit()

            emit("connected", {"user_id": user_id, "message": "Connected to messaging"})
            print(f"✅ User {user_id} connected to messaging")
            return True
        else:
            print("❌ Unauthenticated connection")
            return False
    except Exception as e:
        print(f"❌ Error in handle_connect: {e}")
        import traceback

        traceback.print_exc()
        return False


@socketio.on("disconnect")
def handle_disconnect():
    """Handle user disconnect"""
    try:
        if current_user.is_authenticated:
            user_id = current_user.id

            # Mark user as offline
            current_user.is_online = False
            current_user.last_seen = datetime.utcnow()
            db.session.commit()

            print(f"👋 User {user_id} disconnected")
    except Exception as e:
        print(f"❌ Error in handle_disconnect: {e}")


@socketio.on("join_chat")
def on_join_chat(data):
    """Join specific chat room"""
    try:
        if current_user.is_authenticated:
            friend_id = data.get("friend_id")
            if friend_id:
                room = f"chat_{min(current_user.id, friend_id)}_{max(current_user.id, friend_id)}"
                join_room(room)
                print(f"💬 User {current_user.id} joined chat room {room}")
                emit("chat_joined", {"room": room, "friend_id": friend_id})
    except Exception as e:
        print(f"❌ Error in on_join_chat: {e}")


@socketio.on("ping")
def handle_ping():
    """Simple ping handler"""
    try:
        emit("pong", {"message": "pong", "timestamp": datetime.utcnow().isoformat()})
    except Exception as e:
        print(f"❌ Error in handle_ping: {e}")
