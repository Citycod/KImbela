from datetime import date, datetime, timedelta
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock
import uuid

import pytest


def make_user(db, *, ai=False, super_admin=False):
    from models import User

    user = User(
        first_name="AI" if ai else "Human",
        last_name="Tester",
        email=f"ai-control-{uuid.uuid4().hex}@example.com",
        phone_number=f"+2348{uuid.uuid4().int % 10**9:09d}",
        dob=date(1990, 1, 1),
        gender="Other",
        city="Lagos",
        country="Nigeria",
        state="Lagos",
        marital_status="Single",
        is_active=True,
        is_ai_persona=ai,
        is_super_admin=super_admin,
    )
    user.set_password("StrongPassw0rd!")
    db.session.add(user)
    db.session.flush()
    return user


def make_persona(db):
    from models import AIPersona

    user = make_user(db, ai=True)
    persona = AIPersona(
        user_id=user.id,
        name=f"Persona-{uuid.uuid4().hex[:6]}",
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


def save_config(db, persona, **changes):
    from ai_controls import get_profile_config, save_profile_config

    config = get_profile_config(persona)
    config.update(changes)
    save_profile_config(persona, config)
    db.session.commit()
    return config


@pytest.fixture(autouse=True)
def reset_global_ai_switch(db):
    from ai_controls import set_global_activity_enabled

    set_global_activity_enabled(True)
    db.session.commit()
    yield
    db.session.rollback()


def test_disabled_and_paused_ai_cannot_automate(db):
    from ai_controls import automation_eligibility

    persona = make_persona(db)
    save_config(db, persona, enabled=False)
    assert automation_eligibility(persona, "post") == (False, "disabled")

    persona.is_active = True
    save_config(db, persona, enabled=True, paused=True)
    assert automation_eligibility(persona, "post") == (False, "paused")


def test_enabled_ai_can_post_when_policy_is_open(db):
    from ai_controls import automation_eligibility

    persona = make_persona(db)
    save_config(
        db,
        persona,
        enabled=True,
        paused=False,
        posting_mode="automatic",
        active_days=list(range(7)),
        posting_start_time="00:00",
        posting_end_time="23:59",
        max_posts_per_day=2,
        minimum_post_interval_minutes=0,
    )
    assert automation_eligibility(persona, "post")[0] is True


def test_daily_post_limit_and_minimum_interval_are_enforced(db):
    from ai_controls import automation_eligibility
    from models import AILog

    persona = make_persona(db)
    now = datetime(2026, 8, 30, 12, 0)
    save_config(db, persona, max_posts_per_day=1, minimum_post_interval_minutes=60)
    db.session.add(
        AILog(
            persona_id=persona.id,
            action_type="CREATE_POST_AUTOMATIC",
            timestamp=now - timedelta(minutes=30),
            is_escalated=False,
        )
    )
    db.session.commit()
    assert automation_eligibility(persona, "post", now) == (False, "daily_limit")

    save_config(db, persona, max_posts_per_day=2)
    assert automation_eligibility(persona, "post", now) == (False, "minimum_interval")


def test_posting_window_and_active_day_are_enforced(db):
    from ai_controls import automation_eligibility

    persona = make_persona(db)
    monday_noon = datetime(2026, 8, 31, 12, 0)
    save_config(db, persona, active_days=[1], posting_start_time="09:00", posting_end_time="17:00")
    assert automation_eligibility(persona, "post", monday_noon) == (False, "inactive_day")

    save_config(db, persona, active_days=[0], posting_start_time="13:00", posting_end_time="17:00")
    assert automation_eligibility(persona, "post", monday_noon) == (False, "outside_window")


def test_manual_and_approval_modes_do_not_auto_publish(db):
    from ai_controls import automation_eligibility

    persona = make_persona(db)
    save_config(db, persona, posting_mode="manual")
    assert automation_eligibility(persona, "post") == (False, "manual")
    save_config(db, persona, posting_mode="approval")
    assert automation_eligibility(persona, "post") == (False, "approval")


def test_stop_all_blocks_and_resume_restores_automation(db):
    from ai_controls import automation_eligibility, set_global_activity_enabled

    persona = make_persona(db)
    set_global_activity_enabled(False)
    db.session.commit()
    assert automation_eligibility(persona, "post") == (False, "global_stop")
    set_global_activity_enabled(True)
    db.session.commit()
    assert automation_eligibility(persona, "post")[0] is True


def test_reply_disabled_and_daily_limit_are_enforced(db):
    from ai_controls import automation_eligibility
    from models import AILog

    persona = make_persona(db)
    save_config(db, persona, replies_enabled=False)
    assert automation_eligibility(persona, "reply") == (False, "replies_disabled")

    save_config(db, persona, replies_enabled=True, max_replies_per_day=1)
    db.session.add(
        AILog(
            persona_id=persona.id,
            action_type="REPLY_COMMENT_AUTOMATIC",
            timestamp=datetime.now(),
            is_escalated=False,
        )
    )
    db.session.commit()
    assert automation_eligibility(persona, "reply") == (False, "daily_limit")


def test_reply_self_and_duplicate_source_are_suppressed(db, monkeypatch):
    from ai_action_engine import execute_persona_comment
    from models import AILog, Comment, Post

    persona = make_persona(db)
    post = Post(content="Hello", author_id=persona.user_id)
    db.session.add(post)
    db.session.flush()
    self_comment = Comment(content="Mine", author_id=persona.user_id, post_id=post.id)
    human = make_user(db)
    source = Comment(content="Question", author_id=human.id, post_id=post.id)
    db.session.add_all([self_comment, source])
    db.session.commit()
    provider = Mock(side_effect=AssertionError("provider must not run"))
    monkeypatch.setattr("ai_action_engine.generate_content", provider)
    assert execute_persona_comment(persona, post, self_comment) is False

    db.session.add(
        AILog(
            persona_id=persona.id,
            action_type="REPLY_COMMENT_AUTOMATIC",
            prompt_context=f"source_comment_id={source.id}",
            is_escalated=False,
        )
    )
    db.session.commit()
    assert execute_persona_comment(persona, post, source) is False
    provider.assert_not_called()


def test_reply_delay_and_disallowed_duplicate_content_guards(db):
    from ai_controls import content_is_allowed, is_duplicate_post, reply_is_due
    from models import Comment, Post

    persona = make_persona(db)
    human = make_user(db)
    post = Post(content="Original", author_id=persona.user_id)
    db.session.add(post)
    db.session.flush()
    created_at = datetime(2026, 8, 30, 10, 0)
    comment = Comment(
        content="Please reply",
        author_id=human.id,
        post_id=post.id,
        created_at=created_at,
    )
    db.session.add(comment)
    db.session.commit()
    save_config(
        db,
        persona,
        minimum_reply_delay_minutes=30,
        maximum_reply_delay_minutes=30,
        disallowed_topics=["gambling"],
    )
    assert reply_is_due(persona, comment, created_at + timedelta(minutes=29)) is False
    assert reply_is_due(persona, comment, created_at + timedelta(minutes=30)) is True
    assert content_is_allowed(persona, "A community update") is True
    assert content_is_allowed(persona, "A gambling tip") is False

    duplicate = Post(content=" Same   words ", author_id=persona.user_id)
    db.session.add(duplicate)
    db.session.commit()
    assert is_duplicate_post(persona, "same words") is True


def test_approval_draft_is_persisted_once_across_restarts(db, monkeypatch):
    from ai_action_engine import prepare_persona_post_draft
    from ai_controls import get_pending_draft
    from ai_service import LLMResponse

    persona = make_persona(db)
    save_config(db, persona, posting_mode="approval")
    generate = Mock(return_value=LLMResponse("A fresh post", "groq", False, 10))
    monkeypatch.setattr("ai_action_engine.generate_content", generate)
    assert prepare_persona_post_draft(persona, "community") is True
    assert get_pending_draft(persona.id)["content"] == "A fresh post"
    assert prepare_persona_post_draft(persona, "community") is False
    generate.assert_called_once()


def test_manual_admin_post_receives_image_and_normal_action_engine(db, client, monkeypatch):
    persona = make_persona(db)
    admin = make_user(db, super_admin=True)
    db.session.commit()
    with client.session_transaction() as session:
        session["_user_id"] = str(admin.id)
        session["_fresh"] = True

    execute = Mock(return_value=True)
    monkeypatch.setattr("ai_action_engine.execute_persona_post", execute)
    response = client.post(
        f"/admin/ai-users/{persona.id}/post",
        data={
            "content": "Admin caption",
            "media": (BytesIO(b"fake-image"), "photo.jpg"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 302
    kwargs = execute.call_args.kwargs
    assert kwargs["source"] == "manual"
    assert kwargs["content"] == "Admin caption"
    assert kwargs["media_file"].filename == "photo.jpg"


def test_action_engine_sends_manual_image_post_through_user_dashboard(db, monkeypatch):
    from ai_action_engine import execute_persona_post
    from models import AILog, Post
    from werkzeug.datastructures import FileStorage

    persona = make_persona(db)
    calls = []

    class SessionContext:
        def __enter__(self):
            return {}

        def __exit__(self, *_args):
            return False

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def session_transaction(self):
            return SessionContext()

        def get(self, path, **_kwargs):
            assert path == "/user_dashboard"
            return SimpleNamespace(data=b'<input name="csrf_token" value="token">')

        def post(self, path, data=None, **_kwargs):
            calls.append((path, data))
            post = Post(content=data["post_content"], image="uploaded.jpg", author_id=persona.user_id)
            db.session.add(post)
            db.session.commit()
            return SimpleNamespace(
                status_code=302,
                location="http://localhost/user_dashboard",
                data=b"",
            )

    monkeypatch.setattr(
        "ai_action_engine.current_app",
        SimpleNamespace(test_client=lambda: FakeClient()),
    )
    media = FileStorage(stream=BytesIO(b"image"), filename="photo.jpg", content_type="image/jpeg")
    assert execute_persona_post(
        persona,
        "Admin-authored post",
        content="Caption",
        media_file=media,
        source="manual",
    ) is True
    assert calls[0][0] == "/user_dashboard"
    assert calls[0][1]["media"][1] == "photo.jpg"
    assert AILog.query.filter_by(action_type="CREATE_POST_MANUAL").count() == 1


def test_admin_can_delete_ai_post_but_not_normal_post(db, client):
    from models import AILog, Post

    persona = make_persona(db)
    human = make_user(db)
    admin = make_user(db, super_admin=True)
    ai_post = Post(content="AI post", author_id=persona.user_id)
    human_post = Post(content="Human post", author_id=human.id)
    db.session.add_all([ai_post, human_post])
    db.session.commit()
    with client.session_transaction() as session:
        session["_user_id"] = str(admin.id)
        session["_fresh"] = True

    assert client.post(f"/admin/ai-users/posts/{human_post.id}/delete").status_code == 400
    assert client.post(f"/admin/ai-users/posts/{ai_post.id}/delete").status_code == 302
    assert db.session.get(Post, ai_post.id) is None
    assert AILog.query.filter_by(action_type="DELETE_POST_MANUAL", target_id=ai_post.id).count() == 1


def test_normal_user_state_is_not_changed_by_ai_controls(db):
    from ai_controls import set_global_activity_enabled

    human = make_user(db)
    db.session.commit()
    set_global_activity_enabled(False)
    db.session.commit()
    db.session.refresh(human)
    assert human.is_active is True
    assert human.is_ai_persona is False


def test_ai_admin_page_is_super_admin_only_and_renders_controls(app, db, client):
    from flask import g

    make_persona(db)
    human = make_user(db)
    admin = make_user(db, super_admin=True)
    db.session.commit()
    with client.session_transaction() as session:
        session["_user_id"] = str(human.id)
        session["_fresh"] = True
    assert client.get("/admin/ai-users").status_code == 302
    g.pop("_login_user", None)

    admin_client = app.test_client()
    with admin_client.session_transaction() as session:
        session["_user_id"] = str(admin.id)
        session["_fresh"] = True
    response = admin_client.get("/admin/ai-users")
    assert response.status_code == 200
    assert b"STOP ALL AI ACTIVITY" in response.data
    assert b"Manual only" in response.data


def test_ai_job_uses_the_existing_dedicated_scheduler(app, monkeypatch):
    import scheduler as scheduler_module

    monkeypatch.setattr(scheduler_module, "scheduler", None)
    scheduler_instance = scheduler_module.init_scheduler(app)
    try:
        job = scheduler_instance.get_job("ai_persona_activity")
        assert job is not None
        assert job.max_instances == 1
        assert job.coalesce is True
    finally:
        scheduler_instance.shutdown(wait=True)
        scheduler_module.scheduler = None
