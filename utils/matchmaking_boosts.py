"""Consent and bounded featured-Boost queries for the private Matchmaking group."""

from __future__ import annotations

from sqlalchemy import String, and_, cast, exists, literal, or_

from extensions import db
from models import MatchmakingPayments, MatchmakingRequest, SiteSetting, User
from time_utils import utcnow


BOOST_GROUP_CONSENT_PREFIX = "matchmaking_group_boost_consent:"


def boost_group_consent_key(request_id):
    return f"{BOOST_GROUP_CONSENT_PREFIX}{int(request_id)}"


def set_boost_group_consent(request_id, consented):
    SiteSetting.set_value(
        boost_group_consent_key(request_id), "1" if consented else "0"
    )


def has_boost_group_consent(request_id):
    return SiteSetting.get_value(boost_group_consent_key(request_id), "0") == "1"


def featured_boosts_for_viewer(viewer, *, page=1, per_page=12, now=None):
    now = now or utcnow()
    per_page = 12 if per_page not in (6, 12, 24) else per_page
    page = max(1, int(page or 1))

    active_request_ids = (
        db.session.query(
            MatchmakingRequest.user_id.label("user_id"),
            db.func.max(MatchmakingRequest.id).label("request_id"),
        )
        .filter(
            MatchmakingRequest.status == "active",
            MatchmakingRequest.payment_status == "completed",
            MatchmakingRequest.end_date > now,
        )
        .group_by(MatchmakingRequest.user_id)
        .subquery()
    )
    payment_verified = exists().where(
        and_(
            MatchmakingPayments.matchmaking_request_id == MatchmakingRequest.id,
            MatchmakingPayments.status == "completed",
            MatchmakingPayments.payment_status == "paid",
        )
    )
    blocks = User._blocked_users
    blocked_pair = exists().where(
        or_(
            and_(
                blocks.c.blocker_id == viewer.id,
                blocks.c.blocked_id == User.id,
            ),
            and_(
                blocks.c.blocker_id == User.id,
                blocks.c.blocked_id == viewer.id,
            ),
        )
    )
    consent_key = literal(BOOST_GROUP_CONSENT_PREFIX) + cast(
        MatchmakingRequest.id, String
    )
    today = now.date()
    try:
        adult_cutoff = today.replace(year=today.year - 18)
    except ValueError:
        adult_cutoff = today.replace(year=today.year - 18, day=28)

    query = (
        MatchmakingRequest.query.join(
            active_request_ids,
            active_request_ids.c.request_id == MatchmakingRequest.id,
        )
        .join(User, User.id == MatchmakingRequest.user_id)
        .join(SiteSetting, SiteSetting.key == consent_key)
        .filter(
            SiteSetting.value == "1",
            payment_verified,
            User.id != viewer.id,
            User.is_active.is_(True),
            or_(User.is_admin.is_(False), User.is_admin.is_(None)),
            or_(User.is_super_admin.is_(False), User.is_super_admin.is_(None)),
            or_(User.is_ai_persona.is_(False), User.is_ai_persona.is_(None)),
            User.dob.isnot(None),
            User.dob <= adult_cutoff,
            User.first_name.isnot(None),
            User.last_name.isnot(None),
            User.gender.isnot(None),
            User.country.isnot(None),
            ~blocked_pair,
        )
        .options(db.joinedload(MatchmakingRequest.user))
        .order_by(MatchmakingRequest.created_at.desc(), MatchmakingRequest.id.desc())
    )
    return query.paginate(page=page, per_page=per_page, error_out=False)
