from datetime import date, datetime, timedelta
from io import BytesIO
import inspect
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


def test_manual_ai_post_inside_authenticated_admin_request_uses_persona_author(
    db, app
):
    from ai_action_engine import execute_persona_post
    from flask_login import login_user
    from models import AILog, Post

    persona = make_persona(db)
    admin = make_user(db, super_admin=True)
    db.session.commit()

    content = "Testing AI user posting from the admin panel."
    with app.test_request_context(f"/admin/ai-users/{persona.id}/post"):
        login_user(admin)
        published = execute_persona_post(
            persona,
            prompt_topic="Admin-authored post",
            content=content,
            source="manual",
        )

    assert published is True
    post = Post.query.filter_by(content=content).one()
    assert post.author_id == persona.user_id
    assert Post.query.filter_by(content=content, author_id=admin.id).first() is None
    log = AILog.query.filter_by(
        persona_id=persona.id,
        action_type="CREATE_POST_MANUAL",
    ).one()
    assert log.target_id == post.id


def test_action_engine_sends_manual_image_through_explicit_author_service(db, monkeypatch):
    from ai_action_engine import execute_persona_post
    from models import AILog, Post
    from werkzeug.datastructures import FileStorage

    persona = make_persona(db)
    monkeypatch.setattr(
        "utils.feed_post_service.cloudinary.uploader.upload",
        Mock(return_value={"secure_url": "https://cdn.example/uploaded.jpg"}),
    )
    media = FileStorage(stream=BytesIO(b"image"), filename="photo.jpg", content_type="image/jpeg")
    assert execute_persona_post(
        persona,
        "Admin-authored post",
        content="Caption",
        media_file=media,
        source="manual",
    ) is True
    post = Post.query.filter_by(content="Caption").one()
    assert post.author_id == persona.user_id
    assert post.image == "https://cdn.example/uploaded.jpg"
    assert AILog.query.filter_by(
        action_type="CREATE_POST_MANUAL", target_id=post.id
    ).count() == 1


def test_automatic_ai_post_uses_persona_author(db, monkeypatch):
    from ai_action_engine import execute_persona_post
    from models import AILog, Post

    persona = make_persona(db)
    save_config(
        db,
        persona,
        posting_mode="automatic",
        active_days=list(range(7)),
        posting_start_time="00:00",
        posting_end_time="23:59",
        minimum_post_interval_minutes=0,
    )

    assert execute_persona_post(
        persona,
        "community",
        content="Automatic explicit-author post",
        source="automatic",
    ) is True
    post = Post.query.filter_by(content="Automatic explicit-author post").one()
    assert post.author_id == persona.user_id
    assert AILog.query.filter_by(
        action_type="CREATE_POST_AUTOMATIC", target_id=post.id
    ).count() == 1


def test_failed_shared_feed_post_creation_returns_false_without_ai_log(db, monkeypatch):
    from ai_action_engine import execute_persona_post
    from models import AILog, Post

    persona = make_persona(db)

    def fail_creation(**_kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(
        "utils.feed_post_service.create_feed_post",
        fail_creation,
    )
    assert execute_persona_post(
        persona,
        "Admin-authored post",
        content="Must not persist",
        source="manual",
    ) is False
    assert Post.query.filter_by(content="Must not persist").count() == 0
    assert AILog.query.filter_by(persona_id=persona.id).count() == 0


def test_approved_ai_post_preserves_approved_log_source(db):
    from ai_action_engine import execute_persona_post
    from models import AILog, Post

    persona = make_persona(db)
    assert execute_persona_post(
        persona,
        "Approved topic",
        content="Approved explicit-author post",
        source="approval",
    ) is True
    post = Post.query.filter_by(content="Approved explicit-author post").one()
    assert post.author_id == persona.user_id
    assert AILog.query.filter_by(
        action_type="CREATE_POST_APPROVED", target_id=post.id
    ).count() == 1


def test_execute_persona_post_has_no_nested_client_or_csrf_scraping():
    from ai_action_engine import execute_persona_post

    source = inspect.getsource(execute_persona_post)
    assert ".test_client(" not in source
    assert "csrf_token" not in source


def test_human_dashboard_text_post_uses_current_user_and_invalidates_cache(
    db, client, monkeypatch
):
    from models import Post

    human = make_user(db)
    db.session.commit()
    with client.session_transaction() as session:
        session["_user_id"] = str(human.id)
        session["_fresh"] = True
    cache_delete = Mock()
    monkeypatch.setattr("utils.feed_post_service.cache.delete", cache_delete)

    response = client.post(
        "/user_dashboard",
        data={"post_content": "Human dashboard post", "post_location": "Lagos"},
    )

    assert response.status_code == 302
    post = Post.query.filter_by(content="Human dashboard post").one()
    assert post.author_id == human.id
    assert post.location == "Lagos"
    assert {call.args[0] for call in cache_delete.call_args_list} == {
        f"user_dashboard_{human.id}",
        f"posts_feed_{human.id}",
    }


def test_human_dashboard_image_and_giphy_paths_remain_intact(db, client, monkeypatch):
    from models import Post

    human = make_user(db)
    db.session.commit()
    with client.session_transaction() as session:
        session["_user_id"] = str(human.id)
        session["_fresh"] = True
    upload = Mock(return_value={"secure_url": "https://cdn.example/photo.jpg"})
    monkeypatch.setattr("utils.feed_post_service.cloudinary.uploader.upload", upload)

    image_response = client.post(
        "/user_dashboard",
        data={
            "post_content": "Human image post",
            "media": (BytesIO(b"image"), "photo.jpg"),
        },
        content_type="multipart/form-data",
    )
    gif_response = client.post(
        "/user_dashboard",
        data={
            "post_content": "Human GIF post",
            "gif_url": "https://media.giphy.com/media/example/giphy.gif",
        },
    )

    assert image_response.status_code == 302
    assert gif_response.status_code == 302
    image_post = Post.query.filter_by(content="Human image post").one()
    gif_post = Post.query.filter_by(content="Human GIF post").one()
    assert image_post.author_id == human.id
    assert image_post.image == "https://cdn.example/photo.jpg"
    assert gif_post.author_id == human.id
    assert gif_post.gif == "https://media.giphy.com/media/example/giphy.gif"
    assert upload.call_args.kwargs["folder"] == "kimbela/posts"
    assert upload.call_args.kwargs["transformation"][0]["width"] == 1000


def test_human_dashboard_ajax_upload_uses_shared_explicit_author_service(
    db, client, monkeypatch
):
    from models import Post

    human = make_user(db)
    db.session.commit()
    with client.session_transaction() as session:
        session["_user_id"] = str(human.id)
        session["_fresh"] = True
    upload = Mock(return_value={"secure_url": "https://cdn.example/ajax.jpg"})
    monkeypatch.setattr("utils.feed_post_service.cloudinary.uploader.upload", upload)

    response = client.post(
        "/user_dashboard",
        data={
            "post_content": "Human AJAX post",
            "emoji_data": '{"emojis": [{"name": "wave", "value": "👋"}]}',
            "media": (BytesIO(b"image"), "ajax.jpg"),
        },
        headers={
            "X-Requested-With": "XMLHttpRequest",
            "X-File-Upload": "true",
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert response.get_json()["success"] is True
    post = Post.query.filter_by(content="Human AJAX post").one()
    assert post.author_id == human.id
    assert post.image == "https://cdn.example/ajax.jpg"
    assert post.emoji_data["emojis"][0]["name"] == "wave"
    assert upload.call_args.kwargs["transformation"][0]["width"] == 800


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
        assert job.trigger.interval == timedelta(hours=24)
    finally:
        scheduler_instance.shutdown(wait=True)
        scheduler_module.scheduler = None


def test_ai_activity_pass_reports_bounded_group_and_feed_outcomes(
    app, db, monkeypatch
):
    import scheduler as scheduler_module

    persona = make_persona(db)
    persona_id = persona.id
    monkeypatch.setattr(
        "utils.ai_group_membership.sync_ai_group_memberships", lambda: 2
    )
    monkeypatch.setattr(
        "ai_controls.order_personas_by_last_post", lambda personas: list(personas)
    )
    group_sessions = Mock(return_value=3)
    feed_action = Mock(return_value=True)
    monkeypatch.setattr(
        "ai_group_action_engine.run_scheduled_group_sessions", group_sessions
    )
    monkeypatch.setattr(scheduler_module, "execute_one_feed_ai_action", feed_action)

    result = scheduler_module.run_ai_persona_activity_once(app)

    assert result["active_personas"] >= 1
    assert result["memberships_inserted"] == 2
    assert result["group_slots_completed"] == 3
    assert result["feed_action_completed"] is True
    assert persona_id in {
        selected.id for selected in group_sessions.call_args.args[0]
    }
    feed_action.assert_called_once()


def test_ai_activity_requeries_personas_after_group_phase_removes_session(
    app, db, monkeypatch
):
    from sqlalchemy import inspect as sqlalchemy_inspect

    import scheduler as scheduler_module

    persona = make_persona(db)
    persona_id = persona.id
    monkeypatch.setattr(
        "utils.ai_group_membership.sync_ai_group_memberships", lambda: 0
    )
    order_calls = []

    def order_personas(personas):
        ordered = list(personas)
        order_calls.append(ordered)
        return ordered

    monkeypatch.setattr("ai_controls.order_personas_by_last_post", order_personas)
    group_phase_instances = {}

    def group_phase(personas):
        group_phase_instances.update({item.id: item for item in personas})
        db.session.remove()
        return 1

    def feed_phase(personas, *, actions):
        rebound = {item.id: item for item in personas}
        assert persona_id in rebound
        assert rebound[persona_id] is not group_phase_instances[persona_id]
        assert sqlalchemy_inspect(rebound[persona_id]).detached is False
        assert actions == ("reply", "post")
        return False

    monkeypatch.setattr(
        "ai_group_action_engine.run_scheduled_group_sessions", group_phase
    )
    monkeypatch.setattr(scheduler_module, "execute_one_feed_ai_action", feed_phase)

    result = scheduler_module.run_ai_persona_activity_once(app)

    assert result["group_slots_completed"] == 1
    assert result["feed_action_completed"] is False
    assert len(order_calls) == 2


def test_feed_phase_failure_propagates_without_losing_completed_group_state(
    app, db, monkeypatch
):
    import scheduler as scheduler_module
    from models import AILog

    persona = make_persona(db)
    persona_id = persona.id
    monkeypatch.setattr(
        "utils.ai_group_membership.sync_ai_group_memberships", lambda: 0
    )
    monkeypatch.setattr(
        "ai_controls.order_personas_by_last_post", lambda personas: list(personas)
    )

    def group_phase(_personas):
        db.session.add(
            AILog(
                persona_id=persona_id,
                action_type="GROUP_ACTIVITY_SESSION",
                prompt_context="committed-before-feed",
                generated_content="post",
                provider_used="test",
                is_escalated=False,
            )
        )
        db.session.commit()
        return 1

    monkeypatch.setattr(
        "ai_group_action_engine.run_scheduled_group_sessions", group_phase
    )
    monkeypatch.setattr(
        scheduler_module,
        "execute_one_feed_ai_action",
        Mock(side_effect=RuntimeError("unexpected feed failure")),
    )

    with pytest.raises(RuntimeError, match="unexpected feed failure"):
        scheduler_module.run_ai_persona_activity_once(app)

    assert AILog.query.filter_by(
        action_type="GROUP_ACTIVITY_SESSION",
        prompt_context="committed-before-feed",
    ).count() == 1


def test_ai_activity_pass_propagates_unexpected_failure_to_scheduler(
    app, monkeypatch, caplog
):
    import logging

    import scheduler as scheduler_module

    monkeypatch.setattr(
        "utils.ai_group_membership.sync_ai_group_memberships",
        Mock(side_effect=RuntimeError("unexpected pass failure")),
    )

    with caplog.at_level(logging.ERROR, logger="scheduler"):
        with pytest.raises(RuntimeError, match="unexpected pass failure"):
            scheduler_module.run_ai_persona_activity_once(app)

    assert "AI persona activity pass failed" in caplog.text
