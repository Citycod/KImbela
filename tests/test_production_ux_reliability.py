import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _login_session(client, user):
    with client.session_transaction() as session:
        session["_user_id"] = str(user.id)
        session["_fresh"] = True


def test_login_template_loads_single_submission_state_controller(client):
    response = client.get("/login")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert html.count('id="loginForm"') == 1
    assert html.count('id="loginSubmitButton"') == 1
    assert 'data-loading-label="Signing in..."' in html
    assert html.count("assets/js/login.js?v=login-state-1") == 1
    assert 'name="password" placeholder="Password" minlength="6"' in html


def test_landing_navigation_uses_server_authentication_state(client, user):
    anonymous = client.get("/").get_data(as_text=True)
    assert anonymous.count('data-auth-nav="anonymous"') == 2
    assert 'data-auth-nav="authenticated"' not in anonymous

    login_response = client.post(
        "/login",
        data={"email": user.email, "password": "StrongPassw0rd!"},
        follow_redirects=False,
    )
    assert login_response.status_code == 302
    authenticated = client.get("/").get_data(as_text=True)
    assert authenticated.count('data-auth-nav="authenticated"') == 2
    assert 'data-auth-nav="anonymous"' not in authenticated
    assert 'href="/user_dashboard"' in authenticated


def test_admin_sidebar_has_user_dashboard_link_without_exposing_admin_to_users(
    client, db, user
):
    user.is_admin = True
    user.is_super_admin = True
    db.session.commit()
    _login_session(client, user)

    admin_page = client.get("/admin_dashboard")
    assert admin_page.status_code == 200
    assert b'href="/user_dashboard"' in admin_page.data
    assert b"User Dashboard" in admin_page.data

    user.is_admin = False
    user.is_super_admin = False
    db.session.commit()
    denied = client.get("/admin_dashboard", follow_redirects=False)
    assert denied.status_code == 302
    assert denied.headers["Location"].endswith("/user_dashboard")


def test_all_literal_template_endpoints_exist(app):
    endpoints = {rule.endpoint for rule in app.url_map.iter_rules()}
    pattern = re.compile(r"url_for\(\s*['\"]([^'\"]+)")
    missing = {}
    for template in (PROJECT_ROOT / "templates").rglob("*.html"):
        for endpoint in pattern.findall(template.read_text(errors="ignore")):
            if endpoint not in endpoints:
                missing.setdefault(endpoint, []).append(str(template.relative_to(PROJECT_ROOT)))
    assert missing == {}


def test_feed_and_group_copy_links_use_exact_public_post_uuid():
    dashboard = (PROJECT_ROOT / "templates" / "user_dashboard.html").read_text()
    partial = (PROJECT_ROOT / "templates" / "_posts_partial.html").read_text()
    group_partial = (PROJECT_ROOT / "templates" / "_group_posts_partial.html").read_text()
    expected = "url_for('user.view_shared_post', post_identifier=post.public_id)"
    assert expected in dashboard
    assert expected in partial
    assert expected in group_partial
    assert "preview=private-v1" not in group_partial


def test_video_post_uses_branded_social_preview_fallback(client, db, user):
    from models import Post

    post = Post(
        content="Video preview description",
        author_id=user.id,
        video="https://cdn.example.com/post-video.mp4",
    )
    db.session.add(post)
    db.session.commit()

    response = client.get(
        f"/post/{post.public_id}", base_url="https://www.kimbela.com"
    )
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert '<meta property="og:description" content="Video preview description">' in html
    assert '<meta property="og:image" content="https://www.kimbela.com/static/assets/img/kim.png">' in html
    assert '<meta name="twitter:card" content="summary_large_image">' in html


def test_dynamic_html_is_not_cached_but_static_assets_remain_cacheable(client):
    landing = client.get("/")
    login = client.get("/login")
    static_asset = client.get("/static/assets/js/login.js")
    assert landing.headers["Cache-Control"] == "private, no-store, max-age=0"
    assert login.headers["Cache-Control"] == "private, no-store, max-age=0"
    assert "Cookie" in landing.headers.get("Vary", "")
    assert "no-store" not in static_asset.headers.get("Cache-Control", "")


def test_seller_settings_legacy_forms_resolve_without_build_errors(client, user):
    _login_session(client, user)
    response = client.get("/settings")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'action="/settings"' in html
    assert 'href="/logout"' in html
    assert 'href="/faq"' in html
    assert 'href="/contact"' in html
    assert 'href="/community-guidelines"' in html

    unsupported = client.post(
        "/settings",
        data={"settings_section": "account", "display_currency": "EUR"},
        follow_redirects=False,
    )
    assert unsupported.status_code == 302
    assert unsupported.headers["Location"].endswith("/settings#account")
