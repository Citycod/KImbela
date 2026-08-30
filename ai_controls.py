"""Persisted, schema-free control policy for the existing AI personas.

The project already has a generic ``site_settings`` table.  AI scheduling
settings are stored there as small JSON documents so this control layer does
not require a database migration or a second scheduler.
"""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from extensions import db
from models import AILog, Post, SiteSetting
from time_utils import utcnow


GLOBAL_ACTIVITY_KEY = "ai_activity_enabled"
PROFILE_KEY_PREFIX = "ai_profile_control:"
PENDING_DRAFT_KEY_PREFIX = "ai_pending_draft:"

DEFAULT_PROFILE_CONFIG = {
    "enabled": True,
    "paused": False,
    "posting_mode": "automatic",
    "active_days": [0, 1, 2, 3, 4, 5, 6],
    "posting_start_time": "00:00",
    "posting_end_time": "23:59",
    "max_posts_per_day": 1,
    "minimum_post_interval_minutes": 720,
    "max_replies_per_day": 5,
    "replies_enabled": True,
    "reply_probability": 35,
    "minimum_reply_delay_minutes": 0,
    "maximum_reply_delay_minutes": 0,
    "disallowed_topics": [],
}


def _profile_key(persona_id):
    return f"{PROFILE_KEY_PREFIX}{int(persona_id)}"


def _draft_key(persona_id):
    return f"{PENDING_DRAFT_KEY_PREFIX}{int(persona_id)}"


def _load_json_setting(key, default):
    raw_value = SiteSetting.get_value(key)
    if not raw_value:
        return deepcopy(default)
    try:
        value = json.loads(raw_value)
    except (TypeError, ValueError):
        return deepcopy(default)
    return value if isinstance(value, type(default)) else deepcopy(default)


def _bounded_int(value, default, minimum, maximum):
    try:
        return max(minimum, min(maximum, int(value)))
    except (TypeError, ValueError):
        return default


def _valid_clock(value, default):
    try:
        datetime.strptime(str(value), "%H:%M")
    except (TypeError, ValueError):
        return default
    return str(value)


def normalize_profile_config(raw_config):
    raw_config = raw_config if isinstance(raw_config, dict) else {}
    config = deepcopy(DEFAULT_PROFILE_CONFIG)
    config["enabled"] = bool(raw_config.get("enabled", config["enabled"]))
    config["paused"] = bool(raw_config.get("paused", config["paused"]))
    mode = str(raw_config.get("posting_mode", config["posting_mode"])).lower()
    config["posting_mode"] = mode if mode in {"manual", "approval", "automatic"} else "automatic"

    days = raw_config.get("active_days", config["active_days"])
    if isinstance(days, list):
        config["active_days"] = sorted({int(day) for day in days if str(day).isdigit() and 0 <= int(day) <= 6})

    config["posting_start_time"] = _valid_clock(
        raw_config.get("posting_start_time"), config["posting_start_time"]
    )
    config["posting_end_time"] = _valid_clock(
        raw_config.get("posting_end_time"), config["posting_end_time"]
    )
    config["max_posts_per_day"] = _bounded_int(
        raw_config.get("max_posts_per_day"), 1, 0, 20
    )
    config["minimum_post_interval_minutes"] = _bounded_int(
        raw_config.get("minimum_post_interval_minutes"), 720, 0, 10080
    )
    config["max_replies_per_day"] = _bounded_int(
        raw_config.get("max_replies_per_day"), 5, 0, 100
    )
    config["replies_enabled"] = bool(
        raw_config.get("replies_enabled", config["replies_enabled"])
    )
    config["reply_probability"] = _bounded_int(
        raw_config.get("reply_probability"), 35, 0, 100
    )
    config["minimum_reply_delay_minutes"] = _bounded_int(
        raw_config.get("minimum_reply_delay_minutes"), 0, 0, 10080
    )
    config["maximum_reply_delay_minutes"] = _bounded_int(
        raw_config.get("maximum_reply_delay_minutes"), 0, 0, 10080
    )
    if config["maximum_reply_delay_minutes"] < config["minimum_reply_delay_minutes"]:
        config["maximum_reply_delay_minutes"] = config["minimum_reply_delay_minutes"]

    topics = raw_config.get("disallowed_topics", [])
    if isinstance(topics, str):
        topics = topics.splitlines()
    config["disallowed_topics"] = [
        str(topic).strip() for topic in topics if str(topic).strip()
    ][:100]
    return config


def get_profile_config(persona):
    return normalize_profile_config(
        _load_json_setting(_profile_key(persona.id), DEFAULT_PROFILE_CONFIG)
    )


def save_profile_config(persona, raw_config):
    config = normalize_profile_config(raw_config)
    SiteSetting.set_value(_profile_key(persona.id), json.dumps(config, sort_keys=True))
    return config


def is_global_activity_enabled():
    value = SiteSetting.get_value(GLOBAL_ACTIVITY_KEY, "1")
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def set_global_activity_enabled(enabled):
    SiteSetting.set_value(GLOBAL_ACTIVITY_KEY, "1" if enabled else "0")


def _local_now(persona, now=None):
    now = now or utcnow()
    timezone_name = getattr(getattr(persona, "user", None), "timezone", None) or "UTC"
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        timezone = ZoneInfo("UTC")
    if now.tzinfo is None:
        now = now.replace(tzinfo=ZoneInfo("UTC"))
    return now.astimezone(timezone)


def _inside_window(local_now, start_value, end_value):
    start = time.fromisoformat(start_value)
    end = time.fromisoformat(end_value)
    current = local_now.time().replace(tzinfo=None)
    if start <= end:
        return start <= current <= end
    return current >= start or current <= end


def _action_types(action):
    if action == "post":
        return (
            "CREATE_POST",
            "CREATE_POST_AUTOMATIC",
            "CREATE_POST_MANUAL",
            "CREATE_POST_APPROVED",
        )
    return ("REPLY_COMMENT", "REPLY_COMMENT_AUTOMATIC", "REPLY_COMMENT_MANUAL")


def action_count_since(persona_id, action, since):
    return AILog.query.filter(
        AILog.persona_id == persona_id,
        AILog.action_type.in_(_action_types(action)),
        AILog.timestamp >= since,
        AILog.is_escalated.is_(False),
    ).count()


def today_action_count(persona, action, now=None):
    local_now = _local_now(persona, now)
    local_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    utc_start = local_start.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    return action_count_since(persona.id, action, utc_start)


def last_action_at(persona_id, action):
    row = (
        AILog.query.filter(
            AILog.persona_id == persona_id,
            AILog.action_type.in_(_action_types(action)),
            AILog.is_escalated.is_(False),
        )
        .order_by(AILog.timestamp.desc())
        .first()
    )
    return row.timestamp if row else None


def next_eligible_post_at(persona, now=None):
    """Calculate the next ordinary posting-window opportunity when possible."""
    if not is_global_activity_enabled() or not persona.is_active:
        return None
    config = get_profile_config(persona)
    if (
        not config["enabled"]
        or config["paused"]
        or config["posting_mode"] != "automatic"
        or not config["active_days"]
        or config["max_posts_per_day"] == 0
    ):
        return None

    local_now = _local_now(persona, now)
    candidate = local_now
    last_post = last_action_at(persona.id, "post")
    if last_post:
        last_post = last_post.replace(tzinfo=ZoneInfo("UTC")).astimezone(local_now.tzinfo)
        candidate = max(
            candidate,
            last_post + timedelta(minutes=config["minimum_post_interval_minutes"]),
        )
    if today_action_count(persona, "post", now) >= config["max_posts_per_day"]:
        candidate = (local_now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

    start = time.fromisoformat(config["posting_start_time"])
    end = time.fromisoformat(config["posting_end_time"])
    for day_offset in range(8):
        day = (candidate + timedelta(days=day_offset)).date()
        if day.weekday() not in config["active_days"]:
            continue
        day_candidate = candidate if day == candidate.date() else datetime.combine(day, time.min, tzinfo=local_now.tzinfo)
        if start <= end:
            window_start = datetime.combine(day, start, tzinfo=local_now.tzinfo)
            window_end = datetime.combine(day, end, tzinfo=local_now.tzinfo)
            result = max(day_candidate, window_start)
            if result <= window_end:
                return result.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
        else:
            early_end = datetime.combine(day, end, tzinfo=local_now.tzinfo)
            late_start = datetime.combine(day, start, tzinfo=local_now.tzinfo)
            if day_candidate <= early_end:
                return day_candidate.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
            if day_candidate <= late_start:
                return late_start.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
            return day_candidate.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    return None


def automation_eligibility(persona, action, now=None, posting_modes=None):
    """Return ``(allowed, reason)`` for an automated post or reply."""
    if not is_global_activity_enabled():
        return False, "global_stop"
    if not persona.is_active or not getattr(persona.user, "is_active", False):
        return False, "disabled"

    config = get_profile_config(persona)
    if not config["enabled"]:
        return False, "disabled"
    if config["paused"]:
        return False, "paused"
    permitted_modes = set(posting_modes or ("automatic",))
    if config["posting_mode"] not in permitted_modes and action == "post":
        return False, config["posting_mode"]
    if action == "reply" and not config["replies_enabled"]:
        return False, "replies_disabled"

    local_now = _local_now(persona, now)
    if local_now.weekday() not in config["active_days"]:
        return False, "inactive_day"
    if not _inside_window(
        local_now, config["posting_start_time"], config["posting_end_time"]
    ):
        return False, "outside_window"

    max_actions = (
        config["max_posts_per_day"]
        if action == "post"
        else config["max_replies_per_day"]
    )
    if today_action_count(persona, action, now) >= max_actions:
        return False, "daily_limit"

    if action == "post":
        last_post_at = last_action_at(persona.id, "post")
        if last_post_at:
            comparable_now = now or utcnow()
            if comparable_now.tzinfo is not None:
                comparable_now = comparable_now.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
            minimum_delta = timedelta(minutes=config["minimum_post_interval_minutes"])
            if comparable_now - last_post_at < minimum_delta:
                return False, "minimum_interval"

    return True, "eligible"


def manual_eligibility(persona):
    """Manual admin actions still respect emergency, disabled, and pause state."""
    if not is_global_activity_enabled():
        return False, "global_stop"
    if not persona.is_active or not getattr(persona.user, "is_active", False):
        return False, "disabled"
    config = get_profile_config(persona)
    if not config["enabled"]:
        return False, "disabled"
    if config["paused"]:
        return False, "paused"
    return True, "eligible"


def content_is_allowed(persona, content):
    normalized = (content or "").casefold()
    return not any(
        topic.casefold() in normalized
        for topic in get_profile_config(persona)["disallowed_topics"]
    )


def reply_is_due(persona, comment, now=None):
    """Use a stable per-comment delay without adding a queue or new job store."""
    config = get_profile_config(persona)
    minimum = config["minimum_reply_delay_minutes"]
    maximum = config["maximum_reply_delay_minutes"]
    delay_range = max(0, maximum - minimum)
    delay_minutes = minimum + ((comment.id or 0) % (delay_range + 1))
    comparable_now = now or utcnow()
    if comparable_now.tzinfo is not None:
        comparable_now = comparable_now.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    return comparable_now >= comment.created_at + timedelta(minutes=delay_minutes)


def is_duplicate_post(persona, content, recent_limit=20):
    normalized = " ".join((content or "").casefold().split())
    if not normalized:
        return False
    recent = (
        Post.query.filter_by(author_id=persona.user_id)
        .order_by(Post.created_at.desc())
        .limit(recent_limit)
        .all()
    )
    return any(" ".join((post.content or "").casefold().split()) == normalized for post in recent)


def get_pending_draft(persona_id):
    return _load_json_setting(_draft_key(persona_id), {})


def save_pending_draft(persona_id, draft):
    SiteSetting.set_value(_draft_key(persona_id), json.dumps(draft, sort_keys=True))


def clear_pending_draft(persona_id):
    setting = db.session.get(SiteSetting, _draft_key(persona_id))
    if setting is not None:
        db.session.delete(setting)
