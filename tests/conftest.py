import importlib
import os
import tempfile
import pytest


@pytest.fixture(scope="session")
def app():
    os.environ.setdefault("FLASK_ENV", "development")
    os.environ.setdefault("SECRET_KEY", "test-secret-key")
    os.environ.setdefault("ENABLE_DEBUG_ROUTES", "0")

    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.environ["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"

    app_config = importlib.import_module("app_config")
    test_app = app_config.create_app()
    test_app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
    )

    from extensions import db

    with test_app.app_context():
        db.create_all()

    yield test_app

    with test_app.app_context():
        db.drop_all()

    try:
        os.remove(db_path)
    except OSError:
        pass


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def app_context(app):
    ctx = app.app_context()
    ctx.push()
    yield
    ctx.pop()


@pytest.fixture()
def db(app):
    from extensions import db as _db

    return _db


@pytest.fixture()
def user(db):
    from datetime import date
    import uuid
    from models import User

    email = f"test-{uuid.uuid4().hex[:8]}@example.com"
    u = User(
        first_name="Test",
        last_name="User",
        email=email,
        phone_number="+12345678901",
        dob=date(1980, 1, 1),
        gender="Male",
        city="Testville",
        country="Testland",
        state="TS",
        marital_status="Single",
        is_active=True,
    )
    u.set_password("StrongPassw0rd!")
    db.session.add(u)
    db.session.commit()
    return u


@pytest.fixture()
def login(client, user):
    def _login():
        return client.post(
            "/login",
            data={"email": user.email, "password": "StrongPassw0rd!"},
            follow_redirects=False,
        )

    return _login
