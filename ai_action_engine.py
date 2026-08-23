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


def execute_persona_post(persona: AIPersona, prompt_topic: str, force: bool = False) -> bool:
    """
    Generates and publishes a post for a persona via internal client/route.
    Set force=True to bypass daily post limit checks during manual testing.
    """
    if not force and get_daily_action_count(persona.id, "CREATE_POST") >= MAX_DAILY_POSTS:
        print(f"🛑 Persona '{persona.name}' reached daily post limit ({MAX_DAILY_POSTS}/day). Use force=True to bypass.")
        logger.info("Persona '%s' reached daily post limit.", persona.name)
        return False

    if not persona.is_active:
        print(f"❌ Persona '{persona.name}' is inactive (AIPersona table). Skipping.")
        logger.info("Persona '%s' is inactive (AIPersona table). Skipping.", persona.name)
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
        print(f"❌ Persona '{persona.name}' blocked by financial pre-filter")
        logger.warning("Persona '%s' blocked by financial pre-filter on post generation", persona.name)
        handle_escalation(
            persona, 
            prompt_context=user_prompt, 
            generated_content="[BLOCKED BY PRE-FILTER]", 
            provider_used="none_prefiltered", 
            target_id=None
        )
        return False

    import time
    t_start = time.perf_counter()
    try:
        t_llm_start = time.perf_counter()
        response: LLMResponse = generate_content(persona_config, user_prompt)
        t_llm_end = time.perf_counter()
        print(f"⏱️  [TIMING] LLM Generation took: {t_llm_end - t_llm_start:.3f}s")
    except Exception as exc:
        print(f"❌ Exception during generate_content for '{persona.name}': {exc}")
        import traceback
        traceback.print_exc()
        logger.error("Failed content generation for persona '%s': %s", persona.name, exc)
        return False

    if response.is_escalated:
        print(f"⚠️ Persona '{persona.name}' generated escalated response")
        handle_escalation(persona, user_prompt, response.content, response.provider_used)
        return False
        
    if not response.content.strip():
        print(f"❌ Generated content was empty after stripping think blocks for '{persona.name}'")
        logger.error("Content generation resulted in an empty string for persona '%s'. (Possible max_tokens cutoff). Aborting.", persona.name)
        return False

    # Execute post creation via test client (authenticated route call)
    t_route_start = time.perf_counter()
    with current_app.test_client() as client:
        user_obj = db.session.get(User, persona.user_id)
        print(f"🔍 [DIAGNOSTIC] user_obj Python ID: {id(user_obj)} | DB ID: {user_obj.id if user_obj else 'None'}")
        if not user_obj:
            print(f"❌ User ID {persona.user_id} for persona '{persona.name}' does not exist in DB!")
            return False
            
        if not getattr(user_obj, "is_ai_persona", False):
            print(f"❌ Security violation: User ID {persona.user_id} is NOT an AI persona account!")
            logger.error("Security violation: User ID %d is NOT an AI persona account.", persona.user_id)
            return False

        if not user_obj.is_active:
            print(f"❌ User ID {persona.user_id} for persona '{persona.name}' is inactive! Run seed script to activate.")
            logger.error("User ID %d for persona '%s' is inactive.", persona.user_id, persona.name)
            return False

        # Step 1: Log the user in natively via session_transaction
        with client.session_transaction() as sess:
            sess["_user_id"] = str(user_obj.id)
            sess["_fresh"] = True
            
        # Step 2: Do a GET to fetch the page and establish CSRF token natively
        get_res = client.get("/user_dashboard", base_url="http://localhost/")
        
        # Step 3: Parse the CSRF token out of the HTML form
        import re
        html_str = get_res.data.decode('utf-8', errors='ignore')
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', html_str)
        if not match:
            print("❌ Failed to find csrf_token in the GET response HTML.")
            logger.error("Failed to find csrf_token in the GET response HTML for persona '%s'.", persona.name)
            return False
        csrf_token = match.group(1)

        # Step 4: Execute the POST using the exact same client and session
        with client.session_transaction() as sess:
            print(f"🔍 [DIAGNOSTIC] CSRF Token in test_client session: {sess.get('csrf_token')} | Form token being submitted: {csrf_token}")

        res = client.post(
            "/user_dashboard",
            data={"post_content": response.content, "csrf_token": csrf_token},
            headers={"Referer": "http://localhost/user_dashboard"},
            base_url="http://localhost/",
            follow_redirects=False,
        )

    t_route_end = time.perf_counter()
    print(f"⏱️  [TIMING] Route HTTP POST /user_dashboard took: {t_route_end - t_route_start:.3f}s")
    print(f"📄 Route Response Status: {res.status_code}")
    print(f"📄 Route Response Location: {res.location}")
    if res.status_code not in (200, 302):
        print(f"📄 Route Response Body: {res.data.decode('utf-8', errors='ignore')[:400]}")

    if res.status_code == 302 and "/login" in (res.location or ""):
        print(f"❌ Authentication failed! @login_required redirected to: {res.location}")
        return False

    if res.status_code == 302 and "/user_dashboard" not in (res.location or "") and res.location != "http://localhost/user_dashboard":
        pass  # Just in case

    if res.status_code == 302 and (res.location or "") == "http://localhost/user_dashboard":
        with client.session_transaction() as sess:
            flashes = sess.get("_flashes", [])
            print(f"⚠️  [DIAGNOSTIC] Redirected to absolute URL. Flashed messages: {flashes}")

    t_db_start = time.perf_counter()
    db.session.remove()
    latest_post = Post.query.filter_by(author_id=persona.user_id).order_by(Post.id.desc()).first()
    t_db_end = time.perf_counter()
    print(f"⏱️  [TIMING] DB Query verification took: {t_db_end - t_db_start:.3f}s")
    print(f"⏱️  [TIMING] Total persona execution took: {time.perf_counter() - t_start:.3f}s")
        
    if not latest_post or latest_post.content != response.content:
        actual_content = latest_post.content[:30] if latest_post else "None"
        print(f"❌ Post verification failed! Expected '{response.content[:30]}...', got '{actual_content}...'")
        logger.error("Post creation failed for persona '%s': post not found in DB or content mismatch.", persona.name)
        return False

    log_entry = AILog(
        persona_id=persona.id,
        action_type="CREATE_POST",
        target_id=latest_post.id,
        prompt_context=user_prompt,
        generated_content=response.content,
        provider_used=response.provider_used,
        is_escalated=False,
        timestamp=utcnow(),
    )
    db.session.add(log_entry)
    db.session.commit()
    print(f"✅ Successfully created post ID {latest_post.id} for '{persona.name}'")
    logger.info("Persona '%s' successfully created post %s", persona.name, latest_post.id)
    return True
def execute_persona_comment(persona: AIPersona, post: Post) -> bool:
    """
    Generates and posts a reply comment on a post for a persona.
    """
    if get_daily_action_count(persona.id, "REPLY_COMMENT") >= MAX_DAILY_COMMENTS:
        logger.info("Persona '%s' reached daily comment limit.", persona.name)
        return False

    if not persona.is_active:
        logger.info("Persona '%s' is inactive (AIPersona table). Skipping.", persona.name)
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
        
    if not response.content.strip():
        logger.error("Content generation resulted in an empty string for persona '%s'. (Possible max_tokens cutoff). Aborting.", persona.name)
        return False

    # Execute comment creation via test client
    with current_app.test_client() as client:
        user_obj = db.session.get(User, persona.user_id)
        if not user_obj:
            logger.error("User ID %d for persona '%s' does not exist in DB!", persona.user_id, persona.name)
            return False
            
        if not getattr(user_obj, "is_ai_persona", False):
            logger.error("Security violation: User ID %d is NOT an AI persona account!", persona.user_id)
            return False

        if not user_obj.is_active:
            logger.error("User ID %d for persona '%s' is inactive!", persona.user_id, persona.name)
            return False

        # Step 1: Log the user in natively via session_transaction
        with client.session_transaction() as sess:
            sess["_user_id"] = str(user_obj.id)
            sess["_fresh"] = True

        # Step 2: Do a GET to fetch the page and establish CSRF token natively
        get_res = client.get("/user_dashboard", base_url="http://localhost/")
        
        # Step 3: Parse the CSRF token out of the HTML form
        import re
        html_str = get_res.data.decode('utf-8', errors='ignore')
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', html_str)
        if not match:
            logger.error("Failed to find csrf_token in the GET response HTML for persona '%s'.", persona.name)
            return False
        csrf_token = match.group(1)

        # 3. Submit the comment via the real route to ensure it passes through all standard logic
        res = client.post(
            f"/add_comment/{post.id}",
            json={"content": response.content},
            headers={"X-CSRFToken": csrf_token, "Referer": f"http://localhost/user_dashboard"},
            base_url="http://localhost/",
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
