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
