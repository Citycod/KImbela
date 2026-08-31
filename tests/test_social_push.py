from datetime import date
from unittest.mock import Mock
import uuid


def create_user(db, label):
    from models import User

    unique = uuid.uuid4().hex[:10]
    user = User(
        first_name=label,
        last_name="Social",
        email=f"social-{label.lower()}-{unique}@example.test",
        phone_number=f"+2348{unique}",
        dob=date(1990, 1, 1),
        gender="Other",
        city="Lagos",
        country="Nigeria",
        state="Lagos",
        marital_status="Single",
        is_active=True,
    )
    user.set_password("StrongPassw0rd!")
    db.session.add(user)
    db.session.flush()
    return user


def login_user(client, user):
    with client.session_transaction() as session:
        session.clear()
        session["_user_id"] = str(user.id)
        session["_fresh"] = True


def notification_payload_for(client, user):
    from flask_login import login_user as flask_login_user
    from users.user import get_notifications

    with client.application.test_request_context("/notifications"):
        flask_login_user(user)
        return get_notifications().get_json()


def create_post(db, author, *, group=None, content="Social post"):
    from models import Post

    post = Post(
        content=content,
        author_id=author.id,
        group_id=group.id if group else None,
    )
    db.session.add(post)
    db.session.commit()
    return post


def create_group(db, creator, *members):
    from models import Group

    group = Group(
        name=f"Social Group {uuid.uuid4().hex[:8]}",
        description="Push test group",
        category="social",
        created_by=creator.id,
        is_active=True,
    )
    db.session.add(group)
    group.members.append(creator)
    for member in members:
        group.members.append(member)
    db.session.commit()
    return group


def test_feed_comment_pushes_post_owner_with_valid_post_destination(
    client, user, db, monkeypatch
):
    from models import Comment, Notification

    owner = create_user(db, "Owner")
    post = create_post(db, owner)
    login_user(client, user)
    push_mock = Mock(return_value=True)
    monkeypatch.setattr("utils.push_service.send_push_notification", push_mock)

    response = client.post(
        f"/add_comment/{post.id}",
        json={"content": "A useful comment"},
    )

    assert response.status_code == 200
    comment_id = response.get_json()["comment"]["id"]
    assert db.session.get(Comment, comment_id) is not None
    assert Notification.query.filter_by(
        user_id=owner.id,
        actor_id=user.id,
        entity_id=comment_id,
        entity_type=f"comment:{post.id}",
    ).count() == 1
    push_mock.assert_called_once_with(
        owner.id,
        {
            "title": "New Chime",
            "body": f"{user.full_name} chimed on your post.",
            "url": f"/post/{post.public_id}?notification=1#comment-{comment_id}",
            "avatar": user.profile_pic,
            "event_type": "chime",
            "tag": f"social-post-{post.id}-chime-{comment_id}",
            "renotify": True,
        },
    )
    assert client.get(push_mock.call_args.args[1]["url"]).status_code == 200
    notification_payload = notification_payload_for(client, owner)
    assert notification_payload[0]["url"] == f"/post/{post.public_id}?notification=1#comment-{comment_id}"


def test_deleted_feed_comment_notification_falls_back_to_parent_post(
    client, user, db, monkeypatch
):
    from models import Comment

    owner = create_user(db, "DeletedCommentOwner")
    post = create_post(db, owner)
    login_user(client, user)
    monkeypatch.setattr(
        "utils.push_service.send_push_notification",
        Mock(return_value=True),
    )
    response = client.post(
        f"/add_comment/{post.id}",
        json={"content": "Soon deleted"},
    )
    comment_id = response.get_json()["comment"]["id"]
    db.session.delete(db.session.get(Comment, comment_id))
    db.session.commit()

    notification_payload = notification_payload_for(client, owner)

    assert notification_payload[0]["url"] == f"/post/{post.public_id}?notification=1#post-{post.id}"


def test_deleted_notification_parent_falls_back_without_changing_normal_404s(
    client, user, db, monkeypatch
):
    owner = create_user(db, "DeletedParentOwner")
    post = create_post(db, owner)
    login_user(client, user)
    push_mock = Mock(return_value=True)
    monkeypatch.setattr("utils.push_service.send_push_notification", push_mock)
    response = client.post(
        f"/add_comment/{post.id}",
        json={"content": "Parent will be deleted"},
    )
    assert response.status_code == 200
    notification_url = push_mock.call_args.args[1]["url"]
    db.session.delete(post)
    db.session.commit()

    fallback = client.get(notification_url.split("#", 1)[0], follow_redirects=False)

    assert fallback.status_code == 302
    assert fallback.headers["Location"].endswith("/user_dashboard")
    assert client.get("/post/not-a-real-post").status_code == 404


def test_deleted_group_notification_target_falls_back_safely(client, user):
    login_user(client, user)

    fallback = client.get(
        "/groups/2147483647?notification=1",
        follow_redirects=False,
    )

    assert fallback.status_code == 302
    assert fallback.headers["Location"].endswith("/user_dashboard")
    assert client.get("/groups/2147483647").status_code == 404


def test_own_feed_comment_does_not_notify_actor(client, user, db, monkeypatch):
    from models import Notification

    post = create_post(db, user)
    login_user(client, user)
    push_mock = Mock()
    monkeypatch.setattr("utils.push_service.send_push_notification", push_mock)

    response = client.post(
        f"/add_comment/{post.id}",
        json={"content": "My own comment"},
    )

    assert response.status_code == 200
    push_mock.assert_not_called()
    assert Notification.query.filter_by(
        user_id=user.id,
        actor_id=user.id,
        entity_id=post.id,
    ).count() == 0


def test_feed_reply_notifies_parent_author_and_deduplicates_post_owner(
    client, user, db, monkeypatch
):
    from models import Comment, Notification

    owner = create_user(db, "ReplyOwner")
    post = create_post(db, owner)
    parent = Comment(content="Parent", author_id=owner.id, post_id=post.id)
    db.session.add(parent)
    db.session.commit()
    login_user(client, user)
    push_mock = Mock(return_value=True)
    monkeypatch.setattr("utils.push_service.send_push_notification", push_mock)

    response = client.post(
        f"/add_comment/{post.id}",
        json={"content": "A reply", "parent_id": parent.id},
    )

    assert response.status_code == 200
    reply_id = response.get_json()["comment"]["id"]
    assert response.get_json()["comment"]["parent_id"] == parent.id
    push_mock.assert_called_once()
    assert push_mock.call_args.args[0] == owner.id
    assert push_mock.call_args.args[1] == {
        "title": "New Chime reply",
        "body": f"{user.full_name} replied to your Chime.",
        "url": f"/post/{post.public_id}?notification=1#comment-{reply_id}",
        "avatar": user.profile_pic,
        "event_type": "reply",
        "tag": f"social-post-{post.id}-chime-{reply_id}",
        "renotify": True,
    }
    assert Notification.query.filter_by(
        user_id=owner.id,
        actor_id=user.id,
        entity_id=reply_id,
        entity_type=f"comment:{post.id}",
    ).count() == 1


def test_feed_push_failure_does_not_fail_comment_persistence(
    client, user, db, monkeypatch
):
    from models import Comment

    owner = create_user(db, "FailureOwner")
    post = create_post(db, owner)
    login_user(client, user)
    monkeypatch.setattr(
        "utils.push_service.send_push_notification",
        Mock(side_effect=RuntimeError("provider unavailable")),
    )

    response = client.post(
        f"/add_comment/{post.id}",
        json={"content": "Persist despite push failure"},
    )

    assert response.status_code == 200
    comment_id = response.get_json()["comment"]["id"]
    assert db.session.get(Comment, comment_id) is not None


def test_blocked_feed_recipient_gets_no_social_notification(
    client, user, db, monkeypatch
):
    from models import Notification, User

    owner = create_user(db, "BlockedOwner")
    post = create_post(db, owner)
    db.session.execute(
        User._blocked_users.insert().values(
            blocker_id=owner.id,
            blocked_id=user.id,
        )
    )
    db.session.commit()
    login_user(client, user)
    push_mock = Mock()
    monkeypatch.setattr("utils.push_service.send_push_notification", push_mock)

    response = client.post(
        f"/add_comment/{post.id}",
        json={"content": "Blocked interaction"},
    )

    assert response.status_code == 200
    push_mock.assert_not_called()
    assert Notification.query.filter_by(
        user_id=owner.id,
        actor_id=user.id,
        entity_type=f"comment:{post.id}",
    ).count() == 0


def test_group_post_bulk_push_excludes_actor_left_and_blocked_members(
    client, user, db, monkeypatch
):
    from models import Notification, User

    eligible = create_user(db, "Eligible")
    left_member = create_user(db, "Left")
    blocked_member = create_user(db, "Blocked")
    group = create_group(db, user, eligible, left_member, blocked_member)
    group.members.remove(left_member)
    db.session.execute(
        User._blocked_users.insert().values(
            blocker_id=blocked_member.id,
            blocked_id=user.id,
        )
    )
    db.session.commit()
    login_user(client, user)
    bulk_push_mock = Mock(return_value=True)
    monkeypatch.setattr(
        "utils.push_service.send_push_notifications",
        bulk_push_mock,
    )

    response = client.post(
        f"/groups/{group.id}/post",
        data={"post_content": "A group update"},
    )

    assert response.status_code == 200
    post_id = response.get_json()["post_id"]
    bulk_push_mock.assert_called_once_with(
        {eligible.id},
        {
            "title": "New group post",
            "body": f"{user.full_name} posted in {group.name}.",
            "url": f"/groups/{group.id}?notification=1#post-{post_id}",
            "avatar": user.profile_pic,
            "event_type": "group_post",
            "tag": f"social-group-{group.id}-post-{post_id}",
            "renotify": True,
        },
    )
    assert client.get(bulk_push_mock.call_args.args[1]["url"].split("#", 1)[0]).status_code == 200
    assert Notification.query.filter_by(entity_id=post_id, entity_type="group_post").count() == 1
    assert Notification.query.filter_by(
        user_id=eligible.id,
        entity_id=post_id,
    ).count() == 1


def test_group_comment_only_pushes_post_owner(client, user, db, monkeypatch):
    from models import Notification

    owner = create_user(db, "GroupOwner")
    other_member = create_user(db, "OtherMember")
    group = create_group(db, owner, user, other_member)
    post = create_post(db, owner, group=group)
    login_user(client, user)
    push_mock = Mock(return_value=True)
    bulk_push_mock = Mock()
    monkeypatch.setattr("utils.push_service.send_push_notification", push_mock)
    monkeypatch.setattr("utils.push_service.send_push_notifications", bulk_push_mock)

    response = client.post(
        f"/add_comment/{post.id}",
        json={"content": "Group comment"},
    )

    assert response.status_code == 200
    comment_id = response.get_json()["comment"]["id"]
    push_mock.assert_called_once_with(
        owner.id,
        {
            "title": "New group Chime",
            "body": f"{user.full_name} chimed on your group post.",
            "url": f"/groups/{group.id}?notification=1#comment-{comment_id}",
            "avatar": user.profile_pic,
            "event_type": "chime",
            "tag": f"social-post-{post.id}-chime-{comment_id}",
            "renotify": True,
        },
    )
    assert client.get(push_mock.call_args.args[1]["url"].split("#", 1)[0]).status_code == 200
    bulk_push_mock.assert_not_called()
    assert Notification.query.filter_by(
        user_id=owner.id,
        entity_id=comment_id,
        entity_type=f"group_comment:{post.id}",
    ).count() == 1
    notification_payload = notification_payload_for(client, owner)
    assert notification_payload[0]["url"] == f"/groups/{group.id}?notification=1#comment-{comment_id}"


def test_group_reply_deduplicates_owner_and_parent_author(
    client, user, db, monkeypatch
):
    from models import Comment, Notification

    owner = create_user(db, "GroupReplyOwner")
    group = create_group(db, owner, user)
    post = create_post(db, owner, group=group)
    parent = Comment(content="Group parent", author_id=owner.id, post_id=post.id)
    db.session.add(parent)
    db.session.commit()
    login_user(client, user)
    push_mock = Mock(return_value=True)
    monkeypatch.setattr("utils.push_service.send_push_notification", push_mock)

    response = client.post(
        f"/add_comment/{post.id}",
        json={"content": "Group reply", "parent_id": parent.id},
    )

    assert response.status_code == 200
    reply_id = response.get_json()["comment"]["id"]
    push_mock.assert_called_once_with(
        owner.id,
        {
            "title": "New group Chime reply",
            "body": f"{user.full_name} replied to your group Chime.",
            "url": f"/groups/{group.id}?notification=1#comment-{reply_id}",
            "avatar": user.profile_pic,
            "event_type": "reply",
            "tag": f"social-post-{post.id}-chime-{reply_id}",
            "renotify": True,
        },
    )
    assert Notification.query.filter_by(
        user_id=owner.id,
        entity_id=reply_id,
        entity_type=f"group_comment:{post.id}",
    ).count() == 1


def test_feed_like_creates_one_notification_and_canonical_push(
    client, user, db, monkeypatch
):
    from models import Notification, NotificationType

    owner = create_user(db, "LikeOwner")
    post = create_post(db, owner)
    login_user(client, user)
    push_mock = Mock(return_value=True)
    monkeypatch.setattr("utils.push_service.send_push_notification", push_mock)

    response = client.post(
        f"/react_post/{post.id}",
        json={"reaction_type": "like"},
    )

    assert response.status_code == 200
    assert response.get_json()["reacted"] is True
    notification = Notification.query.filter_by(
        user_id=owner.id,
        actor_id=user.id,
        type=NotificationType.POST_LIKE,
        entity_id=post.id,
        entity_type="post",
    ).one()
    expected_url = f"/post/{post.public_id}?notification=1"
    push_mock.assert_called_once_with(
        owner.id,
        {
            "title": "New like",
            "body": f"{user.full_name} liked your post.",
            "url": expected_url,
            "avatar": user.profile_pic,
            "event_type": "like",
            "tag": f"social-like-{post.id}-{user.id}",
            "renotify": True,
        },
    )
    bell_payload = notification_payload_for(client, owner)
    bell_item = next(item for item in bell_payload if item["id"] == notification.id)
    assert bell_item["url"] == expected_url
    login_user(client, owner)
    routed_bell_payload = client.get("/notifications").get_json()
    routed_bell_item = next(
        item for item in routed_bell_payload if item["id"] == notification.id
    )
    assert routed_bell_item["url"] == expected_url


def test_group_like_uses_group_content_destination(client, user, db, monkeypatch):
    owner = create_user(db, "GroupLikeOwner")
    group = create_group(db, owner, user)
    post = create_post(db, owner, group=group)
    login_user(client, user)
    push_mock = Mock(return_value=True)
    monkeypatch.setattr("utils.push_service.send_push_notification", push_mock)

    response = client.post(
        f"/react_post/{post.id}",
        json={"reaction_type": "love"},
    )

    assert response.status_code == 200
    expected_url = f"/groups/{group.id}?notification=1#post-{post.id}"
    assert push_mock.call_args.args[1]["url"] == expected_url
    assert notification_payload_for(client, owner)[0]["url"] == expected_url


def test_own_post_like_does_not_notify(client, user, db, monkeypatch):
    from models import Notification, NotificationType

    post = create_post(db, user)
    login_user(client, user)
    push_mock = Mock()
    monkeypatch.setattr("utils.push_service.send_push_notification", push_mock)

    response = client.post(
        f"/react_post/{post.id}",
        json={"reaction_type": "like"},
    )

    assert response.status_code == 200
    assert Notification.query.filter_by(
        user_id=user.id,
        actor_id=user.id,
        type=NotificationType.POST_LIKE,
        entity_id=post.id,
    ).count() == 0
    push_mock.assert_not_called()


def test_unlike_and_relike_do_not_spam_notifications(client, user, db, monkeypatch):
    from models import Notification, NotificationType

    owner = create_user(db, "RelikeOwner")
    post = create_post(db, owner)
    login_user(client, user)
    push_mock = Mock(return_value=True)
    monkeypatch.setattr("utils.push_service.send_push_notification", push_mock)

    results = [
        client.post(f"/react_post/{post.id}", json={"reaction_type": "like"})
        for _ in range(3)
    ]

    assert [response.get_json()["reacted"] for response in results] == [True, False, True]
    assert Notification.query.filter_by(
        user_id=owner.id,
        actor_id=user.id,
        type=NotificationType.POST_LIKE,
        entity_id=post.id,
    ).count() == 1
    push_mock.assert_called_once()


def test_like_push_failure_does_not_roll_back_reaction(
    client, user, db, monkeypatch
):
    from models import Reaction

    owner = create_user(db, "LikePushFailureOwner")
    post = create_post(db, owner)
    login_user(client, user)
    monkeypatch.setattr(
        "utils.push_service.send_push_notification",
        Mock(side_effect=RuntimeError("push unavailable")),
    )

    response = client.post(
        f"/react_post/{post.id}",
        json={"reaction_type": "like"},
    )

    assert response.status_code == 200
    assert Reaction.query.filter_by(user_id=user.id, post_id=post.id).count() == 1


def test_group_comment_from_nonmember_persists_without_group_push(
    client, user, db, monkeypatch
):
    from models import Comment

    owner = create_user(db, "MemberOwner")
    group = create_group(db, owner)
    post = create_post(db, owner, group=group)
    login_user(client, user)
    push_mock = Mock()
    monkeypatch.setattr("utils.push_service.send_push_notification", push_mock)

    response = client.post(
        f"/add_comment/{post.id}",
        json={"content": "Existing route still persists this"},
    )

    assert response.status_code == 200
    assert db.session.get(Comment, response.get_json()["comment"]["id"]) is not None
    push_mock.assert_not_called()


def test_group_bulk_push_delivers_to_multiple_subscriptions_only_for_recipients(
    user, db, monkeypatch
):
    from models import PushSubscription
    from utils.push_service import send_push_notifications

    outsider = create_user(db, "Outsider")
    subscriptions = [
        PushSubscription(
            user_id=user.id,
            endpoint=f"https://push.example/{uuid.uuid4().hex}",
            p256dh="recipient-key-1",
            auth="recipient-auth-1",
        ),
        PushSubscription(
            user_id=user.id,
            endpoint=f"https://push.example/{uuid.uuid4().hex}",
            p256dh="recipient-key-2",
            auth="recipient-auth-2",
        ),
        PushSubscription(
            user_id=outsider.id,
            endpoint=f"https://push.example/{uuid.uuid4().hex}",
            p256dh="outsider-key",
            auth="outsider-auth",
        ),
    ]
    db.session.add_all(subscriptions)
    db.session.commit()
    monkeypatch.setenv("VAPID_PRIVATE_KEY", "test-private-key")
    webpush_mock = Mock()
    monkeypatch.setattr("utils.push_service.webpush", webpush_mock)

    assert send_push_notifications(
        {user.id},
        {"title": "New group post", "url": "/groups/1#post-1"},
    ) is True

    assert webpush_mock.call_count == 2
    endpoints = {
        call.kwargs["subscription_info"]["endpoint"]
        for call in webpush_mock.call_args_list
    }
    assert endpoints == {subscriptions[0].endpoint, subscriptions[1].endpoint}


def test_group_push_failure_does_not_fail_persisted_post(
    client, user, db, monkeypatch
):
    from models import Post

    member = create_user(db, "FailureMember")
    group = create_group(db, user, member)
    login_user(client, user)
    monkeypatch.setattr(
        "utils.push_service.send_push_notifications",
        Mock(side_effect=RuntimeError("provider unavailable")),
    )

    response = client.post(
        f"/groups/{group.id}/post",
        data={"post_content": "Persisted group activity"},
    )

    assert response.status_code == 200
    assert db.session.get(Post, response.get_json()["post_id"]) is not None


def test_dashboard_navigation_social_icons_have_distinct_colors():
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1] / "templates" / "user_dashboard.html"
    ).read_text()

    assert 'bi-chat-left-dots text-xl text-purple-600' in source
    assert 'bi-bell text-xl text-amber-500' in source
