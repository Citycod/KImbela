import sys
sys.path.insert(0, '/home/uplix/uplix/KImbela')
from app_config import app
from models import AIPersona
from ai_action_engine import execute_persona_post, get_daily_action_count, MAX_DAILY_POSTS
import logging

logging.basicConfig(level=logging.INFO)

with app.app_context():
    persona = AIPersona.query.filter_by(name="Amara").first()
    count = get_daily_action_count(persona.id, "CREATE_POST")
    print(f"Amara daily posts: {count} / {MAX_DAILY_POSTS}")
    
    # Try generating a post directly
    from ai_service import generate_content, _build_system_prompt
    
    persona_config = {
        "name": persona.name,
        "personality": persona.personality,
        "interests": persona.interests,
        "forbidden_actions": persona.forbidden_actions,
        "escalation_rule": persona.escalation_rule,
        "voice_samples": persona.voice_samples,
    }
    
    user_prompt = "Write a short, engaging post about cooking. Keep it under 150 words. Do not use hashtags."
    print("Calling generate_content...")
    try:
        response = generate_content(persona_config, user_prompt)
        print("Generated content length:", len(response.content))
        print("Raw Content:", repr(response.content))
    except Exception as e:
        print("Exception during generate_content:", repr(e))
