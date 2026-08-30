from datetime import date, datetime, timedelta
import uuid
from unittest.mock import Mock
from types import SimpleNamespace

import pytest


def make_user(db, *, ai=False, super_admin=False, first_name=None):
    from models import User

    user = User(
        first_name=first_name or ("AI" if ai else "Human"),
        last_name="Tester",
        email=f"ai-group-{uuid.uuid4().hex}@example.com",
        phone_number=f"+2347{uuid.uuid4().int % 10**9:09d}",
        dob=date(1990, 1, 1),
        gender="Other",
        city="Lagos",
        country="Nigeria",
        state="Lagos",
        marital_status="Single",
        is_active=True,
        is_ai_persona=ai,
        is_super_admin=super_admin,
        timezone="Africa/Lagos",
    )
    user.set_password("StrongPassw0rd!")
    db.session.add(user)
    db.session.flush()
    return user


def make_persona(db, name="Ada"):
    from models import AIPersona

    user = make_user(db, ai=True, first_name=name)
    persona = AIPersona(
        user_id=user.id,
        name=name,
        bio_disclosure="AI profile",
        personality="Friendly",
        interests=["community"],
        allowed_actions=["post", "comment"],
        forbidden_actions=["financial advice"],
        is_active=True,
    )
    db.session.add(persona)
    db.session.commit()
    return persona


def save_profile(db, persona, **changes):
    from ai_controls import get_profile_config, save_profile_config

    config = get_profile_config(persona)
    config.update(changes)
    saved = save_profile_config(persona, config)
    db.session.commit()
    return saved


def make_group(db, owner, name="Community"):
    from models import Group

    group = Group(name=name, created_by=owner.id, is_active=True)
    db.session.add(group)
    db.session.flush()
    group.members.append(owner)
    db.session.commit()
    return group


def add_log(db, persona, action_type, when, target_id=None):
    from models import AILog

    db.session.add(
        AILog(
            persona_id=persona.id,
            action_type=action_type,
            target_id=target_id,
            timestamp=when,
            is_escalated=False,
        )
    )
    db.session.commit()


def add_published_post(db, persona, when, *, group_id=None):
    from models import Post

    post = Post(
        content=f"Published {uuid.uuid4().hex}",
        author_id=persona.user_id,
        group_id=group_id,
        created_at=when,
    )
    db.session.add(post)
    db.session.commit()
    return post


@pytest.fixture(autouse=True)
def reset_ai_globals(db):
    from ai_controls import set_global_activity_enabled, set_global_post_spacing_hours

    set_global_activity_enabled(True)
    set_global_post_spacing_hours(0)
    db.session.commit()
    yield
    db.session.rollback()


def open_weekly_policy(db, persona, **changes):
    defaults = {
        "active_days": list(range(7)),
        "posting_days": list(range(7)),
        "posting_start_time": "00:00",
        "posting_end_time": "23:59",
        "max_posts_per_day": 20,
        "minimum_post_interval_minutes": 0,
        "maximum_total_posts_per_week": 2,
        "maximum_feed_posts_per_week": 1,
        "maximum_group_posts_per_week": 1,
    }
    defaults.update(changes)
    return save_profile(db, persona, **defaults)


def test_conservative_weekly_defaults_are_two_total_one_per_channel(db):
    from ai_controls import get_profile_config

    config = get_profile_config(make_persona(db))
    assert config["maximum_total_posts_per_week"] == 2
    assert config["maximum_feed_posts_per_week"] == 1
    assert config["maximum_group_posts_per_week"] == 1


def test_weekly_total_and_channel_budgets_are_combined(db):
    from ai_controls import new_post_eligibility, weekly_post_counts

    persona = make_persona(db)
    now = datetime(2026, 8, 31, 12, 0)
    open_weekly_policy(db, persona)
    add_published_post(db, persona, now - timedelta(hours=2))
    assert new_post_eligibility(persona, "feed", now) == (False, "weekly_feed_limit")
    assert new_post_eligibility(persona, "group", now)[0] is True
    add_published_post(db, persona, now - timedelta(hours=1), group_id=1)
    assert weekly_post_counts(persona, now) == {"total": 2, "feed": 1, "group": 1}
    assert new_post_eligibility(persona, "feed", now) == (False, "weekly_total_limit")
    assert new_post_eligibility(persona, "group", now) == (False, "weekly_total_limit")


def test_group_weekly_limit_is_independently_enforced(db):
    from ai_controls import new_post_eligibility

    persona = make_persona(db)
    now = datetime(2026, 8, 31, 12, 0)
    open_weekly_policy(db, persona, maximum_total_posts_per_week=5)
    add_published_post(db, persona, now - timedelta(hours=1), group_id=1)
    assert new_post_eligibility(persona, "group", now) == (False, "weekly_group_limit")
    assert new_post_eligibility(persona, "feed", now)[0] is True


def test_posting_days_and_date_sensitive_post_today(db):
    from ai_controls import new_post_eligibility, post_today_override, set_post_today

    persona = make_persona(db)
    monday = datetime(2026, 8, 31, 12, 0)
    open_weekly_policy(db, persona, posting_days=[1])
    assert new_post_eligibility(persona, "feed", monday) == (False, "posting_day_disabled")

    open_weekly_policy(db, persona, posting_days=[0])
    set_post_today(persona, False, monday)
    db.session.commit()
    assert new_post_eligibility(persona, "feed", monday) == (False, "post_today_disabled")
    set_post_today(persona, True, monday)
    db.session.commit()
    assert new_post_eligibility(persona, "feed", monday)[0] is True
    assert post_today_override(persona, monday + timedelta(days=7)) is None
    assert new_post_eligibility(persona, "feed", monday + timedelta(days=7))[0] is True


def test_global_new_post_spacing_blocks_burst_but_not_replies(db):
    from ai_controls import automation_eligibility, new_post_eligibility, set_global_post_spacing_hours

    first = make_persona(db, "First")
    second = make_persona(db, "Second")
    now = datetime(2026, 8, 31, 12, 0)
    open_weekly_policy(db, first)
    open_weekly_policy(db, second)
    set_global_post_spacing_hours(6)
    add_published_post(db, first, now - timedelta(hours=2))
    assert new_post_eligibility(second, "feed", now) == (False, "global_post_spacing")
    assert automation_eligibility(second, "reply", now)[0] is True


def test_group_eligibility_requires_level_allowlist_and_real_membership(db):
    from ai_controls import group_automation_eligibility, save_group_config

    persona = make_persona(db)
    owner = make_user(db)
    group = make_group(db, owner)
    now = datetime(2026, 8, 31, 12, 0)
    open_weekly_policy(
        db,
        persona,
        group_activity_enabled=True,
        group_can_post=True,
        allowed_group_ids=[group.id],
        minimum_group_activity_interval_minutes=0,
    )
    save_group_config(group, {"activity_level": "medium"})
    db.session.commit()
    assert group_automation_eligibility(persona, group, "post", now) == (False, "not_member")
    group.members.append(persona.user)
    db.session.commit()
    assert group_automation_eligibility(persona, group, "post", now)[0] is True


def test_scheduler_runs_at_most_one_action_and_prioritizes_group_reply(monkeypatch):
    import scheduler

    persona = object()
    group = Mock(return_value=True)
    feed = Mock(return_value=True)
    monkeypatch.setattr("ai_group_action_engine.execute_next_group_action", group)
    monkeypatch.setattr(scheduler, "execute_one_feed_ai_action", feed)
    assert scheduler.run_one_ai_action([persona], feed_first=True) is True
    group.assert_called_once_with([persona], actions=("reply",))
    feed.assert_not_called()


def test_feed_selection_prefers_profile_that_has_not_posted_today(monkeypatch):
    import scheduler

    posted = SimpleNamespace(id=1, interests=["community"])
    quiet = SimpleNamespace(id=2, interests=["community"])
    selected = []
    monkeypatch.setattr("ai_controls.posts_today_count", lambda persona: 1 if persona.id == 1 else 0)
    monkeypatch.setattr("ai_controls.last_ai_post_at", lambda _persona_id: None)
    monkeypatch.setattr(
        "ai_controls.get_profile_config",
        lambda _persona: {"reply_probability": 0, "posting_mode": "automatic"},
    )
    monkeypatch.setattr("ai_controls.automation_eligibility", lambda *_args, **_kwargs: (True, "eligible"))
    monkeypatch.setattr(
        "ai_action_engine.execute_persona_post",
        lambda persona, _topic: selected.append(persona.id) or True,
    )
    monkeypatch.setattr("random.shuffle", lambda values: None)
    assert scheduler.execute_one_feed_ai_action([posted, quiet]) is True
    assert selected == [quiet.id]


def test_ai_to_ai_group_comment_chain_is_rejected_before_generation(db, monkeypatch):
    from ai_controls import save_group_config
    from ai_group_action_engine import execute_persona_group_comment
    from models import Post

    persona = make_persona(db, "Responder")
    author = make_persona(db, "Author")
    owner = make_user(db)
    group = make_group(db, owner)
    group.members.append(persona.user)
    group.members.append(author.user)
    db.session.commit()
    open_weekly_policy(
        db,
        persona,
        group_activity_enabled=True,
        group_can_comment=True,
        allowed_group_ids=[group.id],
        minimum_group_activity_interval_minutes=0,
    )
    save_group_config(group, {"activity_level": "high"})
    post = Post(content="AI topic", author_id=author.user_id, group_id=group.id)
    db.session.add(post)
    db.session.commit()
    generate = Mock(side_effect=AssertionError("AI-to-AI generation must not run"))
    monkeypatch.setattr("ai_group_action_engine.generate_content", generate)
    assert execute_persona_group_comment(persona, group, post) is False
    generate.assert_not_called()


def test_group_post_uses_existing_group_route_and_logs_only_after_success(db, monkeypatch):
    from ai_controls import save_group_config
    from ai_group_action_engine import execute_persona_group_post
    from ai_service import LLMResponse
    from models import AILog, Post

    persona = make_persona(db)
    owner = make_user(db)
    group = make_group(db, owner)
    group.members.append(persona.user)
    db.session.commit()
    open_weekly_policy(
        db,
        persona,
        group_activity_enabled=True,
        group_can_post=True,
        allowed_group_ids=[group.id],
        minimum_group_activity_interval_minutes=0,
    )
    save_group_config(group, {"activity_level": "high", "quiet_post_hours": 24})
    db.session.commit()
    group_id = group.id
    persona_user_id = persona.user_id
    calls = []

    class SessionContext:
        def __enter__(self):
            return {}

        def __exit__(self, *_args):
            return False

    class Response:
        status_code = 200
        is_json = True
        data = b'<input name="csrf_token" value="token">'

        @staticmethod
        def get_json(*_args, **_kwargs):
            return {"success": True}

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def session_transaction(self):
            return SessionContext()

        def get(self, path, **_kwargs):
            assert path == f"/groups/{group_id}"
            return Response()

        def post(self, path, data=None, **_kwargs):
            calls.append(path)
            db.session.add(Post(content=data["post_content"], author_id=persona_user_id, group_id=group_id))
            db.session.commit()
            return Response()

    monkeypatch.setattr(
        "ai_group_action_engine.current_app",
        SimpleNamespace(test_client=lambda: FakeClient()),
    )
    monkeypatch.setattr(
        "ai_group_action_engine.generate_content",
        Mock(return_value=LLMResponse("A group discussion", "test", False, 1)),
    )
    assert execute_persona_group_post(persona, group) is True
    assert calls == [f"/groups/{group_id}/post"]
    created = Post.query.filter_by(author_id=persona_user_id, group_id=group_id).one()
    assert AILog.query.filter_by(
        action_type="GROUP_POST_AUTOMATIC", target_id=created.id
    ).count() == 1


def test_admin_can_rename_ai_and_assignment_adds_real_group_membership(db, client):
    from ai_controls import get_profile_config

    persona = make_persona(db)
    admin = make_user(db, super_admin=True)
    group = make_group(db, admin)
    db.session.commit()
    with client.session_transaction() as session:
        session["_user_id"] = str(admin.id)
        session["_fresh"] = True

    response = client.post(
        f"/admin/ai-users/{persona.id}/display-name",
        data={"first_name": "Amara", "last_name": "Okafor"},
    )
    assert response.status_code == 302
    db.session.refresh(persona)
    assert persona.user.full_name == "Amara Okafor"
    assert persona.name == "Amara Okafor"
    assert persona.user.email.startswith("ai-group-")

    response = client.post(
        f"/admin/ai-users/{persona.id}/settings",
        data={
            "enabled": "on", "posting_mode": "automatic", "active_days": ["0"],
            "posting_days": ["0"], "allowed_group_ids": [str(group.id)],
            "group_activity_enabled": "on", "group_can_post": "on",
        },
    )
    assert response.status_code == 302
    assert group.members.filter_by(id=persona.user_id).first() is not None
    assert get_profile_config(persona)["allowed_group_ids"] == [group.id]


def test_admin_recent_content_includes_and_deletes_feed_group_comment_reply(db, client):
    from models import Comment, Post

    persona = make_persona(db)
    admin = make_user(db, super_admin=True)
    group = make_group(db, admin)
    feed_post = Post(content="AI feed", author_id=persona.user_id)
    group_post = Post(content="AI group", author_id=persona.user_id, group_id=group.id)
    db.session.add_all([feed_post, group_post])
    db.session.flush()
    comment = Comment(content="AI comment", author_id=persona.user_id, post_id=feed_post.id)
    reply = Comment(content="AI reply", author_id=persona.user_id, post_id=group_post.id)
    db.session.add_all([comment, reply])
    db.session.flush()
    reply.parent_id = comment.id
    db.session.commit()
    with client.session_transaction() as session:
        session["_user_id"] = str(admin.id)
        session["_fresh"] = True

    page = client.get("/admin/ai-users")
    assert page.status_code == 200
    assert b"Recent AI Content" in page.data
    assert b"AI feed" in page.data and b"AI group" in page.data
    assert b"AI comment" in page.data and b"AI reply" in page.data
    assert client.post(f"/admin/ai-users/comments/{comment.id}/delete").status_code == 302
    assert db.session.get(Comment, comment.id) is None
    assert client.post(f"/admin/ai-users/posts/{feed_post.id}/delete").status_code == 302
    assert client.post(f"/admin/ai-users/posts/{group_post.id}/delete").status_code == 302
    assert db.session.get(Post, feed_post.id) is None
    assert db.session.get(Post, group_post.id) is None


def test_human_group_content_is_not_mutated_by_ai_admin_delete(db, client):
    from models import Post

    admin = make_user(db, super_admin=True)
    human = make_user(db)
    group = make_group(db, admin)
    post = Post(content="Human group post", author_id=human.id, group_id=group.id)
    db.session.add(post)
    db.session.commit()
    with client.session_transaction() as session:
        session["_user_id"] = str(admin.id)
        session["_fresh"] = True
    assert client.post(f"/admin/ai-users/posts/{post.id}/delete").status_code == 400
    assert db.session.get(Post, post.id) is not None
