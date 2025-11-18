#!/usr/bin/env python3
"""
KIMBELA SEEDER - UPDATED WITH BETTER IMAGES
Generates 50 fake users, posts, likes, and comments.
Run with: python seed_data.py
"""

import os
import random
import sys
from datetime import datetime, timedelta

from faker import Faker
from werkzeug.security import generate_password_hash

# === 1. Setup App & DB Context ===
try:
    from app_config import create_app, db
except ImportError as e:
    print("ERROR: Cannot import app_config. Is app_config.py in the root?")
    print(f"ImportError: {e}")
    sys.exit(1)

app = create_app()
app.app_context().push()

# === 2. Create Tables Before Importing Models ===
try:
    db.create_all()
    print("✅ Tables created successfully.")
except Exception as e:
    print(f"❌ Failed to create tables: {e}")
    sys.exit(1)

# === 3. Import Models ===
try:
    from models import User, Post, Comment, Like
except ImportError as e:
    print("ERROR: Cannot import models. Is models.py in the root?")
    print(f"ImportError: {e}")
    sys.exit(1)

# === 4. Faker Setup ===
fake = Faker(["en_US", "en_GB"])

CITIES = [
    "Lagos", "Abuja", "Port Harcourt", "Kano", "Ibadan", 
    "London", "Toronto", "Berlin", "New York", "Sydney"
]
COUNTRIES = ["Nigeria", "United States", "United Kingdom", "Canada", "Germany"]
RELIGIONS = ["Christianity", "Islam", "Atheism", "Traditional", "Other"]
ETHNICITIES = [
    "Yoruba", "Igbo", "Hausa", "Efik", "Tiv", 
    "English", "German", "Canadian", "American"
]
OCCUPATIONS = [
    "Software Engineer", "Graphic Designer", "Teacher", "Doctor", "Nurse",
    "Photographer", "Lawyer", "Architect", "Civil Engineer", "Marketing Specialist",
    "Entrepreneur", "Chef"
]
EDUCATION_LEVELS = ["High School", "Diploma", "B.Sc", "M.Sc", "PhD"]
INTERESTS = [
    "Traveling, photography, jollof",
    "Reading, yoga, hiking",
    "Afrobeats, live concerts",
    "Fitness, running, meditation",
    "Art, painting, museums",
    "Tech, coding, AI",
    "Volunteering, community",
    "Gardening, sustainability",
    "Food, wine, events",
]
MARITAL_STATUSES = ["Single", "Married", "Divorced", "Widowed"]
GENDERS = ["Male", "Female"]

# BETTER IMAGE URLS - Using reliable sources
PROFILE_PICS = [
    # Male profile pictures
    "https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=400&h=400&fit=crop&crop=face",
    "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=400&h=400&fit=crop&crop=face",
    "https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?w=400&h=400&fit=crop&crop=face",
    "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=400&h=400&fit=crop&crop=face",
    "https://images.unsplash.com/photo-1560250097-0b93528c311a?w=400&h=400&fit=crop&crop=face",
    # Female profile pictures
    "https://images.unsplash.com/photo-1494790108755-2616b612b786?w=400&h=400&fit=crop&crop=face",
    "https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=400&h=400&fit=crop&crop=face",
    "https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=400&h=400&fit=crop&crop=face",
    "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=400&h=400&fit=crop&crop=face",
    "https://images.unsplash.com/photo-1508214751196-bcfd4ca60f91?w=400&h=400&fit=crop&crop=face",
]

COVER_PICS = [
    "https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=800&h=400&fit=crop",
    "https://images.unsplash.com/photo-1469474968028-56623f02e42e?w=800&h=400&fit=crop",
    "https://images.unsplash.com/photo-1441974231531-c6227db76b6e?w=800&h=400&fit=crop",
    "https://images.unsplash.com/photo-1426604966848-d7adac402bff?w=800&h=400&fit=crop",
    "https://images.unsplash.com/photo-1501854140801-50d01698950b?w=800&h=400&fit=crop",
    "https://images.unsplash.com/photo-1470071459604-3b5ec3a7fe05?w=800&h=400&fit=crop",
    "https://images.unsplash.com/photo-1519681393784-d120267933ba?w=800&h=400&fit=crop",
]

POST_IMAGES = [
    "https://images.unsplash.com/photo-1579546929662-711aa81148cf?w=600&h=400&fit=crop",
    "https://images.unsplash.com/photo-1551963831-b3b1ca40c98e?w=600&h=400&fit=crop",
    "https://images.unsplash.com/photo-1546069901-ba9599a7e63c?w=600&h=400&fit=crop",
    "https://images.unsplash.com/photo-1567620905732-2d1ec7ab7445?w=600&h=400&fit=crop",
    "https://images.unsplash.com/photo-1565958011703-44f9829ba187?w=600&h=400&fit=crop",
    "https://images.unsplash.com/photo-1467003909585-2f8a72700288?w=600&h=400&fit=crop",
    "https://images.unsplash.com/photo-1540189549336-e6e99c3679fe?w=600&h=400&fit=crop",
    "https://images.unsplash.com/photo-1565299624946-b28f40a0ae38?w=600&h=400&fit=crop",
    "https://images.unsplash.com/photo-1565958011703-44f9829ba187?w=600&h=400&fit=crop",
    "https://images.unsplash.com/photo-1482049016688-2d3e1b311543?w=600&h=400&fit=crop",
]

POST_TEMPLATES = [
    "Just enjoyed a beautiful sunset in {city}. Life is good! 🌅",
    "Trying out a new recipe tonight: {food}. Wish me luck! 👨‍🍳",
    "Finally finished reading '{book}'. Highly recommend! 📚",
    "Great hike today with friends. {city} never disappoints. 🏞️",
    "Feeling grateful for the little things today. 🙏",
    "New profile pic! What do you think? 😊",
    "Coffee and contemplation — my kind of morning. ☕",
    "Anyone else obsessed with {hobby}? Let's connect!",
    "Throwback to last year's trip to {country}. Miss it! ✈️",
    "Weekend plans: {activity}. Who's with me? 🎉",
    "Just completed an amazing project at work! Feeling accomplished. 💼",
    "Beautiful weather today in {city}. Perfect for outdoor activities! ☀️",
    "Learning something new every day. Growth mindset! 🌱",
    "Family time is the best time. Cherishing these moments. ❤️",
    "Exploring new places and making memories. Adventure awaits! 🗺️",
]

FOODS = [
    "jollof rice", "suya", "egusi soup", "pounded yam", 
    "lasagna", "sushi", "pizza", "shawarma", "barbecue"
]
BOOKS = ["Atomic Habits", "Sapiens", "The Alchemist", "Things Fall Apart", "1984", "The Power of Now"]
HOBBIES = ["photography", "dancing", "coding", "cooking", "reading", "football", "yoga", "painting"]
ACTIVITIES = ["movie night", "beach day", "owambe", "picnic", "road trip", "game night", "brunch"]


# === Helper Functions ===
def random_dob():
    """Generate DOB between 18 and 70 years old"""
    end = datetime.now() - timedelta(days=18 * 365)
    start = datetime.now() - timedelta(days=70 * 365)
    return fake.date_between(start_date=start, end_date=end)


def random_phone():
    prefixes = ["+234", "+1", "+44", "+61", "+49"]
    prefix = random.choice(prefixes)
    if prefix == "+234":
        return f"{prefix}{random.randint(700, 999)}{random.randint(1000000, 9999999)}"
    else:
        return f"{prefix}{random.randint(200, 999)}-{random.randint(200, 999)}-{random.randint(1000, 9999)}"


def get_profile_pic(gender):
    """Get appropriate profile picture based on gender"""
    if gender == "Male":
        return random.choice(PROFILE_PICS[:5])  # First 5 are male
    else:
        return random.choice(PROFILE_PICS[5:])  # Last 5 are female


# === CREATE USERS ===
def create_users(n=50):
    print(f"\n👤 Creating {n} users...")
    users = []

    for i in range(n):
        first = fake.first_name()
        last = fake.last_name()
        email = f"{first.lower()}.{last.lower()}{random.randint(10,99)}@example.com"
        gender = random.choice(GENDERS)
        
        user = User(
            first_name=first,
            last_name=last,
            email=email,
            password_hash=generate_password_hash("SecurePass123!"),
            is_active=True,
            city=random.choice(CITIES),
            country=random.choice(COUNTRIES),
            dob=random_dob(),
            gender=gender,
            marital_status=random.choice(MARITAL_STATUSES),
            interests=random.choice(INTERESTS),
            bio=fake.paragraph(nb_sentences=2),
            about_me=fake.text(max_nb_chars=150),
            profile_pic=get_profile_pic(gender),  # Gender-appropriate profile pics
            cover_pic=random.choice(COVER_PICS),
            phone_number=random_phone(),
            ethnicity=random.choice(ETHNICITIES),
            religion=random.choice(RELIGIONS),
            occupation=random.choice(OCCUPATIONS),
            educational_level=random.choice(EDUCATION_LEVELS),
            is_premium=random.choice([True, False, False, False]),  # ~25% chance premium
        )
        db.session.add(user)
        users.append(user)

        if (i + 1) % 10 == 0:
            db.session.commit()
            print(f"   → {i + 1} users created...")

    db.session.commit()
    print(f"✅ Created {len(users)} users.")
    return users


# === CREATE POSTS ===
def create_posts(users, n=50):
    print(f"\n📝 Creating {n} posts...")
    posts = []

    for i in range(n):
        author = random.choice(users)
        content = random.choice(POST_TEMPLATES).format(
            city=author.city,
            country=author.country,
            food=random.choice(FOODS),
            book=random.choice(BOOKS),
            hobby=random.choice(HOBBIES),
            activity=random.choice(ACTIVITIES),
        )
        
        # 60% chance of having an image, 40% text-only
        image = random.choice(POST_IMAGES) if random.random() > 0.4 else None

        post = Post(
            content=content, 
            image=image, 
            author_id=author.id,
            created_at=fake.date_time_between(start_date='-30d', end_date='now')
        )
        db.session.add(post)
        posts.append(post)

        if (i + 1) % 10 == 0:
            db.session.commit()
            print(f"   → {i + 1} posts created...")

    db.session.commit()
    print(f"✅ Created {len(posts)} posts.")

    # Likes
    print("❤️ Adding likes...")
    for post in posts:
        likers = random.sample(users, k=random.randint(0, min(15, len(users))))
        for liker in likers:
            if liker.id != post.author_id:
                db.session.execute(
                    db.insert(Like).values(
                        user_id=liker.id, 
                        post_id=post.id,
                        created_at=fake.date_time_between_dates(
                            datetime_start=post.created_at, 
                            datetime_end='now'
                        )
                    )
                )
    db.session.commit()

    # Comments
    print("💬 Adding comments...")
    COMMENT_TEMPLATES = [
        "Great post! 😊",
        "I totally agree with this!",
        "This is amazing! 👏",
        "Thanks for sharing!",
        "Beautiful! ❤️",
        "So true! 🙌",
        "Love this perspective!",
        "Well said! 💯",
        "This made my day! 😄",
        "Inspiring content! 🌟"
    ]
    
    for post in posts:
        # 80% chance of having comments
        if random.random() > 0.2:
            commenters = random.sample(
                [u for u in users if u.id != post.author_id], 
                k=random.randint(1, 8)
            )
            for commenter in commenters:
                comment = Comment(
                    content=random.choice(COMMENT_TEMPLATES),
                    author_id=commenter.id,
                    post_id=post.id,
                    created_at=fake.date_time_between_dates(
                        datetime_start=post.created_at, 
                        datetime_end='now'
                    )
                )
                db.session.add(comment)
    
    db.session.commit()
    print("✅ Likes and comments added.")
    return posts


# === MAIN ===
if __name__ == "__main__":
    print("=" * 50)
    print("🚀 KIMBELA SEEDER STARTED")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    try:
        # Clear existing data (optional - uncomment if you want fresh data)
        # print("\n🗑️ Clearing existing data...")
        # db.session.query(Comment).delete()
        # db.session.query(Like).delete()
        # db.session.query(Post).delete()
        # db.session.query(User).delete()
        # db.session.commit()
        
        users = create_users(50)
        posts = create_posts(users, 50)

        print("\n🎉 SEEDING COMPLETE!")
        print(f"Total Users: {len(users)}")
        print(f"Total Posts: {len(posts)}")
        
        # Count likes and comments
        total_likes = db.session.query(Like).count()
        total_comments = db.session.query(Comment).count()
        print(f"Total Likes: {total_likes}")
        print(f"Total Comments: {total_comments}")
        
        print("\n📧 Example Login Credentials:")
        for i in range(3):
            print(f"   {i+1}. Email: {users[i].email} | Password: SecurePass123!")
        
        print("\n🔍 Sample Data Preview:")
        sample_user = users[0]
        print(f"   User: {sample_user.first_name} {sample_user.last_name}")
        print(f"   Profile Pic: {sample_user.profile_pic}")
        print(f"   Cover Pic: {sample_user.cover_pic}")
        
        sample_post = next((p for p in posts if p.image), None)
        if sample_post:
            print(f"   Sample Post with Image: {sample_post.image}")
        
        print("=" * 50)

    except Exception as e:
        print(f"\n❌ SEEDING FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)