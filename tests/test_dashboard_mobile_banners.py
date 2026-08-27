import json
import random
import re
import uuid
from datetime import date, timedelta

import pytest


MOBILE_CANDIDATES_PATTERN = re.compile(
    rb'<script id="mobileFeedAdCandidates" type="application/json">\s*(.*?)\s*</script>',
    re.DOTALL,
)


def _make_user(User, suffix, *, active):
    return User(
        first_name="Dashboard",
        last_name="Renderer",
        email=f"dashboard-render-{suffix}@example.test",
        password_hash="render-only",
        phone_number=f"+234{suffix[:10]}",
        dob=date(1990, 1, 1),
        gender="Other",
        city="Lagos",
        country="Nigeria",
        state="Lagos",
        marital_status="Single",
        is_active=active,
    )


@pytest.fixture(scope="module")
def dashboard_render_data(app):
    from extensions import db
    from models import ActivityLog, AdCampaign, Post, User
    from time_utils import utcnow

    suffix = uuid.uuid4().hex
    with app.app_context():
        viewer = _make_user(User, f"viewer-{suffix}", active=True)
        author = _make_user(User, f"author-{suffix}", active=False)
        db.session.add_all([viewer, author])
        db.session.flush()

        created_at = utcnow() + timedelta(days=365)
        posts = [
            Post(
                content=f"Dashboard render post {index}",
                author_id=author.id,
                created_at=created_at - timedelta(seconds=index),
            )
            for index in range(100)
        ]
        db.session.add_all(posts)
        db.session.commit()
        data = {
            "viewer_id": viewer.id,
            "author_id": author.id,
            "post_ids": [post.id for post in posts],
        }

    yield data

    with app.app_context():
        ActivityLog.query.filter_by(user_id=data["viewer_id"]).delete(
            synchronize_session=False
        )
        AdCampaign.query.filter_by(user_id=data["viewer_id"]).delete(
            synchronize_session=False
        )
        Post.query.filter(Post.id.in_(data["post_ids"])).delete(
            synchronize_session=False
        )
        User.query.filter(
            User.id.in_([data["viewer_id"], data["author_id"]])
        ).delete(synchronize_session=False)
        db.session.commit()


def _login(client, user_id):
    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True


def _mobile_candidates(response):
    match = MOBILE_CANDIDATES_PATTERN.search(response.data)
    assert match is not None
    return json.loads(match.group(1))


def _add_banner(db, AdCampaign, viewer_id, placement, title, budget):
    from time_utils import utcnow

    now = utcnow()
    db.session.add(
        AdCampaign(
            user_id=viewer_id,
            title=title,
            image=f"https://cdn.example.test/{placement}.jpg",
            target_url=f"https://ads.example.test/{placement}",
            status="active",
            start_date=now - timedelta(days=1),
            end_date=now + timedelta(days=1),
            budget=budget,
            daily_budget=10,
            duration_days=2,
            placement=placement,
        )
    )
    db.session.commit()


@pytest.mark.parametrize("post_count", [0, 10, 13, 50, 100])
def test_dashboard_renders_requested_post_counts_without_banner_errors(
    client, dashboard_render_data, post_count
):
    _login(client, dashboard_render_data["viewer_id"])

    response = client.get(f"/user_dashboard?limit={post_count}")

    assert response.status_code == 200
    assert response.data.count(b'class="post-card ') == post_count
    assert response.data.count(b'class="mobile-feed-ad"') == post_count // 13
    assert [candidate["key"] for candidate in _mobile_candidates(response)] == [
        "sidebar",
        "vertical",
        "spotlight",
    ]


def test_mobile_banner_fallback_when_no_ad_backed_candidates(
    client, db, dashboard_render_data, monkeypatch
):
    from models import AdCampaign

    AdCampaign.query.filter_by(user_id=dashboard_render_data["viewer_id"]).delete(
        synchronize_session=False
    )
    db.session.commit()
    monkeypatch.setattr(random, "choice", lambda candidates: candidates[0])
    _login(client, dashboard_render_data["viewer_id"])

    response = client.get("/user_dashboard?limit=13")
    candidates = _mobile_candidates(response)

    assert response.status_code == 200
    assert [candidate["banner"] for candidate in candidates] == [None, None, None]
    assert response.data.count(b'class="mobile-feed-ad-inner"') == 1
    assert b"Sidebar Boost" in response.data


def test_mobile_banner_with_one_ad_backed_candidate(
    client, db, dashboard_render_data, monkeypatch
):
    from models import AdCampaign

    AdCampaign.query.filter_by(user_id=dashboard_render_data["viewer_id"]).delete(
        synchronize_session=False
    )
    db.session.commit()
    _add_banner(
        db,
        AdCampaign,
        dashboard_render_data["viewer_id"],
        "dashboard-sidebar",
        "Sidebar Test Ad",
        100,
    )
    monkeypatch.setattr(random, "choice", lambda candidates: candidates[0])
    _login(client, dashboard_render_data["viewer_id"])

    response = client.get("/user_dashboard?limit=13")
    candidates = _mobile_candidates(response)

    assert response.status_code == 200
    assert candidates[0]["banner"]["title"] == "Sidebar Test Ad"
    assert candidates[1]["banner"] is None
    assert candidates[2]["banner"] is None
    assert response.data.count(b'class="mobile-feed-ad-link"') == 1
    assert b'https://ads.example.test/dashboard-sidebar' in response.data


def test_mobile_banner_with_multiple_ad_backed_candidates(
    client, db, dashboard_render_data, monkeypatch
):
    from models import AdCampaign

    AdCampaign.query.filter_by(user_id=dashboard_render_data["viewer_id"]).delete(
        synchronize_session=False
    )
    db.session.commit()
    for index, (placement, title) in enumerate(
        [
            ("dashboard-sidebar", "Sidebar Test Ad"),
            ("dashboard-vertical", "Vertical Test Ad"),
            ("dashboard-spotlight", "Spotlight Test Ad"),
        ]
    ):
        _add_banner(
            db,
            AdCampaign,
            dashboard_render_data["viewer_id"],
            placement,
            title,
            100 - index,
        )
    monkeypatch.setattr(random, "choice", lambda candidates: candidates[-1])
    _login(client, dashboard_render_data["viewer_id"])

    response = client.get("/user_dashboard?limit=13")
    candidates = _mobile_candidates(response)

    assert response.status_code == 200
    assert [candidate["banner"]["title"] for candidate in candidates] == [
        "Sidebar Test Ad",
        "Vertical Test Ad",
        "Spotlight Test Ad",
    ]
    assert response.data.count(b'class="mobile-feed-ad-link"') == 1
    assert b'https://ads.example.test/dashboard-spotlight' in response.data
