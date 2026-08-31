from datetime import date
import uuid


def create_profile_user(db):
    from models import User

    unique = uuid.uuid4().hex[:10]
    profile_user = User(
        first_name="Profile",
        last_name="Recipient",
        email=f"profile-recipient-{unique}@example.com",
        phone_number=f"+234{unique}",
        dob=date(1985, 3, 3),
        gender="Female",
        city="Testville",
        country="Testland",
        state="TS",
        marital_status="Single",
        is_active=True,
    )
    profile_user.set_password("StrongPassw0rd!")
    db.session.add(profile_user)
    db.session.commit()
    return profile_user


def test_friend_profile_message_targets_current_dashboard_route(
    client, login, user, db
):
    profile_user = create_profile_user(db)
    user.friends.append(profile_user)
    db.session.commit()
    login()

    profile_response = client.get(f"/profile/{profile_user.public_id}")

    assert profile_response.status_code == 200
    body = profile_response.get_data(as_text=True)
    assert body.count(f"handleMessageButtonClick({profile_user.id})") == 3
    assert "/user_dashboard?chat=${encodeURIComponent(userId)}" in body
    assert "/dashboard?chat=" not in body

    dashboard_response = client.get(f"/user_dashboard?chat={profile_user.id}")
    assert dashboard_response.status_code == 200
    assert b'id="messengerPopup"' in dashboard_response.data


def test_non_friend_profile_does_not_render_message_action(client, login, user, db):
    profile_user = create_profile_user(db)
    login()

    response = client.get(f"/profile/{profile_user.public_id}")

    assert response.status_code == 200
    assert (
        f"handleMessageButtonClick({profile_user.id})"
        not in response.get_data(as_text=True)
    )


def test_own_profile_message_control_targets_current_messenger(
    client, login, user
):
    login()

    response = client.get(f"/{user.id}")

    assert response.status_code == 200
    assert "/user_dashboard?messenger=1" in response.get_data(as_text=True)


def test_dashboard_uses_one_versioned_messenger_asset_url(client, login):
    login()

    response = client.get("/user_dashboard")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    versioned_url = "/static/assets/js/messenger.js?v=ux-polish-1"
    assert body.count(versioned_url) == 3
    assert 'src="/static/assets/js/messenger.js"' not in body


def test_dashboard_renders_header_and_sidebar_unread_message_badges(client, login):
    login()

    response = client.get("/user_dashboard")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert body.count('id="openMessaging"') == 1
    assert body.count('id="unreadMessagesBadge"') == 1
    assert body.count('id="openMessagingSidebar"') == 1
    assert body.count('id="sidebarMsgBadge"') == 1
    assert body.count('aria-label="Messages, no unread messages"') == 2


def test_dashboard_always_renders_birthday_shortcut_and_existing_popup(client, login):
    login()

    response = client.get("/user_dashboard")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert body.count('id="birthdayShortcut"') == 1
    assert body.count('id="birthdayCount"') == 1
    assert body.count('id="birthdayNotificationPopup"') == 1
    assert 'onclick="showBirthdayNotifications()"' in body
    assert 'aria-label="Birthdays, none today"' in body


def test_blocked_profile_behavior_remains_redirected(client, login, user, db):
    profile_user = create_profile_user(db)
    user.block(profile_user)
    login()

    response = client.get(
        f"/profile/{profile_user.public_id}",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/user_dashboard")


def test_invalid_profile_user_is_handled_safely(client, login):
    login()

    response = client.get("/profile/not-a-real-user")

    assert response.status_code == 404


def test_profile_variants_contain_no_stale_dashboard_message_redirects():
    from pathlib import Path

    templates = Path(__file__).resolve().parents[1] / "templates"
    for template_name in ("profile.html", "public_profile.html"):
        source = (templates / template_name).read_text()
        assert "window.location.href = '/dashboard'" not in source
        assert "/dashboard?chat=" not in source
