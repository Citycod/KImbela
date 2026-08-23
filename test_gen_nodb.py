import os
import sys

# Setup context
sys.path.insert(0, '/home/uplix/uplix/KImbela')

from ai_service import generate_content

persona_config = {
    "name": "Amara",
    "personality": "Friendly",
    "interests": ["weekend markets"],
    "forbidden_actions": [],
    "escalation_rule": "none",
    "voice_samples": [],
}

user_prompt = (
    f"Write a short, engaging post about weekend markets. "
    f"Keep it under 150 words. Do not use hashtags."
)

print("Running generate_content...")
response = generate_content(persona_config, user_prompt)
print("Is Escalated:", response.is_escalated)
print("Provider used:", response.provider_used)
print("Generated Content:", repr(response.content))
