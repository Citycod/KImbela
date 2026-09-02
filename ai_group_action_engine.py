"""Bounded AI activity for existing Kimbela groups.

All persisted content is submitted through the same authenticated Flask routes
used by human group members.  This module adds policy and selection only; it
does not create a second group-content or notification path.
"""

from contextlib import contextmanager
import logging
import re

from flask import current_app

from ai_controls import (
    content_is_allowed,
    get_profile_config,
    group_automation_eligibility,
    group_is_quiet_enough,
    thread_in_group_cooldown,
)
from ai_service import LLMResponse, generate_content
from ai_action_engine import is_financial_request
from extensions import db
from models import AILog, AIPersona, Comment, Group, Post, User
from time_utils import utcnow


logger = logging.getLogger(__name__)


def _persona_prompt_config(persona):
    return {
        "name": persona.name,
        "personality": persona.personality,
        "interests": persona.interests,
        "forbidden_actions": persona.forbidden_actions,
        "escalation_rule": persona.escalation_rule,
        "voice_samples": persona.voice_samples,
    }


def _group_context(group):
    parts = [group.name]
    if group.category:
        parts.append(f"category: {group.category}")
    if group.description:
        parts.append(f"description: {group.description}")
    return "; ".join(parts)


def _duplicate_group_post(persona, group, content):
    normalized = " ".join((content or "").casefold().split())
    recent = (
        Post.query.filter_by(group_id=group.id, author_id=persona.user_id)
        .order_by(Post.created_at.desc())
        .limit(20)
        .all()
    )
    return any(
        " ".join((post.content or "").casefold().split()) == normalized
        for post in recent
    )


def _valid_persona_member(persona, group):
    user = db.session.get(User, persona.user_id)
    return bool(
        user
        and user.is_active
        and user.is_ai_persona
        and group.is_active
        and group.members.filter_by(id=user.id).first() is not None
    )


@contextmanager
def _authenticated_group_client(persona, group):
    if not _valid_persona_member(persona, group):
        yield None, None
        return

    with current_app.test_client() as client:
        with client.session_transaction() as session:
            session["_user_id"] = str(persona.user_id)
            session["_fresh"] = True
        response = client.get(
            f"/groups/{group.id}",
            base_url="http://localhost/",
        )
        html = response.data.decode("utf-8", errors="ignore")
        token_match = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
        if not token_match:
            token_match = re.search(
                r'<meta\s+name="csrf-token"\s+content="([^"]+)"', html
            )
        if response.status_code != 200 or not token_match:
            logger.error(
                "Could not establish group route session for persona %s and group %s",
                persona.id,
                group.id,
            )
            yield None, None
            return
        yield client, token_match.group(1)


def execute_persona_group_post(
    persona: AIPersona,
    group: Group,
    content=None,
    media_file=None,
) -> bool:
    allowed, reason = group_automation_eligibility(persona, group, "post")
    if not allowed:
        logger.info("AI group post blocked: persona=%s reason=%s", persona.id, reason)
        return False
    if not group_is_quiet_enough(group, "post"):
        return False

    prompt = (
        f"Write a short, natural discussion starter for this group: {_group_context(group)}. "
        "Keep it relevant and invite genuine human discussion in this disclosed AI profile's voice."
    )
    if is_financial_request(prompt):
        return False
    if content is None:
        try:
            response = generate_content(_persona_prompt_config(persona), prompt)
        except Exception as exc:
            logger.error("Group post generation failed for persona %s: %s", persona.id, exc)
            return False
    else:
        response = LLMResponse(content.strip(), "admin", False, 0)
    if response.is_escalated or not response.content.strip():
        return False
    if is_financial_request(response.content):
        return False
    if not content_is_allowed(persona, response.content):
        return False
    if _duplicate_group_post(persona, group, response.content):
        return False

    persona_id = persona.id
    persona_user_id = persona.user_id
    group_id = group.id
    previous = (
        Post.query.filter_by(author_id=persona_user_id, group_id=group_id)
        .order_by(Post.id.desc())
        .first()
    )
    previous_id = previous.id if previous else 0
    with _authenticated_group_client(persona, group) as (client, csrf_token):
        if client is None:
            return False
        data = {"post_content": response.content, "csrf_token": csrf_token}
        if media_file is not None and getattr(media_file, "filename", ""):
            data["media"] = (media_file.stream, media_file.filename)
        route_response = client.post(
            f"/groups/{group_id}/post",
            data=data,
            headers={"Referer": f"http://localhost/groups/{group_id}"},
            base_url="http://localhost/",
        )

    db.session.remove()
    created = (
        Post.query.filter_by(author_id=persona_user_id, group_id=group_id)
        .order_by(Post.id.desc())
        .first()
    )
    if (
        route_response.status_code != 200
        or not route_response.is_json
        or not route_response.get_json().get("success")
        or not created
        or created.id <= previous_id
        or created.content != response.content
    ):
        return False

    db.session.add(
        AILog(
            persona_id=persona_id,
            action_type="GROUP_POST_AUTOMATIC",
            target_id=created.id,
            prompt_context=f"group_id={group_id}\ngroup_post_id={created.id}\n{prompt}",
            generated_content=response.content,
            provider_used=response.provider_used,
            is_escalated=False,
            timestamp=utcnow(),
        )
    )
    db.session.commit()
    return True


def execute_persona_group_comment(
    persona: AIPersona,
    group: Group,
    post: Post,
    source_comment: Comment = None,
) -> bool:
    action = "reply" if source_comment is not None else "comment"
    allowed, reason = group_automation_eligibility(persona, group, action)
    if not allowed:
        logger.info("AI group %s blocked: persona=%s reason=%s", action, persona.id, reason)
        return False
    if post.group_id != group.id or not _valid_persona_member(persona, group):
        return False
    if source_comment is None:
        if post.author_id == persona.user_id or post.author.is_ai_persona:
            return False
        if not group_is_quiet_enough(group, "comment"):
            return False
    else:
        if source_comment.post_id != post.id:
            return False
        if source_comment.author_id == persona.user_id or source_comment.author.is_ai_persona:
            return False
        marker = f"source_group_comment_id={source_comment.id}"
        duplicate = AILog.query.filter(
            AILog.persona_id == persona.id,
            AILog.action_type.in_(("GROUP_REPLY_AUTOMATIC", "GROUP_REPLY_MANUAL")),
            AILog.prompt_context.contains(marker),
        ).first()
        if duplicate:
            return False
    if thread_in_group_cooldown(persona, group, post.id):
        return False

    recent_comments = (
        Comment.query.filter_by(post_id=post.id)
        .order_by(Comment.created_at.desc())
        .limit(3)
        .all()
    )
    comments_context = "\n".join(
        f"{comment.author.first_name}: {comment.content}" for comment in recent_comments
    )
    prompt = (
        f"Group: {_group_context(group)}\n"
        f"Post by {post.author.first_name}: {post.content}\n"
        f"Recent comments:\n{comments_context}\n\n"
        + (
            f"Reply briefly and naturally to this human comment: {source_comment.content}"
            if source_comment is not None
            else "Add one brief, relevant comment that encourages human discussion."
        )
    )
    if is_financial_request(prompt):
        return False
    try:
        response = generate_content(_persona_prompt_config(persona), prompt)
    except Exception as exc:
        logger.error("Group %s generation failed for persona %s: %s", action, persona.id, exc)
        return False
    if response.is_escalated or not response.content.strip():
        return False
    if is_financial_request(response.content):
        return False
    if not content_is_allowed(persona, response.content):
        return False

    persona_id = persona.id
    persona_user_id = persona.user_id
    group_id = group.id
    post_id = post.id
    source_comment_id = source_comment.id if source_comment is not None else None
    previous = Comment.query.order_by(Comment.id.desc()).first()
    previous_id = previous.id if previous else 0
    with _authenticated_group_client(persona, group) as (client, csrf_token):
        if client is None:
            return False
        payload = {"content": response.content}
        if source_comment_id is not None:
            payload["parent_id"] = source_comment_id
        route_response = client.post(
            f"/add_comment/{post_id}",
            json=payload,
            headers={
                "X-CSRFToken": csrf_token,
                "Referer": f"http://localhost/groups/{group_id}",
            },
            base_url="http://localhost/",
        )

    db.session.remove()
    created = Comment.query.order_by(Comment.id.desc()).first()
    response_json = route_response.get_json(silent=True) if route_response.is_json else {}
    if (
        route_response.status_code != 200
        or not response_json.get("success")
        or not created
        or created.id <= previous_id
        or created.post_id != post_id
        or created.author_id != persona_user_id
        or created.parent_id != source_comment_id
    ):
        return False

    source_marker = (
        f"source_group_comment_id={source_comment_id}\n"
        if source_comment_id is not None
        else ""
    )
    db.session.add(
        AILog(
            persona_id=persona_id,
            action_type=(
                "GROUP_REPLY_AUTOMATIC"
                if source_comment_id is not None
                else "GROUP_COMMENT_AUTOMATIC"
            ),
            target_id=created.id,
            prompt_context=(
                f"group_id={group_id}\ngroup_post_id={post_id}\n{source_marker}{prompt}"
            ),
            generated_content=response.content,
            provider_used=response.provider_used,
            is_escalated=False,
            timestamp=utcnow(),
        )
    )
    db.session.commit()
    return True


def eligible_groups_for_persona(persona):
    config = get_profile_config(persona)
    if not config["allowed_group_ids"]:
        return []
    groups = Group.query.filter(
        Group.id.in_(config["allowed_group_ids"]),
        Group.is_active.is_(True),
    ).all()
    return [
        group
        for group in groups
        if group.members.filter_by(id=persona.user_id).first() is not None
    ]


def execute_next_group_action(personas, actions=None) -> bool:
    """Try priorities in order and stop immediately after one successful action."""
    actions = set(actions or ("reply", "comment", "post"))
    personas = list(personas)

    # 1. Human comments on an AI profile's own group post.
    if "reply" in actions:
        for persona in personas:
            for group in eligible_groups_for_persona(persona):
                allowed, _ = group_automation_eligibility(persona, group, "reply")
                if not allowed:
                    continue
                candidates = (
                    Comment.query.join(Post, Comment.post_id == Post.id)
                    .join(User, Comment.author_id == User.id)
                    .filter(
                        Post.group_id == group.id,
                        Post.author_id == persona.user_id,
                        Comment.author_id != persona.user_id,
                        User.is_ai_persona.is_(False),
                    )
                    .order_by(Comment.created_at.desc())
                    .limit(20)
                    .all()
                )
                for comment in candidates:
                    if execute_persona_group_comment(persona, group, comment.post, comment):
                        return True

    # 2. Quiet human-authored group posts.
    if "comment" in actions:
        for persona in personas:
            for group in eligible_groups_for_persona(persona):
                allowed, _ = group_automation_eligibility(persona, group, "comment")
                if not allowed or not group_is_quiet_enough(group, "comment"):
                    continue
                candidates = (
                    Post.query.join(User, Post.author_id == User.id)
                    .filter(
                        Post.group_id == group.id,
                        User.is_ai_persona.is_(False),
                    )
                    .order_by(Post.created_at.desc())
                    .limit(20)
                    .all()
                )
                for post in candidates:
                    if execute_persona_group_comment(persona, group, post):
                        return True

    # 3. A new discussion starter only after the longer quiet threshold.
    if "post" in actions:
        quiet_groups = []
        for persona in personas:
            for group in eligible_groups_for_persona(persona):
                allowed, _ = group_automation_eligibility(persona, group, "post")
                if allowed and group_is_quiet_enough(group, "post"):
                    quiet_groups.append((persona, group))
        for persona, group in quiet_groups:
            if execute_persona_group_post(persona, group):
                return True
    return False
