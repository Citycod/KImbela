from extensions import db, login_manager
from flask_login import UserMixin
from datetime import datetime, timedelta
import random, string, uuid
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash


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
        db.session.commit()
        return True

    def accept_friend_request(self, user):
        req = FriendRequest.query.filter_by(sender_id=user.id, receiver_id=self.id, status=FriendRequestStatus.PENDING).first()
        if not req:
            return False
        req.status = FriendRequestStatus.ACCEPTED
        self.friends.append(user)
        user.friends.append(self)
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

