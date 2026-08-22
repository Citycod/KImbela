"""
ai_action_engine.py — Action Engine for Kimbela AI Personas.

Enforces rate limits, safety rails, escalation handling, and dispatches actions
through Flask's test client / authenticated context to existing backend routes.
No direct database writes for content creation.
"""

import logging
from datetime import datetime, date, timedelta
from time_utils import utcnow
from flask import current_app
from flask_login import login_user, logout_user
from extensions import db
from models import User, AIPersona, AILog, Post, Comment, NotificationType
import re
from ai_service import generate_content, LLMResponse

logger = logging.getLogger(__name__)

# Daily Limits
MAX_DAILY_POSTS = 1
MAX_DAILY_COMMENTS = 5

# Hard Pre-Filter for Financial Requests
FINANCIAL_PATTERNS = [
    r"\b(?:acct|account)\s*(?:no|num|number)?\s*[:#-]?\s*\d{8,12}\b",
    r"\b\d{10}\b.*\b(?:opay|palmpay|kuda|moniepoint|gtb|zenith|access|uba|first bank)\b",
    r"\b(?:opay|palmpay|kuda|moniepoint|gtb|zenith|access|uba|first bank)\b.*\b\d{10}\b",
    r"\b(?:send|transfer|lend|borrow|give)\s+(?:me|us|some|it|the)\s+(?:money|cash|funds|naira|dollars|k|\d+[k]?)\b",
    r"\b(?:need|seeking)\s+(?:a\s+)?(?:loan|financial assistance|funds)\b",
    r"\b(?:help me out|things are tight|i am broke|no money|stranded|pay.*rent|school fees)\b",
    r"\b(?:need|urgent|please|help|send|transfer)\b.*?(?:₦|naira|\$|\b\d+k\b)",
    r"(?:₦|naira|\$|\b\d+k\b).*?\b(?:need|urgent|please|help|send|transfer)\b"
]
COMPILED_FINANCIAL_PATTERNS = [re.compile(p, re.IGNORECASE) for p in FINANCIAL_PATTERNS]

def is_financial_request(text: str) -> bool:
    for pattern in COMPILED_FINANCIAL_PATTERNS:
        if pattern.search(text):
            return True
    return False

def get_daily_action_count(persona_id: int, action_type: str) -> int:
    """Get the number of successful actions taken by a persona today."""
    today_start = datetime.combine(date.today(), datetime.min.time())
    return AILog.query.filter(
        AILog.persona_id == persona_id,
        AILog.action_type == action_type,
        AILog.timestamp >= today_start,
        AILog.is_escalated == False,
    ).count()


def handle_escalation(persona: AIPersona, prompt_context: str, generated_content: str, provider_used: str, target_id: int = None):
    """
    Handle an escalated interaction:
    1. Log to AILog with is_escalated = True
    2. Dispatch in-app notification to all Superadmin accounts
    """
    log_entry = AILog(
        persona_id=persona.id,
        action_type="ESCALATION",
        target_id=target_id,
        prompt_context=prompt_context,
        generated_content=generated_content,
        provider_used=provider_used,
        is_escalated=True,
        timestamp=utcnow(),
    )
    db.session.add(log_entry)
    db.session.commit()

    # Find superadmins to notify
    superadmins = User.query.filter_by(is_super_admin=True).all()
    for admin in superadmins:
        try:
            admin.create_notification(
                actor=persona.user,
                notification_type=NotificationType.SYSTEM if hasattr(NotificationType, "SYSTEM") else NotificationType.NEW_COMMENT,
                entity_id=log_entry.id,
                entity_type="ai_escalation",
            )
        except Exception as exc:
            logger.error("Failed to notify superadmin %s of AI escalation: %s", admin.id, exc)

    logger.warning(
        "AI Escalation triggered for persona '%s' (ID %d). Log ID: %d",
        persona.name, persona.id, log_entry.id
    )


def execute_persona_post(persona: AIPersona, prompt_topic: str) -> bool:
    """
    Generates and publishes a post for a persona via internal client/route.
    """
    if get_daily_action_count(persona.id, "CREATE_POST") >= MAX_DAILY_POSTS:
        logger.info("Persona '%s' reached daily post limit.", persona.name)
        return False

    persona_config = {
        "name": persona.name,
        "personality": persona.personality,
        "interests": persona.interests,
        "forbidden_actions": persona.forbidden_actions,
        "escalation_rule": persona.escalation_rule,
        "voice_samples": persona.voice_samples,
    }

    user_prompt = f"Write a casual short social post for your feed about: {prompt_topic}."
    
    # Hard Pre-Filter Check
    if is_financial_request(prompt_topic):
        logger.warning("Persona '%s' blocked by financial pre-filter on post generation", persona.name)
        handle_escalation(
            persona, 
            prompt_context=user_prompt, 
            generated_content="[BLOCKED BY PRE-FILTER]", 
            provider_used="none_prefiltered", 
            target_id=None
        )
        return False

    try:
        response: LLMResponse = generate_content(persona_config, user_prompt)
    except Exception as exc:
        logger.error("Failed content generation for persona '%s': %s", persona.name, exc)
        return False

    if response.is_escalated:
        handle_escalation(persona, user_prompt, response.content, response.provider_used)
        return False

    # Execute post creation via test client (authenticated route call)
    with current_app.test_client() as client:
        # 1. Create a dummy request context to generate a valid CSRF token 
        # and capture the server-side secret it binds to.
        with current_app.test_request_context("/"):
            from flask_wtf.csrf import generate_csrf
            from flask import session
            csrf_token = generate_csrf()
            csrf_session_data = dict(session)
            
        # 2. Inject both the user authentication and the CSRF secret into the client session
        with client.session_transaction() as sess:
            sess["_user_id"] = str(persona.user_id)
            sess["_fresh"] = True
            for k, v in csrf_session_data.items():
                sess[k] = v

        # 3. Submit the post via the real route to ensure it passes through all standard logic
        res = client.post(
            "/user_dashboard",
            data={"post_content": response.content, "csrf_token": csrf_token},
            follow_redirects=True,
        )

        if res.status_code in (200, 302):
            # Fetch created post to get target_id
            latest_post = Post.query.filter_by(author_id=persona.user_id).order_by(Post.id.desc()).first()
            target_id = latest_post.id if latest_post else None

            log_entry = AILog(
                persona_id=persona.id,
                action_type="CREATE_POST",
                target_id=target_id,
                prompt_context=user_prompt,
                generated_content=response.content,
                provider_used=response.provider_used,
                is_escalated=False,
                timestamp=utcnow(),
            )
            db.session.add(log_entry)
            db.session.commit()
            logger.info("Persona '%s' successfully created post %s", persona.name, target_id)
            return True
        else:
            logger.error("Failed to submit post for persona '%s', HTTP %d", persona.name, res.status_code)
            return False
def execute_persona_comment(persona: AIPersona, post: Post) -> bool:
    """
    Generates and posts a reply comment on a post for a persona.
    """
    if get_daily_action_count(persona.id, "REPLY_COMMENT") >= MAX_DAILY_COMMENTS:
        logger.info("Persona '%s' reached daily comment limit.", persona.name)
        return False

    persona_config = {
        "name": persona.name,
        "personality": persona.personality,
        "interests": persona.interests,
        "forbidden_actions": persona.forbidden_actions,
        "escalation_rule": persona.escalation_rule,
        "voice_samples": persona.voice_samples,
    }

    # Gather recent comments on the post for context
    recent_comments = Comment.query.filter_by(post_id=post.id).order_by(Comment.created_at.desc()).limit(3).all()
    comments_summary = "\n".join([f"{c.author.first_name}: {c.content}" for c in recent_comments])

    user_prompt = (
        f"Post by {post.author.first_name}: '{post.content}'\n"
        f"Recent comments:\n{comments_summary}\n\n"
        f"Write a short, natural reply comment as yourself."
    )
    
    # Hard Pre-Filter Check
    if is_financial_request(post.content) or is_financial_request(comments_summary):
        logger.warning("Persona '%s' blocked by financial pre-filter on post %d", persona.name, post.id)
        handle_escalation(
            persona, 
            prompt_context=user_prompt, 
            generated_content="[BLOCKED BY PRE-FILTER]", 
            provider_used="none_prefiltered", 
            target_id=post.id
        )
        return False

    try:
        response: LLMResponse = generate_content(persona_config, user_prompt)
    except Exception as exc:
        logger.error("Failed comment generation for persona '%s': %s", persona.name, exc)
        return False

    if response.is_escalated:
        handle_escalation(persona, user_prompt, response.content, response.provider_used, target_id=post.id)
        return False

    # Execute comment creation via test client
    with current_app.test_client() as client:
        # 1. Create a dummy request context to generate a valid CSRF token 
        # and capture the server-side secret it binds to.
        with current_app.test_request_context("/"):
            from flask_wtf.csrf import generate_csrf
            from flask import session
            csrf_token = generate_csrf()
            csrf_session_data = dict(session)

        # 2. Inject both the user authentication and the CSRF secret into the client session
        with client.session_transaction() as sess:
            sess["_user_id"] = str(persona.user_id)
            sess["_fresh"] = True
            for k, v in csrf_session_data.items():
                sess[k] = v

        # 3. Submit the comment via the real route to ensure it passes through all standard logic
        res = client.post(
            f"/add_comment/{post.id}",
            json={"content": response.content},
            headers={"X-CSRFToken": csrf_token},
        )

        if res.status_code == 200 and res.json.get("success"):
            comment_id = res.json.get("comment", {}).get("id")
            log_entry = AILog(
                persona_id=persona.id,
                action_type="REPLY_COMMENT",
                target_id=comment_id or post.id,
                prompt_context=user_prompt,
                generated_content=response.content,
                provider_used=response.provider_used,
                is_escalated=False,
                timestamp=utcnow(),
            )
            db.session.add(log_entry)
            db.session.commit()
            logger.info("Persona '%s' commented on post %d", persona.name, post.id)
            return True
        else:
            logger.error("Failed comment post for persona '%s', HTTP %d", persona.name, res.status_code)
            return False
