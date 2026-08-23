import os
import sys

# Ensure app context
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app_config import app
from extensions import db
from models import AIPersona, User, Post, AILog
from ai_service import generate_content
from flask_login import login_user
from flask_wtf.csrf import generate_csrf
from flask import session
import random

with app.app_context():
    print("=" * 60)
    print("🔍 KIMBELA AI POST DIAGNOSTIC SCRIPT")
    print("=" * 60)
    
    # 1. Fetch persona
    persona = AIPersona.query.filter_by(is_active=True).first()
    if not persona:
        print("❌ ERROR: No active AIPersona found in database!")
        sys.exit(1)
        
    print(f"1. Persona Loaded: {persona.name} (User ID: {persona.user_id})")
    
    user_obj = db.session.get(User, persona.user_id)
    if not user_obj:
        print(f"❌ ERROR: User record ID {persona.user_id} for persona does NOT exist!")
        sys.exit(1)
    print(f"   User record found: {user_obj.first_name} {user_obj.last_name} ({user_obj.email})")

    # 2. Topic & Prompt
    topic = random.choice(persona.interests) if persona.interests else "cooking"
    print(f"2. Selected Topic: '{topic}'")
    
    persona_config = {
        "name": persona.name,
        "personality": persona.personality,
        "interests": persona.interests,
        "forbidden_actions": persona.forbidden_actions,
        "escalation_rule": persona.escalation_rule,
        "voice_samples": persona.voice_samples,
    }
    user_prompt = f"Write a casual short social post for your feed about: {topic}."

    # 3. Generate AI Content
    print("3. Calling AI Generation Service...")
    try:
        response = generate_content(persona_config, user_prompt)
        print(f"   Provider Used: {response.provider_used}")
        print(f"   Latency: {response.latency_ms}ms")
        print(f"   Is Escalated: {response.is_escalated}")
        print(f"   Generated Content ({len(response.content)} chars):")
        print(f"   --> '{response.content}'")
    except Exception as e:
        print(f"❌ ERROR during generate_content: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    if not response.content.strip():
        print("❌ ERROR: Generated content is EMPTY after stripping think blocks!")
        sys.exit(1)

    # 4. Test Client Authentication & CSRF
    print("\n4. Setting up Test Client & Authenticated Session...")
    with app.test_client() as client:
        with app.test_request_context("/"):
            login_user(user_obj)
            csrf_token = generate_csrf()
            session_data = dict(session)
            print("   CSRF Token generated:", csrf_token[:20] + "...")
            print("   Session Keys created:", list(session_data.keys()))

        with client.session_transaction() as sess:
            for k, v in session_data.items():
                sess[k] = v

        # 5. Submit POST to /user_dashboard
        print("\n5. Submitting POST request to /user_dashboard...")
        res = client.post(
            "/user_dashboard",
            data={"post_content": response.content, "csrf_token": csrf_token},
            follow_redirects=False,
        )

        print(f"   HTTP Status Code: {res.status_code}")
        print(f"   Location Header: {res.location}")
        
        # If redirected to login
        if res.status_code == 302 and "/login" in (res.location or ""):
            print("❌ FAIL: Request was REDIRECTED TO LOGIN! @login_required blocked access.")
            sys.exit(1)
            
        # If non-302 status (e.g. 400 Bad Request or 500 Error)
        if res.status_code not in (200, 302):
            print("❌ FAIL: Server returned non-redirect status!")
            print("   Response Body Snippet:")
            print(res.data.decode('utf-8', errors='ignore')[:1000])
            sys.exit(1)

        # 6. Check database for Post
        print("\n6. Checking Database for newly created Post record...")
        db.session.commit()
        db.session.expire_all()
        
        latest_post = Post.query.filter_by(author_id=persona.user_id).order_by(Post.id.desc()).first()
        if not latest_post:
            print("❌ FAIL: No post found in DB for this author ID!")
            sys.exit(1)
            
        print(f"   Latest Post ID in DB: {latest_post.id}")
        print(f"   Latest Post Content in DB: '{latest_post.content}'")
        print(f"   Created At: {latest_post.created_at}")

        if latest_post.content == response.content:
            print("\n" + "=" * 60)
            print("🎉 SUCCESS! THE POST WAS PUBLISHED TO THE LIVE FEED!")
            print(f"   Post ID: {latest_post.id}")
            print(f"   Author: {persona.name} (User ID {persona.user_id})")
            print(f"   Content: {latest_post.content}")
            print("=" * 60)
        else:
            print("\n❌ FAIL: Post content mismatch!")
            print(f"   Expected: '{response.content}'")
            print(f"   Found in DB: '{latest_post.content}'")
