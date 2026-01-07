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
            if not current_user.is_authenticated:
                print(f'⚠️ Unauthenticated connection attempt: {request.sid}')
                return False

            user_id = current_user.id

            # Join user's personal room
            join_room(f'user_{user_id}')
            print(f'✅ User {user_id} connected (sid: {request.sid})')

            # Update online status
            current_user.is_online = True
            current_user.last_seen = datetime.utcnow()
            db.session.commit()

            # Notify friends
            notify_friends_online(user_id)

            emit('connected', {
                'status': 'authenticated',
                'user_id': user_id,
                'timestamp': datetime.utcnow().isoformat()
            })

        except Exception as e:
            print(f'❌ Connection error: {e}')
            return False

@socketio.on('disconnect')
def handle_disconnect():
        """Handle user disconnect"""
        try:
            if current_user.is_authenticated:
                user_id = current_user.id

                # Update online status
                current_user.is_online = False
                current_user.last_seen = datetime.utcnow()
                db.session.commit()

                # Notify friends
                notify_friends_offline(user_id)

                print(f'👋 User {user_id} disconnected')

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
                return

            friend_id = data.get('friend_id')
            if not friend_id:
                return

            # Create unique room name
            room = f'chat_{min(current_user.id, friend_id)}_{max(current_user.id, friend_id)}'
            join_room(room)

            print(f'💬 User {current_user.id} joined chat room: {room}')

        except Exception as e:
            print(f'❌ Join chat error: {e}')


@socketio.on('send_message')
def handle_send_message(data):
        """Handle sending a message via Socket.IO"""
        try:
            if not current_user.is_authenticated:
                return

            try:

                receiver_id = data.get('receiver_id')
                content = data.get('content', '').strip()
                message_type = data.get('type', 'text')
                metadata = data.get('metadata', {})
                temp_id = data.get('temp_id')

                if not receiver_id or (not content and message_type == 'text'):
                    return

                friend = User.query.get(receiver_id)
                if not friend:
                    return

                # Check permissions
                if not current_user.can_interact_with(friend) or not current_user.is_friend_with(friend):
                    return

                # Create message
                message = Message(
                    sender_id=current_user.id,
                    receiver_id=receiver_id,
                    content=content,
                    message_type=message_type,
                    metadata=json.dumps(metadata) if metadata else None,
                    status='sent'
                )

                db.session.add(message)
                db.session.commit()
            except Exception as e:
                print(f'❌ Error saving message to db: {e}')

            # Update status
            if friend.is_online:
                message.status = 'delivered'
                db.session.commit()

            # Prepare message data
            message_data = {
                "id": message.id,
                "sender_id": message.sender_id,
                "receiver_id": message.receiver_id,
                "content": message.content,
                "message_type": message.message_type,
                "metadata": metadata,
                "timestamp": message.timestamp.isoformat(),
                "status": message.status,
                "sender_name": current_user.full_name,
                "sender_avatar": current_user.profile_pic or url_for("static",
                                                                     filename="assets/img/default-avatar.png"),
                "temp_id": temp_id
            }

            # Emit to both users
            socketio.emit('new_message', message_data, room=f'user_{receiver_id}')
            socketio.emit('new_message', message_data, room=f'user_{current_user.id}')

            # Also emit to chat room
            # room = f'chat_{min(current_user.id, receiver_id)}_{max(current_user.id, receiver_id)}'
            # socketio.emit('new_message', message_data, room=room)

        except Exception as e:
            print(f'❌ Error sending message via Socket.IO: {e}')
            db.session.rollback()


# Add these to your socketio_events.py

@socketio.on('typing_start')
def handle_typing_start(data):
    """Handle typing start"""
    try:
        receiver_id = data.get('receiver_id')
        if not receiver_id:
            return

        emit('typing_start', {
            'user_id': current_user.id,
            'user_name': current_user.full_name,
            'timestamp': datetime.utcnow().isoformat()
        }, room=f'user_{receiver_id}')

    except Exception as e:
        print(f"❌ Typing start error: {e}")


@socketio.on('typing_stop')
def handle_typing_stop(data):
    """Handle typing stop"""
    try:
        receiver_id = data.get('receiver_id')
        if not receiver_id:
            return

        emit('typing_stop', {
            'user_id': current_user.id,
            'timestamp': datetime.utcnow().isoformat()
        }, room=f'user_{receiver_id}')

    except Exception as e:
        print(f"❌ Typing stop error: {e}")


@socketio.on('message_read')
def handle_message_read(data):
    """Handle message read"""
    try:
        message_id = data.get('message_id')
        sender_id = data.get('sender_id')

        if not message_id or not sender_id:
            return

        # Update message status in database
        message = Message.query.get(message_id)
        if message and message.receiver_id == current_user.id:
            message.status = 'read'
            db.session.commit()

            # Notify sender
            emit('message_read', {
                'message_id': message_id,
                'timestamp': datetime.utcnow().isoformat()
            }, room=f'user_{sender_id}')

    except Exception as e:
        print(f"❌ Message read error: {e}")
        db.session.rollback()


@socketio.on('user_online')
def handle_user_online(data):
    """Handle user online status"""
    try:
        user_id = data.get('user_id')
        if not user_id or user_id != current_user.id:
            return

        # Update user status
        current_user.is_online = True
        current_user.last_seen = datetime.utcnow()
        db.session.commit()

        # Notify friends
        for friend in current_user.friends:
            if current_user.can_interact_with(friend):
                emit('user_online', {
                    'user_id': current_user.id,
                    'user_name': current_user.full_name,
                    'timestamp': datetime.utcnow().isoformat()
                }, room=f'user_{friend.id}')

    except Exception as e:
        print(f"❌ User online error: {e}")
        db.session.rollback()


@socketio.on('user_offline')
def handle_user_offline(data):
    """Handle user offline status"""
    try:
        user_id = data.get('user_id')
        if not user_id or user_id != current_user.id:
            return

        # Update user status
        current_user.is_online = False
        current_user.last_seen = datetime.utcnow()
        db.session.commit()

        # Notify friends
        for friend in current_user.friends:
            if current_user.can_interact_with(friend):
                emit('user_offline', {
                    'user_id': current_user.id,
                    'user_name': current_user.full_name,
                    'timestamp': datetime.utcnow().isoformat()
                }, room=f'user_{friend.id}')

    except Exception as e:
        print(f"❌ User offline error: {e}")
        db.session.rollback()

@socketio.on('message_reaction')
def handle_message_reaction(data):
    """Handle message reactions"""
    try:
        if not current_user.is_authenticated:
            return

        message_id = data.get('message_id')
        reaction = data.get('reaction')
        receiver_id = data.get('receiver_id')

        if not message_id or not reaction or not receiver_id:
            return

        # Update message metadata with reaction
        message = Message.query.get(message_id)
        if message:
            # Parse existing metadata
            metadata = json.loads(message.metadata) if message.metadata else {}
            reactions = metadata.get('reactions', {})

            # Add/update reaction
            if reaction in reactions:
                if current_user.id in reactions[reaction]:
                    reactions[reaction].remove(current_user.id)
                    if not reactions[reaction]:
                        del reactions[reaction]
                else:
                    reactions[reaction].append(current_user.id)
            else:
                reactions[reaction] = [current_user.id]

            metadata['reactions'] = reactions
            message.metadata = json.dumps(metadata)
            db.session.commit()

            # Emit reaction update
            emit('message_reaction', {
                'message_id': message_id,
                'reaction': reaction,
                'user_id': current_user.id,
                'action': 'added' if current_user.id in reactions.get(reaction, []) else 'removed'
            }, room=f'user_{receiver_id}')
            emit('message_reaction', {
                'message_id': message_id,
                'reaction': reaction,
                'user_id': current_user.id,
                'action': 'added' if current_user.id in reactions.get(reaction, []) else 'removed'
            }, room=f'user_{current_user.id}')

    except Exception as e:
        print(f'❌ Message reaction error: {e}')
        db.session.rollback()


@socketio.on('mark_as_read')
def handle_mark_as_read(data):
    message_id = data.get('message_id')
    sender_id = data.get('sender_id')

    # Mark message as read in database
    message = Message.query.get(message_id)
    if message and message.receiver_id == current_user.id:
        message.is_read = True
        db.session.commit()

        # Notify sender that message was read
        emit('message_read', {
            'message_id': message_id
        }, room=f'user_{sender_id}')


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









    @socketio.on('disconnect')
    def handle_disconnect():
        """Handle user disconnect"""
        try:
            if current_user.is_authenticated:
                user_id = current_user.id

                # Update online status
                current_user.is_online = False
                current_user.last_seen = datetime.utcnow()
                db.session.commit()

                # Notify friends
                notify_friends_offline(user_id)

                print(f'👋 User {user_id} disconnected')

        except Exception as e:
            print(f'❌ Disconnect error: {e}')





