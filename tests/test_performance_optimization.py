from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path

from sqlalchemy import event


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def count_sql_statements(db):
    statements = []

    def record_statement(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(db.engine, "before_cursor_execute", record_statement)
    try:
        yield statements
    finally:
        event.remove(db.engine, "before_cursor_execute", record_statement)


def login_session(client, user_id):
    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True


def test_static_cache_headers_are_long_lived_only_for_versioned_assets(client):
    versioned = client.get("/static/assets/js/main.js?v=landing-performance-1")
    unversioned = client.get("/static/assets/js/main.js")
    authenticated_html = client.get("/login")

    assert versioned.status_code == 200
    assert versioned.headers["Cache-Control"] == "public, max-age=31536000, immutable"
    assert unversioned.headers["Cache-Control"] == (
        "public, max-age=3600, stale-while-revalidate=86400"
    )
    assert authenticated_html.headers["Cache-Control"] == (
        "private, no-store, max-age=0"
    )


def test_public_pages_do_not_load_authenticated_foreground_push_controllers(
    client, user
):
    anonymous = client.get("/").get_data(as_text=True)
    assert "notification_sound.js" not in anonymous
    assert "foreground_push.js" not in anonymous

    login_response = client.post(
        "/login",
        data={"email": user.email, "password": "StrongPassw0rd!"},
        follow_redirects=False,
    )
    assert login_response.status_code == 302
    authenticated = client.get("/").get_data(as_text=True)
    assert authenticated.count("notification_sound.js") == 1
    assert authenticated.count("foreground_push.js") == 1


def test_landing_media_and_scripts_follow_the_performance_contract():
    source = (PROJECT_ROOT / "templates" / "index.html").read_text()

    assert "cdn.jsdelivr.net/npm/bootstrap-icons" not in source
    assert "assets/vendor/glightbox" not in source
    assert "assets/vendor/isotope-layout" not in source
    assert "assets/vendor/imagesloaded" not in source
    assert "assets/vendor/purecounter" not in source
    assert 'width="1200" height="675" fetchpriority="high"' in source
    assert 'width="6000" height="4000" loading="lazy" decoding="async"' in source
    assert 'width="2880" height="1620" loading="lazy" decoding="async"' in source
    assert "v='landing-performance-1'" in source


def test_profile_posts_are_paginated_and_query_count_stays_bounded(client, db, user):
    from models import Post, Reaction
    from time_utils import utcnow

    now = utcnow()
    posts = [
        Post(
            content=f"Bounded profile post {index}",
            author_id=user.id,
            created_at=now - timedelta(minutes=index),
        )
        for index in range(25)
    ]
    db.session.add_all(posts)
    db.session.flush()
    db.session.add_all(
        [
            Reaction(user_id=user.id, post_id=post.id, reaction_type="like")
            for post in posts
        ]
    )
    db.session.commit()
    login_session(client, user.id)

    with count_sql_statements(db) as first_page_statements:
        first_page = client.get(f"/{user.id}")
    with count_sql_statements(db) as second_page_statements:
        second_page = client.get(f"/{user.id}?page=2")

    first_html = first_page.get_data(as_text=True)
    second_html = second_page.get_data(as_text=True)
    assert first_page.status_code == 200
    assert second_page.status_code == 200
    assert "25 Posts" in first_html
    assert "Page 1 of 2" in first_html
    assert "Page 2 of 2" in second_html
    assert "Bounded profile post 24" not in first_html
    assert "Bounded profile post 24" in second_html
    assert "1 reactions" in first_html
    assert len(first_page_statements) <= 12
    assert len(second_page_statements) <= 12


def test_admin_dashboard_query_count_does_not_repeat_daily_series(client, db, user):
    user.is_admin = True
    user.is_super_admin = True
    db.session.commit()
    login_session(client, user.id)

    with count_sql_statements(db) as statements:
        response = client.get("/admin_dashboard")

    assert response.status_code == 200
    # Recent admin rows can add a small, bounded number of relationship loads,
    # but the seven-day chart must not return to its former per-day query loop.
    assert len(statements) <= 70


def test_profile_post_media_is_lazy_and_video_preloads_metadata():
    source = (PROJECT_ROOT / "templates" / "_post_card.html").read_text()

    assert source.count('loading="lazy"') >= 7
    assert source.count('preload="metadata"') == 2
    assert "reaction_counts_by_post_id.get(post.id, 0)" in source
