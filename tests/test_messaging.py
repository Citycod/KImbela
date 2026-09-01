from datetime import date
import json
from types import SimpleNamespace
from unittest.mock import Mock, call
import uuid

from pywebpush import WebPushException


def create_recipient(db, sender, *, is_online=False):
    from models import User

    unique = uuid.uuid4().hex[:10]
    recipient = User(
        first_name="Message",
        last_name="Recipient",
        email=f"recipient-{unique}@example.com",
        phone_number=f"+234{unique}",
        dob=date(1981, 2, 2),
        gender="Female",
        city="Testville",
        country="Testland",
        state="TS",
        marital_status="Single",
        is_active=True,
        is_online=is_online,
    )
    recipient.set_password("StrongPassw0rd!")
    db.session.add(recipient)
    db.session.flush()
    sender.friends.append(recipient)
    db.session.commit()
    return recipient


def login_without_sending_alert(monkeypatch, login):
    monkeypatch.setattr("authentication.authenticate.send_login_alert_email", Mock())
    return login()


def register_test_socketio_message_handler(socketio):
    from socketio_events import handle_send_message

    socketio.on_event("send_message", handle_send_message)


def test_messaging_friends_requires_login(client):
    response = client.get("/api/messaging/friends")
    assert response.status_code in (302, 401)


def test_messaging_friends_empty_after_login(client, login):
    login()
    response = client.get("/api/messaging/friends")
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["friends"] == []


def test_messaging_upload_missing_file(client, login):
    login()
    response = client.post("/api/messaging/upload", data={"to_id": 1, "type": "image"})
    assert response.status_code == 400


def test_unread_count_includes_sent_and_delivered_but_excludes_read(
    client, login, user, db, monkeypatch
):
    from models import Message

    sender = create_recipient(db, user, is_online=True)
    login_without_sending_alert(monkeypatch, login)
    db.session.add_all(
        [
            Message(sender_id=sender.id, receiver_id=user.id, content="Sent", status="sent"),
            Message(sender_id=sender.id, receiver_id=user.id, content="Delivered", status="delivered"),
            Message(sender_id=sender.id, receiver_id=user.id, content="Read", status="read"),
            Message(sender_id=user.id, receiver_id=sender.id, content="Outgoing", status="sent"),
        ]
    )
    db.session.commit()

    canonical = client.get("/api/messaging/unread-count")
    legacy = client.get("/api/messaging/unread_count")

    assert canonical.status_code == 200
    assert canonical.get_json() == {"unread_count": 2}
    assert legacy.status_code == 200
    assert legacy.get_json() == {"success": True, "unread_count": 2}


def test_mark_conversation_read_marks_sent_and_delivered_messages(
    client, login, user, db, monkeypatch
):
    from models import Message

    sender = create_recipient(db, user, is_online=True)
    login_without_sending_alert(monkeypatch, login)
    messages = [
        Message(sender_id=sender.id, receiver_id=user.id, content="Sent", status="sent"),
        Message(sender_id=sender.id, receiver_id=user.id, content="Delivered", status="delivered"),
    ]
    db.session.add_all(messages)
    db.session.commit()

    response = client.post(f"/api/messaging/mark-conversation-read/{sender.id}")

    assert response.status_code == 200
    assert response.get_json() == {"success": True, "marked": 2}
    assert [db.session.get(Message, message.id).status for message in messages] == [
        "read",
        "read",
    ]
    assert client.get("/api/messaging/unread-count").get_json() == {"unread_count": 0}


def test_http_send_persists_emits_once_and_pushes_offline_recipient(
    client, login, user, db, monkeypatch
):
    from models import Message

    recipient = create_recipient(db, user, is_online=False)
    login_without_sending_alert(monkeypatch, login)

    emit_mock = Mock()
    push_mock = Mock(return_value=True)
    monkeypatch.setattr("messages.messaging.socketio.emit", emit_mock)
    monkeypatch.setattr("utils.push_service.send_push_notification", push_mock)

    response = client.post(
        "/api/messaging/send",
        json={
            "receiver_id": recipient.id,
            "content": "HTTP message",
            "type": "text",
            "metadata": {"source": "test"},
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True

    message = db.session.get(Message, payload["message"]["id"])
    assert message is not None
    assert message.content == "HTTP message"
    assert message.message_data == {"source": "test"}
    assert message.status == "sent"
    assert emit_mock.call_args_list == [
        call("new_message", payload["message"], room=f"user_{recipient.id}"),
        call("new_message", payload["message"], room=f"user_{user.id}"),
    ]
    push_mock.assert_called_once()
    assert push_mock.call_args.args[0] == recipient.id


def test_http_send_pushes_online_recipient_without_device_conversation_mapping(
    client, login, user, db, monkeypatch
):
    recipient = create_recipient(db, user, is_online=True)
    login_without_sending_alert(monkeypatch, login)

    emit_mock = Mock()
    push_mock = Mock()
    monkeypatch.setattr("messages.messaging.socketio.emit", emit_mock)
    monkeypatch.setattr("utils.push_service.send_push_notification", push_mock)

    response = client.post(
        "/api/messaging/send",
        json={"receiver_id": recipient.id, "content": "Online message"},
    )

    assert response.status_code == 200
    assert response.get_json()["message"]["status"] == "delivered"
    assert emit_mock.call_count == 2
    push_mock.assert_called_once_with(
        recipient.id,
        {
            "title": f"New Message from {user.first_name}",
            "body": "Online message",
            "url": f"/user_dashboard?chat={user.id}",
            "avatar": user.profile_pic,
            "event_type": "message",
            "tag": f"message-{user.id}",
            "renotify": True,
        },
    )
    assert client.get(push_mock.call_args.args[1]["url"]).status_code == 200


def test_http_repeated_push_is_not_suppressed_after_recipient_connects(
    client, login, user, db, monkeypatch
):
    recipient = create_recipient(db, user, is_online=False)
    login_without_sending_alert(monkeypatch, login)

    monkeypatch.setattr("messages.messaging.socketio.emit", Mock())
    push_mock = Mock(return_value=True)
    monkeypatch.setattr("utils.push_service.send_push_notification", push_mock)

    responses = []
    responses.append(client.post(
        "/api/messaging/send",
        json={"receiver_id": recipient.id, "content": "First offline message"},
    ))

    recipient.is_online = True  # Exact persistent state written by Socket.IO connect.
    db.session.commit()

    for content in ("Second message", "Third message"):
        responses.append(client.post(
            "/api/messaging/send",
            json={"receiver_id": recipient.id, "content": content},
        ))

    assert [response.status_code for response in responses] == [200, 200, 200]
    assert push_mock.call_count == 3
    assert [call_.args[0] for call_ in push_mock.call_args_list] == [
        recipient.id,
        recipient.id,
        recipient.id,
    ]


def test_multiple_tab_presence_transitions_do_not_suppress_push(
    client, login, user, db, monkeypatch
):
    recipient = create_recipient(db, user, is_online=True)
    login_without_sending_alert(monkeypatch, login)

    monkeypatch.setattr("messages.messaging.socketio.emit", Mock())
    push_mock = Mock(return_value=True)
    monkeypatch.setattr("utils.push_service.send_push_notification", push_mock)

    first = client.post(
        "/api/messaging/send",
        json={"receiver_id": recipient.id, "content": "While a tab is connected"},
    )
    recipient.is_online = False  # One tab disconnecting can write this stale value.
    db.session.commit()
    second = client.post(
        "/api/messaging/send",
        json={"receiver_id": recipient.id, "content": "After one tab disconnects"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert push_mock.call_count == 2


def test_http_push_failure_does_not_fail_persisted_message(
    client, login, user, db, monkeypatch
):
    from models import Message

    recipient = create_recipient(db, user, is_online=False)
    login_without_sending_alert(monkeypatch, login)

    monkeypatch.setattr("messages.messaging.socketio.emit", Mock())
    push_mock = Mock(side_effect=RuntimeError("push unavailable"))
    monkeypatch.setattr("utils.push_service.send_push_notification", push_mock)

    response = client.post(
        "/api/messaging/send",
        json={"receiver_id": recipient.id, "content": "Stored before push"},
    )

    assert response.status_code == 200
    message_id = response.get_json()["message"]["id"]
    assert db.session.get(Message, message_id) is not None
    push_mock.assert_called_once()


def test_http_persistence_failure_does_not_emit_or_push(
    client, login, user, db, monkeypatch
):
    from models import Message

    recipient = create_recipient(db, user, is_online=False)
    login_without_sending_alert(monkeypatch, login)

    emit_mock = Mock()
    push_mock = Mock()
    monkeypatch.setattr("messages.messaging.socketio.emit", emit_mock)
    monkeypatch.setattr("utils.push_service.send_push_notification", push_mock)

    real_commit = db.session.commit
    monkeypatch.setattr(
        "messages.messaging.db.session.commit",
        Mock(side_effect=RuntimeError("database unavailable")),
    )
    response = client.post(
        "/api/messaging/send",
        json={"receiver_id": recipient.id, "content": "Must not persist"},
    )
    monkeypatch.setattr("messages.messaging.db.session.commit", real_commit)

    assert response.status_code == 500
    assert Message.query.filter_by(content="Must not persist").count() == 0
    emit_mock.assert_not_called()
    push_mock.assert_not_called()


def test_socketio_send_persists_emits_once_and_pushes_offline_recipient(
    app, client, login, user, db, monkeypatch
):
    from extensions import socketio
    from models import Message

    recipient = create_recipient(db, user, is_online=False)
    login_without_sending_alert(monkeypatch, login)
    register_test_socketio_message_handler(socketio)
    socket_client = socketio.test_client(app, flask_test_client=client)
    assert socket_client.is_connected()

    emit_mock = Mock()
    push_mock = Mock(return_value=True)
    monkeypatch.setattr("socketio_events.socketio.emit", emit_mock)
    monkeypatch.setattr("utils.push_service.send_push_notification", push_mock)

    socket_client.emit(
        "send_message",
        {
            "receiver_id": recipient.id,
            "content": "Socket message",
            "type": "text",
            "metadata": {"source": "socket-test"},
            "temp_id": "temp-1",
        },
    )

    message = Message.query.filter_by(content="Socket message").one()
    assert message.message_data == {"source": "socket-test"}
    assert message.status == "sent"
    emitted_payload = emit_mock.call_args_list[0].args[1]
    assert emit_mock.call_args_list == [
        call("new_message", emitted_payload, room=f"user_{recipient.id}"),
        call("new_message", emitted_payload, room=f"user_{user.id}"),
    ]
    push_mock.assert_called_once()
    assert push_mock.call_args.args[0] == recipient.id
    assert push_mock.call_args.args[1]["url"] == f"/user_dashboard?chat={user.id}"

    socket_client.disconnect()


def test_socketio_persistence_failure_does_not_emit_or_push(
    app, client, login, user, db, monkeypatch
):
    from extensions import socketio
    from models import Message

    recipient = create_recipient(db, user, is_online=False)
    login_without_sending_alert(monkeypatch, login)
    register_test_socketio_message_handler(socketio)
    socket_client = socketio.test_client(app, flask_test_client=client)
    assert socket_client.is_connected()

    emit_mock = Mock()
    push_mock = Mock()
    monkeypatch.setattr("socketio_events.socketio.emit", emit_mock)
    monkeypatch.setattr("utils.push_service.send_push_notification", push_mock)

    real_commit = db.session.commit
    monkeypatch.setattr(
        "socketio_events.db.session.commit",
        Mock(side_effect=RuntimeError("database unavailable")),
    )
    socket_client.emit(
        "send_message",
        {"receiver_id": recipient.id, "content": "Socket must not persist"},
    )
    monkeypatch.setattr("socketio_events.db.session.commit", real_commit)

    assert Message.query.filter_by(content="Socket must not persist").count() == 0
    emit_mock.assert_not_called()
    push_mock.assert_not_called()

    socket_client.disconnect()


def test_socketio_send_pushes_when_recipient_account_is_marked_online(
    app, client, login, user, db, monkeypatch
):
    from extensions import socketio

    recipient = create_recipient(db, user, is_online=True)
    login_without_sending_alert(monkeypatch, login)
    register_test_socketio_message_handler(socketio)
    socket_client = socketio.test_client(app, flask_test_client=client)
    assert socket_client.is_connected()

    monkeypatch.setattr("socketio_events.socketio.emit", Mock())
    push_mock = Mock(return_value=True)
    monkeypatch.setattr("utils.push_service.send_push_notification", push_mock)

    socket_client.emit(
        "send_message",
        {"receiver_id": recipient.id, "content": "Online Socket.IO recipient"},
    )

    push_mock.assert_called_once()
    assert push_mock.call_args.args[0] == recipient.id
    assert push_mock.call_args.args[1]["url"] == f"/user_dashboard?chat={user.id}"
    assert push_mock.call_args.args[1]["tag"] == f"message-{user.id}"
    assert push_mock.call_args.args[1]["renotify"] is True
    socket_client.disconnect()


def test_push_payload_adds_kimbela_display_metadata_and_timestamp(monkeypatch):
    from utils.push_service import prepare_push_payload

    monkeypatch.setattr("utils.push_service.time.time", lambda: 1_700_000_000.125)
    source = {
        "title": "New message",
        "body": "Hello",
        "url": "/user_dashboard?chat=13",
        "tag": "message-13",
        "renotify": True,
    }

    payload = prepare_push_payload(source)

    assert payload == {
        **source,
        "icon": "/static/img/icons/icon-192x192.png",
        "badge": "/static/img/icons/icon-192x192.png",
        "timestamp": 1_700_000_000_125,
    }
    assert "icon" not in source
    assert "timestamp" not in source


def test_birthday_payload_gets_a_stable_non_renotifying_tag():
    from utils.push_service import prepare_push_payload

    payload = prepare_push_payload({
        "title": "🎉 Happy Birthday!",
        "body": "Have a great day",
        "url": "/user_dashboard",
    })

    assert payload["tag"] == "birthday"
    assert payload["renotify"] is False
    assert payload["url"] == "/user_dashboard"


def test_expired_push_subscription_is_pruned_without_blocking_valid_subscription(
    user, db, monkeypatch
):
    from models import PushSubscription
    from utils.push_service import send_push_notification

    expired = PushSubscription(
        user_id=user.id,
        endpoint=f"https://push.example/expired-{uuid.uuid4().hex}",
        p256dh="expired-p256dh",
        auth="expired-auth",
    )
    valid = PushSubscription(
        user_id=user.id,
        endpoint=f"https://push.example/valid-{uuid.uuid4().hex}",
        p256dh="valid-p256dh",
        auth="valid-auth",
    )
    db.session.add_all([expired, valid])
    db.session.commit()
    expired_id = expired.id
    valid_id = valid.id

    monkeypatch.setenv("VAPID_PRIVATE_KEY", "test-private-key")
    called_endpoints = []

    def fake_webpush(**kwargs):
        endpoint = kwargs["subscription_info"]["endpoint"]
        called_endpoints.append(endpoint)
        if endpoint == expired.endpoint:
            response = SimpleNamespace(status_code=410, text="expired")
            raise WebPushException("subscription expired", response=response)

    monkeypatch.setattr("utils.push_service.webpush", fake_webpush)

    result = send_push_notification(user.id, {"title": "Test", "body": "Message"})

    assert result is True
    assert len(called_endpoints) == 2
    assert db.session.get(PushSubscription, expired_id) is None
    assert db.session.get(PushSubscription, valid_id) is not None


def test_invalid_push_subscription_failure_is_isolated(user, db, monkeypatch):
    from models import PushSubscription
    from utils.push_service import send_push_notification

    subscription = PushSubscription(
        user_id=user.id,
        endpoint=f"https://push.example/invalid-{uuid.uuid4().hex}",
        p256dh="invalid-p256dh",
        auth="invalid-auth",
    )
    db.session.add(subscription)
    db.session.commit()
    subscription_id = subscription.id

    monkeypatch.setenv("VAPID_PRIVATE_KEY", "test-private-key")
    webpush_mock = Mock(side_effect=ValueError("invalid subscription"))
    monkeypatch.setattr("utils.push_service.webpush", webpush_mock)

    result = send_push_notification(user.id, {"title": "Test", "body": "Message"})

    assert result is False
    webpush_mock.assert_called_once()
    assert db.session.get(PushSubscription, subscription_id) is not None


def test_three_pushes_reuse_all_device_subscriptions(user, db, monkeypatch):
    from models import PushSubscription
    from utils.push_service import send_push_notification

    subscriptions = [
        PushSubscription(
            user_id=user.id,
            endpoint=f"https://push.example/device-{device}-{uuid.uuid4().hex}",
            p256dh=f"p256dh-{device}",
            auth=f"auth-{device}",
        )
        for device in (1, 2)
    ]
    db.session.add_all(subscriptions)
    db.session.commit()
    subscription_ids = [subscription.id for subscription in subscriptions]

    monkeypatch.setenv("VAPID_PRIVATE_KEY", "test-private-key")
    webpush_mock = Mock()
    monkeypatch.setattr("utils.push_service.webpush", webpush_mock)

    results = [
        send_push_notification(
            user.id,
            {
                "title": "Test",
                "body": f"Message {number}",
                "tag": "message-thread",
                "renotify": True,
            },
        )
        for number in (1, 2, 3)
    ]

    assert results == [True, True, True]
    assert webpush_mock.call_count == 6
    sent_payloads = [json.loads(call_.kwargs["data"]) for call_ in webpush_mock.call_args_list]
    assert all(payload["tag"] == "message-thread" for payload in sent_payloads)
    assert all(payload["renotify"] is True for payload in sent_payloads)
    assert all(db.session.get(PushSubscription, sub_id) is not None for sub_id in subscription_ids)


def test_transient_provider_failure_does_not_delete_valid_subscription(
    user, db, monkeypatch
):
    from models import PushSubscription
    from utils.push_service import send_push_notification

    subscription = PushSubscription(
        user_id=user.id,
        endpoint=f"https://push.example/transient-{uuid.uuid4().hex}",
        p256dh="transient-p256dh",
        auth="transient-auth",
    )
    db.session.add(subscription)
    db.session.commit()
    subscription_id = subscription.id

    monkeypatch.setenv("VAPID_PRIVATE_KEY", "test-private-key")
    response = SimpleNamespace(status_code=503, text="temporarily unavailable")
    monkeypatch.setattr(
        "utils.push_service.webpush",
        Mock(side_effect=WebPushException("provider unavailable", response=response)),
    )

    assert send_push_notification(user.id, {"title": "Test"}) is False
    assert db.session.get(PushSubscription, subscription_id) is not None


def test_missing_vapid_configuration_fails_safely_without_provider_call(
    user, db, monkeypatch
):
    from models import PushSubscription
    from utils.push_service import send_push_notification

    db.session.add(
        PushSubscription(
            user_id=user.id,
            endpoint=f"https://push.example/{uuid.uuid4().hex}",
            p256dh="configured-p256dh",
            auth="configured-auth",
        )
    )
    db.session.commit()
    monkeypatch.delenv("VAPID_PRIVATE_KEY", raising=False)
    webpush_mock = Mock()
    monkeypatch.setattr("utils.push_service.webpush", webpush_mock)

    assert send_push_notification(user.id, {"title": "Test"}) is False
    webpush_mock.assert_not_called()


def test_push_provider_diagnostics_do_not_log_secret_endpoint_or_keys(
    user, db, monkeypatch, caplog
):
    from models import PushSubscription
    from utils.push_service import send_push_notification

    endpoint = f"https://push.example/private/{uuid.uuid4().hex}"
    subscription = PushSubscription(
        user_id=user.id,
        endpoint=endpoint,
        p256dh="secret-p256dh",
        auth="secret-auth",
    )
    db.session.add(subscription)
    db.session.commit()
    monkeypatch.setenv("VAPID_PRIVATE_KEY", "test-private-key")
    response = SimpleNamespace(status_code=403)
    monkeypatch.setattr(
        "utils.push_service.webpush",
        Mock(side_effect=WebPushException("contains provider details", response=response)),
    )

    with caplog.at_level("WARNING", logger="utils.push_service"):
        assert send_push_notification(
            user.id,
            {"title": "Test", "event_type": "message"},
        ) is False

    log_output = caplog.text
    assert "endpoint_host=push.example" in log_output
    assert "event_type=message" in log_output
    assert "provider_status=403" in log_output
    assert endpoint not in log_output
    assert "secret-p256dh" not in log_output
    assert "secret-auth" not in log_output


def test_message_push_sources_do_not_generate_stale_page_routes():
    from pathlib import Path

    project_root = Path(__file__).resolve().parents[1]
    for relative_path in (
        "messages/messaging.py",
        "socketio_events.py",
        "users/user.py",
    ):
        source = (project_root / relative_path).read_text()
        assert '"url": "/messages"' not in source
        assert '"url": f"/messages"' not in source
        assert '"url": "/dashboard"' not in source
