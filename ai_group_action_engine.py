"""Bounded AI activity for existing Kimbela groups.

Required group posts retain the existing group route. Optional AI comments and
replies use explicit-author persistence so scheduler work never depends on an
HTTP login session or CSRF token.
"""

from contextlib import contextmanager
from datetime import datetime, timedelta
import logging
import re

from flask import current_app

from ai_controls import (
    content_is_allowed,
    get_profile_config,
    group_automation_eligibility,
    group_is_quiet_enough,
    manual_group_post_eligibility,
    thread_in_group_cooldown,
)
from ai_service import LLMResponse, generate_content
from ai_action_engine import is_financial_request
from extensions import db
from models import AILog, AIPersona, Comment, Group, Post, SiteSetting, User
from time_utils import utcnow


logger = logging.getLogger(__name__)
GROUP_ACTIVITY_SESSION = "GROUP_ACTIVITY_SESSION"
GROUP_SESSION_CURSOR_KEY = "ai_group_session_cursor"


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
    source="automatic",
) -> bool:
    is_manual = source == "manual"
    is_required_slot = source == "required_slot"
    allowed, reason = (
        manual_group_post_eligibility(persona, group)
        if is_manual
        else group_automation_eligibility(
            persona,
            group,
            "post",
            required_slot=is_required_slot,
        )
    )
    if not allowed:
        logger.info("AI group post blocked: persona=%s reason=%s", persona.id, reason)
        return False
    if not is_manual and not is_required_slot and not group_is_quiet_enough(
        group, "post"
    ):
        logger.info(
            "AI group post blocked: persona=%s group=%s reason=group_not_quiet",
            persona.id,
            group.id,
        )
        return False

    prompt = (
        f"Write a short, natural discussion starter for this group: {_group_context(group)}. "
        "Keep it relevant and invite genuine human discussion in this disclosed AI profile's voice."
    )
    if is_financial_request(prompt):
        logger.warning(
            "AI group post blocked by financial prefilter: persona=%s group=%s",
            persona.id,
            group.id,
        )
        return False
    if content is None:
        try:
            response = generate_content(_persona_prompt_config(persona), prompt)
        except Exception as exc:
            logger.error(
                "Group post generation failed: persona=%s group=%s error=%s",
                persona.id,
                group.id,
                exc,
            )
            return False
    else:
        response = LLMResponse(content.strip(), "admin", False, 0)
    if response.is_escalated:
        logger.warning(
            "AI group post blocked: persona=%s group=%s reason=escalated",
            persona.id,
            group.id,
        )
        return False
    if not response.content.strip():
        logger.warning(
            "AI group post blocked: persona=%s group=%s reason=empty_content",
            persona.id,
            group.id,
        )
        return False
    if is_financial_request(response.content):
        logger.warning(
            "AI group post blocked: persona=%s group=%s reason=financial_content",
            persona.id,
            group.id,
        )
        return False
    if not content_is_allowed(persona, response.content):
        logger.warning(
            "AI group post blocked: persona=%s group=%s reason=disallowed_content",
            persona.id,
            group.id,
        )
        return False
    if not is_manual and _duplicate_group_post(persona, group, response.content):
        logger.info(
            "AI group post blocked: persona=%s group=%s reason=duplicate_content",
            persona.id,
            group.id,
        )
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
    route_payload = route_response.get_json(silent=True) if route_response.is_json else {}
    route_succeeded = bool(route_payload and route_payload.get("success"))
    created_is_new = bool(created and created.id > previous_id)
    content_matches = bool(created and created.content == response.content)
    if not (
        route_response.status_code == 200
        and route_succeeded
        and created_is_new
        and content_matches
    ):
        logger.error(
            "AI group post publish verification failed: persona=%s group=%s "
            "status=%s json=%s route_success=%s post_found=%s "
            "post_is_new=%s content_matches=%s route_error=%s",
            persona_id,
            group_id,
            route_response.status_code,
            route_response.is_json,
            route_succeeded,
            bool(created),
            created_is_new,
            content_matches,
            route_payload.get("error") if route_payload else None,
        )
        return False

    db.session.add(
        AILog(
            persona_id=persona_id,
            action_type=("GROUP_POST_MANUAL" if is_manual else "GROUP_POST_AUTOMATIC"),
            target_id=created.id,
            prompt_context=f"group_id={group_id}\ngroup_post_id={created.id}\n{prompt}",
            generated_content=response.content,
            provider_used=response.provider_used,
            is_escalated=False,
            timestamp=utcnow(),
        )
    )
    db.session.commit()
    logger.info(
        "AI group post persisted: persona=%s user=%s group=%s post=%s source=%s",
        persona_id,
        persona_user_id,
        group_id,
        created.id,
        source,
    )
    return True


def execute_persona_group_comment(
    persona,
    group,
    post,
    source_comment=None,
) -> bool:
    """Persist one AI group comment/reply using fresh, session-bound entities."""
    persona_id = persona if isinstance(persona, int) else persona.id
    group_id = group if isinstance(group, int) else group.id
    post_id = post if isinstance(post, int) else post.id
    source_comment_id = (
        source_comment
        if isinstance(source_comment, int)
        else (source_comment.id if source_comment is not None else None)
    )

    persona = db.session.get(AIPersona, persona_id)
    group = db.session.get(Group, group_id)
    post = db.session.get(Post, post_id)
    source_comment = (
        db.session.get(Comment, source_comment_id)
        if source_comment_id is not None
        else None
    )
    if (
        persona is None
        or group is None
        or post is None
        or (source_comment_id is not None and source_comment is None)
    ):
        logger.error(
            "AI group engagement target missing: persona=%s group=%s post=%s "
            "comment=%s",
            persona_id,
            group_id,
            post_id,
            source_comment_id,
        )
        return False

    action = "reply" if source_comment is not None else "comment"
    allowed, reason = group_automation_eligibility(persona, group, action)
    if not allowed:
        logger.info(
            "AI group %s blocked: persona=%s group=%s reason=%s",
            action,
            persona_id,
            group_id,
            reason,
        )
        return False
    if post.group_id != group_id or not _valid_persona_member(persona, group):
        return False
    if source_comment is None:
        if post.author_id == persona.user_id or post.author.is_ai_persona:
            return False
        if not group_is_quiet_enough(group, "comment"):
            return False
    else:
        if source_comment.post_id != post_id:
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
    if thread_in_group_cooldown(persona, group, post_id):
        return False

    recent_comments = (
        Comment.query.filter_by(post_id=post_id)
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

    persona_user_id = persona.user_id
    try:
        from utils.comment_service import create_comment_for_author

        created = create_comment_for_author(
            author_id=persona_user_id,
            post_id=post_id,
            content=response.content,
            parent_comment_id=source_comment_id,
        )
    except Exception as exc:
        db.session.rollback()
        logger.error(
            "AI optional group engagement persistence failed: action=%s "
            "persona=%s group=%s post=%s comment=%s failure=%s",
            action,
            persona_id,
            group_id,
            post_id,
            source_comment_id,
            type(exc).__name__,
        )
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
    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.error(
            "AI optional group engagement commit failed: action=%s persona=%s "
            "group=%s post=%s comment=%s failure=%s",
            action,
            persona_id,
            group_id,
            post_id,
            source_comment_id,
            type(exc).__name__,
        )
        return False

    created_id = created.id
    _send_optional_group_engagement_notifications(
        post_id=post_id,
        comment_id=created_id,
        actor_id=persona_user_id,
        parent_comment_id=source_comment_id,
    )
    logger.info(
        "AI optional group engagement persisted: action=%s persona=%s user=%s "
        "group=%s post=%s comment=%s",
        action,
        persona_id,
        persona_user_id,
        group_id,
        post_id,
        created_id,
    )
    return True


def _send_optional_group_engagement_notifications(
    *, post_id, comment_id, actor_id, parent_comment_id=None
):
    """Preserve existing comment notifications without coupling persistence to them."""
    try:
        post = db.session.get(Post, post_id)
        comment = db.session.get(Comment, comment_id)
        actor = db.session.get(User, actor_id)
        parent_comment = (
            db.session.get(Comment, parent_comment_id)
            if parent_comment_id is not None
            else None
        )
        if post is None or comment is None or actor is None:
            return
        from users.user import (
            _comment_social_targets,
            _persist_social_notifications,
            _send_comment_social_pushes,
        )

        with current_app.test_request_context("/"):
            targets, destination = _comment_social_targets(
                post, comment, actor, parent_comment
            )
            _persist_social_notifications(targets, actor.id)
            _send_comment_social_pushes(targets, destination, post.id, actor)
    except Exception as exc:
        db.session.rollback()
        logger.error(
            "AI optional group engagement notifications failed: post=%s "
            "comment=%s actor=%s failure=%s",
            post_id,
            comment_id,
            actor_id,
            type(exc).__name__,
        )


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


def _calendar_week_slot(now=None):
    current = now or utcnow()
    monday = (current - timedelta(days=current.weekday())).date()
    # Daily retries target one required original post in each half of the week.
    slot = 0 if current.weekday() <= 2 else 1
    return monday.isoformat(), slot


def _session_marker(group_id, now=None):
    week_start, slot = _calendar_week_slot(now)
    return f"group_session={int(group_id)}:{week_start}:{slot}"


def group_session_completed(group_id, now=None):
    return (
        AILog.query.filter(
            AILog.action_type == GROUP_ACTIVITY_SESSION,
            AILog.prompt_context.contains(_session_marker(group_id, now)),
            AILog.is_escalated.is_(False),
        ).first()
        is not None
    )


def _personas_by_group_rotation(personas, now=None):
    """Prefer the least-used required-slot author in the current week."""
    personas = [
        persona
        for persona in personas
        if persona.is_active
        and persona.user
        and persona.user.is_active
        and persona.user.is_ai_persona
    ]
    if not personas:
        return []
    week_start, _slot = _calendar_week_slot(now)
    rows = (
        db.session.query(
            AILog.persona_id,
            db.func.count(AILog.id),
            db.func.max(AILog.id),
        )
        .filter(
            AILog.persona_id.in_([persona.id for persona in personas]),
            AILog.action_type == GROUP_ACTIVITY_SESSION,
            AILog.prompt_context.contains(f":{week_start}:"),
            AILog.is_escalated.is_(False),
        )
        .group_by(AILog.persona_id)
        .all()
    )
    rotation_by_persona = {
        persona_id: (completed_count, last_log_id)
        for persona_id, completed_count, last_log_id in rows
    }
    input_position = {persona.id: index for index, persona in enumerate(personas)}
    return sorted(
        personas,
        key=lambda persona: (
            rotation_by_persona.get(persona.id, (0, 0)),
            input_position[persona.id],
        ),
    )


def execute_group_activity_session(group, personas, now=None):
    """Complete one normal-group slot only after an original AI post succeeds."""
    from utils.matchmaking_group import is_matchmaking_group

    group_id = group.id
    if group_session_completed(group_id, now):
        return False
    if is_matchmaking_group(group):
        logger.info(
            "AI required group-post slot excluded for Matchmaking group=%s",
            group_id,
        )
        return False

    ordered_persona_ids = [
        persona.id
        for persona in _personas_by_group_rotation(personas, now)
    ]
    if not ordered_persona_ids:
        logger.info(
            "AI required group-post slot remains due: group=%s reason=no_active_persona",
            group_id,
        )
        return False
    failure_reasons = []
    post_persona_id = None
    for persona_id in ordered_persona_ids:
        # The group-post route removes its request-scoped SQLAlchemy session.
        # Reload both entities before every attempt instead of retaining ORM
        # objects across that boundary.
        current_persona = db.session.get(AIPersona, persona_id)
        current_group = db.session.get(Group, group_id)
        if current_persona is None or current_group is None:
            failure_reasons.append(f"persona_{persona_id}:missing_context")
            continue
        allowed, reason = group_automation_eligibility(
            current_persona,
            current_group,
            "post",
            now,
            required_slot=True,
        )
        if not allowed:
            failure_reasons.append(f"persona_{persona_id}:{reason}")
            continue
        if execute_persona_group_post(
            current_persona, current_group, source="required_slot"
        ):
            post_persona_id = persona_id
            break
        failure_reasons.append(f"persona_{persona_id}:post_execution_failed")

    if post_persona_id is None:
        logger.warning(
            "AI required group-post slot remains due: group=%s reasons=%s",
            group_id,
            ",".join(failure_reasons) or "no_eligible_poster",
        )
        return False

    # The content route commits the original post first. Persist the slot marker
    # immediately afterward so optional engagement can never define completion.
    db.session.add(
        AILog(
            persona_id=post_persona_id,
            action_type=GROUP_ACTIVITY_SESSION,
            target_id=group_id,
            prompt_context=(
                f"{_session_marker(group_id, now)}\n"
                f"group_id={group_id}\nrequired_original_post=1"
            ),
            generated_content="post",
            provider_used="scheduler",
            is_escalated=False,
            timestamp=now or utcnow(),
        )
    )
    db.session.commit()

    # Comments/replies are additional engagement only. Reload after the normal
    # posting route removed its request-scoped SQLAlchemy session.
    engagement_persona_ids = sorted(
        ordered_persona_ids,
        key=lambda persona_id: (
            persona_id == post_persona_id,
            ordered_persona_ids.index(persona_id),
        ),
    )
    _execute_optional_group_engagement(group_id, engagement_persona_ids, now)
    return True


def _attempt_optional_group_engagement(
    *, action, persona_id, group_id, post_id, source_comment_id=None
):
    """Isolate one optional attempt from required-slot and pass state."""
    try:
        return execute_persona_group_comment(
            persona_id,
            group_id,
            post_id,
            source_comment_id,
        )
    except Exception as exc:
        db.session.rollback()
        logger.error(
            "AI optional group engagement failed: action=%s persona=%s group=%s "
            "post=%s comment=%s failure=%s",
            action,
            persona_id,
            group_id,
            post_id,
            source_comment_id,
            type(exc).__name__,
        )
        return False


def _fresh_engagement_context(persona_id, group_id, action, now=None):
    """Load fresh entities before an optional-engagement eligibility check."""
    persona = db.session.get(AIPersona, persona_id)
    group = db.session.get(Group, group_id)
    if persona is None or group is None:
        return None, None, False
    allowed, _ = group_automation_eligibility(persona, group, action, now)
    return persona, group, allowed


def _execute_optional_group_engagement(group_id, persona_ids, now=None):
    """Attempt one extra reply/comment without affecting required-slot state."""
    group = db.session.get(Group, group_id)
    if group is None:
        return False

    for persona_id in persona_ids:
        persona, group, allowed = _fresh_engagement_context(
            persona_id, group_id, "reply", now
        )
        if not allowed:
            continue
        candidates = (
            db.session.query(Comment.id, Comment.post_id)
            .join(Post, Comment.post_id == Post.id)
            .join(User, Comment.author_id == User.id)
            .filter(
                Post.group_id == group_id,
                Post.author_id == persona.user_id,
                Comment.author_id != persona.user_id,
                User.is_ai_persona.is_(False),
            )
            .order_by(Comment.created_at.desc())
            .limit(20)
            .all()
        )
        for comment_id, post_id in candidates:
            if _attempt_optional_group_engagement(
                action="reply",
                persona_id=persona_id,
                group_id=group_id,
                post_id=post_id,
                source_comment_id=comment_id,
            ):
                return True

    for persona_id in persona_ids:
        persona, group, allowed = _fresh_engagement_context(
            persona_id, group_id, "comment", now
        )
        if not allowed or not group_is_quiet_enough(group, "comment", now):
            continue
        candidate_ids = (
            db.session.query(Post.id)
            .join(User, Post.author_id == User.id)
            .filter(
                Post.group_id == group_id,
                User.is_ai_persona.is_(False),
            )
            .order_by(Post.created_at.desc())
            .limit(20)
            .all()
        )
        for (post_id,) in candidate_ids:
            if _attempt_optional_group_engagement(
                action="comment",
                persona_id=persona_id,
                group_id=group_id,
                post_id=post_id,
            ):
                return True
    return False


def run_scheduled_group_sessions(personas, now=None, max_groups=25):
    """Process one missing calendar-week slot per group in a bounded pass."""
    persona_ids = [persona.id for persona in personas]
    group_ids = [
        group_id
        for (group_id,) in db.session.query(Group.id)
        .filter(Group.is_active.is_(True))
        .order_by(Group.id.asc())
        .all()
    ]
    if not group_ids or max_groups <= 0:
        logger.info(
            "AI group slot pass skipped: active_groups=%s max_groups=%s",
            len(group_ids),
            max_groups,
        )
        return 0
    try:
        start = int(SiteSetting.get_value(GROUP_SESSION_CURSOR_KEY, "0")) % len(
            group_ids
        )
    except (TypeError, ValueError):
        start = 0
    rotated_group_ids = group_ids[start:] + group_ids[:start]
    week_start, slot = _calendar_week_slot(now)
    logger.info(
        "AI group slot pass started: week_start=%s slot=%s active_groups=%s "
        "max_groups=%s cursor=%s active_personas=%s",
        week_start,
        slot,
        len(group_ids),
        max_groups,
        start,
        len(persona_ids),
    )
    completed = 0
    processed = 0
    scanned = 0
    for group_id in rotated_group_ids:
        if group_session_completed(group_id, now):
            scanned += 1
            continue
        if processed >= max_groups:
            break
        scanned += 1
        processed += 1
        group = db.session.get(Group, group_id)
        fresh_personas = AIPersona.query.filter(
            AIPersona.id.in_(persona_ids),
            AIPersona.is_active.is_(True),
        ).all()
        fresh_personas.sort(key=lambda persona: persona_ids.index(persona.id))
        if group is not None and execute_group_activity_session(
            group, fresh_personas, now
        ):
            completed += 1
    SiteSetting.set_value(
        GROUP_SESSION_CURSOR_KEY,
        str((start + scanned) % len(group_ids)),
    )
    db.session.commit()
    logger.info(
        "AI group slot pass completed: week_start=%s slot=%s scanned=%s "
        "processed=%s completed=%s next_cursor=%s",
        week_start,
        slot,
        scanned,
        processed,
        completed,
        (start + scanned) % len(group_ids),
    )
    return completed
