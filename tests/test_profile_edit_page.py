from datetime import date
from io import BytesIO
import importlib
import uuid


def _make_user(db, *, admin=False, super_admin=False):
    from models import User

    token = uuid.uuid4().hex[:10]
    account = User(
        first_name="Profile",
        last_name="Editor",
        email=f"profile-editor-{token}@example.com",
        phone_number=f"+2348{token[:7]}",
        dob=date(1990, 1, 1),
        gender="Female",
        city="Lagos",
        state="Lagos",
        country="Nigeria",
        marital_status="Single",
        is_active=True,
        is_admin=admin,
        is_super_admin=super_admin,
        admin_permissions='["reports_view"]',
    )
    account.set_password("StrongPassw0rd!")
    db.session.add(account)
    db.session.commit()
    return account


def _login_as(client, account):
    with client.session_transaction() as session:
        session.clear()
        session["_user_id"] = str(account.id)
        session["_fresh"] = True


def test_profile_view_links_to_dedicated_editor_without_modal(client, login, user):
    login()

    response = client.get(f"/{user.id}")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert f'href="/{user.id}/edit"' in body
    assert 'id="editProfileModal"' not in body
    assert "openModal('editProfileModal')" not in body
    assert 'id="profileForm"' not in body
    assert 'id="blockedUsersModal"' in body
    assert 'id="createPostModal"' in body
    assert 'id="editPostModal"' in body
    assert "function openModal(modalId)" in body


def test_old_edit_query_string_safely_renders_view_only_profile(client, login, user):
    login()

    response = client.get(f"/{user.id}?edit=1")

    assert response.status_code == 200
    assert b'id="editProfileModal"' not in response.data
    assert f'href="/{user.id}/edit"'.encode() in response.data
    assert client.post(f"/{user.id}", data={"first_name": "No"}).status_code == 405


def test_edit_profile_page_loads_with_csrf_fields_and_location_controls(
    client, login, user
):
    login()

    response = client.get(f"/{user.id}/edit")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'id="profileForm"' in body
    assert f'action="/{user.id}/edit"' in body
    assert 'name="csrf_token"' in body
    assert 'name="profile_pic"' in body
    assert 'name="cover_pic"' in body
    assert 'id="profile_country_select"' in body
    assert 'id="profile_state_select"' in body
    assert 'id="profile_city_select"' in body


def test_edit_profile_updates_existing_fields_and_redirects_to_profile(
    client, login, user, db
):
    login()

    response = client.post(
        f"/{user.id}/edit",
        data={
            "first_name": "Updated",
            "last_name": "Member",
            "email": user.email,
            "phone_number": "+2348000000000",
            "dob": "1992-05-06",
            "gender": "Female",
            "religion": "Islam",
            "ethnicity": "African",
            "educational_level": "Bachelor's Degree",
            "country": "Nigeria",
            "state": "Lagos",
            "city": "Ikeja",
            "marital_status": "Single",
            "bio": "Updated profile biography.",
            "interests": "Reading and music",
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(f"/{user.id}")
    db.session.refresh(user)
    assert user.first_name == "Updated"
    assert user.last_name == "Member"
    assert user.phone_number == "+2348000000000"
    assert user.bio == "Updated profile biography."
    assert user.country == "Nigeria"
    assert user.state == "Lagos"
    assert user.city == "Ikeja"
    assert user.dob == date(1992, 5, 6)


def test_edit_profile_preserves_profile_and_cover_uploads(
    client, login, user, db, monkeypatch
):
    user_module = importlib.import_module("users.user")

    def fake_upload(_file, *, folder, transformation):
        assert transformation
        return {"secure_url": f"https://cdn.example/{folder.rsplit('/', 1)[-1]}.webp"}

    monkeypatch.setattr(user_module.cloudinary.uploader, "upload", fake_upload)
    login()

    response = client.post(
        f"/{user.id}/edit",
        data={
            "profile_pic": (BytesIO(b"profile-image"), "profile.png"),
            "cover_pic": (BytesIO(b"cover-image"), "cover.jpg"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 302
    db.session.refresh(user)
    assert user.profile_pic == "https://cdn.example/profiles.webp"
    assert user.cover_pic == "https://cdn.example/covers.webp"


def test_profile_editor_rejects_another_user_for_normal_and_admin_accounts(
    client, db
):
    target = _make_user(db)
    normal_user = _make_user(db)
    admin = _make_user(db, admin=True, super_admin=True)

    for actor in (normal_user, admin):
        _login_as(client, actor)
        assert client.get(f"/{target.id}/edit").status_code == 403
        assert (
            client.post(
                f"/{target.id}/edit", data={"first_name": "Unauthorized"}
            ).status_code
            == 403
        )

    db.session.refresh(target)
    assert target.first_name == "Profile"


def test_admin_can_edit_self_without_changing_privileges(client, db):
    admin = _make_user(db, admin=True, super_admin=True)
    original_permissions = admin.admin_permissions
    _login_as(client, admin)

    response = client.post(
        f"/{admin.id}/edit",
        data={
            "first_name": "UpdatedAdmin",
            "is_admin": "false",
            "is_super_admin": "false",
            "admin_permissions": '["all"]',
        },
    )

    assert response.status_code == 302
    db.session.refresh(admin)
    assert admin.first_name == "UpdatedAdmin"
    assert admin.is_admin is True
    assert admin.is_super_admin is True
    assert admin.admin_permissions == original_permissions


def test_edit_profile_requires_authentication(client, user):
    response = client.get(f"/{user.id}/edit")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
