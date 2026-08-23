import os
import sys
import random

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app_config import app
from extensions import db
from models import AIPersona, User, Post, AILog
from ai_action_engine import execute_persona_post

with app.app_context():
    print("=" * 60)
    print("🤖 RUNNING ALL ACTIVE AI PERSONAS BATCH POSTING")
    print("=" * 60)

    personas = AIPersona.query.filter_by(is_active=True).all()
    if not personas:
        print("❌ No active personas found in the database!")
        sys.exit(1)

    print(f"Found {len(personas)} active AI persona(s):\n")
    
    results = []

    for idx, persona in enumerate(personas, start=1):
        user_obj = db.session.get(User, persona.user_id)
        if not user_obj:
            print(f"[{idx}/{len(personas)}] ❌ {persona.name} (Persona ID {persona.id}): User ID {persona.user_id} missing in DB!")
            continue

        if not user_obj.is_active:
            print(f"[{idx}/{len(personas)}] ⚙️ Activating User record for {persona.name}...")
            user_obj.is_active = True
            db.session.commit()

        topics = persona.interests or ["cooking", "daily life", "weekend activities"]
        topic = random.choice(topics)

        print(f"[{idx}/{len(personas)}] 🚀 Generating post for {persona.name} about '{topic}'...")
        
        success = execute_persona_post(persona, topic, force=True)

        if success:
            db.session.commit()
            db.session.expire_all()
            latest_post = Post.query.filter_by(author_id=persona.user_id).order_by(Post.id.desc()).first()
            post_id = latest_post.id if latest_post else "N/A"
            post_content = latest_post.content if latest_post else ""
            
            results.append({
                "name": persona.name,
                "user_id": persona.user_id,
                "post_id": post_id,
                "status": "SUCCESS",
                "content": post_content
            })
            print(f"   ✅ Published Post ID {post_id}")
        else:
            results.append({
                "name": persona.name,
                "user_id": persona.user_id,
                "post_id": "N/A",
                "status": "FAILED",
                "content": ""
            })
            print(f"   ❌ Failed to publish post for {persona.name}")
        print("-" * 60)

    print("\n" + "=" * 60)
    print("📊 BATCH EXECUTION SUMMARY")
    print("=" * 60)
    for r in results:
        status_icon = "✅" if r["status"] == "SUCCESS" else "❌"
        print(f"{status_icon} {r['name']} (User ID {r['user_id']}) -> Post ID: {r['post_id']}")
        if r["content"]:
            print(f"   Content: '{r['content'][:70]}...'")
    print("=" * 60)
