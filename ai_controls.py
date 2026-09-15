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
from models import AILog, AIPersona, Post, SiteSetting, User
from time_utils import utcnow


GLOBAL_ACTIVITY_KEY = "ai_activity_enabled"
GLOBAL_POST_SPACING_KEY = "ai_global_post_spacing_hours"
PROFILE_KEY_PREFIX = "ai_profile_control:"
PENDING_DRAFT_KEY_PREFIX = "ai_pending_draft:"
GROUP_CONTROL_KEY_PREFIX = "ai_group_control:"
AUTOMATIC_POST_COOLDOWN = timedelta(days=14)
AUTOMATIC_GLOBAL_POST_SPACING = timedelta(hours=24)
_UNSET = object()

DEFAULT_PROFILE_CONFIG = {
    "enabled": True,
    "paused": False,
    "posting_mode": "automatic",
    "active_days": [0, 1, 2, 3, 4, 5, 6],
    "posting_start_time": "00:00",
    "posting_end_time": "23:59",
    "max_posts_per_day": 1,
    "minimum_post_interval_minutes": 720,
    "maximum_total_posts_per_week": 2,
    "maximum_feed_posts_per_week": 1,
    "maximum_group_posts_per_week": 1,
    "posting_days": [0, 1, 2, 3, 4, 5, 6],
    "post_today_enabled": None,
    "post_today_date": None,
    "max_replies_per_day": 5,
    "replies_enabled": True,
    "reply_probability": 35,
    "minimum_reply_delay_minutes": 0,
    "maximum_reply_delay_minutes": 0,
    "disallowed_topics": [],
    "allow_general_feed_posts": True,
    "group_activity_enabled": False,
    "group_can_post": False,
    "group_can_comment": False,
    "group_can_reply": False,
    "allowed_group_ids": [],
    "max_group_posts_per_day": 1,
    "max_group_comments_per_day": 2,
    "max_group_replies_per_day": 2,
    "minimum_group_activity_interval_minutes": 360,
}

DEFAULT_GROUP_CONFIG = {
    "activity_level": "off",
    "quiet_comment_hours": 24,
    "quiet_post_hours": 72,
    "thread_cooldown_minutes": 1440,
}

GROUP_LEVEL_RULES = {
    "off": {"minimum_interval": None, "comment_multiplier": None, "post_multiplier": None},
    "low": {"minimum_interval": 1440, "comment_multiplier": 2.0, "post_multiplier": 2.0},
    "medium": {"minimum_interval": 360, "comment_multiplier": 1.0, "post_multiplier": 1.0},
    "high": {"minimum_interval": 120, "comment_multiplier": 0.5, "post_multiplier": 0.5},
}


def _profile_key(persona_id):
    return f"{PROFILE_KEY_PREFIX}{int(persona_id)}"


def _draft_key(persona_id):
    return f"{PENDING_DRAFT_KEY_PREFIX}{int(persona_id)}"


def _group_key(group_id):
    return f"{GROUP_CONTROL_KEY_PREFIX}{int(group_id)}"


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
    config["maximum_total_posts_per_week"] = _bounded_int(
        raw_config.get("maximum_total_posts_per_week"), 2, 0, 20
    )
    config["maximum_feed_posts_per_week"] = _bounded_int(
        raw_config.get("maximum_feed_posts_per_week"), 1, 0, 20
    )
    config["maximum_group_posts_per_week"] = _bounded_int(
        raw_config.get("maximum_group_posts_per_week"), 1, 0, 20
    )
    posting_days = raw_config.get("posting_days", config["posting_days"])
    if isinstance(posting_days, list):
        config["posting_days"] = sorted(
            {int(day) for day in posting_days if str(day).isdigit() and 0 <= int(day) <= 6}
        )
    post_today = raw_config.get("post_today_enabled")
    config["post_today_enabled"] = post_today if isinstance(post_today, bool) else None
    post_today_date = raw_config.get("post_today_date")
    try:
        config["post_today_date"] = datetime.strptime(
            str(post_today_date), "%Y-%m-%d"
        ).date().isoformat()
    except (TypeError, ValueError):
        config["post_today_date"] = None
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
    config["allow_general_feed_posts"] = bool(
        raw_config.get(
            "allow_general_feed_posts", config["allow_general_feed_posts"]
        )
    )
    config["group_activity_enabled"] = bool(
        raw_config.get("group_activity_enabled", config["group_activity_enabled"])
    )
    for capability in ("group_can_post", "group_can_comment", "group_can_reply"):
        config[capability] = bool(raw_config.get(capability, config[capability]))
    group_ids = raw_config.get("allowed_group_ids", [])
    if isinstance(group_ids, list):
        config["allowed_group_ids"] = sorted(
            {int(group_id) for group_id in group_ids if str(group_id).isdigit() and int(group_id) > 0}
        )
    config["max_group_posts_per_day"] = _bounded_int(
        raw_config.get("max_group_posts_per_day"), 1, 0, 20
    )
    config["max_group_comments_per_day"] = _bounded_int(
        raw_config.get("max_group_comments_per_day"), 2, 0, 50
    )
    config["max_group_replies_per_day"] = _bounded_int(
        raw_config.get("max_group_replies_per_day"), 2, 0, 50
    )
    config["minimum_group_activity_interval_minutes"] = _bounded_int(
        raw_config.get("minimum_group_activity_interval_minutes"), 360, 0, 10080
    )
    return config


def normalize_group_config(raw_config):
    raw_config = raw_config if isinstance(raw_config, dict) else {}
    config = deepcopy(DEFAULT_GROUP_CONFIG)
    level = str(raw_config.get("activity_level", "off")).lower()
    config["activity_level"] = level if level in GROUP_LEVEL_RULES else "off"
    config["quiet_comment_hours"] = _bounded_int(
        raw_config.get("quiet_comment_hours"), 24, 1, 720
    )
    config["quiet_post_hours"] = _bounded_int(
        raw_config.get("quiet_post_hours"), 72, 1, 1440
    )
    if config["quiet_post_hours"] < config["quiet_comment_hours"]:
        config["quiet_post_hours"] = config["quiet_comment_hours"]
    config["thread_cooldown_minutes"] = _bounded_int(
        raw_config.get("thread_cooldown_minutes"), 1440, 0, 10080
    )
    return config


def get_profile_config(persona):
    return normalize_profile_config(
        _load_json_setting(_profile_key(persona.id), DEFAULT_PROFILE_CONFIG)
    )


def get_profile_configs(personas):
    """Load all per-persona JSON controls in one query for admin rendering."""
    personas = list(personas)
    keys = {_profile_key(persona.id): persona.id for persona in personas}
    rows = SiteSetting.query.filter(SiteSetting.key.in_(keys or {""})).all()
    raw_by_id = {}
    for row in rows:
        try:
            raw_by_id[keys[row.key]] = json.loads(row.value or "{}")
        except (TypeError, ValueError):
            raw_by_id[keys[row.key]] = {}
    return {
        persona.id: normalize_profile_config(raw_by_id.get(persona.id, {}))
        for persona in personas
    }


def get_pending_drafts(personas):
    """Load pending approval drafts for an admin page in one query."""
    personas = list(personas)
    keys = {_draft_key(persona.id): persona.id for persona in personas}
    rows = SiteSetting.query.filter(SiteSetting.key.in_(keys or {""})).all()
    drafts = {persona.id: {} for persona in personas}
    for row in rows:
        try:
            parsed = json.loads(row.value or "{}")
        except (TypeError, ValueError):
            parsed = {}
        drafts[keys[row.key]] = parsed if isinstance(parsed, dict) else {}
    return drafts


def save_profile_config(persona, raw_config):
    config = normalize_profile_config(raw_config)
    SiteSetting.set_value(_profile_key(persona.id), json.dumps(config, sort_keys=True))
    return config


def get_group_config(group_or_id):
    group_id = getattr(group_or_id, "id", group_or_id)
    return normalize_group_config(
        _load_json_setting(_group_key(group_id), DEFAULT_GROUP_CONFIG)
    )


def get_group_configs(groups):
    groups = list(groups)
    keys = {_group_key(group.id): group.id for group in groups}
    rows = SiteSetting.query.filter(SiteSetting.key.in_(keys or {""})).all()
    raw_by_id = {}
    for row in rows:
        try:
            raw_by_id[keys[row.key]] = json.loads(row.value or "{}")
        except (TypeError, ValueError):
            raw_by_id[keys[row.key]] = {}
    return {
        group.id: normalize_group_config(raw_by_id.get(group.id, {}))
        for group in groups
    }


def save_group_config(group_or_id, raw_config):
    group_id = getattr(group_or_id, "id", group_or_id)
    config = normalize_group_config(raw_config)
    SiteSetting.set_value(_group_key(group_id), json.dumps(config, sort_keys=True))
    return config


def is_global_activity_enabled():
    value = SiteSetting.get_value(GLOBAL_ACTIVITY_KEY, "1")
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def set_global_activity_enabled(enabled):
    SiteSetting.set_value(GLOBAL_ACTIVITY_KEY, "1" if enabled else "0")


def get_global_post_spacing_hours():
    return _bounded_int(SiteSetting.get_value(GLOBAL_POST_SPACING_KEY, "6"), 6, 0, 48)


def set_global_post_spacing_hours(hours):
    value = _bounded_int(hours, 6, 0, 48)
    SiteSetting.set_value(GLOBAL_POST_SPACING_KEY, str(value))
    return value


def set_post_today(persona, enabled, now=None):
    config = get_profile_config(persona)
    config["post_today_enabled"] = bool(enabled)
    config["post_today_date"] = _local_now(persona, now).date().isoformat()
    return save_profile_config(persona, config)


def post_today_override(persona, now=None, config=None):
    """Return today's explicit override, or ``None`` for stale/unset values."""
    config = config or get_profile_config(persona)
    if config["post_today_date"] != _local_now(persona, now).date().isoformat():
        return None
    return config["post_today_enabled"]


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


def _group_action_types(action=None):
    mapping = {
        "post": ("GROUP_POST_AUTOMATIC", "GROUP_POST_MANUAL"),
        "comment": ("GROUP_COMMENT_AUTOMATIC", "GROUP_COMMENT_MANUAL"),
        "reply": ("GROUP_REPLY_AUTOMATIC", "GROUP_REPLY_MANUAL"),
    }
    if action:
        return mapping[action]
    return tuple(value for values in mapping.values() for value in values)


def action_count_since(persona_id, action, since):
    return AILog.query.filter(
        AILog.persona_id == persona_id,
        AILog.action_type.in_(_action_types(action)),
        AILog.timestamp >= since,
        AILog.is_escalated.is_(False),
    ).count()


def group_action_count_since(persona_id, action, since):
    return AILog.query.filter(
        AILog.persona_id == persona_id,
        AILog.action_type.in_(_group_action_types(action)),
        AILog.timestamp >= since,
        AILog.is_escalated.is_(False),
    ).count()


def today_action_count(persona, action, now=None):
    local_now = _local_now(persona, now)
    local_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    utc_start = local_start.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    return action_count_since(persona.id, action, utc_start)


def today_group_action_count(persona, action, now=None):
    local_now = _local_now(persona, now)
    local_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    utc_start = local_start.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    return group_action_count_since(persona.id, action, utc_start)


def _local_week_start_utc(persona, now=None):
    local_now = _local_now(persona, now)
    monday = (local_now - timedelta(days=local_now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return monday.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


def weekly_post_counts(persona, now=None):
    """Monday 00:00 through Sunday 23:59 in the AI user's timezone."""
    since = _local_week_start_utc(persona, now)
    base = Post.query.filter(Post.author_id == persona.user_id, Post.created_at >= since)
    feed = base.filter(Post.group_id.is_(None)).count()
    group = base.filter(Post.group_id.is_not(None)).count()
    return {"total": feed + group, "feed": feed, "group": group}


def admin_persona_metrics(personas, configs, now=None):
    """Build control-center counters with bounded bulk queries."""
    personas = list(personas)
    if not personas:
        return {}
    now = now or utcnow()
    week_starts = {
        persona.id: _local_week_start_utc(persona, now) for persona in personas
    }
    day_starts = {}
    for persona in personas:
        local_now = _local_now(persona, now)
        day_starts[persona.id] = local_now.replace(
            hour=0, minute=0, second=0, microsecond=0
        ).astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

    user_to_persona = {persona.user_id: persona.id for persona in personas}
    recent_posts = (
        db.session.query(Post.author_id, Post.created_at, Post.group_id)
        .filter(
            Post.author_id.in_(user_to_persona),
            Post.created_at >= min(week_starts.values()),
        )
        .all()
    )
    last_post_rows = (
        db.session.query(Post.author_id, db.func.max(Post.created_at))
        .filter(Post.author_id.in_(user_to_persona))
        .group_by(Post.author_id)
        .all()
    )
    last_post_by_persona = {
        user_to_persona[user_id]: timestamp for user_id, timestamp in last_post_rows
    }
    global_last = max(last_post_by_persona.values(), default=None)

    tracked_log_types = (
        _action_types("post")
        + _action_types("reply")
        + _group_action_types("comment")
        + _group_action_types("reply")
    )
    recent_logs = (
        db.session.query(AILog.persona_id, AILog.action_type, AILog.timestamp)
        .filter(
            AILog.persona_id.in_([persona.id for persona in personas]),
            AILog.action_type.in_(tracked_log_types),
            AILog.timestamp >= min(day_starts.values()),
            AILog.is_escalated.is_(False),
        )
        .all()
    )
    last_action_rows = (
        db.session.query(AILog.persona_id, db.func.max(AILog.timestamp))
        .filter(
            AILog.persona_id.in_([persona.id for persona in personas]),
            AILog.action_type.in_(_action_types("post")),
            AILog.is_escalated.is_(False),
        )
        .group_by(AILog.persona_id)
        .all()
    )
    last_post_action_by_persona = dict(last_action_rows)

    metrics = {}
    for persona in personas:
        week_start = week_starts[persona.id]
        day_start = day_starts[persona.id]
        persona_posts = [
            row
            for row in recent_posts
            if row.author_id == persona.user_id and row.created_at >= week_start
        ]
        feed_count = sum(row.group_id is None for row in persona_posts)
        group_count = len(persona_posts) - feed_count
        today_posts = sum(row.created_at >= day_start for row in persona_posts)
        persona_logs = [
            row
            for row in recent_logs
            if row.persona_id == persona.id and row.timestamp >= day_start
        ]
        replies_today = sum(row.action_type in _action_types("reply") for row in persona_logs)
        group_comments_today = sum(
            row.action_type in _group_action_types("comment") for row in persona_logs
        )
        group_replies_today = sum(
            row.action_type in _group_action_types("reply") for row in persona_logs
        )
        post_actions_today = sum(
            row.action_type in _action_types("post") for row in persona_logs
        )
        counts = {
            "total": feed_count + group_count,
            "feed": feed_count,
            "group": group_count,
        }
        config = configs[persona.id]
        metrics[persona.id] = {
            "posts_today": today_posts,
            "replies_today": replies_today,
            "group_comments_today": group_comments_today,
            "group_replies_today": group_replies_today,
            "weekly_counts": counts,
            "post_today_override": post_today_override(
                persona, now, config=config
            ),
            "last_post_at": last_post_by_persona.get(persona.id),
            "next_post_at": next_eligible_post_at(
                persona,
                now,
                config=config,
                counts=counts,
                last_post_at_value=last_post_by_persona.get(persona.id),
                global_last_post_at=global_last,
                today_post_actions=post_actions_today,
                last_post_action_at=last_post_action_by_persona.get(persona.id),
            ),
        }
    return metrics


def posts_today_count(persona, now=None):
    local_now = _local_now(persona, now)
    local_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    utc_start = local_start.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    return Post.query.filter(
        Post.author_id == persona.user_id,
        Post.created_at >= utc_start,
    ).count()


def last_ai_post_at(persona_id=None):
    query = db.session.query(Post.created_at).join(User, Post.author_id == User.id).filter(
        User.is_ai_persona.is_(True)
    )
    if persona_id is not None:
        query = query.join(AIPersona, AIPersona.user_id == User.id).filter(
            AIPersona.id == persona_id
        )
    row = query.order_by(Post.created_at.desc()).first()
    return row[0] if row else None


def order_personas_by_last_post(personas):
    """Order personas by oldest successful feed/group post using one query."""
    personas = list(personas)
    if not personas:
        return []

    persona_by_user_id = {persona.user_id: persona for persona in personas}
    rows = (
        db.session.query(Post.author_id, db.func.max(Post.created_at))
        .filter(Post.author_id.in_(persona_by_user_id))
        .group_by(Post.author_id)
        .all()
    )
    last_post_by_user_id = {author_id: created_at for author_id, created_at in rows}
    return sorted(
        personas,
        key=lambda persona: (
            last_post_by_user_id.get(persona.user_id) or datetime.min,
            persona.id,
        ),
    )


def new_post_eligibility(
    persona,
    channel,
    now=None,
    *,
    enforce_automatic_cadence=True,
):
    """Shared 14-day/weekly/stagger policy for feed and group NEW posts."""
    config = get_profile_config(persona)
    if channel == "feed" and not config["allow_general_feed_posts"]:
        return False, "feed_posting_disabled"
    if not action_is_allowed(persona, "post"):
        return False, "action_forbidden"
    local_now = _local_now(persona, now)
    if local_now.weekday() not in config["posting_days"]:
        return False, "posting_day_disabled"

    if post_today_override(persona, now) is False:
        return False, "post_today_disabled"

    comparable_now = now or utcnow()
    if comparable_now.tzinfo is not None:
        comparable_now = comparable_now.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

    if enforce_automatic_cadence:
        # A successful feed or group Post consumes the same persisted 14-day budget.
        persona_last = last_ai_post_at(persona.id)
        if persona_last:
            elapsed = comparable_now - persona_last
            if timedelta(0) <= elapsed < AUTOMATIC_POST_COOLDOWN:
                return False, "fourteen_day_post_limit"

    counts = weekly_post_counts(persona, now)
    if counts["total"] >= config["maximum_total_posts_per_week"]:
        return False, "weekly_total_limit"
    channel_key = (
        "maximum_feed_posts_per_week"
        if channel == "feed"
        else "maximum_group_posts_per_week"
    )
    if counts[channel] >= config[channel_key]:
        return False, f"weekly_{channel}_limit"

    if enforce_automatic_cadence:
        global_last = last_ai_post_at()
        if global_last:
            elapsed = comparable_now - global_last
            configured_spacing = timedelta(hours=get_global_post_spacing_hours())
            if timedelta(0) <= elapsed < max(
                AUTOMATIC_GLOBAL_POST_SPACING,
                configured_spacing,
            ):
                return False, "global_post_spacing"
    return True, "eligible"


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


def last_group_action_at(persona_id, group_id=None):
    query = AILog.query.filter(
        AILog.persona_id == persona_id,
        AILog.action_type.in_(_group_action_types()),
        AILog.is_escalated.is_(False),
    )
    if group_id is not None:
        query = query.filter(AILog.prompt_context.contains(f"group_id={int(group_id)}"))
    row = query.order_by(AILog.timestamp.desc()).first()
    return row.timestamp if row else None


def next_eligible_post_at(
    persona,
    now=None,
    *,
    config=None,
    counts=None,
    last_post_at_value=_UNSET,
    global_last_post_at=_UNSET,
    today_post_actions=None,
    last_post_action_at=_UNSET,
):
    """Calculate the next ordinary posting-window opportunity when possible."""
    if not is_global_activity_enabled() or not persona.is_active:
        return None
    config = config or get_profile_config(persona)
    if (
        not config["enabled"]
        or config["paused"]
        or config["posting_mode"] != "automatic"
        or not config["active_days"]
        or not config["posting_days"]
        or config["max_posts_per_day"] == 0
        or config["maximum_total_posts_per_week"] == 0
    ):
        return None
    feed_destination_enabled = bool(
        config["allow_general_feed_posts"]
        and config["maximum_feed_posts_per_week"] > 0
    )
    group_destination_enabled = bool(
        config["group_activity_enabled"]
        and config["group_can_post"]
        and config["maximum_group_posts_per_week"] > 0
        and config["allowed_group_ids"]
    )
    if not feed_destination_enabled and not group_destination_enabled:
        return None

    local_now = _local_now(persona, now)
    candidate = local_now
    counts = counts or weekly_post_counts(persona, now)
    feed_exhausted = (
        not feed_destination_enabled
        or counts["feed"] >= config["maximum_feed_posts_per_week"]
    )
    group_exhausted = (
        not group_destination_enabled
        or counts["group"] >= config["maximum_group_posts_per_week"]
    )
    if counts["total"] >= config["maximum_total_posts_per_week"] or (
        feed_exhausted and group_exhausted
    ):
        candidate = (local_now + timedelta(days=7 - local_now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    if (
        config["post_today_date"] == local_now.date().isoformat()
        and config["post_today_enabled"] is False
    ):
        candidate = max(
            candidate,
            (local_now + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            ),
        )
    global_last = (
        global_last_post_at
        if global_last_post_at is not _UNSET
        else last_ai_post_at()
    )
    if global_last:
        global_candidate = global_last.replace(tzinfo=ZoneInfo("UTC")).astimezone(
            local_now.tzinfo
        ) + max(
            AUTOMATIC_GLOBAL_POST_SPACING,
            timedelta(hours=get_global_post_spacing_hours()),
        )
        candidate = max(candidate, global_candidate)
    persona_last = (
        last_post_at_value
        if last_post_at_value is not _UNSET
        else last_ai_post_at(persona.id)
    )
    if persona_last:
        persona_candidate = persona_last.replace(tzinfo=ZoneInfo("UTC")).astimezone(
            local_now.tzinfo
        ) + AUTOMATIC_POST_COOLDOWN
        candidate = max(candidate, persona_candidate)
    last_post = (
        last_post_action_at
        if last_post_action_at is not _UNSET
        else last_action_at(persona.id, "post")
    )
    if last_post:
        last_post = last_post.replace(tzinfo=ZoneInfo("UTC")).astimezone(local_now.tzinfo)
        candidate = max(
            candidate,
            last_post + timedelta(minutes=config["minimum_post_interval_minutes"]),
        )
    current_today_actions = (
        today_post_actions
        if today_post_actions is not None
        else today_action_count(persona, "post", now)
    )
    if current_today_actions >= config["max_posts_per_day"]:
        candidate = (local_now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

    start = time.fromisoformat(config["posting_start_time"])
    end = time.fromisoformat(config["posting_end_time"])
    for day_offset in range(8):
        day = (candidate + timedelta(days=day_offset)).date()
        if day.weekday() not in config["active_days"] or day.weekday() not in config["posting_days"]:
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
    if not action_is_allowed(persona, action):
        return False, "action_forbidden"
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
        post_allowed, post_reason = new_post_eligibility(persona, "feed", now)
        if not post_allowed:
            return False, post_reason

    return True, "eligible"


def manual_eligibility(persona, channel=None, now=None):
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
    if not action_is_allowed(persona, "post" if channel else "comment"):
        return False, "action_forbidden"
    if channel:
        return new_post_eligibility(
            persona,
            channel,
            now,
            enforce_automatic_cadence=False,
        )
    return True, "eligible"


def group_automation_eligibility(persona, group, action, now=None):
    """Return eligibility for one automated group post/comment/reply."""
    if not is_global_activity_enabled():
        return False, "global_stop"
    if not persona.is_active or not getattr(persona.user, "is_active", False):
        return False, "disabled"
    if not getattr(group, "is_active", False):
        return False, "inactive_group"

    config = get_profile_config(persona)
    if not config["enabled"]:
        return False, "disabled"
    if config["paused"]:
        return False, "paused"
    if not action_is_allowed(persona, action):
        return False, "action_forbidden"
    if config["posting_mode"] != "automatic":
        return False, config["posting_mode"]
    if not config["group_activity_enabled"]:
        return False, "group_activity_disabled"
    if group.id not in config["allowed_group_ids"]:
        return False, "group_not_allowed"
    if group.members.filter_by(id=persona.user_id).first() is None:
        return False, "not_member"

    capability = {
        "post": "group_can_post",
        "comment": "group_can_comment",
        "reply": "group_can_reply",
    }[action]
    if not config[capability]:
        return False, "capability_disabled"

    group_config = get_group_config(group)
    level = group_config["activity_level"]
    level_rules = GROUP_LEVEL_RULES[level]
    if level == "off":
        return False, "group_level_off"

    local_now = _local_now(persona, now)
    if local_now.weekday() not in config["active_days"]:
        return False, "inactive_day"
    if not _inside_window(
        local_now, config["posting_start_time"], config["posting_end_time"]
    ):
        return False, "outside_window"

    limit_key = {
        "post": "max_group_posts_per_day",
        "comment": "max_group_comments_per_day",
        "reply": "max_group_replies_per_day",
    }[action]
    if today_group_action_count(persona, action, now) >= config[limit_key]:
        return False, "daily_limit"

    comparable_now = now or utcnow()
    if comparable_now.tzinfo is not None:
        comparable_now = comparable_now.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    minimum_interval = max(
        config["minimum_group_activity_interval_minutes"],
        level_rules["minimum_interval"],
    )
    # A direct human reply should not wait behind the broader group cadence.
    # Duplicate-source and per-thread cooldown checks still bound reply loops.
    if action != "reply":
        last_activity = last_group_action_at(persona.id)
        if last_activity and comparable_now - last_activity < timedelta(minutes=minimum_interval):
            return False, "minimum_interval"
    if action == "post":
        post_allowed, post_reason = new_post_eligibility(persona, "group", now)
        if not post_allowed:
            return False, post_reason
    return True, "eligible"


def manual_group_post_eligibility(persona, group, now=None):
    """Validate an explicit admin-selected group destination without automation cadence."""
    allowed, reason = manual_eligibility(persona, "group", now)
    if not allowed:
        return allowed, reason
    if not getattr(group, "is_active", False):
        return False, "inactive_group"
    config = get_profile_config(persona)
    if not config["group_activity_enabled"] or not config["group_can_post"]:
        return False, "group_posting_disabled"
    if group.id not in config["allowed_group_ids"]:
        return False, "group_not_allowed"
    if group.members.filter_by(id=persona.user_id).first() is None:
        return False, "not_member"
    if not action_is_allowed(persona, "post"):
        return False, "action_forbidden"
    return True, "eligible"


def group_quiet_threshold_hours(group, action):
    config = get_group_config(group)
    level_rules = GROUP_LEVEL_RULES[config["activity_level"]]
    if config["activity_level"] == "off":
        return None
    base = config["quiet_post_hours"] if action == "post" else config["quiet_comment_hours"]
    multiplier = (
        level_rules["post_multiplier"]
        if action == "post"
        else level_rules["comment_multiplier"]
    )
    floor = 24 if action == "post" else 6
    return max(floor, int(base * multiplier))


def human_group_quiet_hours(group, now=None):
    """Hours since the newest human post or comment in a group."""
    from models import Comment, User

    last_post = (
        db.session.query(Post.created_at)
        .join(User, Post.author_id == User.id)
        .filter(Post.group_id == group.id, User.is_ai_persona.is_(False))
        .order_by(Post.created_at.desc())
        .first()
    )
    last_comment = (
        db.session.query(Comment.created_at)
        .join(Post, Comment.post_id == Post.id)
        .join(User, Comment.author_id == User.id)
        .filter(Post.group_id == group.id, User.is_ai_persona.is_(False))
        .order_by(Comment.created_at.desc())
        .first()
    )
    timestamps = [row[0] for row in (last_post, last_comment) if row and row[0]]
    if not timestamps:
        return float("inf")
    comparable_now = now or utcnow()
    if comparable_now.tzinfo is not None:
        comparable_now = comparable_now.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    return max(0, (comparable_now - max(timestamps)).total_seconds() / 3600)


def group_is_quiet_enough(group, action, now=None):
    threshold = group_quiet_threshold_hours(group, action)
    return threshold is not None and human_group_quiet_hours(group, now) >= threshold


def thread_in_group_cooldown(persona, group, post_id, now=None):
    config = get_group_config(group)
    comparable_now = now or utcnow()
    if comparable_now.tzinfo is not None:
        comparable_now = comparable_now.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    since = comparable_now - timedelta(minutes=config["thread_cooldown_minutes"])
    marker = f"group_post_id={int(post_id)}"
    return AILog.query.filter(
        AILog.persona_id == persona.id,
        AILog.action_type.in_(
            _group_action_types("comment") + _group_action_types("reply")
        ),
        AILog.timestamp >= since,
        AILog.prompt_context.contains(marker),
    ).first() is not None


def prefer_feed_this_tick(now=None):
    """Reserve one of every four scheduler slots for feed-first selection."""
    current = now or utcnow()
    return int(current.timestamp() // (15 * 60)) % 4 == 0


def content_is_allowed(persona, content):
    normalized = (content or "").casefold()
    return not any(
        topic.casefold() in normalized
        for topic in get_profile_config(persona)["disallowed_topics"]
    )


def _normalized_action_values(values):
    return {
        str(value).strip().casefold().replace("-", "_").replace(" ", "_")
        for value in (values or [])
        if str(value).strip()
    }


def action_is_allowed(persona, action):
    """Enforce persisted action policy as an execution boundary.

    Historic persona records use ``comment`` to cover comments and replies, so
    reply retains that backwards-compatible alias.
    """
    action = str(action or "").strip().casefold().replace("-", "_")
    aliases = {
        "post": {"post", "create_post", "feed_post", "group_post"},
        "comment": {"comment", "create_comment", "group_comment"},
        "reply": {"reply", "comment", "create_comment", "group_reply"},
    }.get(action, {action})
    forbidden = _normalized_action_values(persona.forbidden_actions)
    if aliases & forbidden:
        return False
    allowed = _normalized_action_values(persona.allowed_actions)
    return not allowed or bool(aliases & allowed)


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
