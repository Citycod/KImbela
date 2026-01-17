# rate_limit_config.py
from extensions import limiter

# Define rate limits for specific endpoints
rate_limit_config = {
    "user.user_dashboard": "10 per minute",
    "messaging.get_friends": "30 per minute",
    "messaging.send_message": "20 per minute",
    "user.get_user_groups": "30 per minute",
    "auth.login": "5 per minute",
    "auth.register": "3 per hour",
    "payments.*": "20 per minute",
    "admin.*": "30 per minute",
    "market.*": "50 per minute",
    "match.*": "30 per minute",
}


def apply_rate_limits(app):
    """Apply rate limits to specific endpoints"""
    # This function will be called after blueprints are registered
    for endpoint, limit in rate_limit_config.items():
        if "*" in endpoint:
            # Apply to all endpoints in blueprint
            blueprint_name = endpoint.split(".")[0]
            limiter.limit(limit, key_func=lambda: f"{blueprint_name}.*")
        else:
            limiter.limit(limit, key_func=lambda: endpoint)

    print("✅ Rate limits applied to endpoints")
