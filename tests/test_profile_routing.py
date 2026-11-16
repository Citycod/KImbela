"""Tests for Kimbela's revamped profile URL routing and redirects."""

import uuid
from datetime import date
from flask import g, session
from models import User, Post
from extensions import db as _db


def _create_user(db, email, first_name="Test", last_name="User", age=25, **kwargs):
    dob = date(2026 - age, 1, 1)
    token = uuid.uuid4().hex[:7]
    user_attrs = {
        "email": email,
        "first_name": first_name,
        "last_name": last_name,
        "phone_number": f"+1555{token}",
        "dob": dob,
        "gender": "Female",
        "city": "Lagos",
        "state": "Lagos",
        "country": "Nigeria",
        "marital_status": "Single",
        "is_active": True,
    }
    user_attrs.update(kwargs)
    user = User(**user_attrs)
    user.set_password("Secret123!")
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, user):
    with client.session_transaction() as sess:
        sess.clear()
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
    g.pop("_login_user", None)


def test_unauthenticated_profile_access(client):
    """Unauthenticated users accessing /profile or /profile/edit are redirected to login."""
    resp = client.get("/profile")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]

    resp_edit = client.get("/profile/edit")
    assert resp_edit.status_code == 302
    assert "/login" in resp_edit.headers["Location"]


def test_own_profile_canonical_url(client, db):
    """Authenticated user accessing /profile sees their own profile with 200 OK."""
    user = _create_user(db, "profile_alice@example.com", first_name="Alice", last_name="Walker")
    _login(client, user)

    resp = client.get("/profile")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Alice Walker" in html
    assert 'href="/profile/edit"' in html


def test_old_numeric_url_redirects_own_profile(client, db):
    """Accessing /<int:user_id> for current_user 301-redirects to canonical /profile."""
    user = _create_user(db, "profile_bob@example.com", first_name="Bob", last_name="Smith")
    _login(client, user)

    resp = client.get(f"/{user.id}")
    assert resp.status_code == 301
    assert resp.headers["Location"].endswith("/profile")

    # Following redirect lands on /profile with 200
    followed = client.get(f"/{user.id}", follow_redirects=True)
    assert followed.status_code == 200
    assert "Bob Smith" in followed.get_data(as_text=True)


def test_old_numeric_url_redirects_with_query_params(client, db):
    """Old numeric URLs preserve query parameters like page on redirect."""
    user = _create_user(db, "profile_charlie@example.com", first_name="Charlie")
    _login(client, user)

    resp = client.get(f"/{user.id}?page=2")
    assert resp.status_code == 301
    assert "/profile?page=2" in resp.headers["Location"]


def test_old_numeric_url_redirects_other_profile_to_public_id(client, db):
    """Accessing /<int:user_id> for another user 301-redirects to /profile/<public_id>."""
    viewer = _create_user(db, "viewer_dan@example.com", first_name="Dan")
    target = _create_user(db, "target_eva@example.com", first_name="Eva", last_name="Green")
    _login(client, viewer)

    resp = client.get(f"/{target.id}")
    assert resp.status_code == 301
    assert resp.headers["Location"].endswith(f"/profile/{target.public_id}")

    followed = client.get(f"/{target.id}", follow_redirects=True)
    assert followed.status_code == 200
    assert "Eva Green" in followed.get_data(as_text=True)


def test_nonexistent_numeric_url_returns_404(client, db):
    """Accessing a non-existent numeric user ID returns 404."""
    user = _create_user(db, "profile_frank@example.com")
    _login(client, user)

    resp = client.get("/999999")
    assert resp.status_code == 404


def test_own_profile_edit_canonical_url(client, db):
    """User can view and submit the edit profile form at /profile/edit without numeric ID."""
    user = _create_user(db, "profile_grace@example.com", first_name="Grace", bio="Original Bio")
    _login(client, user)

    # GET /profile/edit
    resp = client.get("/profile/edit")
    assert resp.status_code == 200
    assert 'action="/profile/edit"' in resp.get_data(as_text=True)

    # POST /profile/edit
    post_resp = client.post(
        "/profile/edit",
        data={
            "first_name": "Grace",
            "last_name": "Hopper",
            "bio": "Pioneering computer scientist",
            "gender": "Female",
            "dob": "1995-12-09",
            "marital_status": "Single",
            "show_age_on_profile": "y",
        },
        follow_redirects=False,
    )
    assert post_resp.status_code == 302
    assert post_resp.headers["Location"].endswith("/profile")

    db.session.refresh(user)
    assert user.bio == "Pioneering computer scientist"
    assert user.last_name == "Hopper"


def test_old_numeric_edit_url_redirects_and_enforces_auth(client, db):
    """Old edit URL /<id>/edit 301-redirects owner to /profile/edit and forbids other users."""
    owner = _create_user(db, "profile_henry@example.com", first_name="Henry")
    stranger = _create_user(db, "profile_ian@example.com", first_name="Ian")

    # Owner accessing own old edit URL redirects to /profile/edit
    _login(client, owner)
    resp = client.get(f"/{owner.id}/edit")
    assert resp.status_code == 301
    assert resp.headers["Location"].endswith("/profile/edit")

    # Stranger accessing owner's edit URL is forbidden (403)
    _login(client, stranger)
    resp_forbidden = client.get(f"/{owner.id}/edit")
    assert resp_forbidden.status_code == 403

    resp_post_forbidden = client.post(f"/{owner.id}/edit", data={"bio": "Hacked"})
    assert resp_post_forbidden.status_code == 403


def test_view_profile_numeric_id_redirects_to_public_id(client, db):
    """Accessing /profile/<numeric_id> 301-redirects to /profile/<public_id>."""
    viewer = _create_user(db, "profile_jane@example.com", first_name="Jane")
    target = _create_user(db, "profile_kevin@example.com", first_name="Kevin")
    _login(client, viewer)

    resp = client.get(f"/profile/{target.id}")
    assert resp.status_code == 301
    assert resp.headers["Location"].endswith(f"/profile/{target.public_id}")


def test_view_profile_own_identifier_redirects_to_profile(client, db):
    """Accessing /profile/<my_public_id> or /profile/<my_id> redirects to canonical /profile."""
    user = _create_user(db, "profile_laura@example.com", first_name="Laura")
    _login(client, user)

    # Own public_id
    resp_uuid = client.get(f"/profile/{user.public_id}")
    assert resp_uuid.status_code == 302
    assert resp_uuid.headers["Location"].endswith("/profile")

    # Own numeric id
    resp_num = client.get(f"/profile/{user.id}")
    assert resp_num.status_code == 302
    assert resp_num.headers["Location"].endswith("/profile")


def test_blocked_user_profile_access_denied(client, db):
    """Viewing profile of someone who blocked you or whom you blocked is denied."""
    alice = _create_user(db, "block_alice@example.com", first_name="Alice")
    bob = _create_user(db, "block_bob@example.com", first_name="Bob")

    bob.block(alice)
    db.session.commit()

    _login(client, alice)
    resp = client.get(f"/profile/{bob.public_id}")
    assert resp.status_code == 302
    assert "/user_dashboard" in resp.headers["Location"]


def test_age_privacy_on_profile_view(client, db):
    """Hidden age is not exposed on /profile/<public_id> to regular viewers."""
    viewer = _create_user(db, "privacy_viewer@example.com", first_name="Viewer")
    hidden_user = _create_user(
        db,
        "privacy_target@example.com",
        first_name="Target",
        age=30,
        show_age_on_profile=False,
    )
    _login(client, viewer)

    resp = client.get(f"/profile/{hidden_user.public_id}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    # Age 30 should not appear as an age badge
    assert "Age: 30" not in html
