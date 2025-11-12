from extensions import db, login_manager
from flask_login import UserMixin
from datetime import datetime, timedelta
import random, string, uuid, secrets
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask import url_for

# app/models.py  (or wherever the signal lives)

from sqlalchemy import event


# db = SQLAlchemy()


# Association table for many-to-many friendship
friendship = db.Table(
    "friendship",
    db.Column("user_id", db.Integer, db.ForeignKey("users.id"), primary_key=True),
    db.Column("friend_id", db.Integer, db.ForeignKey("users.id"), primary_key=True),
    db.Column("accepted_at", db.DateTime, default=datetime.utcnow),
)

# Many-to-many block list
# Many-to-many block list
blocked_users = db.Table(
    "blocked_users",
    db.Column("blocker_id", db.Integer, db.ForeignKey("users.id"), primary_key=True),
    db.Column("blocked_id", db.Integer, db.ForeignKey("users.id"), primary_key=True),
)

# Relationships - FIXED VERSION
# blocks = db.relationship(
#         'User',
#         secondary=blocked_users,
#         primaryjoin=(blocked_users.c.blocker_id == id),
#         secondaryjoin=(blocked_users.c.blocked_id == id),
#         backref=db.backref('blockers', lazy='dynamic'),  # Changed from 'blocked_by'
#         lazy='dynamic'
#     )


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(user_id)


# Main User model
class User(db.Model, UserMixin):
    __tablename__ = "users"
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
    gender = db.Column(db.String(20), nullable=False)
    phone_number = db.Column(db.String(20), nullable=False)
    interests = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    email_token = db.Column(db.String(255))
    email_token_expires = db.Column(db.DateTime)
    educational_level = db.Column(db.String(50), nullable=True)
    occupation = db.Column(db.String(100), nullable=True)
    ethnicity = db.Column(db.String(50), nullable=True)
    religion = db.Column(db.String(50), nullable=True)
    is_premium = db.Column(db.Boolean, default=False)
    profile_pic = db.Column(
        db.String(500),
        default="https://res.cloudinary.com/demo/image/upload/v1312461204/sample.jpg",
    )
    cover_pic = db.Column(
        db.String(500),
        default="https://res.cloudinary.com/demo/image/upload/v1312461204/sample.jpg",
    )
    bio = db.Column(db.Text, nullable=True)
    marital_status = db.Column(db.String(50), nullable=True)
    email_token = db.Column(db.String(10))
    email_token_expires = db.Column(db.DateTime)
    otp = db.Column(db.String(255), nullable=True)
    otp_expires = db.Column(db.DateTime, nullable=True)
    is_online = db.Column(db.Boolean, default=False)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    about_me = db.Column(db.Text, nullable=True)  # NEW FIELD

    # Enhanced blocking system using a proper association table
    _blocked_users = db.Table(
        "user_blocks",
        db.Column(
            "blocker_id", db.Integer, db.ForeignKey("users.id"), primary_key=True
        ),
        db.Column(
            "blocked_id", db.Integer, db.ForeignKey("users.id"), primary_key=True
        ),
        db.Column("created_at", db.DateTime, default=datetime.utcnow),
        db.UniqueConstraint("blocker_id", "blocked_id", name="uq_user_block"),
    )

    # Relationship for blocked users
    blocked_users = db.relationship(
        "User",
        secondary=_blocked_users,
        primaryjoin=(_blocked_users.c.blocker_id == id),
        secondaryjoin=(_blocked_users.c.blocked_id == id),
        backref=db.backref("blocked_by", lazy="dynamic"),
        lazy="dynamic",
    )

    def generate_otp(self):
        """Generate a 6-digit numeric OTP"""
        self.otp = f"{random.randint(0, 999999):06d}"  # always 6 digits
        self.otp_expires = datetime.utcnow() + timedelta(minutes=10)
        db.session.commit()

    # In your User model, enhance the blocked users methods:

    def get_blocked_users(self):
        """Get list of users blocked by current user"""
        return self.blocked_users.all()

    def get_blocked_users_with_details(self):
        """Get blocked users with complete details"""
        blocked_users = self.get_blocked_users()
        result = []
        for user in blocked_users:
            result.append(
                {
                    "id": user.id,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "profile_pic": user.profile_pic
                    or url_for("static", filename="assets/img/default-avatar.png"),
                    "email": user.email,
                    "created_at": user.created_at,
                }
            )
        return result

    def get_blockers(self):
        """Get list of users who blocked current user"""
        return (
            User.query.join(
                self._blocked_users, User.id == self._blocked_users.c.blocker_id
            )
            .filter(self._blocked_users.c.blocked_id == self.id)
            .all()
        )

    def is_blocked_by(self, user):
        """Check if this user is blocked by another user"""
        return (
            db.session.query(self._blocked_users)
            .filter(
                self._blocked_users.c.blocker_id == user.id,
                self._blocked_users.c.blocked_id == self.id,
            )
            .first()
            is not None
        )

    def is_blocking(self, user):
        """Check if this user is blocking another user"""
        return (
            db.session.query(self._blocked_users)
            .filter(
                self._blocked_users.c.blocker_id == self.id,
                self._blocked_users.c.blocked_id == user.id,
            )
            .first()
            is not None
        )

    def block(self, user):
        """Block a user"""
        if not self.is_blocking(user):
            stmt = self._blocked_users.insert().values(
                blocker_id=self.id, blocked_id=user.id, created_at=datetime.utcnow()
            )
            db.session.execute(stmt)

            # Remove friendship if exists
            if user in self.friends:
                self.remove_friend(user)

            # Remove any pending friend requests
            FriendRequest.query.filter(
                (
                    (FriendRequest.sender_id == self.id)
                    & (FriendRequest.receiver_id == user.id)
                )
                | (
                    (FriendRequest.sender_id == user.id)
                    & (FriendRequest.receiver_id == self.id)
                )
            ).delete()

            db.session.commit()

    def unblock(self, user):
        """Unblock a user"""
        if self.is_blocking(user):
            stmt = self._blocked_users.delete().where(
                (self._blocked_users.c.blocker_id == self.id)
                & (self._blocked_users.c.blocked_id == user.id)
            )
            db.session.execute(stmt)
            db.session.commit()

    def is_visible_to(self, viewer):
        """True if viewer can see this user (not blocked either way)"""
        return not (self.is_blocking(viewer) or self.is_blocked_by(viewer))

    def get_blocked_users_count(self):
        """Get count of blocked users"""
        return self.blocked_users.count()

    def get_blockers_count(self):
        """Get count of users who blocked this user"""
        return (
            User.query.join(
                self._blocked_users, User.id == self._blocked_users.c.blocker_id
            )
            .filter(self._blocked_users.c.blocked_id == self.id)
            .count()
        )

    def can_interact_with(self, other_user):
        """Check if users can interact (neither has blocked the other)"""
        return not (self.is_blocking(other_user) or other_user.is_blocking(self))

    # Relationships
    friends = db.relationship(
        "User",
        secondary=friendship,
        primaryjoin=(friendship.c.user_id == id),
        secondaryjoin=(friendship.c.friend_id == id),
        backref=db.backref("friend_of", lazy="dynamic"),
        lazy="dynamic",
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
        """Return list of friend user IDs"""
        return [friend.id for friend in self.friends]

    @property
    def pending_requests(self):
        """IDs of users who sent a PENDING request to me"""
        return [
            req.sender_id
            for req in self.received_requests.filter(
                FriendRequest.status == FriendRequestStatus.PENDING
            ).all()
        ]

    @property
    def sent_pending_ids(self):
        """IDs of users I sent a PENDING request to"""
        return [
            req.receiver_id
            for req in self.sent_requests.filter(
                FriendRequest.status == FriendRequestStatus.PENDING
            ).all()
        ]

    # --- Friendship Methods ---
    def send_friend_request(self, user):
        if user.id == self.id:
            return False
        if user in self.friends:
            return False
        if FriendRequest.query.filter_by(
            sender_id=self.id, receiver_id=user.id
        ).first():
            return False

        request = FriendRequest(sender=self, receiver=user)
        db.session.add(request)

        # Create notification for the receiver
        user.create_notification(
            actor=self,
            notification_type=NotificationType.FRIEND_REQUEST,
            entity_id=self.id,
            entity_type="user",
        )

        db.session.commit()
        return True

    def accept_friend_request(self, user):
        req = FriendRequest.query.filter_by(
            sender_id=user.id, receiver_id=self.id, status=FriendRequestStatus.PENDING
        ).first()
        if not req:
            return False

        req.status = FriendRequestStatus.ACCEPTED  # <-- enum
        self.friends.append(user)
        user.friends.append(self)

        # Notify the *sender* that the request was accepted
        user.create_notification(
            actor=self,
            notification_type=NotificationType.FRIEND_ACCEPTED,
            entity_id=self.id,
            entity_type="user",
        )
        db.session.commit()
        return True

    def decline_friend_request(self, user):
        req = FriendRequest.query.filter_by(
            sender_id=user.id, receiver_id=self.id, status=FriendRequestStatus.PENDING
        ).first()
        if not req:
            return False
        req.status = FriendRequestStatus.DECLINED  # <-- enum
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
        return (
            Like.query.filter_by(user_id=self.id, post_id=post_id).first() is not None
        )

    def create_notification(
        self,
        actor,
        notification_type,
        entity_id=None,
        entity_type=None,
        custom_message=None,
    ):
        """Create a notification for this user"""
        messages = {
            NotificationType.FRIEND_REQUEST: f"{actor.full_name} sent you a friend request",
            NotificationType.FRIEND_ACCEPTED: f"{actor.full_name} accepted your friend request",
            NotificationType.POST_LIKE: f"{actor.full_name} liked your post",
            NotificationType.COMMENT_LIKE: f"{actor.full_name} liked your comment",
            NotificationType.NEW_COMMENT: f"{actor.full_name} commented on your post",
            NotificationType.PROFILE_UPDATE: f"{actor.full_name} updated their profile",
            NotificationType.NEW_POST: f"{actor.full_name} created a new post",
            NotificationType.MENTION: f"{actor.full_name} mentioned you in a post",
        }

        message = custom_message or messages.get(
            notification_type, "You have a new notification"
        )

        notification = Notification(
            user_id=self.id,
            actor_id=actor.id,
            type=notification_type,
            entity_id=entity_id,
            entity_type=entity_type,
            message=message,
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
            return (
                Notification.query.filter_by(user_id=self.id)
                .order_by(Notification.created_at.desc())
                .limit(20)
                .all()
            )
        except Exception as e:
            print(f"Error in recent_notifications: {e}")
            return []

    # models.py  (inside User class)

    def is_blocked_by(self, user):
        """Check if this user is blocked by another user"""
        # Method 1: Try the relationship first
        if hasattr(self, "blockers"):
            return (
                self.blockers.filter(blocked_users.c.blocker_id == user.id).first()
                is not None
            )

        # Method 2: Direct query fallback
        from sqlalchemy import and_

        return (
            db.session.query(blocked_users)
            .filter(
                and_(
                    blocked_users.c.blocker_id == user.id,
                    blocked_users.c.blocked_id == self.id,
                )
            )
            .first()
            is not None
        )

    def is_blocking(self, user):
        """Check if this user is blocking another user"""
        if hasattr(self, "blocks"):
            return (
                self.blocks.filter(blocked_users.c.blocked_id == user.id).first()
                is not None
            )

        # Fallback
        from sqlalchemy import and_

        return (
            db.session.query(blocked_users)
            .filter(
                and_(
                    blocked_users.c.blocker_id == self.id,
                    blocked_users.c.blocked_id == user.id,
                )
            )
            .first()
            is not None
        )

    def block(self, user):
        if not self.is_blocking(user):
            # Using the relationship
            if hasattr(self, "blocks"):
                self.blocks.append(user)
            else:
                # Fallback: direct insert
                stmt = blocked_users.insert().values(
                    blocker_id=self.id, blocked_id=user.id
                )
                db.session.execute(stmt)

            # Remove friendship if exists
            if user in self.friends:
                self.remove_friend(user)
            db.session.commit()

    def unblock(self, user):
        if self.is_blocking(user):
            if hasattr(self, "blocks"):
                self.blocks.remove(user)
            else:
                # Fallback: direct delete
                stmt = blocked_users.delete().where(
                    (blocked_users.c.blocker_id == self.id)
                    & (blocked_users.c.blocked_id == user.id)
                )
                db.session.execute(stmt)
            db.session.commit()

    def is_visible_to(self, viewer):
        """True if viewer can see this user (not blocked either way)"""
        return not (self.is_blocking(viewer) or self.is_blocked_by(viewer))


# Friend request statuses
class FriendRequestStatus:
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"


# Friend Request model
class FriendRequest(db.Model):
    __tablename__ = "friend_requests"

    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    status = db.Column(db.String(20), default="pending")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    sender = db.relationship("User", foreign_keys=[sender_id], backref="sent_requests")
    receiver = db.relationship(
        "User", foreign_keys=[receiver_id], backref="received_requests"
    )

    __table_args__ = (
        db.UniqueConstraint("sender_id", "receiver_id", name="uq_friend_request"),
    )


# Post model
class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    image = db.Column(db.String(255))
    video = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    author = db.relationship("User", backref="posts")
    comments = db.relationship(
        "Comment", backref="post", lazy="dynamic", cascade="all, delete-orphan"
    )
    likes = db.relationship(
        "Like", backref="post", lazy="dynamic", cascade="all, delete-orphan"
    )

    @property
    def comments_list(self):
        return self.comments.order_by(Comment.created_at.asc()).all()

    @property
    def likes_list(self):
        return self.likes.all()


@event.listens_for(FriendRequest, "after_insert")
def maybe_create_notification(mapper, connection, target):
    if getattr(target, "_skip_notification", False):
        return

    # Use correct column names
    notification = Notification(
        user_id=target.receiver_id,  # receiver gets the notification
        actor_id=target.sender_id,  # sender is the actor
        type="friend_request",
        message=f"{target.sender.full_name} sent you a friend request",
        entity_id=target.id,
    )
    db.session.add(notification)
    db.session.commit()


# Comment model
class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey("comment.id"), nullable=True)

    author = db.relationship("User", backref="comments")
    parent = db.relationship("Comment", remote_side=[id], backref="replies")


# Like model
class Like(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint("user_id", "post_id", name="unique_like"),)


# # models.py
# class BlockedUser(db.Model):
#     __tablename__ = 'blocked_users'
#     __table_args__ = (
#         db.UniqueConstraint('blocker_id', 'blocked_id', name='uq_block'),
#         {'extend_existing': True}
#     )

#     id         = db.Column(db.Integer, primary_key=True)
#     blocker_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
#     blocked_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
#     created_at = db.Column(db.DateTime, default=datetime.utcnow)

#     blocker = db.relationship('User', foreign_keys=[blocker_id])
#     blocked = db.relationship('User', foreign_keys=[blocked_id])


# Notification Types
class NotificationType:
    FRIEND_REQUEST = "friend_request"
    FRIEND_ACCEPTED = "friend_accepted"
    POST_LIKE = "post_like"
    COMMENT_LIKE = "comment_like"
    NEW_COMMENT = "new_comment"
    PROFILE_UPDATE = "profile_update"
    NEW_POST = "new_post"
    MENTION = "mention"


# Notification Model
class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    type = db.Column(db.String(50), nullable=False)
    entity_id = db.Column(db.Integer)  # post_id, comment_id, etc.
    entity_type = db.Column(db.String(50))  # 'post', 'comment', 'user'
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", foreign_keys=[user_id], backref="notifications")
    actor = db.relationship("User", foreign_keys=[actor_id])

    def to_dict(self):
        return {
            "id": self.id,
            "type": self.type,
            "message": self.message,
            "is_read": self.is_read,
            "created_at": self.created_at.isoformat(),
            "actor": {
                "id": self.actor.id,
                "name": self.actor.full_name,
                "avatar": self.actor.profile_pic
                or url_for("static", filename="assets/img/default-avatar.png"),
            },
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
        }


from flask_socketio import emit


class Message(db.Model):
    __tablename__ = "messages"
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    status = db.Column(db.String(20), default="sent")  # sent, delivered, read

    sender = db.relationship("User", foreign_keys=[sender_id], backref="sent_messages")
    receiver = db.relationship(
        "User", foreign_keys=[receiver_id], backref="received_messages"
    )

    def to_dict(self):
        return {
            "id": self.id,
            "sender_id": self.sender_id,
            "receiver_id": self.receiver_id,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "status": self.status,
            "sender_name": self.sender.full_name,
            "sender_avatar": self.sender.profile_pic
            or url_for("static", filename="assets/img/default-avatar.png"),
        }

    @staticmethod
    def are_friends(u1, u2):
        return u2 in u1.friends
