# messaging.py - Fix these routes
from flask import Blueprint, jsonify, request, url_for
from flask_login import login_required, current_user
from extensions import db, socketio
from models import Message, User
from datetime import datetime
from flask_socketio import join_room, leave_room, emit

messaging = Blueprint('messaging', __name__)




# === ROUTES ===
@messaging.route('/friends')  # REMOVED /messaging prefix
@login_required
def get_messaging_friends():
    """Get friends list for messaging"""
    try:
        friends = []
        for friend in current_user.friends:
            if friend.is_visible_to(current_user):  # Check if not blocked
                # Get unread message count for this friend
                unread_count = Message.query.filter(
                    Message.sender_id == friend.id,
                    Message.receiver_id == current_user.id,
                    Message.status != 'read'
                ).count()
                
                friends.append({
                    'id': friend.id,
                    'name': friend.full_name,
                    'avatar': friend.profile_pic or url_for('static', filename='assets/img/default-avatar.png'),
                    'online': friend.is_online,
                    'last_seen': friend.last_seen.isoformat() if friend.last_seen else None,
                    'unread_count': unread_count
                })
        return jsonify(friends)
    except Exception as e:
        print(f"Error getting friends: {e}")
        return jsonify([])

@messaging.route('/messages/<int:friend_id>')  # REMOVED /messaging prefix
@login_required
def get_messages(friend_id):
    """Get messages between current user and friend"""
    try:
        friend = User.query.get_or_404(friend_id)
        if not current_user.is_friend_with(friend):
            return jsonify({'error': 'Not friends'}), 403

        messages = Message.query.filter(
            ((Message.sender_id == current_user.id) & (Message.receiver_id == friend_id)) |
            ((Message.sender_id == friend_id) & (Message.receiver_id == current_user.id))
        ).order_by(Message.timestamp.asc()).all()

        # Mark messages as read (update status to 'read')
        unread_messages = Message.query.filter(
            Message.sender_id == friend_id,
            Message.receiver_id == current_user.id,
            Message.status != 'read'
        ).all()
        
        for msg in unread_messages:
            msg.status = 'read'
        
        db.session.commit()

        # Notify sender that messages were read
        socketio.emit('messages_read', {
            'sender_id': current_user.id,
            'receiver_id': friend_id,
            'message_ids': [msg.id for msg in unread_messages]
        }, room=f"user_{friend_id}")

        return jsonify([msg.to_dict() for msg in messages])
    except Exception as e:
        print(f"Error getting messages: {e}")
        return jsonify([])

@messaging.route('/mark_read/<int:friend_id>', methods=['POST'])  # REMOVED /messaging prefix
@login_required
def mark_messages_read(friend_id):
    """Mark messages from friend as read"""
    try:
        unread_messages = Message.query.filter(
            Message.sender_id == friend_id,
            Message.receiver_id == current_user.id,
            Message.status != 'read'
        ).all()
        
        message_ids = []
        for msg in unread_messages:
            msg.status = 'read'
            message_ids.append(msg.id)
        
        db.session.commit()
        
        # Notify sender
        socketio.emit('messages_read', {
            'sender_id': current_user.id,
            'receiver_id': friend_id,
            'message_ids': message_ids
        }, room=f"user_{friend_id}")
        
        return jsonify({'success': True, 'marked': len(message_ids)})
    except Exception as e:
        print(f"Error marking messages read: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    
    
# Flask routes for the new functionality
@messaging.route('/messaging/conversations')
def get_conversations():
    # Return recent conversations with unread counts
    pass

@messaging.route('/messaging/unread_count')
def get_unread_count():
    # Return total unread messages count
    pass

@messaging.route('/messaging/mark_all_read', methods=['POST'])
def mark_all_read():
    # Mark all messages as read
    pass





# === SOCKET.IO HANDLERS ===
@socketio.on('connect')
def handle_connect():
    """Handle user connection"""
    if current_user.is_authenticated:
        join_room(f"user_{current_user.id}")
        current_user.is_online = True
        current_user.last_seen = datetime.utcnow()
        db.session.commit()
        print(f"User {current_user.id} connected to messaging")

@socketio.on('disconnect')
def handle_disconnect():
    """Handle user disconnect"""
    if current_user.is_authenticated:
        current_user.is_online = False
        current_user.last_seen = datetime.utcnow()
        db.session.commit()
        print(f"User {current_user.id} disconnected from messaging")

@socketio.on('join_messenger')
def on_join_messenger():
    """Join messenger room"""
    if current_user.is_authenticated:
        join_room(f"user_{current_user.id}")
        emit('messenger_joined', {'user_id': current_user.id})

@socketio.on('join_chat')
def on_join_chat(data):
    """Join specific chat room"""
    if current_user.is_authenticated:
        friend_id = data.get('friend_id')
        friend = User.query.get(friend_id)
        if friend and current_user.is_friend_with(friend):
            room = f"chat_{min(current_user.id, friend_id)}_{max(current_user.id, friend_id)}"
            join_room(room)
            emit('chat_joined', {'room': room})

@socketio.on('send_message')
def handle_message(data):
    """Handle sending a message"""
    if not current_user.is_authenticated:
        return
    
    friend_id = data.get('friend_id')
    content = data.get('content', '').strip()
    
    if not friend_id or not content:
        return
    
    try:
        friend = User.query.get(friend_id)
        if not friend or not current_user.is_friend_with(friend):
            emit('error', {'message': 'You can only message friends'})
            return

        # Create message
        message = Message(
            sender_id=current_user.id,
            receiver_id=friend_id,
            content=content,
            status='sent'
        )
        
        db.session.add(message)
        db.session.commit()

        # Prepare message data
        message_data = message.to_dict()
        
        # Send to chat room
        room = f"chat_{min(current_user.id, friend_id)}_{max(current_user.id, friend_id)}"
        emit('new_message', message_data, room=room)
        
        # Also send to individual user rooms for real-time updates
        emit('new_message', message_data, room=f"user_{friend_id}")
        
        # Mark as delivered if receiver is online
        if friend.is_online:
            message.status = 'delivered'
            db.session.commit()
            
            # Emit delivery status
            emit('message_delivered', {
                'message_id': message.id
            }, room=f"user_{current_user.id}")
            
        print(f"Message sent from {current_user.id} to {friend_id}")
        
    except Exception as e:
        print(f"Error sending message: {e}")
        emit('error', {'message': 'Failed to send message'})

@socketio.on('typing')
def on_typing(data):
    """Handle typing indicator"""
    if current_user.is_authenticated:
        friend_id = data.get('friend_id')
        friend = User.query.get(friend_id)
        if friend and current_user.is_friend_with(friend):
            room = f"chat_{min(current_user.id, friend_id)}_{max(current_user.id, friend_id)}"
            emit('user_typing', {
                'user_id': current_user.id,
                'user_name': current_user.full_name
            }, room=room, include_self=False)

@socketio.on('stop_typing')
def on_stop_typing(data):
    """Handle stop typing"""
    if current_user.is_authenticated:
        friend_id = data.get('friend_id')
        friend = User.query.get(friend_id)
        if friend and current_user.is_friend_with(friend):
            room = f"chat_{min(current_user.id, friend_id)}_{max(current_user.id, friend_id)}"
            emit('user_stopped_typing', {
                'user_id': current_user.id
            }, room=room, include_self=False)