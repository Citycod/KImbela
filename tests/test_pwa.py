from pathlib import Path


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


def test_worker_does_not_reference_removed_precache_asset():
    source = (PROJECT_ROOT / "static" / "sw.js").read_text()

    assert "/static/css/style.css" not in source
    assert "'/offline'" in source
    assert "'/static/manifest.json'" in source


def test_install_readiness_manifest_and_icons_are_available(client):
    manifest_response = client.get("/static/manifest.json")
    icon_192_response = client.get("/static/img/icons/icon-192x192.png")
    icon_512_response = client.get("/static/img/icons/icon-512x512.png")

    assert manifest_response.status_code == 200
    assert manifest_response.get_json()["display"] == "standalone"
    assert icon_192_response.status_code == 200
    assert icon_192_response.mimetype == "image/png"
    assert icon_512_response.status_code == 200
    assert icon_512_response.mimetype == "image/png"


def test_dashboard_static_assets_use_reusable_version_urls():
    source = (PROJECT_ROOT / "templates" / "user_dashboard.html").read_text()

    assert "range(1, 1000000) | random" not in source
    assert source.count("v='slow-network-1'") == 2
    assert source.count("v='network-resilience-1'") == 1
    assert source.count("v='foreground-feedback-1'") == 1
    assert source.count("v='unread-badge-1'") == 1


def test_network_resilience_script_is_loaded_by_base_template():
    source = (PROJECT_ROOT / "templates" / "base.html").read_text()

    assert "assets/js/network_resilience.js" in source


def test_foreground_push_feedback_is_loaded_from_the_shared_base_template():
    source = (PROJECT_ROOT / "templates" / "base.html").read_text()

    assert "assets/js/foreground_push.js" in source
    assert "v='foreground-feedback-1'" in source
    assert "v='network-resilience-1'" in source


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
