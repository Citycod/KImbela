from datetime import date, timedelta
import uuid


def create_user(db, label):
    from models import User

    token = uuid.uuid4().hex[:10]
    account = User(
        first_name=label,
        last_name="Notifications",
        email=f"notification-{label.lower()}-{token}@example.test",
        phone_number=f"+2349{uuid.uuid4().int % 10**9:09d}",
        dob=date(1990, 1, 1),
        gender="Other",
        city="Lagos",
        state="Lagos",
        country="Nigeria",
        marital_status="Single",
        is_active=True,
    )
    account.set_password("StrongPassw0rd!")
    db.session.add(account)
    db.session.flush()
    return account


def login_user(client, account):
    from flask import g

    with client.session_transaction() as session:
        session.clear()
        session["_user_id"] = str(account.id)
        session["_fresh"] = True
    g.pop("_login_user", None)


def create_group(db, creator, *members, private=False):
    from models import Group

    group = Group(
        name=f"Notification Group {uuid.uuid4().hex[:8]}",
        description="Notification correctness",
        category="social",
        created_by=creator.id,
        is_private=private,
        is_active=True,
    )
    db.session.add(group)
    group.members.append(creator)
    for member in members:
        group.members.append(member)
    db.session.flush()
    return group


def create_group_post(db, author, group, content):
    from models import Post

    post = Post(content=content, author_id=author.id, group_id=group.id)
    db.session.add(post)
    db.session.flush()
    return post


def create_notification(db, recipient, actor, *, post=None, message="Activity"):
    from models import Notification, NotificationType

    notification = Notification(
        user_id=recipient.id,
        actor_id=actor.id,
        type=NotificationType.NEW_POST,
        entity_id=post.id if post else None,
        entity_type="group_post" if post else None,
        message=message,
        is_read=False,
    )
    db.session.add(notification)
    db.session.commit()
    return notification


def test_opening_notification_center_persists_read_state_and_clears_badge(
    client, user, db
):
    actor = create_user(db, "CenterActor")
    notification = create_notification(db, user, actor)
    login_user(client, user)

    assert client.get("/notifications/count").get_json()["count"] == 1
    response = client.get("/notifications")

    assert response.status_code == 200
    assert [item["id"] for item in response.get_json()] == [notification.id]
    assert client.get("/notifications/count").get_json()["count"] == 0
    assert client.get("/notifications/count").get_json()["count"] == 0


def test_unread_badge_does_not_silently_drop_older_unread_rows(client, user, db):
    from time_utils import utcnow

    actor = create_user(db, "OlderUnreadActor")
    notification = create_notification(db, user, actor, message="Still unread")
    notification.created_at = utcnow() - timedelta(days=45)
    db.session.commit()
    login_user(client, user)

    assert client.get("/notifications/count").get_json()["count"] == 1


def test_mark_all_read_is_scoped_to_current_user(client, user, db):
    from models import Notification

    actor = create_user(db, "MarkAllActor")
    other = create_user(db, "MarkAllOther")
    own = create_notification(db, user, actor, message="Mine")
    other_notification = create_notification(db, other, actor, message="Theirs")
    login_user(client, user)

    response = client.post("/notifications/read")

    assert response.status_code == 200
    assert db.session.get(Notification, own.id).is_read is True
    assert db.session.get(Notification, other_notification.id).is_read is False


def test_notification_deep_link_marks_only_its_owner_notification_read(
    client, user, db
):
    from models import Notification

    actor = create_user(db, "DeepLinkActor")
    other = create_user(db, "DeepLinkOther")
    group = create_group(db, actor, user)
    post = create_group_post(db, actor, group, "Deep-link target")
    own = create_notification(db, user, actor, post=post, message="Own target")
    other_notification = create_notification(
        db, other, actor, post=post, message="Other target"
    )
    login_user(client, user)

    response = client.get(
        f"/groups/{group.id}?notification=1&focus_post={post.id}"
        f"&notification_id={own.id}#post-{post.id}"
    )
    assert response.status_code == 200
    assert db.session.get(Notification, own.id).is_read is True

    client.get(
        f"/groups/{group.id}?notification=1&focus_post={post.id}"
        f"&notification_id={other_notification.id}#post-{post.id}"
    )
    assert db.session.get(Notification, other_notification.id).is_read is False


def test_group_notification_page_is_filtered_authorized_and_marks_displayed_read(
    client, user, db
):
    from models import Comment, Notification, NotificationType

    actor = create_user(db, "GroupPageActor")
    group_a = create_group(db, actor, user)
    group_b = create_group(db, actor, user)
    post_a = create_group_post(db, actor, group_a, "Only group A")
    post_b = create_group_post(db, actor, group_b, "Only group B")
    notification_a = create_notification(
        db, user, actor, post=post_a, message="Visible group A notification"
    )
    notification_b = create_notification(
        db, user, actor, post=post_b, message="Hidden group B notification"
    )
    comment = Comment(content="Exact comment", author_id=actor.id, post_id=post_a.id)
    db.session.add(comment)
    db.session.flush()
    comment_notification = Notification(
        user_id=user.id,
        actor_id=actor.id,
        type=NotificationType.NEW_COMMENT,
        entity_id=comment.id,
        entity_type=f"group_comment:{post_a.id}",
        message="Exact group A comment",
        is_read=False,
    )
    db.session.add(comment_notification)
    db.session.commit()
    login_user(client, user)

    response = client.get(f"/groups/{group_a.id}/notifications")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Visible group A notification" in body
    assert "Exact group A comment" in body
    assert "Hidden group B notification" not in body
    assert (
        f"focus_post={post_a.id}&amp;focus_comment={comment.id}"
        f"&amp;notification_id={comment_notification.id}#comment-{comment.id}"
    ) in body
    assert db.session.get(Notification, notification_a.id).is_read is True
    assert db.session.get(Notification, comment_notification.id).is_read is True
    assert db.session.get(Notification, notification_b.id).is_read is False


def test_group_notification_page_rejects_nonmembers_and_protects_matchmaking(
    client, db, app, monkeypatch
):
    member = create_user(db, "PrivateMember")
    outsider = create_user(db, "PrivateOutsider")
    private_group = create_group(db, member, private=True)
    matchmaking = create_group(db, member, private=True)
    db.session.commit()
    monkeypatch.setitem(app.config, "MATCHMAKING_GROUP_ID", str(matchmaking.id))
    login_user(client, outsider)

    assert client.get(f"/groups/{private_group.id}/notifications").status_code == 403
    assert client.get(f"/groups/{matchmaking.id}/notifications").status_code == 403

    login_user(client, member)
    assert client.get(f"/groups/{private_group.id}/notifications").status_code == 200
    assert client.get(f"/groups/{matchmaking.id}/notifications").status_code == 200


def test_group_notification_page_is_paginated(client, user, db):
    actor = create_user(db, "PaginationActor")
    group = create_group(db, actor, user)
    for index in range(21):
        post = create_group_post(db, actor, group, f"Post {index}")
        create_notification(
            db,
            user,
            actor,
            post=post,
            message=f"Group notification {index}",
        )
    login_user(client, user)

    first = client.get(f"/groups/{group.id}/notifications")
    second = client.get(f"/groups/{group.id}/notifications?page=2")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.get_data(as_text=True).count("notification_id=") == 20
    assert second.get_data(as_text=True).count("notification_id=") == 1
