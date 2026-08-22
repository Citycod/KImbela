from app_config import app
from ai_action_engine import execute_persona_post
from models import AIPersona

with app.app_context():
    p = AIPersona.query.first()
    if p:
        try:
            execute_persona_post(p, 'hello')
            print("Success")
        except Exception as e:
            print(f"Failed: {e}")
