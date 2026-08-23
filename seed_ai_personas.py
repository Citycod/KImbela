"""
seed_ai_personas.py — Creates the 4 AI persona user accounts and AIPersona config records.
"""

import sys
import yaml
from werkzeug.security import generate_password_hash
from time_utils import utcnow
from app_config import app
from extensions import db
from models import User, AIPersona

PROFILE_PICS = {
    "Amara": "https://res.cloudinary.com/demo/image/upload/v1312461204/sample.jpg", # Or generated avatar URL
    "Tunde": "https://res.cloudinary.com/demo/image/upload/v1312461204/sample.jpg",
    "Ngozi": "https://res.cloudinary.com/demo/image/upload/v1312461204/sample.jpg",
    "Emeka": "https://res.cloudinary.com/demo/image/upload/v1312461204/sample.jpg",
}


def seed():
    with app.app_context():
        with open("kimbela-ai-persona-character-sheets.yaml", "r") as f:
            data = yaml.safe_load(f)

        personas_spec = data.get("personas", [])

        surnames = {
            "Amara": "Okafor",
            "Tunde": "Balogun",
            "Ngozi": "Eze",
            "Emeka": "Obi"
        }

        for p_data in personas_spec:
            name = p_data["name"]
            email = f"ai.{name.lower()}@kimbela.com"
            
            user = User.query.filter_by(email=email).first()
            if not user:
                user = User(
                    first_name=name,
                    last_name=surnames.get(name, "User"),
                    email=email,
                    password_hash=generate_password_hash("PersonaPass123!"),
                    is_active=True,
                    is_ai_persona=True,
                    city="Lagos",
                    country="Nigeria",
                    gender="Female" if name in ["Amara", "Ngozi"] else "Male",
                    phone_number="+2348000000000",
                    bio=p_data["bio_disclosure"],
                    dob=utcnow().date(),
                    profile_pic=PROFILE_PICS.get(name),
                )
                db.session.add(user)
                db.session.commit()
                print(f"✓ Created User account for {name} (ID: {user.id})")
            else:
                user.is_active = True
                user.is_ai_persona = True
                user.bio = p_data["bio_disclosure"]
                db.session.commit()
                print(f"✓ Updated existing User account for {name} (ID: {user.id}, Active: {user.is_active})")

            # Create or update AIPersona config
            persona_rec = AIPersona.query.filter_by(user_id=user.id).first()
            if not persona_rec:
                persona_rec = AIPersona(
                    user_id=user.id,
                    name=name,
                    bio_disclosure=p_data["bio_disclosure"],
                    personality=p_data["personality"],
                    interests=p_data["interests"],
                    posting_frequency=p_data["posting_frequency"],
                    comment_frequency=p_data["comment_frequency"],
                    allowed_actions=p_data["allowed_actions"],
                    forbidden_actions=p_data["forbidden_actions"],
                    escalation_rule=p_data["escalation_rule"],
                    voice_samples=p_data["voice_samples"],
                    is_active=True,
                )
                db.session.add(persona_rec)
            else:
                persona_rec.personality = p_data["personality"]
                persona_rec.bio_disclosure = p_data["bio_disclosure"]
                persona_rec.interests = p_data["interests"]
                persona_rec.escalation_rule = p_data["escalation_rule"]
                persona_rec.forbidden_actions = p_data["forbidden_actions"]

            db.session.commit()
            print(f"✓ Seeded AIPersona config for {name}")

        print("\n✅ All 4 AI Personas seeded successfully.")


if __name__ == "__main__":
    seed()
