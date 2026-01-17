#!/usr/bin/env python3
"""
Quick fix for Redis connection issues.
Run this before starting your server.
"""
import os

# Create a .env.local file with memory storage for rate limiting
env_content = """# Local development overrides
REDIS_URL=memory://
FLASK_ENV=development
FLASK_DEBUG=1
"""

with open(".env.local", "w") as f:
    f.write(env_content)

print("✅ Created .env.local with memory storage for rate limiting")
print("💡 Now run: source .env.local && python runserver.py")
