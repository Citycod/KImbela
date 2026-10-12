from dataclasses import dataclass

from flask_login import AnonymousUserMixin
from sqlalchemy import and_, or_

from extensions import db
from models import (
    PROFILE_VISIBILITY_FIELDS,
    PROFILE_VISIBILITY_VALUES,
    User,
    UserProfilePrivacy,
    friendship,
)
from time_utils import utcnow


PRIVACY_FORM_FIELDS = {
    field: f"{field}_visibility" for field in PROFILE_VISIBILITY_FIELDS
}


def _authenticated(viewer):
    return bool(
        viewer is not None
        and not isinstance(viewer, AnonymousUserMixin)
        and getattr(viewer, "is_authenticated", False)
        and getattr(viewer, "id", None) is not None
    )


@dataclass(frozen=True)
class ProfileViewerContext:
    subject_id: int
    viewer_id: int | None
    is_owner: bool = False
    is_friend: bool = False
    is_blocked: bool = False
    authorized_admin: bool = False

    def can_view(self, subject, field):
        if field not in PROFILE_VISIBILITY_FIELDS:
            raise ValueError(f"Unknown profile privacy field: {field}")
        if self.is_blocked and not self.authorized_admin:
            return False
        if self.is_owner or self.authorized_admin:
            return True

        privacy = subject.profile_privacy
        if privacy is None:
            return False
        visibility = getattr(privacy, f"{field}_visibility", "private")
        if visibility == "public":
            return self.viewer_id is not None
        if visibility == "friends":
            return self.is_friend
        return False


def build_profile_viewer_context(subject, viewer, *, authorized_admin=False):
    viewer_id = getattr(viewer, "id", None) if _authenticated(viewer) else None
    is_owner = viewer_id is not None and viewer_id == subject.id
    if is_owner or authorized_admin:
        return ProfileViewerContext(
            subject_id=subject.id,
            viewer_id=viewer_id,
            is_owner=is_owner,
            authorized_admin=authorized_admin,
        )
    if viewer_id is None:
        return ProfileViewerContext(subject_id=subject.id, viewer_id=None)

    blocks = User._blocked_users
    is_blocked = (
        db.session.query(blocks.c.blocker_id)
        .filter(
            or_(
                and_(
                    blocks.c.blocker_id == viewer_id,
                    blocks.c.blocked_id == subject.id,
                ),
                and_(
                    blocks.c.blocker_id == subject.id,
                    blocks.c.blocked_id == viewer_id,
                ),
            )
        )
        .first()
        is not None
    )
    if is_blocked:
        return ProfileViewerContext(
            subject_id=subject.id,
            viewer_id=viewer_id,
            is_blocked=True,
        )

    is_friend = (
        db.session.query(friendship.c.user_id)
        .filter(
            or_(
                and_(
                    friendship.c.user_id == viewer_id,
                    friendship.c.friend_id == subject.id,
                ),
                and_(
                    friendship.c.user_id == subject.id,
                    friendship.c.friend_id == viewer_id,
                ),
            )
        )
        .first()
        is not None
    )
    return ProfileViewerContext(
        subject_id=subject.id,
        viewer_id=viewer_id,
        is_friend=is_friend,
    )


def build_profile_viewer_contexts(subjects, viewer):
    subjects = list(subjects)
    viewer_id = getattr(viewer, "id", None) if _authenticated(viewer) else None
    if not subjects:
        return {}
    if viewer_id is None:
        return {
            subject.id: ProfileViewerContext(subject.id, None) for subject in subjects
        }

    subject_ids = {subject.id for subject in subjects if subject.id != viewer_id}
    blocked_ids = set()
    friend_ids = set()
    if subject_ids:
        blocks = User._blocked_users
        for blocker_id, blocked_id in (
            db.session.query(blocks.c.blocker_id, blocks.c.blocked_id)
            .filter(
                or_(
                    and_(
                        blocks.c.blocker_id == viewer_id,
                        blocks.c.blocked_id.in_(subject_ids),
                    ),
                    and_(
                        blocks.c.blocked_id == viewer_id,
                        blocks.c.blocker_id.in_(subject_ids),
                    ),
                )
            )
            .all()
        ):
            blocked_ids.add(blocked_id if blocker_id == viewer_id else blocker_id)

        for user_id, friend_id in (
            db.session.query(friendship.c.user_id, friendship.c.friend_id)
            .filter(
                or_(
                    and_(
                        friendship.c.user_id == viewer_id,
                        friendship.c.friend_id.in_(subject_ids),
                    ),
                    and_(
                        friendship.c.friend_id == viewer_id,
                        friendship.c.user_id.in_(subject_ids),
                    ),
                )
            )
            .all()
        ):
            friend_ids.add(friend_id if user_id == viewer_id else user_id)

    return {
        subject.id: ProfileViewerContext(
            subject_id=subject.id,
            viewer_id=viewer_id,
            is_owner=subject.id == viewer_id,
            is_friend=subject.id in friend_ids,
            is_blocked=subject.id in blocked_ids,
        )
        for subject in subjects
    }


def calculate_age(dob):
    if not dob:
        return None
    today = utcnow().date()
    return today.year - dob.year - (
        (today.month, today.day) < (dob.month, dob.day)
    )


def serialize_profile(subject, context):
    can = lambda field: context.can_view(subject, field)
    location_visible = can("location")
    activity_visible = can("activity")
    birthday_visible = can("birthday")
    return {
        "id": subject.id,
        "public_id": subject.public_id,
        "first_name": subject.first_name,
        "last_name": subject.last_name,
        "full_name": subject.full_name,
        "profile_pic": subject.profile_pic,
        "cover_pic": subject.cover_pic,
        "show_bio": can("bio"),
        "bio": subject.bio if can("bio") else None,
        "age": calculate_age(subject.dob) if can("age") else None,
        "birthday": (
            subject.dob.strftime("%B %d")
            if birthday_visible and subject.dob
            else None
        ),
        "gender": subject.gender if can("gender") else None,
        "city": subject.city if location_visible else None,
        "state": subject.state if location_visible else None,
        "country": subject.country if location_visible else None,
        "marital_status": (
            subject.marital_status if can("relationship") else None
        ),
        "occupation": subject.occupation if can("occupation") else None,
        "educational_level": (
            subject.educational_level if can("education") else None
        ),
        "religion": subject.religion if can("religion") else None,
        "ethnicity": subject.ethnicity if can("ethnicity") else None,
        "interests": subject.interests if can("interests") else None,
        "is_online": bool(subject.is_online) if activity_visible else False,
        "last_seen": (
            subject.last_seen.isoformat()
            if activity_visible and subject.last_seen
            else None
        ),
    }


def privacy_form_values(privacy):
    if privacy is None:
        return {
            field: "private" for field in PROFILE_VISIBILITY_FIELDS
        }
    return {
        field: getattr(privacy, form_name, "private")
        for field, form_name in PRIVACY_FORM_FIELDS.items()
    }


def parse_privacy_form(form, defaults=None):
    values = {}
    errors = []
    defaults = defaults or {}
    for field, form_name in PRIVACY_FORM_FIELDS.items():
        raw_value = form.get(form_name)
        value = (
            defaults.get(field, "private")
            if raw_value is None
            else raw_value.strip().lower()
        )
        if value not in PROFILE_VISIBILITY_VALUES:
            errors.append(field)
        else:
            values[field] = value
    return values, errors


def ensure_owner_privacy(subject):
    if subject.profile_privacy is None:
        subject.profile_privacy = UserProfilePrivacy()
    return subject.profile_privacy


def apply_privacy_values(privacy, values):
    for field, value in values.items():
        privacy.set_visibility(field, value)
