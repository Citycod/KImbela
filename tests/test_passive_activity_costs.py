from datetime import date, timedelta
from unittest.mock import Mock
import uuid


def authenticate(client, user):
    with client.session_transaction() as session:
        session["_user_id"] = str(user.id)
        session["_fresh"] = True


def clear_activity_logs(db):
    from models import ActivityLog

    ActivityLog.query.delete()
    db.session.commit()


def test_passive_status_routes_do_not_log_or_advance_last_seen(client, user, db):
    from models import ActivityLog
    from time_utils import utcnow

    authenticate(client, user)
    user.last_seen = utcnow() - timedelta(hours=2)
    baseline_last_seen = user.last_seen
    db.session.commit()
    clear_activity_logs(db)

    responses = [
        client.get("/notifications/count"),
        client.get("/api/messaging/unread-count"),
        client.get("/api/birthdays/today"),
        client.get("/sw.js"),
        client.get("/offline"),
    ]

    assert all(response.status_code == 200 for response in responses)
    assert ActivityLog.query.count() == 0
    db.session.refresh(user)
    assert user.last_seen == baseline_last_seen


def test_message_send_remains_a_meaningful_logged_action(
    client, user, db, monkeypatch
):
    from models import ActivityLog, User
    from time_utils import utcnow

    unique = uuid.uuid4().hex[:10]
    recipient = User(
        first_name="Logged",
        last_name="Recipient",
        email=f"logged-recipient-{unique}@example.com",
        phone_number=f"+2346{uuid.uuid4().int % 10**9:09d}",
        dob=date(1990, 1, 1),
        gender="Other",
        city="Lagos",
        country="Nigeria",
        state="Lagos",
        marital_status="Single",
        is_active=True,
    )
    recipient.set_password("StrongPassw0rd!")
    db.session.add(recipient)
    db.session.flush()
    user.friends.append(recipient)
    user.last_seen = utcnow() - timedelta(hours=2)
    old_last_seen = user.last_seen
    db.session.commit()
    authenticate(client, user)
    clear_activity_logs(db)
    monkeypatch.setattr("messages.messaging.socketio.emit", Mock())
    monkeypatch.setattr("utils.push_service.send_push_notification", Mock())

    response = client.post(
        "/api/messaging/send",
        json={"receiver_id": recipient.id, "content": "Meaningful action"},
    )

    assert response.status_code == 200
    logged = ActivityLog.query.filter_by(
        path="/api/messaging/send",
        method="POST",
        user_id=user.id,
    ).one()
    assert logged.event_type == "api"
    db.session.refresh(user)
    assert user.last_seen > old_last_seen


def test_anonymous_404_is_not_written_to_activity_log(client, db):
    from models import ActivityLog

    with client.session_transaction() as session:
        session.clear()
    clear_activity_logs(db)

    response = client.get("/definitely-not-a-kimbela-route")

    assert response.status_code == 404
    assert ActivityLog.query.count() == 0
