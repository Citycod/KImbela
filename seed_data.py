#!/usr/bin/env python3
"""
KIMBELA SEEDER
Generates 50 fake users, 50 posts, likes, and comments.
Run with: python seed_data.py
"""

import os
import random
import sys
from datetime import datetime, timedelta

from faker import Faker
from werkzeug.security import generate_password_hash

# === 1. Setup App & DB Context FIRST ===
try:
    from app_config import create_app, db
except ImportError as e:
    print("ERROR: Cannot import app_config. Is app_config.py in the root?")
    print(f"ImportError: {e}")
    sys.exit(1)

app = create_app()
app.app_context().push()

# === 2. Create ALL tables BEFORE importing models ===
try:
    db.create_all()
    print("All database tables created successfully.")
except Exception as e:
    print(f"Failed to create tables: {e}")
    sys.exit(1)

# === 3. NOW safely import models ===
try:
    from models import User, Post, Comment, Like
except ImportError as e:
    print("ERROR: Cannot import models. Is models.py in the root?")
    print(f"ImportError: {e}")
    sys.exit(1)

# === 4. Faker & Data Pools ===
fake = Faker(['en_US', 'en_GB', 'en_CA', 'en_AU'])  # Added Nigeria!

CITIES = [
    'Lagos', 'Abuja', 'Port Harcourt', 'Kano', 'Ibadan',  # Nigeria
    'New York', 'London', 'Toronto', 'Sydney', 'Berlin'
]
COUNTRIES = ['Nigeria', 'United States', 'United Kingdom', 'Canada', 'Germany']
INTERESTS = [
    "Traveling, photography, jollof", "Reading, yoga, hiking", "Afrobeats, live concerts",
    "Fitness, running, meditation", "Art, painting, museums", "Tech, coding, AI",
    "Volunteering, community", "Gardening, sustainability", "Food, wine, events"
]
MARITAL_STATUSES = ['Single', 'Married', 'Divorced', 'Widowed']
GENDERS = ['Male', 'Female']
IMAGE_URLS = [f"https://picsum.photos/800/600?random={i}" for i in range(1, 101)]

POST_TEMPLATES = [
    "Just enjoyed a beautiful sunset in {city}. Life is good!",
    "Trying out a new recipe tonight: {food}. Wish me luck!",
    "Finally finished reading '{book}'. Highly recommend!",
    "Great hike today with friends. {city} never disappoints.",
    "Feeling grateful for the little things today.",
    "New profile pic! What do you think?",
    "Coffee and contemplation — my kind of morning.",
    "Anyone else obsessed with {hobby}?",
    "Throwback to last year's trip to {country}. Miss it!",
    "Weekend plans: {activity}. Who's with me?"
]

FOODS = ['jollof rice', 'suya', 'egusi soup', 'pounded yam', 'lasagna', 'sushi', 'pizza']
BOOKS = ['Atomic Habits', 'Sapiens', 'The Alchemist', 'Things Fall Apart', '1984']
HOBBIES = ['photography', 'dancing', 'coding', 'cooking', 'reading', 'football']
ACTIVITIES = ['movie night', 'beach day', 'owambe', 'picnic', 'road trip']


# === Helper Functions ===
def random_dob():
    """Generate realistic DOB between 18 and 75 years old"""
    end = datetime.now() - timedelta(days=18 * 365)
    start = datetime.now() - timedelta(days=75 * 365)
    return fake.date_between(start_date=start, end_date=end)


def random_phone():
    """Generate fake Nigerian or international phone"""
    prefixes = ['+234', '+1', '+44', '+61', '+49']
    prefix = random.choice(prefixes)
    if prefix == '+234':
        return f"{prefix}{random.randint(700, 999)}{random.randint(1000000, 9999999)}"
    else:
        return f"{prefix}{random.randint(200, 999)}-{random.randint(200, 999)}-{random.randint(1000, 9999)}"


# === CREATE USERS ===
def create_users(n=50):
    print(f"\nCreating {n} users...")
    users = []

    for i in range(n):
        first = fake.first_name()
        last = fake.last_name()
        email = f"{first.lower()}.{last.lower()}{random.randint(10, 99)}@example.com"

        user = User(
            first_name=first,
            last_name=last,
            email=email,
            password_hash=generate_password_hash("SecurePass123!"),
            is_active=True,
            city=random.choice(CITIES),
            country=random.choice(COUNTRIES),
            dob=random_dob(),
            gender=random.choice(GENDERS),
            marital_status=random.choice(MARITAL_STATUSES),
            interests=random.choice(INTERESTS),
            bio=fake.paragraph(nb_sentences=2),
            profile_pic=random.choice(IMAGE_URLS),
            cover_pic=random.choice(IMAGE_URLS),
            phone_number=random_phone()
        )
        db.session.add(user)
        users.append(user)

        if (i + 1) % 10 == 0:
            db.session.commit()
            print(f"   → {i + 1} users created...")

    db.session.commit()
    print(f"Created {len(users)} users.")
    return users


# === CREATE POSTS, LIKES, COMMENTS ===
def create_posts(users, n=50):
    print(f"\nCreating {n} posts...")
    posts = []

    for i in range(n):
        author = random.choice(users)
        content = random.choice(POST_TEMPLATES).format(
            city=author.city,
            country=author.country,
            food=random.choice(FOODS),
            book=random.choice(BOOKS),
            hobby=random.choice(HOBBIES),
            activity=random.choice(ACTIVITIES)
        )
        image = random.choice(IMAGE_URLS) if random.random() > 0.4 else None

        post = Post(content=content, image=image, author_id=author.id)
        db.session.add(post)
        posts.append(post)

        if (i + 1) % 10 == 0:
            db.session.commit()
            print(f"   → {i + 1} posts created...")

    db.session.commit()
    print(f"Created {len(posts)} posts.")

    # === Add Likes ===
    print("Adding likes...")
    for post in posts:
        likers = random.sample(users, k=random.randint(0, min(15, len(users))))
        for liker in likers:
            if liker.id != post.author_id:
                db.session.execute(
                    db.insert(Like).values(user_id=liker.id, post_id=post.id)
                )
    db.session.commit()

    # === Add Comments ===
    print("Adding comments...")
    commented_posts = random.sample(posts, k=min(30, len(posts)))
    for post in commented_posts:
        commenters = random.sample(
            [u for u in users if u.id != post.author_id],
            k=random.randint(1, 5)
        )
        for commenter in commenters:
            comment = Comment(
                content=fake.sentence(nb_words=8),
                author_id=commenter.id,
                post_id=post.id
            )
            db.session.add(comment)
    db.session.commit()

    print("Likes and comments added.")
    return posts


# === MAIN ===
if __name__ == '__main__':
    print("KIMBELA SEEDER STARTED".center(50, '='))
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Database: kimbela")
    print(f"App: {app.name}\n")

    try:
        users = create_users(50)
        posts = create_posts(users, 50)

        print("\n" + "SEEDING COMPLETE!".center(50, ''))
        print("50 users created")
        print("50 posts created")
        print("Likes & comments added")
        print("\nLogin with:")
        print("   Email: any generated email")
        print("   Password: SecurePass123!")
        print("\nExample:")
        print(f"   {users[0].email} → SecurePass123!")
        print("=" * 50)

    except Exception as e:
        print(f"\nSEEDING FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)