from extensions import db, login_manager
from flask_login import UserMixin
from datetime import datetime, timedelta
import random, string, uuid, secrets
import json  # Add this import
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask import url_for, current_app
from sqlalchemy import event, func
import requests

from time_utils import utcnow


friendship = db.Table(
    "friendship",
    db.Column("user_id", db.Integer, db.ForeignKey("users.id"), primary_key=True),
    db.Column("friend_id", db.Integer, db.ForeignKey("users.id"), primary_key=True),
    db.Column("accepted_at", db.DateTime, default=utcnow),
)

blocked_users = db.Table(
    "blocked_users",
    db.Column("blocker_id", db.Integer, db.ForeignKey("users.id"), primary_key=True),
    db.Column("blocked_id", db.Integer, db.ForeignKey("users.id"), primary_key=True),
)


@login_manager.user_loader
def load_user(user_id):
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return None

    try:
        return db.session.get(User, user_id)
    except Exception:
        return None


group_members = db.Table(
    "group_members",
    db.Column("user_id", db.Integer, db.ForeignKey("users.id", ondelete="CASCADE")),
    db.Column("group_id", db.Integer, db.ForeignKey("groups.id", ondelete="CASCADE")),
)


# Main User model
class User(db.Model, UserMixin):
    __tablename__ = "users"

    __table_args__ = (
        # Single column indexes
        db.Index("idx_users_email", "email", unique=True),
        db.Index("idx_users_is_online", "is_online"),
        db.Index("idx_users_last_seen", "last_seen"),
        db.Index("idx_users_city", "city"),
        db.Index("idx_users_country", "country"),
        db.Index("idx_users_gender", "gender"),
        db.Index("idx_users_created_at", "created_at"),
        # Composite indexes for common queries
        db.Index(
            "idx_users_marketplace_status",
            "marketplace_subscription_status",
            "marketplace_subscription_expires",
        ),
        db.Index("idx_users_featured_until", "marketplace_featured_until"),
        db.Index("idx_users_city_country", "city", "country"),
        db.Index("idx_users_gender_country", "gender", "country"),
    )

    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(
        db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4())
    )
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_super_admin = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=False)
    city = db.Column(db.String(50), nullable=False)
    country = db.Column(db.String(50), nullable=False)
    state = db.Column(db.String(50), nullable=True)
    dob = db.Column(db.Date, nullable=False)
    gender = db.Column(db.String(20), nullable=False)
    phone_number = db.Column(db.String(20), nullable=False)
    interests = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(
        db.DateTime, default=utcnow, onupdate=utcnow
    )

    educational_level = db.Column(db.String(50), nullable=True)
    occupation = db.Column(db.String(100), nullable=True)
    ethnicity = db.Column(db.String(50), nullable=True)
    religion = db.Column(db.String(50), nullable=True)
    is_premium = db.Column(db.Boolean, default=False)

    is_featured_seller = db.Column(db.Boolean, default=False)

    # Email preferences
    receive_promotional_emails = db.Column(db.Boolean, default=True)
    receive_subscription_reminders = db.Column(db.Boolean, default=True)

    # FIXED: Payment transactions relationship
    campaigns = db.relationship("AdCampaign", back_populates="user", lazy="dynamic")

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
    last_seen = db.Column(db.DateTime, default=utcnow)
    about_me = db.Column(db.Text, nullable=True)
    admin_role = db.Column(db.String(50), default="moderator")
    admin_permissions = db.Column(db.Text)

    password_reset_token = db.Column(db.String(255), nullable=True, unique=True)
    password_reset_expires = db.Column(db.DateTime, nullable=True)

    # Marketplace subscription fields
    marketplace_subscription_id = db.Column(
        db.Integer, db.ForeignKey("marketplace_subscriptions.id"), nullable=True
    )
    marketplace_subscription_status = db.Column(
        db.String(20), default="inactive"
    )  # inactive, active, expired
    marketplace_subscription_expires = db.Column(db.DateTime)
    marketplace_subscription_tier = db.Column(
        db.String(50), default="free"
    )  # free, basic, pro, enterprise
    marketplace_featured_until = db.Column(
        db.DateTime
    )  # When featured visibility expires

    # Relationship
    marketplace_subscription = db.relationship(
        "MarketplaceSubscription", foreign_keys=[marketplace_subscription_id]
    )

    # Enhanced blocking system using a proper association table
    _blocked_users = db.Table(
        "user_blocks",
        db.Column(
            "blocker_id", db.Integer, db.ForeignKey("users.id"), primary_key=True
        ),
        db.Column(
            "blocked_id", db.Integer, db.ForeignKey("users.id"), primary_key=True
        ),
        db.Column("created_at", db.DateTime, default=utcnow),
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

    # Friends relationship
    friends = db.relationship(
        "User",
        secondary=friendship,
        primaryjoin=(friendship.c.user_id == id),
        secondaryjoin=(friendship.c.friend_id == id),
        backref=db.backref("friend_of", lazy="dynamic"),
        lazy="dynamic",
    )

    comments = db.relationship(
        "Comment", back_populates="author", cascade="all, delete-orphan", lazy="dynamic"
    )

    def get_unsubscribe_token(self):
        """Generate unsubscribe token"""
        import jwt

        payload = {
            "user_id": self.id,
            "type": "email_unsubscribe",
            "exp": utcnow() + timedelta(days=365),
        }
        return jwt.encode(payload, current_app.config["SECRET_KEY"], algorithm="HS256")

    @property
    def avg_rating(self):
        """Get average rating for seller"""
        if hasattr(self, "seller_rating") and self.seller_rating:
            return self.seller_rating.average_rating
        return 0.0

    @property
    def review_count(self):
        """Get total review count for seller"""
        if hasattr(self, "seller_rating") and self.seller_rating:
            return self.seller_rating.total_reviews
        return 0

    def get_reviews(self, limit=None, service_id=None):
        """Get seller reviews"""
        query = MarketplaceReview.query.filter_by(
            seller_id=self.id, status="approved"
        ).order_by(MarketplaceReview.created_at.desc())

        if service_id:
            query = query.filter_by(service_id=service_id)

        if limit:
            query = query.limit(limit)

        return query.all()

    def has_purchased_from(self, seller_id):
        """Check if user has purchased from seller (for verified reviews)"""
        # This should check your purchase/order records
        # For now, returning True for demo purposes
        return True  # Implement actual purchase verification

    def can_review_seller(self, seller_id):
        """Check if user can review seller"""
        if self.id == seller_id:
            return False  # Cannot review yourself

        # Check if already reviewed recently
        existing_review = MarketplaceReview.query.filter_by(
            buyer_id=self.id, seller_id=seller_id, review_type="seller"
        ).first()

        return existing_review is None

    def can_review_service(self, service_id):
        """Check if user can review service"""
        service = MarketplaceService.query.get(service_id)
        if not service:
            return False

        if self.id == service.seller_id:
            return False  # Cannot review your own service

        # Check if already reviewed
        existing_review = MarketplaceReview.query.filter_by(
            buyer_id=self.id, service_id=service_id
        ).first()

        return existing_review is None

    @property
    def has_active_marketplace_subscription(self):
        """Check if user has an active marketplace subscription"""
        # First check: Do they have a valid subscription status and expiration?
        if not self.marketplace_subscription_expires:
            return False

        if self.marketplace_subscription_status != "active":
            return False

        if utcnow() > self.marketplace_subscription_expires:
            return False

        # SECONDARY CHECK: Do they have at least one completed payment?
        # This prevents showing "Subscribed" for users with fake expiration dates
        try:
            from models import MarketplacePayment

            completed_payments = MarketplacePayment.query.filter_by(
                user_id=self.id, status="completed"
            ).count()

            if completed_payments == 0:
                # No actual payments, so not really subscribed
                return False

        except Exception as e:
            # If we can't check payments, at least use the date check
            print(f"⚠️ Could not check payments for user {self.id}: {e}")

        return True

    def is_friend_with(self, user):
        """Check if this user is friends with another user"""
        return user in self.friends

    def can_interact_with(self, user):
        """Check if user can interact with another user (not blocked)"""
        # Check if either user has blocked the other
        is_blocked = (user in self.blocked_users) or (self in user.blocked_users)
        return not is_blocked

    @property
    def full_name(self):
        """Get full name"""
        return f"{self.first_name} {self.last_name}"

    @property
    def uuid(self):
        return self.public_id

    @property
    def age(self):
        """Calculate the user's age based on dob"""
        if not self.dob:
            return None
        today = utcnow().date()
        return today.year - self.dob.year - ((today.month, today.day) < (self.dob.month, self.dob.day))

    @property
    def is_birthday_today(self):
        """Check if today is the user's birthday"""
        if not self.dob:
            return False
        today = utcnow().date()
        return today.month == self.dob.month and today.day == self.dob.day

    def get_friends(self):
        """Get all friends"""
        return self.friends.all()

    @property
    def is_marketplace_featured(self):
        """Check if seller is currently featured"""
        if not self.marketplace_featured_until:
            return False
        return self.marketplace_featured_until > utcnow()

    # All other User methods remain the same...
    def generate_password_reset_token(self):
        """Generate a password reset token that expires in 1 hour"""
        self.password_reset_token = secrets.token_urlsafe(32)
        self.password_reset_expires = utcnow() + timedelta(hours=1)
        return self.password_reset_token

    @staticmethod
    def verify_password_reset_token(token):
        """Verify password reset token and return user if valid"""
        if not token:
            return None
        return User.query.filter(
            User.password_reset_token == token,
            User.password_reset_expires > utcnow(),
        ).first()

    def get_user_reaction(self, post_id):
        """Get user's reaction for a specific post"""
        reaction = Reaction.query.filter_by(user_id=self.id, post_id=post_id).first()
        return reaction.reaction_type if reaction else None

    def has_reacted_to_post(self, post_id):
        """Check if user has reacted to a post"""
        return (
            Reaction.query.filter_by(user_id=self.id, post_id=post_id).first()
            is not None
        )

    def has_admin_permission(self, permission):
        """Check if admin has specific permission"""
        if self.is_super_admin:
            return True
        if not self.admin_permissions:
            return False
        try:
            permissions = json.loads(self.admin_permissions)
            return permission in permissions
        except:
            return False

    def generate_otp(self):
        """Generate a 6-digit numeric OTP"""
        self.otp = f"{random.randint(0, 999999):06d}"
        self.otp_expires = utcnow() + timedelta(minutes=10)
        db.session.commit()
        return self.otp

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
                blocker_id=self.id, blocked_id=user.id, created_at=utcnow()
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

        req.status = FriendRequestStatus.ACCEPTED
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

    def get_friend_request_status(self, other_user_id):
        """Check the status of friend request between users"""
        # Check if we sent a request
        sent_request = FriendRequest.query.filter(
            FriendRequest.sender_id == self.id,
            FriendRequest.receiver_id == other_user_id,
            FriendRequest.status == "pending",
        ).first()

        if sent_request:
            return "sent"

        # Check if we received a request
        received_request = FriendRequest.query.filter(
            FriendRequest.sender_id == other_user_id,
            FriendRequest.receiver_id == self.id,
            FriendRequest.status == "pending",
        ).first()

        if received_request:
            return "received"

        # Check if already friends
        if self.is_friend_with(User.query.get(other_user_id)):
            return "friends"

        return "none"

    def decline_friend_request(self, user):
        req = FriendRequest.query.filter_by(
            sender_id=user.id, receiver_id=self.id, status=FriendRequestStatus.PENDING
        ).first()
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
            NotificationType.POST_SHARE: f"{actor.full_name} shared your post",
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

    # In User class
    @property
    def unread_notifications_count(self):
        """Count only unread notifications - OPTIMIZED"""
        try:
            # Use direct SQL count for speed
            count = Notification.query.filter_by(user_id=self.id, is_read=False).count()
            return count
        except Exception as e:
            current_app.logger.error(f"Error in unread_notifications_count: {e}")
            return 0

    @property
    def recent_notifications(self):
        """Get recent notifications - OPTIMIZED"""
        try:
            # Only load essential fields and limit to 20
            notifications = (
                Notification.query.filter_by(user_id=self.id)
                .order_by(Notification.created_at.desc())
                .limit(20)
                .all()
            )

            return notifications
        except Exception as e:
            current_app.logger.error(f"Error in recent_notifications: {e}")
            return []


# Friend request statuses
class FriendRequestStatus:
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"


# Friend Request model
class FriendRequest(db.Model):
    __tablename__ = "friend_requests"

    __table_args__ = (
        db.Index("idx_friend_requests_sender_id", "sender_id"),
        db.Index("idx_friend_requests_receiver_id", "receiver_id"),
        db.Index("idx_friend_requests_status", "status"),
        db.Index(
            "idx_friend_requests_sender_receiver_status",
            "sender_id",
            "receiver_id",
            "status",
        ),
        db.Index("idx_friend_requests_created_at", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    status = db.Column(db.String(20), default="pending")
    created_at = db.Column(db.DateTime, default=utcnow)

    sender = db.relationship("User", foreign_keys=[sender_id], backref="sent_requests")
    receiver = db.relationship(
        "User", foreign_keys=[receiver_id], backref="received_requests"
    )

    __table_args__ = (
        db.UniqueConstraint("sender_id", "receiver_id", name="uq_friend_request"),
    )


# Post model
class Post(db.Model):
    __tablename__ = "posts"

    __table_args__ = (
        # Foreign key indexes
        db.Index("idx_posts_author_id", "author_id"),
        db.Index("idx_posts_group_id", "group_id"),
        # Timestamp indexes (very important for sorting)
        db.Index("idx_posts_created_at", "created_at"),
        # Composite indexes
        db.Index("idx_posts_author_created", "author_id", "created_at"),
        db.Index("idx_posts_group_created", "group_id", "created_at"),
        db.Index("idx_post_author_created", "author_id", "created_at"),
        db.Index("idx_post_created", "created_at"),
        db.Index("idx_post_author", "author_id"),
        # Text search optimization (for LIKE queries)
        # db.Index('idx_posts_content_trgm', 'content', postgresql_using='gin', postgresql_ops={'content': 'gin_trgm_ops'}),
    )

    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(
        db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4())
    )
    content = db.Column(db.Text, nullable=False)
    image = db.Column(db.String(255))
    video = db.Column(db.String(255))
    gif = db.Column(db.String(255), nullable=True)
    location = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=True)
    shared_post_id = db.Column(db.Integer, db.ForeignKey("posts.id"), nullable=True)
    share_type = db.Column(db.String(20), default="original")

    author = db.relationship("User", backref="posts")
    shared_post = db.relationship(
        "Post", remote_side=[id], backref="shared_posts", foreign_keys=[shared_post_id]
    )
    comments = db.relationship(
        "Comment", backref="post", lazy="select", cascade="all, delete-orphan"
    )
    likes = db.relationship(
        "Like",
        backref="post",
        lazy="select",  # or "joined" – both work
        cascade="all, delete-orphan",
    )

    emoji_data = db.Column(db.JSON, nullable=True)

    def get_emoji_data(self):
        """Get parsed emoji/sticker/GIF data"""
        if self.emoji_data:
            return self.emoji_data
        return {}

    @property
    def uuid(self):
        return self.public_id

    @property
    def comments_count(self):
        return len(self.comments) if self.comments else 0

    @property
    def reactions_count(self):
        """Get total number of reactions (likes, love, etc.) on this post"""
        return self.get_reaction_count()  # Uses your existing efficient query

    @property
    def comments_list(self):
        """Return ordered list of comments for template compatibility"""
        return self.comments.order_by(Comment.created_at.asc()).all()

    def get_reaction_count(self):
        """Get total reaction count"""
        return Reaction.query.filter_by(post_id=self.id).count()

    @property
    def likes_list(self):
        return self.likes.all()

    # Enhanced reaction methods - MOVED FROM REACTION CLASS
    def toggle_reaction(self, user_id, reaction_type):
        """Toggle reaction for a post"""
        existing_reaction = Reaction.query.filter_by(
            user_id=user_id, post_id=self.id
        ).first()

        if existing_reaction:
            if existing_reaction.reaction_type == reaction_type:
                # Remove reaction if same type clicked again
                db.session.delete(existing_reaction)
                db.session.commit()
                return False, "removed"
            else:
                # Update reaction type
                existing_reaction.reaction_type = reaction_type
                db.session.commit()
                return True, "updated"
        else:
            # Add new reaction
            new_reaction = Reaction(
                user_id=user_id, post_id=self.id, reaction_type=reaction_type
            )
            db.session.add(new_reaction)
            db.session.commit()
            return True, "added"

    def get_reaction_count(self):
        """Get total reaction count"""
        return Reaction.query.filter_by(post_id=self.id).count()

    def get_user_reaction(self, user_id):
        """Get user's reaction for this post"""
        reaction = Reaction.query.filter_by(user_id=user_id, post_id=self.id).first()
        return reaction.reaction_type if reaction else None

    def get_reaction_breakdown(self):
        """Get count of each reaction type"""
        from sqlalchemy import func

        breakdown = (
            db.session.query(Reaction.reaction_type, func.count(Reaction.id))
            .filter(Reaction.post_id == self.id)
            .group_by(Reaction.reaction_type)
            .all()
        )
        return dict(breakdown)


# @event.listens_for(FriendRequest, "after_insert")
# def maybe_create_notification(mapper, connection, target):
#     if getattr(target, "_skip_notification", False):
#         return
#
#     notification = Notification(
#         user_id=target.receiver_id,
#         actor_id=target.sender_id,
#         type="friend_request",
#         message=f"{target.sender.full_name} sent you a friend request",
#         entity_id=target.id,
#     )
#     db.session.add(notification)
#     db.session.commit()


# Comment model
class Comment(db.Model):
    __tablename__ = "comments"

    __table_args__ = (
        db.Index("idx_comments_post_id", "post_id"),
        db.Index("idx_comments_author_id", "author_id"),
        db.Index("idx_comments_parent_id", "parent_id"),
        db.Index("idx_comments_created_at", "created_at"),
        db.Index("idx_comments_post_created", "post_id", "created_at"),
        db.Index("idx_comments_author_post", "author_id", "post_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey("posts.id"), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey("comments.id"), nullable=True)

    # Relationships - FIXED
    author = db.relationship(
        "User", back_populates="comments"
    )  # This references User.comments

    # Self-referential relationship
    parent = db.relationship(
        "Comment",
        remote_side=[id],
        backref="replies",  # Using backref is simpler here
        foreign_keys=[parent_id],
    )


# Like model
class Like(db.Model):

    __tablename__ = "likes"

    __table_args__ = (
        db.Index("idx_likes_user_id", "user_id"),
        db.Index("idx_likes_post_id", "post_id"),
        db.Index("idx_likes_user_post", "user_id", "post_id"),
        db.Index("idx_likes_created_at", "created_at"),
        db.Index("ix_like_post", "post_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey("posts.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)

    __table_args__ = (db.UniqueConstraint("user_id", "post_id", name="unique_like"),)


# Notification Types
class NotificationType:
    FRIEND_REQUEST = "friend_request"
    FRIEND_ACCEPTED = "friend_accepted"
    POST_LIKE = "post_like"
    POST_SHARE = "post_share"
    COMMENT_LIKE = "comment_like"
    NEW_COMMENT = "new_comment"
    PROFILE_UPDATE = "profile_update"
    NEW_POST = "new_post"
    MENTION = "mention"


# Notification Model
class Notification(db.Model):

    __tablename__ = "notifications"

    __table_args__ = (
        db.Index("idx_notifications_user_id", "user_id"),
        db.Index("idx_notifications_actor_id", "actor_id"),
        db.Index("idx_notifications_is_read", "is_read"),
        db.Index("idx_notifications_created_at", "created_at"),
        db.Index("idx_notifications_type", "type"),
        db.Index("idx_notifications_user_unread", "user_id", "is_read", "created_at"),
        # db.Index('ix_notification_user_read', 'user_id', 'read'),
        db.Index("ix_notification_created", "created_at"),
        db.Index("ix_notification_user_created", "user_id", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    type = db.Column(db.String(50), nullable=False)
    entity_id = db.Column(db.Integer)
    entity_type = db.Column(db.String(50))
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=utcnow)

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


class Message(db.Model):
    __tablename__ = "messages"

    __table_args__ = (
        # For finding conversations between users
        db.Index("idx_messages_sender_receiver", "sender_id", "receiver_id"),
        db.Index("idx_messages_receiver_sender", "receiver_id", "sender_id"),
        # Timestamp for chronological ordering
        db.Index("idx_messages_timestamp", "timestamp"),
        # Composite index for conversation history
        db.Index("idx_messages_conversation", "sender_id", "receiver_id", "timestamp"),
        db.Index("idx_messages_unread_status", "receiver_id", "status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=utcnow, index=True)
    status = db.Column(db.String(20), default="sent")
    message_type = db.Column(db.String(20), default="text")
    message_data = db.Column(db.JSON, nullable=True)
    is_deleted = db.Column(db.Boolean, default=False)
    edited_at = db.Column(db.DateTime)

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
            "message_type": self.message_type,
            "message_data": self.message_data if self.message_data else {},
            "is_deleted": self.is_deleted,
            "edited_at": self.edited_at.isoformat() if self.edited_at else None,
            "sender_name": self.sender.full_name,
            "sender_avatar": self.sender.profile_pic
            or url_for("static", filename="assets/img/default-avatar.png"),
        }

    @staticmethod
    def are_friends(u1, u2):
        return u2 in u1.friends


class Group(db.Model):
    __tablename__ = "groups"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    category = db.Column(db.String(50))
    image = db.Column(db.String(500))
    is_private = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    created_by = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at = db.Column(db.DateTime, default=utcnow)
    member_count = db.Column(db.Integer, default=0)

    creator = db.relationship(
        "User", foreign_keys=[created_by], backref="created_groups"
    )
    members = db.relationship(
        "User", secondary=group_members, backref="user_groups", lazy="dynamic"
    )

    def update_member_count(self):
        """Update the member count from the actual relationship"""
        self.member_count = self.members.count()
        db.session.commit()

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "image": self.image,
            "is_private": self.is_private,
            "is_active": self.is_active,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat(),
            "member_count": self.member_count,
        }


class SponsoredAd(db.Model):
    __tablename__ = "sponsored_ads"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    image = db.Column(db.String(500))
    target_audience = db.Column(db.String(50), default="all")
    start_date = db.Column(db.DateTime, nullable=False)
    end_date = db.Column(db.DateTime, nullable=False)
    budget = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(20), default="active")
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=utcnow)
    clicks = db.Column(db.Integer, default=0)
    impressions = db.Column(db.Integer, default=0)

    creator = db.relationship("User", foreign_keys=[created_by])


class ReportedContent(db.Model):
    __tablename__ = "reported_content"
    id = db.Column(db.Integer, primary_key=True)
    reporter_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    reported_user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    content_type = db.Column(db.String(50))
    content_id = db.Column(db.Integer)
    reason = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default="pending")
    admin_notes = db.Column(db.Text)
    resolved_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    resolved_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=utcnow)

    reporter = db.relationship("User", foreign_keys=[reporter_id])
    reported_user = db.relationship("User", foreign_keys=[reported_user_id])
    resolver = db.relationship("User", foreign_keys=[resolved_by])


class ActivityLog(db.Model):
    __tablename__ = "activity_logs"

    __table_args__ = (
        db.Index("idx_activity_created_at", "created_at"),
        db.Index("idx_activity_user_id", "user_id"),
        db.Index("idx_activity_path", "path"),
        db.Index("idx_activity_event_type", "event_type"),
        db.Index("idx_activity_ip", "ip_address"),
        db.Index("idx_activity_country", "country"),
    )

    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    is_authenticated = db.Column(db.Boolean, default=False)

    event_type = db.Column(db.String(30), nullable=False, default="page")
    path = db.Column(db.String(255), nullable=False)
    method = db.Column(db.String(10), nullable=False)
    status_code = db.Column(db.Integer, nullable=False)
    query_string = db.Column(db.Text)
    referrer = db.Column(db.Text)
    user_agent = db.Column(db.Text)

    ip_address = db.Column(db.String(45))
    country = db.Column(db.String(80))
    region = db.Column(db.String(120))
    city = db.Column(db.String(120))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)

    response_ms = db.Column(db.Integer)

    user = db.relationship("User", foreign_keys=[user_id])


class SiteSetting(db.Model):
    __tablename__ = "site_settings"

    key = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.Text, nullable=True)
    updated_at = db.Column(
        db.DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    @classmethod
    def get_value(cls, key, default=None):
        setting = cls.query.filter_by(key=key).first()
        if setting is None or setting.value is None:
            return default
        return setting.value

    @classmethod
    def set_value(cls, key, value):
        setting = cls.query.filter_by(key=key).first()
        if setting is None:
            setting = cls(key=key, value=value)
            db.session.add(setting)
        else:
            setting.value = value
        return setting


class Reaction(db.Model):
    __tablename__ = "reactions"

    __table_args__ = (
        db.Index("idx_reactions_user_id", "user_id"),
        db.Index("idx_reactions_post_id", "post_id"),
        db.Index("idx_reactions_user_post", "user_id", "post_id"),
        db.Index("idx_reactions_created_at", "created_at"),
        db.Index("idx_reactions_type", "reaction_type"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    post_id = db.Column(
        db.Integer, db.ForeignKey("posts.id", ondelete="CASCADE"), nullable=False
    )
    reaction_type = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)

    # Fixed relationships with proper cascade
    user = db.relationship(
        "User", backref=db.backref("reactions", cascade="all, delete-orphan")
    )
    post = db.relationship(
        "Post", backref=db.backref("post_reactions", cascade="all, delete-orphan")
    )

    __table_args__ = (
        db.UniqueConstraint("user_id", "post_id", name="unique_user_post_reaction"),
    )


# Add these new models to your existing models.py
class AdCampaign(db.Model):
    __tablename__ = "ad_campaigns"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    # Ad content
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    image = db.Column(db.Text)
    target_url = db.Column(db.String(500))
    call_to_action = db.Column(db.String(50), default="Learn More")

    # Campaign details
    status = db.Column(db.String(20), default="pending")
    start_date = db.Column(db.DateTime)
    end_date = db.Column(db.DateTime)
    budget = db.Column(db.Float, nullable=False)  # Total budget
    daily_budget = db.Column(db.Float, nullable=False)  # Daily budget
    duration_days = db.Column(db.Integer, nullable=False)
    placement = db.Column(db.String(50), default="sponsored")

    # Tracking
    impressions = db.Column(db.Integer, default=0)
    clicks = db.Column(db.Integer, default=0)
    click_through_rate = db.Column(db.Float, default=0.0)

    # Payment
    payment_status = db.Column(db.String(20), default="pending")
    payment_gateway = db.Column(db.String(20))
    payment_id = db.Column(db.String(255))
    currency = db.Column(db.String(3), default="USD")

    # Targeting fields
    target_gender = db.Column(db.Text)  # JSON string of genders
    target_age_min = db.Column(db.Integer, default=18)
    target_age_max = db.Column(db.Integer, default=65)
    target_country = db.Column(db.String(100))
    target_state = db.Column(db.String(100))
    target_city = db.Column(db.String(100))
    target_countries = db.Column(db.Text)  # JSON string of countries
    target_interests = db.Column(db.Text)  # JSON string of interests
    target_education = db.Column(db.Text)  # JSON string of education levels
    target_occupation = db.Column(db.Text)  # JSON string of occupations
    target_relationship = db.Column(db.Text)  # JSON string of relationship statuses
    target_language = db.Column(db.String(50))  # Single language

    # Additional targeting fields
    target_devices = db.Column(db.Text)  # JSON string of devices
    target_platforms = db.Column(db.Text)  # JSON string of platforms

    # Expiration tracking
    expiry_notification_sent = db.Column(db.Boolean, default=False)
    auto_renew = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(
        db.DateTime, default=utcnow, onupdate=utcnow
    )

    # FIXED: Relationship without conflicts
    user = db.relationship("User", foreign_keys=[user_id], back_populates="campaigns")

    def get_targeting_data(self):
        """Return targeting data as a dictionary"""
        return {
            "gender": json.loads(self.target_gender) if self.target_gender else [],
            "age_min": self.target_age_min,
            "age_max": self.target_age_max,
            "country": self.target_country,
            "state": self.target_state,
            "city": self.target_city,
            "countries": (
                json.loads(self.target_countries) if self.target_countries else []
            ),
            "interests": (
                json.loads(self.target_interests) if self.target_interests else []
            ),
            "education": (
                json.loads(self.target_education) if self.target_education else []
            ),
            "occupation": (
                json.loads(self.target_occupation) if self.target_occupation else []
            ),
            "relationship": (
                json.loads(self.target_relationship) if self.target_relationship else []
            ),
            "language": self.target_language,
            "devices": json.loads(self.target_devices) if self.target_devices else [],
            "platforms": (
                json.loads(self.target_platforms) if self.target_platforms else []
            ),
        }


class PaymentTransaction(db.Model):
    __tablename__ = "payment_transactions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    # Support both ad campaigns and matchmaking requests
    campaign_id = db.Column(db.Integer, db.ForeignKey("ad_campaigns.id"), nullable=True)
    matchmaking_request_id = db.Column(
        db.Integer, db.ForeignKey("matchmaking_requests.id"), nullable=True
    )

    amount = db.Column(db.Numeric(10, 2), nullable=False)
    currency = db.Column(db.String(3), default="USD")
    gateway = db.Column(db.String(50))  # 'flutterwave', 'paypal', etc.
    gateway_reference = db.Column(db.String(100), unique=True)
    gateway_payment_id = db.Column(db.String(100))
    gateway_status = db.Column(db.String(50))
    gateway_metadata = db.Column(db.Text)

    # Make sure this field exists
    transaction_type = db.Column(
        db.String(20), default="ad_campaign"
    )  # 'ad_campaign' or 'matchmaking'

    status = db.Column(
        db.String(20), default="pending"
    )  # 'pending', 'completed', 'failed'
    description = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(
        db.DateTime, default=utcnow, onupdate=utcnow
    )

    # FIXED: Use string references
    user = db.relationship(
        "User",
        foreign_keys=[user_id],
        backref=db.backref("payment_transactions", lazy=True),
    )
    campaign = db.relationship(
        "AdCampaign",
        foreign_keys=[campaign_id],
        backref=db.backref("payments", lazy=True),
    )
    matchmaking_request = db.relationship(
        "MatchmakingRequest",
        foreign_keys=[matchmaking_request_id],
        backref=db.backref("payment_transactions", lazy=True),
    )


class AdPackage(db.Model):
    __tablename__ = "ad_packages"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Float, nullable=False)
    duration_days = db.Column(db.Integer, nullable=False)
    impressions = db.Column(db.Integer)
    features = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=utcnow)

    # campaigns = db.relationship("AdCampaign", backref="ad_package", lazy=True)


# Add these to your existing models


class MatchmakingPackage(db.Model):
    __tablename__ = "matchmaking_packages"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Float, nullable=False)
    duration_days = db.Column(db.Integer, nullable=False)
    features = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=utcnow)

    # FIXED: Use string reference for forward declaration
    matchmaking_requests = db.relationship(
        "MatchmakingRequest", back_populates="package", lazy=True
    )


class MatchmakingRequest(db.Model):
    __tablename__ = "matchmaking_requests"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    package_id = db.Column(
        db.Integer, db.ForeignKey("matchmaking_packages.id"), nullable=False
    )

    # Partner Preferences
    min_age = db.Column(db.Integer)
    max_age = db.Column(db.Integer)
    partner_gender = db.Column(db.String(20), default="any")
    partner_ethnicity = db.Column(db.String(50))
    partner_religion = db.Column(db.String(50))

    # Interests & Lists (stored as JSON strings)
    partner_interests = db.Column(db.Text)  # List of interests they want in partner
    your_interests = db.Column(db.Text)  # User's own interests
    lifestyles = db.Column(db.Text)  # User's lifestyle choices

    # NEW: Precise location preferences for ideal partner
    partner_country = db.Column(db.String(100))  # e.g., "Nigeria"
    partner_state = db.Column(db.String(100))  # e.g., "Lagos"
    partner_city = db.Column(db.String(100))  # e.g., "Ikeja"

    # Backward compatibility: old multi-country selection
    target_countries = db.Column(db.Text)  # JSON list of countries (kept for legacy)

    # About the user
    about_you = db.Column(db.Text, nullable=False)
    ideal_partner = db.Column(db.Text, nullable=False)
    image = db.Column(db.Text)  # URL to uploaded photo

    # Request details
    status = db.Column(
        db.String(20), default="pending"
    )  # pending, active, expired, cancelled
    start_date = db.Column(db.DateTime, default=utcnow)
    end_date = db.Column(db.DateTime)

    # Payment
    payment_status = db.Column(db.String(20), default="pending")
    payment_gateway = db.Column(db.String(20))

    # Tracking
    views = db.Column(db.Integer, default=0)
    likes = db.Column(db.Integer, default=0)
    matches = db.Column(db.Integer, default=0)

    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(
        db.DateTime, default=utcnow, onupdate=utcnow
    )

    # Relationships
    user = db.relationship("User", foreign_keys=[user_id])
    package = db.relationship(
        "MatchmakingPackage",
        foreign_keys=[package_id],
        back_populates="matchmaking_requests",
    )

    # Payment transaction
    @property
    def payment_transaction(self):
        """Get the payment transaction for this matchmaking request"""
        return PaymentTransaction.query.filter_by(
            matchmaking_request_id=self.id
        ).first()

    # Helper methods for JSON fields
    def get_partner_interests(self):
        if self.partner_interests:
            try:
                return json.loads(self.partner_interests)
            except:
                return []
        return []

    def get_your_interests(self):
        if self.your_interests:
            try:
                return json.loads(self.your_interests)
            except:
                return []
        return []

    def get_lifestyles(self):
        if self.lifestyles:
            try:
                return json.loads(self.lifestyles)
            except:
                return []
        return []

    def get_target_countries(self):
        """Legacy: returns list of countries from old multi-select"""
        if self.target_countries:
            try:
                return json.loads(self.target_countries)
            except:
                return []
        return []

    def is_active(self):
        """Check if the request is currently active"""
        return (
            self.status == "active"
            and self.end_date
            and self.end_date > utcnow()
        )

    def get_location_display(self):
        """Return a nicely formatted location string for display"""
        parts = [self.partner_city, self.partner_state, self.partner_country]
        parts = [p for p in parts if p]  # Remove empty/None
        return ", ".join(parts) or "Any Location"

    def __repr__(self):
        return f"<MatchmakingRequest {self.id} - User {self.user_id} - {self.status}>"


class MatchmakingLike(db.Model):
    __tablename__ = "matchmaking_likes"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    request_id = db.Column(
        db.Integer, db.ForeignKey("matchmaking_requests.id"), nullable=False
    )
    created_at = db.Column(db.DateTime, default=utcnow)

    user = db.relationship("User", foreign_keys=[user_id])
    request = db.relationship("MatchmakingRequest", foreign_keys=[request_id])

    __table_args__ = (
        db.UniqueConstraint("user_id", "request_id", name="unique_matchmaking_like"),
    )


class MatchmakingView(db.Model):
    __tablename__ = "matchmaking_views"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    request_id = db.Column(
        db.Integer, db.ForeignKey("matchmaking_requests.id"), nullable=False
    )
    created_at = db.Column(db.DateTime, default=utcnow)

    user = db.relationship("User", foreign_keys=[user_id])
    request = db.relationship("MatchmakingRequest", foreign_keys=[request_id])


class MatchmakingPayments(db.Model):
    __tablename__ = "matchmaking_payments"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    matchmaking_request_id = db.Column(
        db.Integer, db.ForeignKey("matchmaking_requests.id"), nullable=False
    )
    package_id = db.Column(
        db.Integer, db.ForeignKey("matchmaking_packages.id"), nullable=False
    )

    # Payment details
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(10), default="USD")
    gateway = db.Column(
        db.String(50), default="flutterwave"
    )  # 'flutterwave', 'paypal', etc.
    gateway_reference = db.Column(db.String(100), unique=True)  # tx_ref for Flutterwave
    gateway_payment_id = db.Column(db.String(100))  # Flutterwave transaction ID
    gateway_status = db.Column(db.String(50))  # Status from payment gateway

    # Payment status
    status = db.Column(
        db.String(20), default="pending"
    )  # 'pending', 'completed', 'failed', 'cancelled'
    payment_status = db.Column(
        db.String(20), default="pending"
    )  # 'pending', 'paid', 'failed'

    # Metadata
    gateway_metadata = db.Column(db.Text)  # JSON response from payment gateway
    description = db.Column(db.Text)

    # Timestamps
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(
        db.DateTime, default=utcnow, onupdate=utcnow
    )
    paid_at = db.Column(db.DateTime)  # When payment was completed

    # Relationships
    user = db.relationship(
        "User", backref=db.backref("matchmaking_payments", lazy=True)
    )
    matchmaking_request = db.relationship(
        "MatchmakingRequest", backref=db.backref("payments", lazy=True)
    )
    package = db.relationship(
        "MatchmakingPackage", backref=db.backref("payments", lazy=True)
    )

    def __repr__(self):
        return f"<MatchmakingPayment {self.id} - {self.status} - ${self.amount}>"

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "matchmaking_request_id": self.matchmaking_request_id,
            "package_id": self.package_id,
            "amount": self.amount,
            "currency": self.currency,
            "gateway": self.gateway,
            "gateway_reference": self.gateway_reference,
            "gateway_payment_id": self.gateway_payment_id,
            "gateway_status": self.gateway_status,
            "status": self.status,
            "payment_status": self.payment_status,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "paid_at": self.paid_at.isoformat() if self.paid_at else None,
        }


# Add these new models to your existing models.py file


class MarketplaceCategory(db.Model):
    """Categories for marketplace services"""

    __tablename__ = "marketplace_categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False)
    icon = db.Column(db.String(50))
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    parent_id = db.Column(
        db.Integer, db.ForeignKey("marketplace_categories.id"), nullable=True
    )
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=utcnow)

    # Relationships
    parent = db.relationship(
        "MarketplaceCategory", remote_side=[id], backref="subcategories"
    )
    services = db.relationship("MarketplaceService", backref="category", lazy="dynamic")

    def __repr__(self):
        return f"<MarketplaceCategory {self.name}>"


class MarketplaceService(db.Model):
    """Services listed in the marketplace"""

    __tablename__ = "marketplace_services"

    __table_args__ = (
        # Foreign key indexes
        db.Index("idx_services_seller_id", "seller_id"),
        db.Index("idx_services_category_id", "category_id"),
        db.Index("idx_services_subscription_id", "subscription_id"),
        # Status and filtering indexes
        db.Index("idx_services_status", "status"),
        db.Index("idx_services_is_featured", "is_featured"),
        db.Index("idx_services_service_type", "service_type"),
        db.Index("idx_services_price", "price"),
        # Composite indexes for common queries
        db.Index("idx_services_category_status", "category_id", "status"),
        db.Index("idx_services_featured_status", "is_featured", "status"),
        db.Index("idx_services_seller_status", "seller_id", "status"),
        db.Index("idx_services_created_at", "created_at"),
        # For sorting and pagination
        db.Index("idx_services_rating_views", "average_rating", "views"),
        db.Index("idx_services_price_created", "price", "created_at"),
        db.Index("idx_services_country", "country"),
        db.Index("idx_services_state", "state"),
        db.Index("idx_services_city", "city"),
        db.Index("idx_services_country_state_city", "country", "state", "city"),
        # Text search optimization
        # db.Index('idx_services_title_trgm', 'title', postgresql_using='gin', postgresql_ops={'title': 'gin_trgm_ops'}),
        # db.Index('idx_services_description_trgm', 'description', postgresql_using='gin', postgresql_ops={'description': 'gin_trgm_ops'}),
    )

    id = db.Column(db.Integer, primary_key=True)
    seller_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    category_id = db.Column(
        db.Integer, db.ForeignKey("marketplace_categories.id"), nullable=False
    )

    # Service details
    title = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(200), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=False)
    short_description = db.Column(db.String(500))
    service_type = db.Column(db.String(50), default="service")  # "service" or "digital"
    earnings = db.Column(db.Numeric(10, 2), default=0)
    currency = db.Column(db.String(10), default="USD")

    # Pricing
    price = db.Column(db.Numeric(10, 2), default=0)
    is_free = db.Column(db.Boolean, default=False)
    is_featured = db.Column(db.Boolean, default=False)

    # Digital product specific
    digital_file = db.Column(db.String(500))  # For e-books, courses, etc.
    file_size = db.Column(db.String(20))
    file_type = db.Column(db.String(50))
    download_count = db.Column(db.Integer, default=0)

    # Subscription reminder tracking
    expiry_reminder_sent = db.Column(db.Boolean, default=False)
    welcome_email_sent = db.Column(db.Boolean, default=False)

    # Ranking score for sorting
    ranking_score = db.Column(db.Float, default=0.0)

    # Service specific
    duration = db.Column(db.String(50))  # e.g., "60 min", "4 sessions"
    availability = db.Column(db.String(200))  # e.g., "Mon-Fri, 9AM-5PM"
    country = db.Column(db.String(128))
    state = db.Column(db.String(128))
    city = db.Column(db.String(128))

    # Contact methods (JSON encoded)
    contact_methods = db.Column(
        db.Text, default=json.dumps(["whatsapp", "phone", "messenger"])
    )
    phone_number = db.Column(db.String(30))
    whatsapp_number = db.Column(db.String(30))
    email = db.Column(db.String(100))

    # Add these fields for better file management
    digital_file = db.Column(db.String(500))  # Cloudinary URL
    file_name = db.Column(db.String(255))  # Original filename
    file_size = db.Column(db.Integer)  # Size in bytes
    file_type = db.Column(db.String(100))  # MIME type
    cloudinary_public_id = db.Column(db.String(255))  # Cloudinary public ID

    # Media
    cover_image = db.Column(db.String(500))
    gallery_images = db.Column(db.Text)  # JSON encoded list of image URLs
    video_url = db.Column(db.String(500))

    # Status
    status = db.Column(
        db.String(50), default="pending"
    )  # pending, active, rejected, paused, sold_out, awaiting_subscription
    rejection_reason = db.Column(db.Text)

    # Features (JSON encoded)
    features = db.Column(db.Text)

    # Stats
    views = db.Column(db.Integer, default=0)
    clicks = db.Column(db.Integer, default=0)
    shares = db.Column(db.Integer, default=0)

    # Seller subscription
    subscription_id = db.Column(
        db.Integer, db.ForeignKey("marketplace_subscriptions.id")
    )
    subscription_status = db.Column(db.String(20), default="active")
    subscription_expires = db.Column(db.DateTime)

    # Review stats
    average_rating = db.Column(db.Float, default=0.0)
    review_count = db.Column(db.Integer, default=0)

    # SEO
    meta_title = db.Column(db.String(200))
    meta_description = db.Column(db.Text)
    keywords = db.Column(db.Text)

    # Dates
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(
        db.DateTime, default=utcnow, onupdate=utcnow
    )
    published_at = db.Column(db.DateTime)

    # Relationships
    seller = db.relationship("User", foreign_keys=[seller_id])
    subscription = db.relationship("MarketplaceSubscription", back_populates="services")
    reviews = db.relationship(
        "MarketplaceReview",
        backref="service",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<MarketplaceService {self.title}>"

    @property
    def contact_methods_list(self):
        """Get contact methods as list"""
        try:
            return json.loads(self.contact_methods)
        except:
            return ["whatsapp", "phone", "messenger"]

    @property
    def gallery_images_list(self):
        """Get gallery images as list"""
        if self.gallery_images:
            try:
                return json.loads(self.gallery_images)
            except:
                return []
        return []

    @property
    def features_list(self):
        """Get features as list"""
        if self.features:
            try:
                return json.loads(self.features)
            except:
                return []
        return []

    @property
    def whatsapp_link(self):
        """Generate WhatsApp link with pre-filled message"""
        if self.whatsapp_number:
            message = f"Hi {self.seller.first_name}, I saw your service '{self.title}' on Kimbela Marketplace and I'm interested. Can you tell me more?"
            phone = self.whatsapp_number.replace("+", "").replace(" ", "")
            return f"https://wa.me/{phone}?text={requests.utils.quote(message)}"
        return None

    @property
    def is_active(self):
        """Check if service is active and subscription is valid"""
        return (
            self.status == "active"
            and self.subscription_status == "active"
            and (
                self.subscription_expires is None
                or self.subscription_expires > utcnow()
            )
        )

    def update_review_stats(self):
        """Update service review statistics"""
        reviews = MarketplaceReview.query.filter_by(
            service_id=self.id, status="approved"
        ).all()

        if reviews:
            total_rating = sum([r.rating for r in reviews])
            self.average_rating = round(total_rating / len(reviews), 1)
            self.review_count = len(reviews)
        else:
            self.average_rating = 0.0
            self.review_count = 0

        db.session.commit()

    def get_reviews(self, limit=None, sort="newest"):
        """Get service reviews with sorting"""
        query = MarketplaceReview.query.filter_by(service_id=self.id, status="approved")

        if sort == "helpful":
            query = query.order_by(MarketplaceReview.helpful_count.desc())
        elif sort == "highest":
            query = query.order_by(MarketplaceReview.rating.desc())
        elif sort == "lowest":
            query = query.order_by(MarketplaceReview.rating.asc())
        else:  # newest
            query = query.order_by(MarketplaceReview.created_at.desc())

        if limit:
            query = query.limit(limit)

        return query.all()


class MarketplaceSubscription(db.Model):
    """Subscription plans for sellers"""

    __tablename__ = "marketplace_subscriptions"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text)

    # Pricing
    price_tokens = db.Column(db.Integer, nullable=False)
    price_usd = db.Column(db.Float, nullable=False)
    billing_period = db.Column(
        db.String(20), default="monthly"
    )  # monthly, yearly, lifetime
    trial_days = db.Column(db.Integer, default=0)

    # Features
    max_services = db.Column(db.Integer, default=1)  # 0 = unlimited
    max_images = db.Column(db.Integer, default=5)
    is_featured = db.Column(db.Boolean, default=False)
    can_add_video = db.Column(db.Boolean, default=False)
    can_add_contact = db.Column(db.Boolean, default=True)
    can_add_digital = db.Column(db.Boolean, default=True)
    support_level = db.Column(
        db.String(20), default="basic"
    )  # basic, priority, premium

    # Display
    badge_color = db.Column(db.String(20), default="blue")
    is_popular = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)

    # Order
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=utcnow)

    # Relationships
    services = db.relationship(
        "MarketplaceService", back_populates="subscription", lazy="dynamic"
    )

    def __repr__(self):
        return f"<MarketplaceSubscription {self.name}>"


class MarketplaceReview(db.Model):
    """Reviews for marketplace services"""

    __tablename__ = "marketplace_reviews"

    id = db.Column(db.Integer, primary_key=True)
    service_id = db.Column(
        db.Integer, db.ForeignKey("marketplace_services.id"), nullable=False
    )
    buyer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    seller_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # Review details
    rating = db.Column(db.Integer, nullable=False)  # 1-5
    title = db.Column(db.String(200))
    comment = db.Column(db.Text, nullable=False)

    # Type of review (service or seller) - ADD THIS
    review_type = db.Column(db.String(20), default="service")  # 'service' or 'seller'

    # Response
    seller_response = db.Column(db.Text)
    seller_response_at = db.Column(db.DateTime)

    # Status
    is_verified = db.Column(db.Boolean, default=False)  # Verified purchase
    is_featured = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(20), default="approved")  # pending, approved, rejected

    # For compatibility with your route - ADD THIS
    # Or rename is_verified to is_verified_purchase in your route
    @property
    def is_verified_purchase(self):
        """Alias for is_verified"""
        return self.is_verified

    @is_verified_purchase.setter
    def is_verified_purchase(self, value):
        self.is_verified = value

    # Review images - ADD THIS
    review_images = db.Column(db.Text)  # JSON encoded list of image URLs

    # Dates
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(
        db.DateTime, default=utcnow, onupdate=utcnow
    )

    # Relationships
    buyer = db.relationship("User", foreign_keys=[buyer_id])

    # Add this method:
    def has_user_voted(self, user_id, is_helpful):
        """Check if a user has voted on this review"""
        from models import ReviewHelpfulVote  # Import here to avoid circular imports

        vote = ReviewHelpfulVote.query.filter_by(
            review_id=self.id, user_id=user_id, is_helpful=is_helpful
        ).first()

        return vote is not None

    # Also add a method to check if user voted at all (for either helpful or not helpful)
    def get_user_vote(self, user_id):
        """Get user's vote on this review"""
        from models import ReviewHelpfulVote

        vote = ReviewHelpfulVote.query.filter_by(
            review_id=self.id, user_id=user_id
        ).first()

        if vote:
            return "helpful" if vote.is_helpful else "not_helpful"
        return None

    def __repr__(self):
        return f"<MarketplaceReview {self.id} - {self.rating} stars>"

    @property
    def review_images_list(self):
        """Get review images as list"""
        if self.review_images:
            try:
                import json

                return json.loads(self.review_images)
            except:
                return []
        return []


class SellerRating(db.Model):
    """Aggregate seller ratings (updated when new reviews are added)"""

    __tablename__ = "seller_ratings"

    id = db.Column(db.Integer, primary_key=True)
    seller_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    # Aggregate stats
    average_rating = db.Column(db.Float, default=0.0)
    total_reviews = db.Column(db.Integer, default=0)
    rating_1 = db.Column(db.Integer, default=0)  # Count of 1-star ratings
    rating_2 = db.Column(db.Integer, default=0)  # Count of 2-star ratings
    rating_3 = db.Column(db.Integer, default=0)  # Count of 3-star ratings
    rating_4 = db.Column(db.Integer, default=0)  # Count of 4-star ratings
    rating_5 = db.Column(db.Integer, default=0)  # Count of 5-star ratings

    # Communication rating (if applicable)
    communication_rating = db.Column(db.Float, default=0.0)

    # Last updated
    updated_at = db.Column(
        db.DateTime, default=utcnow, onupdate=utcnow
    )

    def update_stats(self):
        """Update aggregate stats from reviews"""
        from models import MarketplaceReview  # Import here to avoid circular import

        reviews = MarketplaceReview.query.filter_by(
            seller_id=self.seller_id, status="approved"
        ).all()

        self.total_reviews = len(reviews)

        if reviews:
            total_rating = sum([r.rating for r in reviews])
            self.average_rating = round(total_rating / self.total_reviews, 1)

            # Reset counts
            self.rating_1 = 0
            self.rating_2 = 0
            self.rating_3 = 0
            self.rating_4 = 0
            self.rating_5 = 0

            # Count ratings
            for review in reviews:
                if review.rating == 1:
                    self.rating_1 += 1
                elif review.rating == 2:
                    self.rating_2 += 1
                elif review.rating == 3:
                    self.rating_3 += 1
                elif review.rating == 4:
                    self.rating_4 += 1
                elif review.rating == 5:
                    self.rating_5 += 1

        db.session.commit()

    def get_rating_percentage(self, star):
        """Get percentage for specific star rating"""
        if self.total_reviews == 0:
            return 0
        count = getattr(self, f"rating_{star}", 0)
        return round((count / self.total_reviews) * 100, 1)


class MarketplacePayment(db.Model):
    """Payments for marketplace subscriptions"""

    __tablename__ = "marketplace_payments"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    subscription_id = db.Column(
        db.Integer, db.ForeignKey("marketplace_subscriptions.id"), nullable=False
    )
    service_id = db.Column(
        db.Integer, db.ForeignKey("marketplace_services.id"), nullable=True
    )

    # Payment details
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(10), default="USD")
    tokens_paid = db.Column(db.Integer, nullable=False)

    # Gateway
    gateway = db.Column(db.String(50), default="flutterwave")
    gateway_reference = db.Column(db.String(100), unique=True)
    gateway_payment_id = db.Column(db.String(100))
    gateway_status = db.Column(db.String(50))
    gateway_metadata = db.Column(db.Text)

    # Status
    status = db.Column(
        db.String(20), default="pending"
    )  # pending, completed, failed, refunded
    payment_method = db.Column(db.String(50))  # card, bank, mobile_money, etc.

    # Period
    start_date = db.Column(db.DateTime, default=utcnow)
    end_date = db.Column(db.DateTime)

    # Metadata
    description = db.Column(db.Text)

    # Dates
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(
        db.DateTime, default=utcnow, onupdate=utcnow
    )
    paid_at = db.Column(db.DateTime)

    # Relationships
    user = db.relationship("User", foreign_keys=[user_id])
    subscription = db.relationship(
        "MarketplaceSubscription", foreign_keys=[subscription_id]
    )
    service = db.relationship("MarketplaceService", foreign_keys=[service_id])

    def __repr__(self):
        return f"<MarketplacePayment {self.id} - {self.status} - ${self.amount}>"


class MarketplaceClick(db.Model):
    """Track clicks on services"""

    __tablename__ = "marketplace_clicks"

    id = db.Column(db.Integer, primary_key=True)
    service_id = db.Column(
        db.Integer, db.ForeignKey("marketplace_services.id"), nullable=False
    )
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    # Click details
    click_type = db.Column(db.String(50))  # view, contact, whatsapp, phone, email
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.Text)

    # Date
    created_at = db.Column(db.DateTime, default=utcnow)

    # Relationships
    service = db.relationship("MarketplaceService", foreign_keys=[service_id])
    user = db.relationship("User", foreign_keys=[user_id])

    def __repr__(self):
        return f"<MarketplaceClick {self.id} - {self.click_type}>"


class ApiKey(db.Model):
    __tablename__ = "api_keys"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    name = db.Column(db.String(100))
    key = db.Column(db.String(100), unique=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=utcnow)
    last_used = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User", backref=db.backref("api_keys", lazy=True))


class LoginHistory(db.Model):
    __tablename__ = "login_history"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    ip_address = db.Column(db.String(50))
    user_agent = db.Column(db.Text)
    device = db.Column(db.String(200))
    location = db.Column(db.String(200))
    success = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=utcnow)

    user = db.relationship("User", backref=db.backref("login_history", lazy=True))


class UserSession(db.Model):
    __tablename__ = "user_sessions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    session_id = db.Column(db.String(100), unique=True)
    ip_address = db.Column(db.String(50))
    user_agent = db.Column(db.Text)
    device = db.Column(db.String(200))
    location = db.Column(db.String(200))
    last_active = db.Column(db.DateTime, default=utcnow)
    created_at = db.Column(db.DateTime, default=utcnow)

    user = db.relationship("User", backref=db.backref("active_sessions", lazy=True))


# Add to models.py if not already there
class MarketplaceSubscriptionPlan(db.Model):
    __tablename__ = "marketplace_subscription_plans"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Float, nullable=False)  # Price in USD
    price_ngn = db.Column(db.Float, nullable=False)  # Price in NGN
    duration_days = db.Column(db.Integer, nullable=False)  # 30, 90, 365
    features = db.Column(db.Text)  # JSON encoded features
    is_featured = db.Column(db.Boolean, default=False)
    max_services = db.Column(db.Integer, default=5)
    priority_visibility = db.Column(db.Boolean, default=False)
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=utcnow)

    # Method to get features as list
    @property
    def features_list(self):
        if self.features:
            try:
                return json.loads(self.features)
            except:
                return []
        return []


class BirthdayNotification(db.Model):
    __tablename__ = "birthday_notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    birthday_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    birthday_date = db.Column(db.Date, nullable=False)
    is_seen = db.Column(db.Boolean, default=False)
    is_wished = db.Column(db.Boolean, default=False)
    wish_message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=utcnow)
    wished_at = db.Column(db.DateTime)

    # Relationships
    user = db.relationship(
        "User", foreign_keys=[user_id], backref="birthday_notifications"
    )
    birthday_user = db.relationship("User", foreign_keys=[birthday_user_id])


class Country(db.Model):
    __tablename__ = "countries"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False, unique=True, index=True)
    iso2 = db.Column(db.String(2), nullable=True, index=True)
    iso3 = db.Column(db.String(3), nullable=True, index=True)


class State(db.Model):
    __tablename__ = "states"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False, index=True)
    country_id = db.Column(
        db.Integer, db.ForeignKey("countries.id", ondelete="CASCADE"), nullable=False
    )
    country = db.relationship("Country", backref=db.backref("states", lazy="dynamic"))

    __table_args__ = (db.Index("ix_states_country_name", "country_id", "name"),)


class City(db.Model):
    __tablename__ = "cities"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False, index=True)
    state_id = db.Column(
        db.Integer, db.ForeignKey("states.id", ondelete="CASCADE"), nullable=False
    )
    country_id = db.Column(
        db.Integer, db.ForeignKey("countries.id", ondelete="CASCADE"), nullable=False
    )
    state = db.relationship("State", backref=db.backref("cities", lazy="dynamic"))
    country = db.relationship("Country", backref=db.backref("cities", lazy="dynamic"))

    __table_args__ = (db.Index("ix_cities_state_name", "state_id", "name"),)

