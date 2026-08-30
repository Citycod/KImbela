from pathlib import Path

from sqlalchemy import event


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_install_page_is_public_and_database_independent(client, db):
    statements = []

    def record_statement(_connection, _cursor, statement, *_args):
        statements.append(statement)

    event.listen(db.engine, "before_cursor_execute", record_statement)
    try:
        response = client.get("/install")
    finally:
        event.remove(db.engine, "before_cursor_execute", record_statement)

    assert response.status_code == 200
    assert response.location is None
    assert statements == []
    assert b"Install Kimbela" in response.data


def test_install_page_remains_available_to_authenticated_users(client, user):
    with client.session_transaction() as session:
        session["_user_id"] = str(user.id)
        session["_fresh"] = True

    response = client.get("/install")

    assert response.status_code == 200
    assert response.location is None


def test_install_page_has_social_metadata_and_lightweight_assets(client):
    response = client.get("/install")
    page = response.get_data(as_text=True)

    assert '<link rel="canonical" href="https://kimbela.com/install">' in page
    assert '<meta property="og:title" content="Install Kimbela">' in page
    assert 'property="og:description"' in page
    assert 'property="og:image"' in page
    assert "pwa_init.js" in page
    assert "manifest.json" in page
    assert "cdn." not in page
    assert "<video" not in page


def test_install_page_contains_all_progressive_platform_states(client):
    page = client.get("/install").get_data(as_text=True)

    assert 'id="install-page-native"' in page
    assert 'id="install-page-ios"' in page
    assert 'id="install-page-installed"' in page
    assert 'id="install-page-fallback"' in page
    assert "Tap the Share button in Safari" in page
    assert "Add to Home Screen" in page
    assert "You can still use Kimbela in your browser." in page
    assert "Continue to Kimbela" in page
    assert "Notification.requestPermission" not in page


def test_existing_site_surfaces_link_to_install_page():
    landing = (PROJECT_ROOT / "templates" / "index.html").read_text()
    dashboard = (PROJECT_ROOT / "templates" / "user_dashboard.html").read_text()

    assert "url_for('user.install_app')" in landing
    assert dashboard.count("url_for('user.install_app')") >= 2


def test_install_page_reuses_single_existing_install_controller():
    template = (PROJECT_ROOT / "templates" / "install.html").read_text()
    initializer = (PROJECT_ROOT / "static" / "pwa_init.js").read_text()

    assert template.count("pwa_init.js") == 1
    assert "beforeinstallprompt" not in template
    assert initializer.count("window.addEventListener('beforeinstallprompt'") == 1
    assert "Notification.requestPermission" not in template
