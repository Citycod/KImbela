from pathlib import Path
from datetime import timedelta


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_root_service_worker_route_has_root_scope_headers(client):
    response = client.get("/sw.js")

    assert response.status_code == 200
    assert response.mimetype == "application/javascript"
    assert response.headers["Service-Worker-Allowed"] == "/"
    assert "no-cache" in response.headers["Cache-Control"]


def test_offline_fallback_route_is_available(client):
    response = client.get("/offline")

    assert response.status_code == 200
    assert response.mimetype == "text/html"
    assert b"You're Offline" in response.data


def test_registration_uses_one_canonical_worker_path():
    source = (PROJECT_ROOT / "static" / "pwa_init.js").read_text()

    assert "const CANONICAL_SERVICE_WORKER_PATH = '/sw.js';" in source
    assert "navigator.serviceWorker.register(\n    CANONICAL_SERVICE_WORKER_PATH" in source
    assert "navigator.serviceWorker.register('/static/sw.js')" not in source


def test_subscription_endpoint_upsert_does_not_create_duplicates(
    client, login, user, db, monkeypatch
):
    from models import PushSubscription

    monkeypatch.setattr("authentication.authenticate.send_login_alert_email", lambda *args: None)
    assert login().status_code in (200, 302)
    payload = {
        "endpoint": "https://push.example/current-device",
        "keys": {"p256dh": "first-key", "auth": "first-auth"},
        "isStandalone": True,
    }

    first = client.post("/api/pwa/subscribe", json=payload)
    payload["keys"] = {"p256dh": "replacement-key", "auth": "replacement-auth"}
    second = client.post("/api/pwa/subscribe", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert PushSubscription.query.filter_by(endpoint=payload["endpoint"]).count() == 1
    subscription = PushSubscription.query.filter_by(endpoint=payload["endpoint"]).one()
    assert subscription.user_id == user.id
    assert subscription.p256dh == "replacement-key"
    assert subscription.auth == "replacement-auth"


def test_unchanged_subscription_resync_does_not_refresh_database_timestamp(
    client, login, user, db, monkeypatch
):
    from models import PushSubscription
    from time_utils import utcnow

    monkeypatch.setattr("authentication.authenticate.send_login_alert_email", lambda *args: None)
    assert login().status_code in (200, 302)
    payload = {
        "endpoint": "https://push.example/unchanged-device",
        "keys": {"p256dh": "same-key", "auth": "same-auth"},
        "isStandalone": True,
    }
    assert client.post("/api/pwa/subscribe", json=payload).status_code == 200
    subscription = PushSubscription.query.filter_by(endpoint=payload["endpoint"]).one()
    subscription.last_seen_at = utcnow() - timedelta(days=1)
    db.session.commit()
    unchanged_timestamp = subscription.last_seen_at

    response = client.post("/api/pwa/subscribe", json=payload)

    assert response.status_code == 200
    assert response.get_json()["message"] == "Subscription already current"
    db.session.refresh(subscription)
    assert subscription.last_seen_at == unchanged_timestamp


def test_worker_does_not_reference_removed_precache_asset():
    source = (PROJECT_ROOT / "static" / "sw.js").read_text()

    assert "/static/css/style.css" not in source
    assert "'/offline'" in source
    assert "'/static/manifest.json'" in source


def test_install_readiness_manifest_and_icons_are_available(client):
    manifest_response = client.get("/static/manifest.json")
    icon_192_response = client.get("/static/img/icons/icon-192x192.png")
    icon_512_response = client.get("/static/img/icons/icon-512x512.png")
    maskable_192_response = client.get("/static/img/icons/icon-maskable-192x192.png")
    maskable_512_response = client.get("/static/img/icons/icon-maskable-512x512.png")

    assert manifest_response.status_code == 200
    manifest = manifest_response.get_json()
    assert manifest["display"] == "standalone"
    assert {icon["purpose"] for icon in manifest["icons"]} == {"any", "maskable"}
    assert icon_192_response.status_code == 200
    assert icon_192_response.mimetype == "image/png"
    assert icon_512_response.status_code == 200
    assert icon_512_response.mimetype == "image/png"
    assert maskable_192_response.status_code == 200
    assert maskable_192_response.mimetype == "image/png"
    assert maskable_512_response.status_code == 200
    assert maskable_512_response.mimetype == "image/png"
    assert manifest["background_color"] == "#fffdfb"
    assert manifest["theme_color"] == "#7c3aed"


def test_android_icons_are_opaque_pngs_with_dedicated_maskable_assets():
    icon_root = PROJECT_ROOT / "static" / "img" / "icons"
    for name in (
        "icon-192x192.png",
        "icon-512x512.png",
        "icon-maskable-192x192.png",
        "icon-maskable-512x512.png",
    ):
        png = (icon_root / name).read_bytes()
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
        assert png[25] == 2  # PNG truecolor RGB, with no alpha channel.


def test_dashboard_static_assets_use_reusable_version_urls():
    source = (PROJECT_ROOT / "templates" / "user_dashboard.html").read_text()

    assert "range(1, 1000000) | random" not in source
    assert source.count("v='slow-network-1'") == 2
    assert source.count("v='network-resilience-1'") == 0
    assert source.count("v='ux-polish-1'") == 3


def test_network_resilience_script_is_loaded_by_base_template():
    source = (PROJECT_ROOT / "templates" / "base.html").read_text()

    assert "assets/js/network_resilience.js" in source


def test_foreground_push_feedback_is_loaded_from_the_shared_base_template():
    source = (PROJECT_ROOT / "templates" / "base.html").read_text()

    assert "assets/js/notification_sound.js" in source
    assert "assets/js/foreground_push.js" in source
    assert source.count("v='foreground-native-3'") == 2
    assert "v='network-resilience-1'" in source


def test_dashboard_exposes_accessible_persisted_sound_controls():
    dashboard = (PROJECT_ROOT / "templates" / "user_dashboard.html").read_text()
    controller = (
        PROJECT_ROOT / "static" / "assets" / "js" / "notification_sound.js"
    ).read_text()

    assert dashboard.count('data-notification-sound-toggle') == 2
    assert dashboard.count('role="switch"') >= 2
    assert "kimbela_notification_sounds" in controller
    assert "localStorage" in controller
    assert "new Audio(SOUND_URL)" in controller
    assert controller.count("new Audio(") == 1


def test_foreground_notification_sound_is_small_and_locally_served(client):
    response = client.get("/static/assets/audio/kimbela-notification.wav")

    assert response.status_code == 200
    assert response.data.startswith(b"RIFF")
    assert len(response.data) < 16 * 1024


def test_dashboard_feed_uses_native_lazy_loading_for_appended_content():
    source = (PROJECT_ROOT / "templates" / "_posts_partial.html").read_text()

    assert source.count('loading="lazy"') >= 8
    assert 'width="40" height="40" loading="lazy"' in source


def test_dashboard_birthday_bootstrap_reuses_its_initial_response():
    source = (
        PROJECT_ROOT / "templates" / "partials" / "user_dashboard_body_scripts.html"
    ).read_text()

    assert "this.updateBirthdayBadge(data);" in source
    assert "async updateBirthdayBadge(existingData = null)" in source


def test_dashboard_timezone_sync_only_posts_when_browser_value_changed():
    source = (PROJECT_ROOT / "templates" / "user_dashboard.html").read_text()

    assert "const storedTimezone = {{ current_user.timezone|tojson }};" in source
    assert "if (tz && tz !== storedTimezone)" in source
