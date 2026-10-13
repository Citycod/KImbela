from datetime import date
import importlib.util
from pathlib import Path
import uuid


def _user(db, label, **overrides):
    from models import User

    token = uuid.uuid4().hex[:10]
    values = {
        "first_name": label,
        "last_name": "Privacy",
        "email": f"privacy-{label.lower()}-{token}@example.test",
        "phone_number": f"+2348{uuid.uuid4().int % 10**9:09d}",
        "dob": date(1990, 6, 15),
        "gender": "Female",
        "city": "Lagos",
        "state": "Lagos",
        "country": "Nigeria",
        "marital_status": "Single",
        "bio": f"{label} private biography",
        "occupation": "Engineer",
        "educational_level": "Bachelor's Degree",
        "religion": "Other",
        "ethnicity": "Private ethnicity",
        "interests": "Music, travel",
        "is_active": True,
        "is_online": True,
    }
    values.update(overrides)
    account = User(**values)
    account.set_password("StrongPassw0rd!")
    db.session.add(account)
    db.session.commit()
    return account


def _login(client, account):
    from flask import g

    with client.session_transaction() as session:
        session.clear()
        session["_user_id"] = str(account.id)
        session["_fresh"] = True
    g.pop("_login_user", None)


def _set_all(privacy, value):
    from models import PROFILE_VISIBILITY_FIELDS

    for field in PROFILE_VISIBILITY_FIELDS:
        privacy.set_visibility(field, value)


def test_new_user_privacy_defaults_are_fail_safe(db):
    account = _user(db, "Defaults")

    assert account.profile_privacy.age_visibility == "friends"
    assert account.profile_privacy.bio_visibility == "friends"
    assert account.profile_privacy.activity_visibility == "friends"
    assert account.profile_privacy.birthday_visibility == "private"
    assert account.profile_privacy.ethnicity_visibility == "private"


def test_missing_privacy_row_fails_closed(db):
    from utils.profile_privacy import build_profile_viewer_context, serialize_profile

    viewer = _user(db, "MissingViewer")
    subject = _user(db, "MissingSubject")
    db.session.delete(subject.profile_privacy)
    db.session.commit()
    db.session.expire(subject, ["profile_privacy"])

    payload = serialize_profile(
        subject,
        build_profile_viewer_context(subject, viewer),
    )

    for field in ("age", "birthday", "bio", "city", "last_seen"):
        assert field not in payload


def test_owner_public_friend_private_and_block_precedence(db):
    from utils.profile_privacy import build_profile_viewer_context

    owner = _user(db, "Owner")
    friend = _user(db, "Friend")
    stranger = _user(db, "Stranger")
    friend.friends.append(owner)
    owner.profile_privacy.age_visibility = "public"
    owner.profile_privacy.bio_visibility = "friends"
    owner.profile_privacy.ethnicity_visibility = "private"
    db.session.commit()

    owner_context = build_profile_viewer_context(owner, owner)
    friend_context = build_profile_viewer_context(owner, friend)
    stranger_context = build_profile_viewer_context(owner, stranger)

    assert owner_context.can_view(owner, "ethnicity") is True
    assert friend_context.can_view(owner, "age") is True
    assert friend_context.can_view(owner, "bio") is True
    assert friend_context.can_view(owner, "ethnicity") is False
    assert stranger_context.can_view(owner, "age") is True
    assert stranger_context.can_view(owner, "bio") is False

    friend.blocked_users.append(owner)
    db.session.commit()
    blocked_context = build_profile_viewer_context(owner, friend)
    assert blocked_context.is_blocked is True
    assert blocked_context.can_view(owner, "age") is False
    assert blocked_context.can_view(owner, "bio") is False


def test_serialized_profile_never_contains_exact_dob_for_non_owner(db):
    from utils.profile_privacy import build_profile_viewer_context, serialize_profile

    viewer = _user(db, "BirthdayViewer")
    subject = _user(db, "BirthdaySubject")
    subject.profile_privacy.age_visibility = "public"
    subject.profile_privacy.birthday_visibility = "public"
    db.session.commit()

    payload = serialize_profile(
        subject,
        build_profile_viewer_context(subject, viewer),
    )

    assert payload["age"] is not None
    assert payload["birthday"] == "June 15"
    assert "dob" not in payload
    assert "1990" not in str(payload)


def test_general_profile_api_filters_private_fields_and_account_contact(
    client, db
):
    viewer = _user(db, "ApiViewer")
    subject = _user(db, "ApiSubject")
    _set_all(subject.profile_privacy, "private")
    subject.profile_privacy.location_visibility = "public"
    db.session.commit()
    _login(client, viewer)

    response = client.get(f"/get_user_profile/{subject.id}")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["city"] == "Lagos"
    assert "bio" not in payload
    assert "gender" not in payload
    assert "birthday" not in payload
    assert "dob" not in payload
    assert "email" not in payload
    assert "phone_number" not in payload


def test_general_profile_api_rejects_blocked_viewer(client, db):
    viewer = _user(db, "BlockedViewer")
    subject = _user(db, "BlockedSubject")
    subject.profile_privacy.age_visibility = "public"
    subject.blocked_users.append(viewer)
    db.session.commit()
    _login(client, viewer)

    assert client.get(f"/get_user_profile/{subject.id}").status_code == 403


def test_private_fields_are_absent_from_public_profile_html(client, db):
    viewer = _user(db, "HtmlViewer")
    subject = _user(
        db,
        "HtmlSubject",
        bio="PRIVATE-BIO-SENTINEL",
        occupation="PRIVATE-OCCUPATION-SENTINEL",
        ethnicity="PRIVATE-ETHNICITY-SENTINEL",
    )
    _set_all(subject.profile_privacy, "private")
    db.session.commit()
    _login(client, viewer)

    response = client.get(f"/profile/{subject.public_id}")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "PRIVATE-BIO-SENTINEL" not in body
    assert "PRIVATE-OCCUPATION-SENTINEL" not in body
    assert "PRIVATE-ETHNICITY-SENTINEL" not in body
    assert subject.dob.isoformat() not in body


def test_search_and_blocked_user_json_do_not_expose_email(client, db):
    viewer = _user(db, "DirectoryViewer")
    subject = _user(db, "DirectorySubject")
    viewer.blocked_users.append(subject)
    db.session.commit()
    _login(client, viewer)

    blocked_payload = client.get("/get_blocked_users").get_json()
    assert blocked_payload[0]["id"] == subject.id
    assert "email" not in blocked_payload[0]

    viewer.blocked_users.remove(subject)
    db.session.commit()
    search_payload = client.get("/search?q=DirectorySubject").get_json()
    match = next(item for item in search_payload["users"] if item["id"] == subject.id)
    assert "email" not in match


def test_messaging_friend_activity_obeys_activity_visibility(client, db):
    viewer = _user(db, "MessageViewer")
    friend = _user(db, "MessageFriend")
    viewer.friends.append(friend)
    friend.profile_privacy.activity_visibility = "private"
    db.session.commit()
    _login(client, viewer)

    payload = client.get("/api/messaging/friends").get_json()
    friend_payload = next(item for item in payload["friends"] if item["id"] == friend.id)

    assert "online" not in friend_payload
    assert "last_seen" not in friend_payload


def test_profile_edit_persists_all_privacy_selectors(client, db):
    from models import PROFILE_VISIBILITY_FIELDS

    owner = _user(db, "EditOwner")
    _login(client, owner)
    form = {
        f"{field}_visibility": "private"
        for field in PROFILE_VISIBILITY_FIELDS
    }

    response = client.post(f"/{owner.id}/edit", data=form)

    assert response.status_code == 302
    db.session.refresh(owner.profile_privacy)
    assert all(
        getattr(owner.profile_privacy, f"{field}_visibility") == "private"
        for field in PROFILE_VISIBILITY_FIELDS
    )


def test_anonymous_marketplace_seller_api_hides_controlled_profile_fields(
    client, db
):
    seller = _user(
        db,
        "MarketSeller",
        bio="PRIVATE-MARKET-BIO",
        occupation="PRIVATE-MARKET-OCCUPATION",
    )
    _set_all(seller.profile_privacy, "private")
    db.session.commit()

    response = client.get(f"/api/seller/{seller.id}")
    payload = response.get_json()["seller"]

    assert response.status_code == 200
    assert "bio" not in payload
    assert payload["title"] == "Professional Seller"
    assert "email" not in payload
    assert "phone" not in payload


def test_privacy_migration_descends_from_tracked_head():
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "versions"
        / "a7c9e2f4b6d8_add_user_profile_privacy.py"
    )
    spec = importlib.util.spec_from_file_location(
        "profile_privacy_migration",
        migration_path,
    )
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    assert migration.revision == "a7c9e2f4b6d8"
    assert migration.down_revision == "f4a1c2d3e4b5"
