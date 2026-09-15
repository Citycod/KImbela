import json
import uuid
from datetime import date, datetime, timedelta
from io import BytesIO

import pytest


def make_user(db, *, admin=False, super_admin=False, ai=False, dob=None, permissions=None):
    from models import User

    user = User(
        first_name="AI" if ai else "Human",
        last_name=uuid.uuid4().hex[:6],
        email=f"control-{uuid.uuid4().hex}@example.com",
        phone_number=f"+2346{uuid.uuid4().int % 10**9:09d}",
        dob=dob or date(1990, 1, 1),
        gender="Other",
        city="Lagos",
        state="Lagos",
        country="Nigeria",
        marital_status="Single",
        is_active=True,
        is_admin=admin,
        is_super_admin=super_admin,
        is_ai_persona=ai,
        admin_permissions=json.dumps(permissions or []),
    )
    user.set_password("StrongPassw0rd!")
    db.session.add(user)
    db.session.flush()
    return user


def make_persona(db, *, allowed_actions=None, forbidden_actions=None):
    from models import AIPersona

    user = make_user(db, ai=True)
    persona = AIPersona(
        user_id=user.id,
        name="AI Persona",
        bio_disclosure="This is an automated AI profile.",
        personality="Helpful",
        interests=["community"],
        allowed_actions=allowed_actions or ["post", "comment"],
        forbidden_actions=forbidden_actions or ["financial advice"],
        is_active=True,
    )
    db.session.add(persona)
    db.session.commit()
    return persona


def make_group(db, owner, *, name="Community", private=False):
    from models import Group

    group = Group(
        name=name,
        created_by=owner.id,
        is_active=True,
        is_private=private,
    )
    db.session.add(group)
    db.session.flush()
    group.members.append(owner)
    db.session.commit()
    return group


def login(client, user):
    from flask import g

    g.pop("_login_user", None)
    with client.session_transaction() as session:
        session.clear()
        session["_user_id"] = str(user.id)
        session["_fresh"] = True


def test_matchmaking_group_privacy_and_posting_are_server_enforced(app, db, client):
    from models import Comment, Post

    admin = make_user(db, admin=True, permissions=["groups_manage"])
    member = make_user(db)
    outsider = make_user(db)
    group = make_group(db, admin, name="Renamed protected community", private=False)
    group.members.append(member)
    db.session.commit()
    original = app.config.get("MATCHMAKING_GROUP_ID")
    app.config["MATCHMAKING_GROUP_ID"] = str(group.id)
    try:
        login(client, outsider)
        assert client.get(f"/groups/{group.id}").status_code == 403
        assert client.get(f"/groups/{group.id}/posts").status_code == 403
        assert client.post(f"/groups/{group.id}/join").status_code == 403

        login(client, member)
        assert client.get(f"/groups/{group.id}").status_code == 200
        assert client.post(
            f"/groups/{group.id}/post", data={"post_content": "bypass"}
        ).status_code == 403

        login(client, admin)
        response = client.post(
            f"/groups/{group.id}/post", data={"post_content": "Official update"}
        )
        assert response.status_code == 200
        protected_post = Post.query.filter_by(group_id=group.id).one()
        protected_post.content = "classified matchmaking update"
        protected_comment = Comment(
            content="authorized comment",
            author_id=member.id,
            post_id=protected_post.id,
        )
        db.session.add(protected_comment)
        db.session.commit()

        login(client, outsider)
        assert protected_post.public_id not in client.get(
            "/search?q=classified"
        ).get_data(as_text=True)
        assert client.post(
            f"/comments/{protected_comment.id}/report",
            data={"report_reason": "Spam"},
        ).status_code == 403

        login(client, member)
        assert protected_post.public_id in client.get(
            "/search?q=classified"
        ).get_data(as_text=True)
        assert client.post(f"/repost/{protected_post.public_id}").status_code == 403
        assert client.post(f"/share_post/{protected_post.public_id}").status_code == 403
        assert client.post(
            f"/add_comment/{protected_post.id}",
            json={"content": "Member reply"},
        ).status_code == 200

        login(client, admin)
        response = client.post(
            f"/admin/groups/{group.id}/update",
            data={"name": "Still protected", "is_private": "false"},
        )
        assert response.status_code == 200
        db.session.refresh(group)
        assert group.is_private is True
    finally:
        app.config["MATCHMAKING_GROUP_ID"] = original


def test_similar_group_and_malformed_config_do_not_lock_unrelated_group(app, db, client, caplog):
    user = make_user(db)
    group = make_group(db, user, name="Matchmaking lookalike")
    original = app.config.get("MATCHMAKING_GROUP_ID")
    app.config["MATCHMAKING_GROUP_ID"] = "not-an-id"
    try:
        login(client, user)
        response = client.post(
            f"/groups/{group.id}/post", data={"post_content": "ordinary group"}
        )
        assert response.status_code == 200
        assert "MATCHMAKING_GROUP_ID is missing or malformed" in caplog.text
    finally:
        app.config["MATCHMAKING_GROUP_ID"] = original


def test_admin_profile_link_and_public_ai_labels_render(db, client):
    admin = make_user(db, super_admin=True)
    persona = make_persona(db)
    login(client, admin)
    dashboard = client.get("/admin_dashboard").get_data(as_text=True)
    assert "My Profile" in dashboard
    assert f'href="/{admin.id}"' in dashboard

    profile = client.get(f"/profile/{persona.user.public_id}").get_data(as_text=True)
    assert "AI · Automated" in profile


def test_ai_identity_name_and_avatar_share_canonical_user_fields(db, client, monkeypatch):
    from models import SiteSetting

    admin = make_user(db, super_admin=True)
    persona = make_persona(db)
    login(client, admin)
    response = client.post(
        f"/admin/ai-users/{persona.id}/display-name",
        data={"first_name": "Nova", "last_name": "Ray"},
    )
    assert response.status_code == 302
    db.session.refresh(persona)
    assert persona.name == "Nova Ray"
    assert persona.user.full_name == "Nova Ray"

    monkeypatch.setattr(
        "utils.ai_identity.cloudinary.uploader.upload",
        lambda *_args, **_kwargs: {"secure_url": "https://cdn.example/ai-avatar.webp"},
    )
    response = client.post(
        f"/admin/ai-users/{persona.id}/avatar",
        data={"profile_pic": (BytesIO(b"small-image"), "avatar.webp")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 302
    db.session.refresh(persona)
    assert persona.user.profile_pic == "https://cdn.example/ai-avatar.webp"
    assert SiteSetting.get_value(f"ai_identity_customized:{persona.id}") == "1"


def test_ai_identity_rename_rolls_back_both_names_on_commit_failure(
    db, client, monkeypatch
):
    admin = make_user(db, super_admin=True)
    persona = make_persona(db)
    original_persona_name = persona.name
    original_user_name = persona.user.full_name
    login(client, admin)

    def fail_commit():
        raise RuntimeError("simulated commit failure")

    with monkeypatch.context() as scoped:
        scoped.setattr(db.session, "commit", fail_commit)
        response = client.post(
            f"/admin/ai-users/{persona.id}/display-name",
            data={"first_name": "Rollback", "last_name": "Together"},
        )
    assert response.status_code == 302
    db.session.expire_all()
    refreshed = db.session.get(type(persona), persona.id)
    assert refreshed.name == original_persona_name
    assert refreshed.user.full_name == original_user_name


def test_feed_switch_and_forbidden_actions_are_hard_boundaries(db, monkeypatch):
    import scheduler
    from ai_controls import automation_eligibility, get_profile_config, save_profile_config

    persona = make_persona(db, forbidden_actions=["post"])
    config = get_profile_config(persona)
    config.update(
        active_days=list(range(7)),
        posting_days=list(range(7)),
        posting_start_time="00:00",
        posting_end_time="23:59",
        allow_general_feed_posts=True,
    )
    save_profile_config(persona, config)
    db.session.commit()
    assert automation_eligibility(persona, "post") == (False, "action_forbidden")

    persona.forbidden_actions = []
    config["allow_general_feed_posts"] = False
    save_profile_config(persona, config)
    db.session.commit()
    assert automation_eligibility(persona, "post") == (
        False,
        "feed_posting_disabled",
    )
    publish = monkeypatch.setattr(
        "ai_action_engine.execute_persona_post",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not post")),
    )
    assert scheduler.execute_one_feed_ai_action([persona], actions=("post",)) is False

    persona.allowed_actions = ["post", "comment"]
    persona.forbidden_actions = ["reply"]
    db.session.commit()
    assert automation_eligibility(persona, "reply") == (
        False,
        "action_forbidden",
    )


def test_allowlist_membership_and_manual_group_destination_are_explicit(db, client, monkeypatch):
    from ai_controls import get_profile_config, save_profile_config

    admin = make_user(db, super_admin=True)
    persona = make_persona(db)
    group = make_group(db, admin)
    config = get_profile_config(persona)
    config.update(
        group_activity_enabled=True,
        group_can_post=True,
        allowed_group_ids=[group.id],
        maximum_total_posts_per_week=5,
        maximum_group_posts_per_week=5,
    )
    save_profile_config(persona, config)
    db.session.commit()

    called = []
    monkeypatch.setattr(
        "ai_group_action_engine.execute_persona_group_post",
        lambda selected, destination, **kwargs: called.append(
            (selected.id, destination.id, kwargs["source"])
        ) or True,
    )
    login(client, admin)
    response = client.post(
        f"/admin/ai-users/{persona.id}/group-post",
        data={"group_id": group.id, "content": "Selected destination"},
    )
    assert response.status_code == 302
    assert called == [(persona.id, group.id, "manual")]

    response = client.post(
        f"/admin/ai-users/{persona.id}/group-membership",
        data={"group_id": group.id, "action": "add"},
    )
    assert response.status_code == 302
    assert group.members.filter_by(id=persona.user_id).first() is not None
    response = client.post(
        f"/admin/ai-users/{persona.id}/group-membership",
        data={"group_id": group.id, "action": "remove"},
    )
    assert response.status_code == 302
    assert group.members.filter_by(id=persona.user_id).first() is None
    assert group.id in get_profile_config(persona)["allowed_group_ids"]


def test_reject_draft_does_not_publish(db, client):
    from ai_controls import get_pending_draft, save_pending_draft
    from models import AILog, Post

    admin = make_user(db, super_admin=True)
    persona = make_persona(db)
    save_pending_draft(persona.id, {"content": "Do not publish", "topic": "test"})
    db.session.commit()
    login(client, admin)
    before = Post.query.filter_by(author_id=persona.user_id).count()
    response = client.post(f"/admin/ai-users/{persona.id}/draft/reject")
    assert response.status_code == 302
    assert get_pending_draft(persona.id) == {}
    assert Post.query.filter_by(author_id=persona.user_id).count() == before
    assert AILog.query.filter_by(
        persona_id=persona.id, action_type="DRAFT_REJECTED_MANUAL"
    ).count() == 1


def test_shared_post_deletion_cleans_relations_and_logs_ai_action(db, monkeypatch):
    from models import AILog, Comment, Like, Notification, Post, Reaction
    from utils.post_deletion import delete_post_safely

    admin = make_user(db, super_admin=True)
    persona = make_persona(db)
    human = make_user(db)
    post = Post(
        content="AI content",
        image="https://res.cloudinary.com/demo/image/upload/v1/kimbela/posts/item.jpg",
        author_id=persona.user_id,
    )
    db.session.add(post)
    db.session.flush()
    shared = Post(content="shared", author_id=human.id, shared_post_id=post.id)
    comment = Comment(content="reply", author_id=human.id, post_id=post.id)
    like = Like(user_id=human.id, post_id=post.id)
    reaction = Reaction(user_id=admin.id, post_id=post.id, reaction_type="love")
    notification = Notification(
        user_id=persona.user_id,
        actor_id=human.id,
        type="post_like",
        entity_id=post.id,
        entity_type="post",
        message="liked",
    )
    db.session.add_all([shared, comment, like, reaction, notification])
    db.session.commit()
    destroy = monkeypatch.setattr(
        "utils.post_deletion.cloudinary.uploader.destroy", lambda *_args, **_kwargs: None
    )

    delete_post_safely(post, admin, ai_admin_persona=persona)
    db.session.refresh(shared)
    assert db.session.get(Post, post.id) is None
    assert shared.shared_post_id is None
    assert Comment.query.filter_by(post_id=post.id).count() == 0
    assert Like.query.filter_by(post_id=post.id).count() == 0
    assert Reaction.query.filter_by(post_id=post.id).count() == 0
    assert Notification.query.filter_by(entity_id=post.id, entity_type="post").count() == 0
    assert AILog.query.filter_by(action_type="DELETE_POST_MANUAL", target_id=post.id).count() == 1


def test_shared_post_deletion_rolls_back_all_database_changes_on_failure(
    db, monkeypatch
):
    from models import Comment, Post
    from utils.post_deletion import delete_post_safely

    persona = make_persona(db)
    owner = persona.user
    post = Post(content="Keep all of this", author_id=owner.id)
    db.session.add(post)
    db.session.flush()
    comment = Comment(content="Keep reply", author_id=owner.id, post_id=post.id)
    db.session.add(comment)
    db.session.commit()
    post_id = post.id
    comment_id = comment.id

    def fail_commit():
        raise RuntimeError("simulated commit failure")

    with monkeypatch.context() as scoped:
        scoped.setattr(db.session, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="simulated commit failure"):
            delete_post_safely(post, owner)

    db.session.expire_all()
    assert db.session.get(Post, post_id) is not None
    assert db.session.get(Comment, comment_id) is not None


def test_admin_birthdays_authorization_filters_and_rollover(db, client, monkeypatch):
    from admin import admin as admin_module

    fixed_now = datetime(2026, 12, 29, 12, 0)
    monkeypatch.setattr(admin_module, "utcnow", lambda: fixed_now)
    super_admin = make_user(db, super_admin=True)
    scoped_admin = make_user(db, admin=True, permissions=["birthdays_view"])
    normal = make_user(db)
    dec = make_user(db, dob=date(1990, 12, 30))
    jan = make_user(db, dob=date(1992, 1, 2))
    make_user(db, dob=date(1988, 2, 29))
    inactive = make_user(db, dob=date(1990, 12, 31))
    inactive.is_active = False
    db.session.commit()

    login(client, normal)
    assert client.get("/admin/birthdays").status_code == 403
    login(client, scoped_admin)
    assert client.get("/admin/birthdays?filter=7").status_code == 200
    login(client, super_admin)
    html = client.get("/admin/birthdays?filter=7").get_data(as_text=True)
    assert html.index(dec.full_name) < html.index(jan.full_name)
    assert inactive.full_name not in html
    assert client.get(f"/admin/birthdays?filter=all&search={jan.email}").status_code == 200
    assert admin_module._next_birthday_date(date(1988, 2, 29), date(2027, 1, 1)) == date(2027, 2, 28)


def test_admin_birthdays_non_leap_filter_includes_february_29_user(
    db, client, monkeypatch
):
    from admin import admin as admin_module

    monkeypatch.setattr(admin_module, "utcnow", lambda: datetime(2027, 2, 27, 12, 0))
    super_admin = make_user(db, super_admin=True)
    leap_user = make_user(db, dob=date(1988, 2, 29))
    db.session.commit()
    login(client, super_admin)

    html = client.get("/admin/birthdays?filter=7").get_data(as_text=True)
    assert leap_user.full_name in html
    assert "28 Feb 2027" in html
    assert "1 day" in html


def test_only_consented_verified_active_boosts_are_featured(db):
    from models import MatchmakingPackage, MatchmakingPayments, MatchmakingRequest
    from time_utils import utcnow
    from utils.matchmaking_boosts import featured_boosts_for_viewer, set_boost_group_consent

    viewer = make_user(db)
    featured = make_user(db, dob=date(1990, 2, 2))
    legacy = make_user(db, dob=date(1991, 3, 3))
    package = MatchmakingPackage(
        name="Boost", price=10, duration_days=30, is_active=True
    )
    db.session.add(package)
    db.session.flush()

    def request_for(user, *, expired=False, consent=False):
        request_row = MatchmakingRequest(
            user_id=user.id,
            package_id=package.id,
            about_you="About this person",
            ideal_partner="Ideal match",
            status="active",
            payment_status="completed",
            end_date=utcnow() + timedelta(days=-1 if expired else 10),
        )
        db.session.add(request_row)
        db.session.flush()
        db.session.add(
            MatchmakingPayments(
                user_id=user.id,
                matchmaking_request_id=request_row.id,
                package_id=package.id,
                amount=10,
                status="completed",
                payment_status="paid",
                gateway_reference=f"boost-{uuid.uuid4().hex}",
            )
        )
        set_boost_group_consent(request_row.id, consent)
        return request_row

    request_for(featured, consent=True)
    featured_request = request_for(featured, consent=True)
    request_for(legacy, consent=False)
    request_for(make_user(db), expired=True, consent=True)
    db.session.commit()

    page = featured_boosts_for_viewer(viewer)
    assert [row.id for row in page.items] == [featured_request.id]

    blocks = viewer._blocked_users
    db.session.execute(blocks.insert().values(blocker_id=viewer.id, blocked_id=featured.id))
    db.session.commit()
    assert featured_boosts_for_viewer(viewer).items == []
