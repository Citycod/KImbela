from datetime import date
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


def test_http_send_does_not_push_online_recipient(
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
    push_mock.assert_not_called()


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
