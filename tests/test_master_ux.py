from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_has_one_accessible_search_and_distinct_message_bell_controls(
    client, login
):
    login()

    response = client.get("/user_dashboard")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert body.count('id="globalSearch"') == 1
    assert body.count('id="openMessaging"') == 1
    assert body.count('id="notificationDropdown"') == 1
    assert 'aria-label="Messages, no unread messages"' in body
    assert 'aria-label="Notifications"' in body
    assert 'bg-purple-50' in body
    assert 'bg-amber-50' in body


def test_social_bell_uses_server_destination_instead_of_actor_profile():
    source = (PROJECT_ROOT / "static" / "assets" / "js" / "dashboard.js").read_text()

    assert "notification.url || ''" in source
    assert "window.location.assign(destination)" in source
    assert "if (type === 'friend_request' && actorId)" in source
    assert "/dashboard?open_chat=" not in source
    assert "/user_dashboard?chat=${encodeURIComponent(userId)}" in source


def test_deep_link_focus_and_polish_assets_load_once():
    base = (PROJECT_ROOT / "templates" / "base.html").read_text()
    dashboard = (PROJECT_ROOT / "templates" / "user_dashboard.html").read_text()

    assert base.count("assets/js/deep_link_focus.js") == 1
    assert dashboard.count("assets/css/dashboard_redesign.css") == 1
    assert 'max-w-xl' in dashboard
    assert 'justify-start' in dashboard
