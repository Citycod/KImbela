"""Authorization policy for Kimbela's configured Matchmaking group.

The group is deliberately identified only by ``MATCHMAKING_GROUP_ID``.  This
module must never fall back to a mutable display name.
"""

from __future__ import annotations

from flask import current_app

from extensions import db
from models import Group


_logged_config_errors = set()


def _log_config_error_once(message, *args):
    key = (message, args)
    if key in _logged_config_errors:
        return
    _logged_config_errors.add(key)
    current_app.logger.error(message, *args)


def configured_matchmaking_group_id(*, validate_exists=False):
    raw_value = current_app.config.get("MATCHMAKING_GROUP_ID")
    try:
        group_id = int(raw_value)
        if group_id <= 0:
            raise ValueError
    except (TypeError, ValueError):
        _log_config_error_once(
            "MATCHMAKING_GROUP_ID is missing or malformed; protected "
            "Matchmaking features are unavailable"
        )
        return None

    if validate_exists and db.session.get(Group, group_id) is None:
        _log_config_error_once(
            "MATCHMAKING_GROUP_ID=%s does not resolve to a deployed Group row; "
            "protected Matchmaking features are unavailable",
            group_id,
        )
        return None
    return group_id


def is_matchmaking_group(group):
    if group is None:
        return False
    configured_id = configured_matchmaking_group_id()
    return configured_id is not None and group.id == configured_id


def is_matchmaking_post(post):
    """Identify protected content without relying on mutable group metadata."""
    if post is None or post.group_id is None:
        return False
    configured_id = configured_matchmaking_group_id()
    return configured_id is not None and post.group_id == configured_id


def is_group_member(group, user):
    return bool(
        group
        and user
        and getattr(user, "is_authenticated", True)
        and group.members.filter_by(id=user.id).first() is not None
    )


def can_view_group(group, user):
    if not is_matchmaking_group(group):
        return True
    return bool(
        getattr(user, "is_admin", False)
        or getattr(user, "is_super_admin", False)
        or is_group_member(group, user)
    )


def can_join_group(group, user):
    if not is_matchmaking_group(group):
        return True
    return bool(
        getattr(user, "is_admin", False)
        or getattr(user, "is_super_admin", False)
    )


def can_create_group_post(group, user):
    if not is_group_member(group, user):
        return False
    if not is_matchmaking_group(group):
        return True
    return bool(
        getattr(user, "is_admin", False)
        or getattr(user, "is_super_admin", False)
    )


def can_view_post(post, user):
    if not post or post.group_id is None:
        return True
    group = db.session.get(Group, post.group_id)
    return can_view_group(group, user)
