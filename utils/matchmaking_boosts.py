"""Bounded paid-profile queries for the private Matchmaking group."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import timedelta
from math import ceil

from sqlalchemy import and_, exists, literal, or_, select, union_all

from extensions import db
from models import (
    MatchmakingPayments,
    MatchmakingRequest,
    PaymentTransaction,
    SiteSetting,
    User,
)
from payments.browse_access import BROWSE_ACCESS_DAYS, BROWSE_TRANSACTION_TYPE
from time_utils import utcnow
from utils.matchmaking_group import can_view_group, is_matchmaking_group


BOOST_GROUP_CONSENT_PREFIX = "matchmaking_group_boost_consent:"


def boost_group_consent_key(request_id):
    return f"{BOOST_GROUP_CONSENT_PREFIX}{int(request_id)}"


def set_boost_group_consent(request_id, consented):
    SiteSetting.set_value(
        boost_group_consent_key(request_id), "1" if consented else "0"
    )


def has_boost_group_consent(request_id):
    return SiteSetting.get_value(boost_group_consent_key(request_id), "0") == "1"


@dataclass(frozen=True)
class PaidMatchmakingProfile:
    """Display-safe paid Matchmaking profile prepared by the server."""

    user: User
    source: str
    activated_at: object
    expires_at: object
    image: str | None
    about: str
    interests: tuple[str, ...]
    age: int | None
    location: str

    @property
    def badge(self):
        return "Boosted" if self.source == "boost" else "Find Your Match"


@dataclass(frozen=True)
class PaidMatchmakingProfilePage:
    items: tuple[PaidMatchmakingProfile, ...]
    page: int
    per_page: int
    total: int

    @property
    def pages(self):
        return ceil(self.total / self.per_page) if self.total else 0

    @property
    def has_prev(self):
        return self.page > 1

    @property
    def has_next(self):
        return self.page < self.pages

    @property
    def prev_num(self):
        return self.page - 1 if self.has_prev else None

    @property
    def next_num(self):
        return self.page + 1 if self.has_next else None


def _empty_paid_profile_page(page, per_page):
    return PaidMatchmakingProfilePage((), page, per_page, 0)


def _display_interests(user, request_row):
    if request_row is not None:
        return tuple(request_row.get_your_interests()[:6])

    raw = (user.interests or "").strip()
    if not raw:
        return ()
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        parsed = [item.strip() for item in raw.split(",")]
    if not isinstance(parsed, list):
        return ()
    return tuple(str(item).strip() for item in parsed if str(item).strip())[:6]


def _display_age(dob, today):
    if not dob:
        return None
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def _adult_cutoff(today):
    try:
        return today.replace(year=today.year - 18)
    except ValueError:
        return today.replace(year=today.year - 18, day=28)


def visible_paid_matchmaking_profiles(viewer, group, *, page=1, per_page=12, now=None):
    """Return one bounded, deduplicated page of verified paid profiles.

    Boost profiles sort first. Find Your Match-only profiles follow. Within
    each product the newest currently-active entitlement sorts first.
    """
    now = now or utcnow()
    per_page = 12 if per_page not in (6, 12, 24) else per_page
    page = max(1, int(page or 1))

    if not is_matchmaking_group(group) or not can_view_group(group, viewer):
        return _empty_paid_profile_page(page, per_page)

    verified_boost_payment = exists().where(
        and_(
            MatchmakingPayments.matchmaking_request_id == MatchmakingRequest.id,
            MatchmakingPayments.user_id == MatchmakingRequest.user_id,
            MatchmakingPayments.status == "completed",
            MatchmakingPayments.payment_status == "paid",
        )
    )
    boost_candidates = select(
        MatchmakingRequest.user_id.label("user_id"),
        literal(0).label("source_rank"),
        literal("boost").label("source"),
        MatchmakingRequest.id.label("request_id"),
        db.func.coalesce(
            MatchmakingRequest.updated_at,
            MatchmakingRequest.created_at,
        ).label("activated_at"),
        MatchmakingRequest.end_date.label("expires_at"),
    ).where(
        MatchmakingRequest.status == "active",
        MatchmakingRequest.payment_status == "completed",
        MatchmakingRequest.end_date.isnot(None),
        MatchmakingRequest.end_date > now,
        verified_boost_payment,
    )

    find_activated_at = db.func.coalesce(
        PaymentTransaction.updated_at,
        PaymentTransaction.created_at,
    )
    find_candidates = select(
        PaymentTransaction.user_id.label("user_id"),
        literal(1).label("source_rank"),
        literal("find").label("source"),
        literal(None).label("request_id"),
        find_activated_at.label("activated_at"),
        literal(None).label("expires_at"),
    ).where(
        PaymentTransaction.transaction_type == BROWSE_TRANSACTION_TYPE,
        PaymentTransaction.status == "completed",
        find_activated_at > now - timedelta(days=BROWSE_ACCESS_DAYS),
    )

    candidates = union_all(boost_candidates, find_candidates).subquery()
    ranked = select(
        candidates,
        db.func.row_number()
        .over(
            partition_by=candidates.c.user_id,
            order_by=(
                candidates.c.source_rank.asc(),
                candidates.c.activated_at.desc(),
                candidates.c.request_id.desc(),
            ),
        )
        .label("choice_rank"),
    ).subquery()
    chosen = select(ranked).where(ranked.c.choice_rank == 1).subquery()

    blocks = User._blocked_users
    adult_cutoff = _adult_cutoff(now.date())
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
    query = (
        db.session.query(
            User,
            chosen.c.source,
            chosen.c.activated_at,
            chosen.c.expires_at,
            MatchmakingRequest,
        )
        .join(chosen, chosen.c.user_id == User.id)
        .outerjoin(MatchmakingRequest, MatchmakingRequest.id == chosen.c.request_id)
        .filter(
            User.id != viewer.id,
            User.is_active.is_(True),
            or_(User.is_admin.is_(False), User.is_admin.is_(None)),
            or_(User.is_super_admin.is_(False), User.is_super_admin.is_(None)),
            or_(User.is_ai_persona.is_(False), User.is_ai_persona.is_(None)),
            User.first_name.isnot(None),
            User.last_name.isnot(None),
            User.dob.isnot(None),
            User.dob <= adult_cutoff,
            User.gender.isnot(None),
            User.country.isnot(None),
            ~blocked_pair,
        )
        .order_by(
            chosen.c.source_rank.asc(),
            chosen.c.activated_at.desc(),
            User.id.desc(),
        )
    )

    total = query.count()
    rows = query.offset((page - 1) * per_page).limit(per_page).all()
    profiles = []
    for user, source, activated_at, boost_expires_at, request_row in rows:
        expires_at = (
            boost_expires_at
            if source == "boost"
            else activated_at + timedelta(days=BROWSE_ACCESS_DAYS)
        )
        location = ", ".join(
            part for part in (user.city, user.state, user.country) if part
        )
        profiles.append(
            PaidMatchmakingProfile(
                user=user,
                source=source,
                activated_at=activated_at,
                expires_at=expires_at,
                image=(request_row.image if request_row else None) or user.profile_pic,
                about=(request_row.about_you if request_row else None)
                or user.bio
                or user.about_me
                or "",
                interests=_display_interests(user, request_row),
                age=_display_age(user.dob, now.date()),
                location=location,
            )
        )

    return PaidMatchmakingProfilePage(tuple(profiles), page, per_page, total)


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
    adult_cutoff = _adult_cutoff(now.date())

    query = (
        MatchmakingRequest.query.join(
            active_request_ids,
            active_request_ids.c.request_id == MatchmakingRequest.id,
        )
        .join(User, User.id == MatchmakingRequest.user_id)
        .filter(
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
