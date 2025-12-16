# socketio_events.py - IMPROVED with better error handling
from flask_socketio import emit, join_room, leave_room
from flask_login import current_user
from datetime import datetime
from extensions import socketio, db
from models import User, Message
from flask import request, session
import traceback

print("✅ Socket.IO event handlers loading...")

# WebSocket connection handler with better error handling
@socketio.on('connect')
def handle_connect():
    """Handle user connection"""
    try:
        print(f'🔗 WebSocket connection attempt: {request.sid}')
        
        # Check authentication
        if not current_user.is_authenticated:
            print(f'⚠️ Unauthenticated WebSocket connection: {request.sid}')
            emit('connected', {
                'status': 'error',
                'message': 'Authentication required'
            })
            return False  # Reject connection
            
        user_id = current_user.id
        
        # Join user's personal room
        join_room(f'user_{user_id}')
        print(f'✅ User {user_id} connected via WebSocket (sid: {request.sid})')
        
        # Update user status
        current_user.is_online = True
        current_user.last_seen = datetime.utcnow()
        db.session.commit()
        
        # Send welcome message
        emit('connected', {
            'status': 'authenticated',
            'user_id': user_id,
            'message': f'Welcome back, {current_user.first_name}!',
            'socket_id': request.sid,
            'timestamp': datetime.utcnow().isoformat()
        })
        
        # Notify friends that user is online
        notify_friends_online(user_id)
        
        return True
        
    except Exception as e:
        print(f'❌ WebSocket connection error: {e}')
        traceback.print_exc()
        return False

@socketio.on('disconnect')
def handle_disconnect():
    """Handle user disconnect"""
    try:
        print(f'👋 WebSocket disconnected: {request.sid}')
        
        if current_user.is_authenticated:
            user_id = current_user.id
            
            # Update user status
            current_user.is_online = False
            current_user.last_seen = datetime.utcnow()
            db.session.commit()
            
            print(f'✅ User {user_id} marked as offline')
            
            # Notify friends that user is offline
            notify_friends_offline(user_id)
            
    except Exception as e:
        print(f'❌ Disconnect error: {e}')

def notify_friends_online(user_id):
    """Notify user's friends that they're online"""
    try:
        user = User.query.get(user_id)
        if not user:
            return
            
        for friend in user.friends:
            if user.can_interact_with(friend):
                emit('friend_online', {
                    'user_id': user_id,
                    'user_name': user.full_name,
                    'timestamp': datetime.utcnow().isoformat()
                }, room=f'user_{friend.id}')
                
    except Exception as e:
        print(f'❌ Error notifying friends online: {e}')

def notify_friends_offline(user_id):
    """Notify user's friends that they're offline"""
    try:
        user = User.query.get(user_id)
        if not user:
            return
            
        for friend in user.friends:
            if user.can_interact_with(friend):
                emit('friend_offline', {
                    'user_id': user_id,
                    'user_name': user.full_name,
                    'timestamp': datetime.utcnow().isoformat()
                }, room=f'user_{friend.id}')
                
    except Exception as e:
        print(f'❌ Error notifying friends offline: {e}')

# Test endpoint
@socketio.on('ping')
def handle_ping(data=None):
    """Test ping endpoint"""
    print(f'🏓 Ping received from {request.sid}')
    return {
        'status': 'ok',
        'message': 'pong',
        'timestamp': datetime.utcnow().isoformat(),
        'user_id': current_user.id if current_user.is_authenticated else None,
        'socket_id': request.sid
    }

# Messaging handlers (keep your existing ones)
@socketio.on('join_chat')
def handle_join_chat(data):
    """Join a chat room"""
    try:
        if not current_user.is_authenticated:
            emit('error', {'message': 'Not authenticated'})
            return
            
        friend_id = data.get('friend_id')
        if not friend_id:
            emit('error', {'message': 'No friend_id provided'})
            return
            
        # Create room name (always same for both users)
        room = f'chat_{min(current_user.id, friend_id)}_{max(current_user.id, friend_id)}'
        join_room(room)
        
        print(f'💬 User {current_user.id} joined chat room: {room}')
        emit('chat_joined', {
            'room': room,
            'friend_id': friend_id,
            'status': 'joined',
            'timestamp': datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        print(f'❌ Join chat error: {e}')
        emit('error', {'message': str(e)})


@socketio.on('send_message')
def handle_send_message(data):
    try:
        from models import Message, db
        from flask_login import current_user

        friend_id = data['friend_id']
        content = data['content']

        # Create and save message
        message = Message(
            sender_id=current_user.id,
            receiver_id=friend_id,
            content=content,
            status='delivered'
        )
        db.session.add(message)
        db.session.commit()

        # Emit to sender
        emit('new_message', {
            'id': message.id,
            'sender_id': message.sender_id,
            'receiver_id': message.receiver_id,
            'content': message.content,
            'timestamp': message.timestamp.isoformat(),
            'status': message.status,
            'is_mine': True,
            'sender_name': current_user.full_name,
            'sender_avatar': current_user.profile_pic or url_for("static", filename="assets/img/default-avatar.png")
        }, room=request.sid)

        # Emit to receiver if online
        emit('new_message', {
            'id': message.id,
            'sender_id': message.sender_id,
            'receiver_id': message.receiver_id,
            'content': message.content,
            'timestamp': message.timestamp.isoformat(),
            'status': message.status,
            'is_mine': False,
            'sender_name': current_user.full_name,
            'sender_avatar': current_user.profile_pic or url_for("static", filename="assets/img/default-avatar.png")
        }, room=f"user_{friend_id}")

    except Exception as e:
        print(f"Error sending message: {e}")
        emit('error', {'error': str(e)})






# Typing indicators
@socketio.on('typing_start')
def handle_typing_start(data):
    """Handle typing start"""
    try:
        if not current_user.is_authenticated:
            return
            
        friend_id = data.get('friend_id')
        if not friend_id:
            return
            
        room = f'chat_{min(current_user.id, friend_id)}_{max(current_user.id, friend_id)}'
        emit('user_typing', {
            'user_id': current_user.id,
            'user_name': current_user.full_name,
            'timestamp': datetime.utcnow().isoformat()
        }, room=room, include_self=False)
        
    except Exception as e:
        print(f'❌ Typing start error: {e}')

@socketio.on('typing_stop')
def handle_typing_stop(data):
    """Handle typing stop"""
    try:
        if not current_user.is_authenticated:
            return
            
        friend_id = data.get('friend_id')
        if not friend_id:
            return
            
        room = f'chat_{min(current_user.id, friend_id)}_{max(current_user.id, friend_id)}'
        emit('user_stopped_typing', {
            'user_id': current_user.id,
            'timestamp': datetime.utcnow().isoformat()
        }, room=room, include_self=False)
        
    except Exception as e:
        print(f'❌ Typing stop error: {e}')

print("✅ Socket.IO event handlers registered successfully!")


@socketio.on('friend_request_sent')
def handle_friend_request_sent(data):
    """Notify user when friend request is sent to them"""
    receiver_id = data.get('receiver_id')
    sender_id = data.get('sender_id')

    # Emit to the receiver
    emit('friend_request_update', {
        'type': 'request_sent',
        'sender_id': sender_id,
        'message': f'{current_user.full_name} sent you a friend request'
    }, room=f'user_{receiver_id}')


@socketio.on('friend_request_cancelled')
def handle_friend_request_cancelled(data):
    """Notify user when friend request is cancelled"""
    receiver_id = data.get('receiver_id')
    sender_id = data.get('sender_id')

    # Emit to the receiver
    emit('friend_request_update', {
        'type': 'request_cancelled',
        'sender_id': sender_id,
        'message': f'{current_user.full_name} cancelled their friend request'
    }, room=f'user_{receiver_id}')


@socketio.on('friend_request_accepted')
def handle_friend_request_accepted(data):
    """Notify user when friend request is accepted"""
    user_id = data.get('user_id')
    friend_id = data.get('friend_id')

    # Emit to both users
    emit('friend_request_update', {
        'type': 'request_accepted',
        'friend_id': friend_id,
        'message': f'You are now friends with {current_user.full_name}'
    }, room=f'user_{user_id}')

    emit('friend_request_update', {
        'type': 'request_accepted',
        'friend_id': user_id,
        'message': f'You are now friends with {User.query.get(user_id).full_name}'
    }, room=f'user_{friend_id}')