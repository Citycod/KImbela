"""Safe, explicit deletion policy for accounts marked as test users."""

import uuid

from sqlalchemy import select

from extensions import db


def _user_dependency_tables(user_id):
    """Return tables that currently reference a user, using bounded existence checks."""
    dependencies = set()
    for table in db.metadata.sorted_tables:
        if table.name == "users":
            continue
        for column in table.columns:
            if not any(
                foreign_key.column.table.name == "users"
                for foreign_key in column.foreign_keys
            ):
                continue
            found = db.session.execute(
                select(column).where(column == user_id).limit(1)
            ).first()
            if found:
                dependencies.add(table.name)
    return sorted(dependencies)


def delete_or_anonymize_test_user(user):
    """Delete an unused test account, or anonymize it when history depends on it.

    This deliberately refuses non-test, administrative, AI, and super-admin accounts.
    The caller owns the transaction so the mutation and audit log stay atomic.
    """
    if not user.is_test_user:
        raise ValueError("Only explicitly marked test users can use this deletion path.")
    if user.is_super_admin or user.is_admin or user.is_ai_persona:
        raise ValueError("Administrative and AI accounts cannot use the test-user deletion path.")

    dependencies = _user_dependency_tables(user.id)
    if not dependencies:
        db.session.delete(user)
        return "deleted", []

    suffix = uuid.uuid4().hex[:12]
    user.first_name = "Deleted"
    user.last_name = "Test User"
    user.email = f"deleted-test-{user.id}-{suffix}@invalid.kimbela.local"
    user.phone_number = f"deleted-{user.id}"[:20]
    user.profile_pic = None
    user.cover_pic = None
    user.bio = None
    user.about_me = None
    user.interests = None
    user.occupation = None
    user.is_active = False
    user.is_online = False
    user.is_test_user = False
    user.is_admin = False
    user.is_super_admin = False
    user.admin_permissions = None
    user.set_password(uuid.uuid4().hex + "Aa1!")
    return "anonymized", dependencies
