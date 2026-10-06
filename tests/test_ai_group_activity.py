from datetime import date, datetime, timedelta
import uuid
from unittest.mock import Mock, call
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
    from models import AILog, Post, User

    ai_user_ids = db.session.query(User.id).filter(User.is_ai_persona.is_(True))
    Post.query.filter(Post.author_id.in_(ai_user_ids)).delete(
        synchronize_session=False
    )
    AILog.query.delete()

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


def test_feed_and_group_share_the_same_fourteen_day_budget(db):
    from ai_controls import new_post_eligibility, weekly_post_counts
    from models import Post

    persona = make_persona(db)
    now = datetime(2026, 8, 31, 12, 0)
    open_weekly_policy(db, persona)
    add_published_post(db, persona, now - timedelta(hours=2))
    assert new_post_eligibility(persona, "feed", now) == (
        False,
        "fourteen_day_post_limit",
    )
    assert new_post_eligibility(persona, "group", now) == (
        False,
        "fourteen_day_post_limit",
    )
    assert weekly_post_counts(persona, now) == {"total": 1, "feed": 1, "group": 0}

    db.session.query(Post).filter(Post.author_id == persona.user_id).delete()
    add_published_post(db, persona, now - timedelta(hours=1), group_id=1)
    assert new_post_eligibility(persona, "feed", now) == (
        False,
        "fourteen_day_post_limit",
    )
    assert new_post_eligibility(persona, "group", now) == (
        False,
        "fourteen_day_post_limit",
    )


def test_persona_is_eligible_again_after_fourteen_days(db):
    from ai_controls import new_post_eligibility

    persona = make_persona(db)
    now = datetime(2026, 8, 31, 12, 0)
    open_weekly_policy(db, persona, maximum_total_posts_per_week=5)
    add_published_post(db, persona, now - timedelta(days=14), group_id=1)
    assert new_post_eligibility(persona, "group", now)[0] is True
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


def test_scheduler_prefers_quiet_group_post_before_feed_post(monkeypatch):
    import scheduler

    persona = object()
    group = Mock(side_effect=[False, False, True])
    feed = Mock(return_value=False)
    monkeypatch.setattr("ai_group_action_engine.execute_next_group_action", group)
    monkeypatch.setattr(scheduler, "execute_one_feed_ai_action", feed)

    assert scheduler.run_one_ai_action([persona]) is True
    assert group.call_args_list == [
        call([persona], actions=("reply",)),
        call([persona], actions=("comment",)),
        call([persona], actions=("post",)),
    ]
    feed.assert_called_once_with([persona], actions=("reply",))


def test_scheduler_does_nothing_when_no_action_is_eligible(monkeypatch):
    import scheduler

    personas = [object(), object()]
    group = Mock(return_value=False)
    feed = Mock(return_value=False)
    monkeypatch.setattr("ai_group_action_engine.execute_next_group_action", group)
    monkeypatch.setattr(scheduler, "execute_one_feed_ai_action", feed)

    assert scheduler.run_one_ai_action(personas) is False
    assert group.call_count == 3
    assert feed.call_count == 2


def test_feed_selection_preserves_oldest_post_first_scheduler_order(monkeypatch):
    import scheduler

    posted = SimpleNamespace(id=1, interests=["community"])
    quiet = SimpleNamespace(id=2, interests=["community"])
    selected = []
    monkeypatch.setattr(
        "ai_controls.get_profile_config",
        lambda _persona: {"reply_probability": 0, "posting_mode": "automatic"},
    )
    monkeypatch.setattr("ai_controls.automation_eligibility", lambda *_args, **_kwargs: (True, "eligible"))
    monkeypatch.setattr(
        "ai_action_engine.execute_persona_post",
        lambda persona, _topic: selected.append(persona.id) or True,
    )
    assert scheduler.execute_one_feed_ai_action([quiet, posted], actions=("post",)) is True
    assert selected == [quiet.id]


def test_feed_executor_publishes_at_most_one_profile_per_run(monkeypatch):
    import scheduler

    first = SimpleNamespace(id=1, interests=["community"])
    second = SimpleNamespace(id=2, interests=["community"])
    selected = []
    monkeypatch.setattr(
        "ai_controls.get_profile_config",
        lambda _persona: {"reply_probability": 0, "posting_mode": "automatic"},
    )
    monkeypatch.setattr(
        "ai_controls.automation_eligibility",
        lambda *_args, **_kwargs: (True, "eligible"),
    )
    monkeypatch.setattr(
        "ai_action_engine.execute_persona_post",
        lambda persona, _topic: selected.append(persona.id) or True,
    )

    assert scheduler.execute_one_feed_ai_action(
        [first, second], actions=("post",)
    ) is True
    assert selected == [first.id]


def test_bulk_persona_order_prefers_never_then_longest_without_posting(db):
    from ai_controls import order_personas_by_last_post

    oldest = make_persona(db, "Oldest")
    recent = make_persona(db, "Recent")
    never = make_persona(db, "Never")
    now = datetime(2026, 8, 31, 12, 0)
    add_published_post(db, oldest, now - timedelta(days=30))
    add_published_post(db, recent, now - timedelta(days=15))

    ordered = order_personas_by_last_post([recent, oldest, never])

    assert [persona.id for persona in ordered] == [never.id, oldest.id, recent.id]


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


def test_group_provider_failure_is_logged_and_leaves_slot_due(
    db, monkeypatch, caplog
):
    import logging

    from ai_controls import save_group_config
    from ai_group_action_engine import execute_group_activity_session
    from models import AILog, Post

    persona = make_persona(db, "Provider failure")
    owner = make_user(db)
    group = make_group(db, owner, "Provider failure group")
    group.members.append(persona.user)
    open_weekly_policy(
        db,
        persona,
        group_activity_enabled=True,
        group_can_post=True,
        allowed_group_ids=[group.id],
        minimum_group_activity_interval_minutes=0,
        maximum_group_posts_per_week=5,
        maximum_total_posts_per_week=5,
    )
    save_group_config(group, {"activity_level": "high", "quiet_post_hours": 1})
    db.session.commit()
    monkeypatch.setattr(
        "ai_group_action_engine.generate_content",
        Mock(side_effect=RuntimeError("configured provider model is unavailable")),
    )

    with caplog.at_level(logging.INFO, logger="ai_group_action_engine"):
        assert execute_group_activity_session(group, [persona]) is False

    assert Post.query.filter_by(group_id=group.id, author_id=persona.user_id).count() == 0
    assert AILog.query.filter_by(action_type="GROUP_POST_AUTOMATIC").count() == 0
    assert AILog.query.filter_by(action_type="GROUP_ACTIVITY_SESSION").count() == 0
    assert "Group post generation failed" in caplog.text
    assert "configured provider model is unavailable" in caplog.text


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


def test_all_ai_membership_sync_is_idempotent_for_existing_and_new_groups(db):
    from models import group_members
    from utils.ai_group_membership import (
        add_ai_users_to_group,
        add_ai_user_to_active_groups,
        sync_ai_group_memberships,
    )

    first = make_persona(db, "First member")
    disabled = make_persona(db, "Disabled member")
    disabled.is_active = False
    disabled.user.is_active = False
    owner = make_user(db)
    existing = make_group(db, owner, "Existing group")
    assert sync_ai_group_memberships() >= 2
    db.session.commit()
    assert sync_ai_group_memberships() == 0

    new_group = make_group(db, owner, "New group")
    assert add_ai_users_to_group(new_group) >= 2
    db.session.commit()
    second = make_persona(db, "New persona")
    second.is_active = False
    second.user.is_active = False
    assert add_ai_user_to_active_groups(second) >= 2
    db.session.commit()

    pairs = db.session.execute(
        db.select(group_members.c.user_id, group_members.c.group_id).where(
            group_members.c.user_id.in_(
                [first.user_id, disabled.user_id, second.user_id]
            ),
            group_members.c.group_id.in_([existing.id, new_group.id]),
        )
    ).all()
    assert len(pairs) == 6
    assert len(set(pairs)) == 6


def test_user_created_group_receives_enabled_and_disabled_ai_membership(db, client):
    from models import Group

    persona = make_persona(db, "New group member")
    disabled = make_persona(db, "Disabled new group member")
    disabled.is_active = False
    disabled.user.is_active = False
    db.session.commit()
    owner = make_user(db)
    with client.session_transaction() as session:
        session["_user_id"] = str(owner.id)
        session["_fresh"] = True
    name = f"Created {uuid.uuid4().hex}"
    response = client.post(
        "/groups/create",
        data={
            "name": name,
            "description": "A new active group",
            "category": "social",
            "is_private": "false",
        },
    )
    assert response.status_code == 200
    group = Group.query.filter_by(name=name).one()
    assert group.members.filter_by(id=persona.user_id).first() is not None
    assert group.members.filter_by(id=disabled.user_id).first() is not None


def test_admin_reactivation_synchronizes_ai_into_existing_groups(db, client):
    from ai_controls import get_profile_config, save_profile_config

    persona = make_persona(db, "Reactivated")
    owner = make_user(db)
    admin = make_user(db, super_admin=True)
    group = make_group(db, owner, "Existing before activation")
    persona.is_active = False
    config = get_profile_config(persona)
    config["enabled"] = False
    save_profile_config(persona, config)
    db.session.commit()
    with client.session_transaction() as session:
        session["_user_id"] = str(admin.id)
        session["_fresh"] = True
    response = client.post(
        f"/admin/ai-users/{persona.id}/settings",
        data={"enabled": "on", "posting_mode": "automatic"},
    )
    assert response.status_code == 302
    assert group.members.filter_by(id=persona.user_id).first() is not None


def test_group_sessions_use_two_calendar_slots_and_rotate_personas(db, monkeypatch):
    from ai_group_action_engine import execute_group_activity_session
    from models import AILog

    first = make_persona(db, "First rotation")
    second = make_persona(db, "Second rotation")
    owner = make_user(db)
    group = make_group(db, owner, "Rotation group")
    group.members.append(first.user)
    group.members.append(second.user)
    db.session.commit()
    selected = []
    monkeypatch.setattr(
        "ai_group_action_engine.group_automation_eligibility",
        lambda *_args, **_kwargs: (True, "eligible"),
    )
    monkeypatch.setattr(
        "ai_group_action_engine.group_is_quiet_enough",
        lambda *_args, **_kwargs: True,
    )

    def publish(persona, destination):
        selected.append(persona.id)
        db.session.add(
            AILog(
                persona_id=persona.id,
                action_type="GROUP_POST_AUTOMATIC",
                target_id=destination.id,
                prompt_context=f"group_id={destination.id}",
                generated_content="rotation",
                provider_used="test",
                is_escalated=False,
            )
        )
        db.session.commit()
        return True

    monkeypatch.setattr("ai_group_action_engine.execute_persona_group_post", publish)
    monday = datetime(2026, 10, 5, 12, 0)
    thursday = datetime(2026, 10, 8, 12, 0)
    assert execute_group_activity_session(group, [first, second], monday) is True
    assert execute_group_activity_session(group, [first, second], monday) is False
    assert execute_group_activity_session(group, [first, second], thursday) is True
    assert selected == [first.id, second.id]
    assert AILog.query.filter_by(action_type="GROUP_ACTIVITY_SESSION").count() == 2


def test_comment_only_activity_does_not_complete_required_post_slot(db, monkeypatch):
    from ai_group_action_engine import execute_group_activity_session
    from models import AILog, Post

    persona = make_persona(db, "Commenter")
    owner = make_user(db)
    group = make_group(db, owner, "Comment group")
    group.members.append(persona.user)
    human_post = Post(content="Human topic", author_id=owner.id, group_id=group.id)
    db.session.add(human_post)
    db.session.commit()
    comments = []
    monkeypatch.setattr(
        "ai_group_action_engine.group_automation_eligibility",
        lambda _persona, _group, action, *_args, **_kwargs: (
            (False, "not available")
            if action in {"post", "reply"}
            else (True, "eligible")
        ),
    )
    monkeypatch.setattr(
        "ai_group_action_engine.group_is_quiet_enough",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        "ai_group_action_engine.execute_persona_group_comment",
        lambda selected, destination, post, *_args: comments.append(
            (selected.id, destination.id, post.id)
        )
        or True,
    )
    assert execute_group_activity_session(
        group, [persona], datetime(2026, 10, 5, 12, 0)
    ) is False
    assert comments == []
    assert AILog.query.filter_by(action_type="GROUP_ACTIVITY_SESSION").count() == 0


def test_comment_may_run_in_addition_to_required_original_post(db, monkeypatch):
    from ai_group_action_engine import execute_group_activity_session
    from models import AILog, Post

    poster = make_persona(db, "Required poster")
    commenter = make_persona(db, "Optional commenter")
    owner = make_user(db)
    group = make_group(db, owner, "Post plus comment group")
    group.members.append(poster.user)
    group.members.append(commenter.user)
    human_post = Post(content="Human discussion", author_id=owner.id, group_id=group.id)
    db.session.add(human_post)
    db.session.commit()
    comments = []
    monkeypatch.setattr(
        "ai_group_action_engine.group_automation_eligibility",
        lambda _persona, _group, action, *_args, **_kwargs: (
            (False, "no reply") if action == "reply" else (True, "eligible")
        ),
    )
    monkeypatch.setattr(
        "ai_group_action_engine.group_is_quiet_enough",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        "ai_group_action_engine.execute_persona_group_post",
        lambda selected, _group: selected.id == poster.id,
    )
    monkeypatch.setattr(
        "ai_group_action_engine.execute_persona_group_comment",
        lambda selected, destination, post, *_args: comments.append(
            (selected.id, destination.id, post.id)
        )
        or True,
    )
    assert execute_group_activity_session(
        group, [poster, commenter], datetime(2026, 10, 5, 12, 0)
    ) is True
    assert comments == [(commenter.id, group.id, human_post.id)]
    marker = AILog.query.filter_by(action_type="GROUP_ACTIVITY_SESSION").one()
    assert marker.generated_content == "post"
    assert "required_original_post=1" in marker.prompt_context


def test_failed_original_post_leaves_required_slot_due(db, monkeypatch, caplog):
    import logging

    from ai_group_action_engine import execute_group_activity_session
    from models import AILog

    persona = make_persona(db, "Failed poster")
    owner = make_user(db)
    group = make_group(db, owner, "Failed post group")
    group.members.append(persona.user)
    db.session.commit()
    monkeypatch.setattr(
        "ai_group_action_engine.group_automation_eligibility",
        lambda *_args, **_kwargs: (True, "eligible"),
    )
    monkeypatch.setattr(
        "ai_group_action_engine.group_is_quiet_enough",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        "ai_group_action_engine.execute_persona_group_post",
        lambda *_args, **_kwargs: False,
    )
    with caplog.at_level(logging.INFO, logger="ai_group_action_engine"):
        assert execute_group_activity_session(
            group, [persona], datetime(2026, 10, 5, 12, 0)
        ) is False
    assert AILog.query.filter_by(action_type="GROUP_ACTIVITY_SESSION").count() == 0
    assert "post_execution_failed" in caplog.text



def test_disabled_persona_remains_member_but_cannot_complete_slot(db, monkeypatch):
    from ai_group_action_engine import execute_group_activity_session
    from utils.ai_group_membership import sync_ai_group_memberships

    persona = make_persona(db, "Disabled activity")
    owner = make_user(db)
    group = make_group(db, owner, "Disabled activity group")
    persona.is_active = False
    persona.user.is_active = False
    sync_ai_group_memberships()
    db.session.commit()
    publish = Mock(side_effect=AssertionError("disabled persona must not publish"))
    monkeypatch.setattr("ai_group_action_engine.execute_persona_group_post", publish)
    assert group.members.filter_by(id=persona.user_id).first() is not None
    assert execute_group_activity_session(
        group, [persona], datetime(2026, 10, 5, 12, 0)
    ) is False
    publish.assert_not_called()


@pytest.mark.parametrize(
    ("group_level", "can_post"),
    [("off", True), ("high", False)],
)
def test_group_or_post_setting_blocks_slot_completion(
    db, monkeypatch, group_level, can_post
):
    from ai_controls import save_group_config
    from ai_group_action_engine import execute_group_activity_session
    from models import AILog

    persona = make_persona(db, f"Settings {group_level} {can_post}")
    owner = make_user(db)
    group = make_group(db, owner, f"Settings group {group_level} {can_post}")
    group.members.append(persona.user)
    open_weekly_policy(
        db,
        persona,
        group_activity_enabled=True,
        group_can_post=can_post,
        allowed_group_ids=[group.id],
        minimum_group_activity_interval_minutes=0,
        maximum_group_posts_per_week=5,
        maximum_total_posts_per_week=5,
    )
    save_group_config(group, {"activity_level": group_level})
    db.session.commit()
    publish = Mock(side_effect=AssertionError("blocked settings must prevent post"))
    monkeypatch.setattr("ai_group_action_engine.execute_persona_group_post", publish)
    assert execute_group_activity_session(group, [persona]) is False
    assert AILog.query.filter_by(action_type="GROUP_ACTIVITY_SESSION").count() == 0
    publish.assert_not_called()


def test_bounded_group_session_pass_rotates_without_starving_later_groups(db, monkeypatch):
    from ai_group_action_engine import GROUP_SESSION_CURSOR_KEY, run_scheduled_group_sessions
    from models import Group, SiteSetting

    owner = make_user(db)
    groups = [make_group(db, owner, f"Fair group {index}") for index in range(3)]
    ordered_ids = [
        group.id
        for group in Group.query.filter(Group.is_active.is_(True))
        .order_by(Group.id.asc())
        .all()
    ]
    SiteSetting.set_value(GROUP_SESSION_CURSOR_KEY, str(ordered_ids.index(groups[0].id)))
    db.session.commit()
    visited = []
    monkeypatch.setattr(
        "ai_group_action_engine.group_session_completed",
        lambda *_args, **_kwargs: False,
    )
    monkeypatch.setattr(
        "ai_group_action_engine.execute_group_activity_session",
        lambda group, *_args, **_kwargs: visited.append(group.id) or False,
    )
    run_scheduled_group_sessions([], max_groups=2)
    first_pass = list(visited)
    visited.clear()
    run_scheduled_group_sessions([], max_groups=2)
    assert len(first_pass) == 2
    assert groups[-1].id in visited


def test_successive_bounded_passes_complete_due_slots_across_multiple_groups(
    db, monkeypatch
):
    from ai_group_action_engine import (
        GROUP_ACTIVITY_SESSION,
        GROUP_SESSION_CURSOR_KEY,
        _session_marker,
        run_scheduled_group_sessions,
    )
    from models import AILog, Group, SiteSetting

    first = make_persona(db, "Bounded first")
    second = make_persona(db, "Bounded second")
    owner = make_user(db)
    groups = [make_group(db, owner, f"Bounded group {index}") for index in range(3)]
    for group in groups:
        group.members.append(first.user)
        group.members.append(second.user)
    db.session.commit()
    ordered_ids = [
        group_id
        for (group_id,) in db.session.query(Group.id)
        .filter(Group.is_active.is_(True))
        .order_by(Group.id.asc())
        .all()
    ]
    SiteSetting.set_value(
        GROUP_SESSION_CURSOR_KEY, str(ordered_ids.index(groups[0].id))
    )
    target_ids = {group.id for group in groups}
    for group_id in ordered_ids:
        if group_id in target_ids:
            continue
        db.session.add(
            AILog(
                persona_id=first.id,
                action_type=GROUP_ACTIVITY_SESSION,
                target_id=group_id,
                prompt_context=_session_marker(group_id, datetime(2026, 10, 5, 12, 0)),
                generated_content="preexisting completion",
                provider_used="test",
                is_escalated=False,
            )
        )
    db.session.commit()
    monkeypatch.setattr(
        "ai_group_action_engine.group_automation_eligibility",
        lambda *_args, **_kwargs: (True, "eligible"),
    )
    monkeypatch.setattr(
        "ai_group_action_engine.group_is_quiet_enough",
        lambda *_args, **_kwargs: True,
    )

    def publish(persona, group):
        db.session.add(
            AILog(
                persona_id=persona.id,
                action_type="GROUP_POST_AUTOMATIC",
                target_id=group.id,
                prompt_context=f"group_id={group.id}",
                generated_content="bounded post",
                provider_used="test",
                is_escalated=False,
            )
        )
        db.session.commit()
        return True

    monkeypatch.setattr("ai_group_action_engine.execute_persona_group_post", publish)
    now = datetime(2026, 10, 5, 12, 0)

    assert run_scheduled_group_sessions([first, second], now, max_groups=2) == 2
    assert run_scheduled_group_sessions([first, second], now, max_groups=2) == 1
    completed_group_ids = {
        row.target_id
        for row in AILog.query.filter_by(action_type="GROUP_ACTIVITY_SESSION").all()
    }
    assert target_ids.issubset(completed_group_ids)


def test_ai_cannot_create_original_matchmaking_group_post(app, db, monkeypatch):
    from ai_controls import save_group_config
    from ai_group_action_engine import (
        execute_group_activity_session,
        execute_persona_group_post,
    )
    from models import AILog

    persona = make_persona(db, "Matchmaking AI")
    owner = make_user(db)
    group = make_group(db, owner, "Renamed protected group")
    group.members.append(persona.user)
    db.session.commit()
    monkeypatch.setitem(app.config, "MATCHMAKING_GROUP_ID", str(group.id))
    open_weekly_policy(
        db,
        persona,
        group_activity_enabled=True,
        group_can_post=True,
        allowed_group_ids=[group.id],
        minimum_group_activity_interval_minutes=0,
        maximum_group_posts_per_week=5,
        maximum_total_posts_per_week=5,
    )
    save_group_config(group, {"activity_level": "high"})
    db.session.commit()
    generation = Mock(side_effect=AssertionError("generation must not run"))
    monkeypatch.setattr("ai_group_action_engine.generate_content", generation)
    assert execute_persona_group_post(persona, group) is False
    assert execute_group_activity_session(
        group, [persona], datetime(2026, 10, 5, 12, 0)
    ) is False
    assert AILog.query.filter_by(action_type="GROUP_ACTIVITY_SESSION").count() == 0
    generation.assert_not_called()


def test_ai_membership_in_matchmaking_group_is_allowed(app, db, monkeypatch):
    """Test 13: AI persona accounts may be members of the Matchmaking group."""
    from utils.ai_group_membership import add_ai_users_to_group, sync_ai_group_memberships

    persona = make_persona(db, "Matchmaking member")
    disabled = make_persona(db, "Disabled matchmaking member")
    disabled.is_active = False
    disabled.user.is_active = False
    owner = make_user(db)
    group = make_group(db, owner, "Protected matchmaking group")
    db.session.commit()
    monkeypatch.setitem(app.config, "MATCHMAKING_GROUP_ID", str(group.id))
    inserted = sync_ai_group_memberships()
    db.session.commit()
    assert group.members.filter_by(id=persona.user_id).first() is not None
    assert group.members.filter_by(id=disabled.user_id).first() is not None

    # Idempotent — a second sync adds zero rows.
    assert add_ai_users_to_group(group) == 0


def test_admin_can_post_in_matchmaking_but_ai_cannot(app, db, monkeypatch):
    """Test 14: Admin/system Matchmaking posting remains allowed; AI is blocked."""
    from utils.matchmaking_group import can_create_group_post

    persona = make_persona(db, "Matchmaking blocked AI")
    admin = make_user(db, super_admin=True)
    regular_human = make_user(db)
    owner = make_user(db)
    group = make_group(db, owner, "Matchmaking posting test")
    group.members.append(persona.user)
    group.members.append(admin)
    group.members.append(regular_human)
    db.session.commit()
    monkeypatch.setitem(app.config, "MATCHMAKING_GROUP_ID", str(group.id))
    # AI persona is blocked from posting in Matchmaking.
    assert can_create_group_post(group, persona.user) is False

    # Admin/super-admin can still post.
    assert can_create_group_post(group, admin) is True

    # Regular human cannot post either (Matchmaking is admin-only).
    assert can_create_group_post(group, regular_human) is False
