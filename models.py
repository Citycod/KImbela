from extensions import db, login_manager
from flask_login import UserMixin
from datetime import datetime, timedelta
import random, string, uuid
from werkzeug.security import generate_password_hash, check_password_hash

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(user_id)




class User(db.Model, UserMixin):
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
        """Create a 6-digit OTP, store it and set expiry."""
        token = ''.join(random.choices(string.digits, k=6))
        self.email_token = token
        self.email_token_expires = datetime.utcnow() + timedelta(minutes=30)
        return token

    def get_id(self):
        return str(self.id)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def generate_email_token(self):
        token = ''.join(random.choices(string.ascii_letters + string.digits, k=32))
        self.email_token = token
        self.email_token_expires = datetime.utcnow() + timedelta(hours=24)
        return token

    def __repr__(self):
        role = "Super Admin" if self.is_super_admin else ("Admin" if self.is_admin else "User")
        return f"<User {self.email} | {role}>"
    
    
    
    
class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text)
    image = db.Column(db.String(500))
    video = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    author = db.relationship('User', backref='posts')
    likes = db.relationship('User', secondary='post_like', backref='liked_posts')
    comments = db.relationship('Comment', backref='post', lazy='dynamic')

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'))
    author = db.relationship('User', backref='comments')

# Association table
post_like = db.Table('post_like',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('post_id', db.Integer, db.ForeignKey('post.id'))
)