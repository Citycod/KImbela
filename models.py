from extensions import db, login_manager
from flask_login import UserMixin
from datetime import datetime, timedelta
import random, string, uuid
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask import url_for

# db = SQLAlchemy()



# Association table for many-to-many friendship
friendship = db.Table(
    'friendship',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
    db.Column('friend_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
    db.Column('accepted_at', db.DateTime, default=datetime.utcnow)
)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(user_id)


# Main User model
class User(db.Model, UserMixin):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_super_admin = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=False)  
    city = db.Column(db.String(50), nullable=False)
    country = db.Column(db.String(50), nullable=False)
    dob = db.Column(db.Date, nullable=False)
    gender = db.Column(db.String(20), nullable=False)  # Add this field
    phone_number = db.Column(db.String(20), nullable=False)
    interests = db.Column(db.Text, nullable=True)  # Add this field for hobbies/interests
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    email_token = db.Column(db.String(255))  # 6-digit token
    email_token_expires = db.Column(db.DateTime)
    # In your User model (add these lines)
    profile_pic = db.Column(db.String(500), default='https://res.cloudinary.com/demo/image/upload/v1312461204/sample.jpg')
    cover_pic = db.Column(db.String(500), default='https://res.cloudinary.com/demo/image/upload/v1312461204/sample.jpg')
    bio = db.Column(db.Text, nullable=True)
    marital_status = db.Column(db.String(50), nullable=True)
    
    def generate_otp(self):
        self.email_token = ''.join(random.choices(string.digits, k=6))
        self.email_token_expires = datetime.utcnow() + timedelta(minutes=10)
        db.session.commit()

    # Relationships
    friends = db.relationship(
        'User',
        secondary=friendship,
        primaryjoin=(friendship.c.user_id == id),
        secondaryjoin=(friendship.c.friend_id == id),
        backref=db.backref('friend_of', lazy='dynamic'),
        lazy='dynamic'
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    # --- Helper Properties ---
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def friend_ids(self):
        """Return set of friend user IDs"""
        return {friend.id for friend in self.friends}

    @property
    def pending_requests(self):
        """Return set of user IDs who have pending friend requests to this user"""
        return {
            req.sender_id for req in self.received_requests.filter(
                FriendRequest.status == FriendRequestStatus.PENDING
            ).all()
        }

    @property
    def sent_pending_ids(self):
        """Return set of user IDs this user has sent pending requests to"""
        return {
            req.receiver_id for req in self.sent_requests.filter(
                FriendRequest.status == FriendRequestStatus.PENDING
            ).all()
        }

    # --- Friendship Methods ---
    def send_friend_request(self, user):
        if user.id == self.id:
            return False
        if user in self.friends:
            return False
        if FriendRequest.query.filter_by(sender_id=self.id, receiver_id=user.id).first():
            return False

        request = FriendRequest(sender=self, receiver=user)
        db.session.add(request)
        
        # Create notification for the receiver
        user.create_notification(
            actor=self,
            notification_type=NotificationType.FRIEND_REQUEST,
            entity_id=self.id,
            entity_type='user'
        )
        
        db.session.commit()
        return True

    def accept_friend_request(self, user):
        req = FriendRequest.query.filter_by(sender_id=user.id, receiver_id=self.id, status=FriendRequestStatus.PENDING).first()
        if not req:
            return False
        req.status = FriendRequestStatus.ACCEPTED
        self.friends.append(user)
        user.friends.append(self)
        
        # Create notification for the person who sent the request
        user.create_notification(
            actor=self,
            notification_type=NotificationType.FRIEND_ACCEPTED,
            entity_id=self.id,
            entity_type='user'
        )
        
        db.session.commit()
        return True

    def decline_friend_request(self, user):
        req = FriendRequest.query.filter_by(sender_id=user.id, receiver_id=self.id, status=FriendRequestStatus.PENDING).first()
        if not req:
            return False
        req.status = FriendRequestStatus.DECLINED
        db.session.commit()
        return True

    def remove_friend(self, user):
        if user not in self.friends:
            return False
        self.friends.remove(user)
        user.friends.remove(self)
        db.session.commit()
        return True

    def is_friend_with(self, user):
        return user in self.friends

    def has_pending_request_to(self, user):
        return user.id in self.sent_pending_ids

    def has_pending_request_from(self, user):
        return user.id in self.pending_requests
    
    @property
    def friends_list(self):
        """Return list of friends for template compatibility"""
        return self.friends.all()
    
    def has_liked_post(self, post_id):
        """Check if user has liked a specific post"""
        return Like.query.filter_by(user_id=self.id, post_id=post_id).first() is not None
    
    
    def create_notification(self, actor, notification_type, entity_id=None, entity_type=None, custom_message=None):
        """Create a notification for this user"""
        messages = {
            NotificationType.FRIEND_REQUEST: f"{actor.full_name} sent you a friend request",
            NotificationType.FRIEND_ACCEPTED: f"{actor.full_name} accepted your friend request",
            NotificationType.POST_LIKE: f"{actor.full_name} liked your post",
            NotificationType.COMMENT_LIKE: f"{actor.full_name} liked your comment",
            NotificationType.NEW_COMMENT: f"{actor.full_name} commented on your post",
            NotificationType.PROFILE_UPDATE: f"{actor.full_name} updated their profile",
            NotificationType.NEW_POST: f"{actor.full_name} created a new post",
            NotificationType.MENTION: f"{actor.full_name} mentioned you in a post"
        }
        
        message = custom_message or messages.get(notification_type, "You have a new notification")
        
        notification = Notification(
            user_id=self.id,
            actor_id=actor.id,
            type=notification_type,
            entity_id=entity_id,
            entity_type=entity_type,
            message=message
        )
        
        db.session.add(notification)
        db.session.commit()
        return notification

    @property
    def unread_notifications_count(self):
        """Count only unread notifications"""
        try:
            return Notification.query.filter_by(user_id=self.id, is_read=False).count()
        except Exception as e:
            print(f"Error in unread_notifications_count: {e}")
            return 0

    @property
    def recent_notifications(self):
        """Get recent notifications (both read and unread)"""
        try:
            return Notification.query.filter_by(user_id=self.id)\
                                    .order_by(Notification.created_at.desc())\
                                    .limit(20)\
                                    .all()
        except Exception as e:
            print(f"Error in recent_notifications: {e}")
            return []




# Friend request statuses
class FriendRequestStatus:
    PENDING = 'pending'
    ACCEPTED = 'accepted'
    DECLINED = 'declined'

# Friend Request model
class FriendRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status = db.Column(db.String(20), default=FriendRequestStatus.PENDING)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_requests')
    receiver = db.relationship('User', foreign_keys=[receiver_id], backref='received_requests')

    __table_args__ = (db.UniqueConstraint('sender_id', 'receiver_id', name='unique_request'),)

# Post model
class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    image = db.Column(db.String(255))
    video = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    author = db.relationship('User', backref='posts')
    comments = db.relationship('Comment', backref='post', lazy='dynamic', cascade='all, delete-orphan')
    likes = db.relationship('Like', backref='post', lazy='dynamic', cascade='all, delete-orphan')

    @property
    def comments_list(self):
        return self.comments.order_by(Comment.created_at.asc()).all()

    @property
    def likes_list(self):
        return self.likes.all()





    

# Comment model
class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('comment.id'), nullable=True)

    author = db.relationship('User', backref='comments')
    parent = db.relationship('Comment', remote_side=[id], backref='replies')

# Like model
class Like(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('user_id', 'post_id', name='unique_like'),)



# Notification Types
class NotificationType:
    FRIEND_REQUEST = 'friend_request'
    FRIEND_ACCEPTED = 'friend_accepted'
    POST_LIKE = 'post_like'
    COMMENT_LIKE = 'comment_like'
    NEW_COMMENT = 'new_comment'
    PROFILE_UPDATE = 'profile_update'
    NEW_POST = 'new_post'
    MENTION = 'mention'

# Notification Model
class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    actor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    type = db.Column(db.String(50), nullable=False)
    entity_id = db.Column(db.Integer)  # post_id, comment_id, etc.
    entity_type = db.Column(db.String(50))  # 'post', 'comment', 'user'
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', foreign_keys=[user_id], backref='notifications')
    actor = db.relationship('User', foreign_keys=[actor_id])

    def to_dict(self):
        return {
            'id': self.id,
            'type': self.type,
            'message': self.message,
            'is_read': self.is_read,
            'created_at': self.created_at.isoformat(),
            'actor': {
                'id': self.actor.id,
                'name': self.actor.full_name,
                'avatar': self.actor.profile_pic or url_for('static', filename='assets/img/default-avatar.png')
            },
            'entity_id': self.entity_id,
            'entity_type': self.entity_type
        }