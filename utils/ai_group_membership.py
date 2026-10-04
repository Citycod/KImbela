"""Idempotent membership synchronization for active AI personas and groups."""

from __future__ import annotations

from sqlalchemy import func, select

from extensions import db
from models import AIPersona, Group, User, group_members


def _ai_persona_user_ids():
    return [
        user_id
        for (user_id,) in (
            db.session.query(User.id)
            .join(AIPersona, AIPersona.user_id == User.id)
            .filter(
                User.is_ai_persona.is_(True),
            )
            .all()
        )
    ]


def _insert_missing_memberships(user_ids, group_ids):
    user_ids = sorted({int(user_id) for user_id in user_ids})
    group_ids = sorted({int(group_id) for group_id in group_ids})
    if not user_ids or not group_ids:
        return 0

    existing = set(
        db.session.execute(
            select(group_members.c.user_id, group_members.c.group_id).where(
                group_members.c.user_id.in_(user_ids),
                group_members.c.group_id.in_(group_ids),
            )
        ).all()
    )
    missing = [
        {"user_id": user_id, "group_id": group_id}
        for group_id in group_ids
        for user_id in user_ids
        if (user_id, group_id) not in existing
    ]
    if missing:
        db.session.execute(group_members.insert(), missing)
        db.session.flush()

    counts = dict(
        db.session.execute(
            select(group_members.c.group_id, func.count(group_members.c.user_id))
            .where(group_members.c.group_id.in_(group_ids))
            .group_by(group_members.c.group_id)
        ).all()
    )
    for group in Group.query.filter(Group.id.in_(group_ids)).all():
        group.member_count = counts.get(group.id, 0)
    return len(missing)


def sync_ai_group_memberships():
    """Make every AI persona account a member of every active group."""
    group_ids = [
        group_id
        for (group_id,) in db.session.query(Group.id)
        .filter(Group.is_active.is_(True))
        .all()
    ]
    return _insert_missing_memberships(_ai_persona_user_ids(), group_ids)


def add_ai_users_to_group(group):
    """Synchronize every AI persona account into one active group."""
    if group is None or not group.is_active:
        return 0
    db.session.flush()
    return _insert_missing_memberships(_ai_persona_user_ids(), [group.id])


def add_ai_user_to_active_groups(persona):
    """Synchronize one AI persona account into all active groups."""
    if (
        persona is None
        or not persona.user
        or not persona.user.is_ai_persona
    ):
        return 0
    group_ids = [
        group_id
        for (group_id,) in db.session.query(Group.id)
        .filter(Group.is_active.is_(True))
        .all()
    ]
    return _insert_missing_memberships([persona.user_id], group_ids)
