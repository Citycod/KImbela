import os
import sys
sys.path.insert(0, '/home/uplix/uplix/KImbela')
from ai_service import _call_groq, _build_system_prompt

persona_config = {
    "name": "Amara",
    "personality": "Friendly",
    "interests": ["weekend markets"],
    "forbidden_actions": [],
    "escalation_rule": "none",
    "voice_samples": [],
}
user_prompt = "Write a short, engaging post about weekend markets. Keep it under 150 words. Do not use hashtags."
system_prompt = _build_system_prompt(persona_config)

print("Calling Groq...")
raw_output = _call_groq(system_prompt, user_prompt)
print("--- RAW OUTPUT ---")
print(repr(raw_output))
