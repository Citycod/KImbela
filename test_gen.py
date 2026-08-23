import os
import sys

# Setup context
sys.path.insert(0, '/home/uplix/uplix/KImbela')
from app_config import app
from models import AIPersona
from ai_action_engine import execute_persona_post
import random

with app.app_context():
    persona = AIPersona.query.filter_by(is_active=True).first()
    topic = "weekend markets" # Force the same topic as the user
    
    print(f"Testing persona post for {persona.name} on topic '{topic}'...")
    
    # Let's bypass the test_client and just check what `generate_content` does
    from ai_service import generate_content
    
    persona_config = {
        "name": persona.name,
        "personality": persona.personality,
        "interests": persona.interests,
        "forbidden_actions": persona.forbidden_actions,
        "escalation_rule": persona.escalation_rule,
        "voice_samples": persona.voice_samples,
    }
    
    user_prompt = (
        f"Write a short, engaging post about {topic}. "
        f"Keep it under 150 words. Do not use hashtags."
    )
    
    response = generate_content(persona_config, user_prompt)
    print("Is Escalated:", response.is_escalated)
    print("Provider used:", response.provider_used)
    print("Generated Content:", repr(response.content))
