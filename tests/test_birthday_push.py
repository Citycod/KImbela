from unittest.mock import Mock
import uuid


def add_push_subscription(db, user):
    from models import PushSubscription

    subscription = PushSubscription(
        user_id=user.id,
        endpoint=f"https://push.example/birthday-{uuid.uuid4().hex}",
        p256dh="birthday-p256dh",
        auth="birthday-auth",
    )
    db.session.add(subscription)
    db.session.commit()
    return subscription


def test_successful_birthday_push_creates_annual_log(
    user, db, client, monkeypatch
):
    from models import BirthdayNotificationLog
    from scheduler import process_birthday_push

    add_push_subscription(db, user)
    push_mock = Mock(return_value=True)
    email_mock = Mock(return_value=True)
    monkeypatch.setattr("utils.push_service.send_push_notification", push_mock)
    monkeypatch.setattr("email_service.EmailService.send_birthday_email", email_mock)

    assert process_birthday_push(user, 2026) == "completed"
    assert BirthdayNotificationLog.query.filter_by(user_id=user.id, year=2026).count() == 1
    push_mock.assert_called_once()
    assert push_mock.call_args.args[1]["url"] == "/user_dashboard"
    assert push_mock.call_args.args[1]["event_type"] == "birthday"
    assert client.get(push_mock.call_args.args[1]["url"]).status_code != 404
    email_mock.assert_called_once_with(user)


def test_transient_birthday_failure_retries_and_successful_retry_completes(
    user, db, monkeypatch
):
    from models import BirthdayNotificationLog
    from scheduler import process_birthday_push

    add_push_subscription(db, user)
    push_mock = Mock(side_effect=[False, True])
    email_mock = Mock(return_value=True)
    monkeypatch.setattr("utils.push_service.send_push_notification", push_mock)
    monkeypatch.setattr("email_service.EmailService.send_birthday_email", email_mock)

    assert process_birthday_push(user, 2026) == "retry"
    assert BirthdayNotificationLog.query.filter_by(user_id=user.id, year=2026).count() == 0
    email_mock.assert_not_called()

    assert process_birthday_push(user, 2026) == "completed"
    assert push_mock.call_count == 2
    assert BirthdayNotificationLog.query.filter_by(user_id=user.id, year=2026).count() == 1
    email_mock.assert_called_once_with(user)


def test_same_year_birthday_completion_is_deduplicated(user, db, monkeypatch):
    from models import BirthdayNotificationLog
    from scheduler import process_birthday_push

    add_push_subscription(db, user)
    push_mock = Mock(return_value=True)
    monkeypatch.setattr("utils.push_service.send_push_notification", push_mock)
    monkeypatch.setattr(
        "email_service.EmailService.send_birthday_email",
        Mock(return_value=True),
    )

    assert process_birthday_push(user, 2026) == "completed"
    assert process_birthday_push(user, 2026) == "already_completed"
    assert push_mock.call_count == 1
    assert BirthdayNotificationLog.query.filter_by(user_id=user.id, year=2026).count() == 1


def test_birthday_is_eligible_again_next_year(user, db, monkeypatch):
    from models import BirthdayNotificationLog
    from scheduler import process_birthday_push

    add_push_subscription(db, user)
    push_mock = Mock(return_value=True)
    monkeypatch.setattr("utils.push_service.send_push_notification", push_mock)
    monkeypatch.setattr(
        "email_service.EmailService.send_birthday_email",
        Mock(return_value=True),
    )

    assert process_birthday_push(user, 2026) == "completed"
    assert process_birthday_push(user, 2027) == "completed"
    assert push_mock.call_count == 2
    assert BirthdayNotificationLog.query.filter_by(user_id=user.id).count() == 2


def test_no_subscription_keeps_email_fallback_and_annual_completion(
    user, db, monkeypatch
):
    from models import BirthdayNotificationLog
    from scheduler import process_birthday_push

    push_mock = Mock(return_value=False)
    email_mock = Mock(return_value=True)
    monkeypatch.setattr("utils.push_service.send_push_notification", push_mock)
    monkeypatch.setattr("email_service.EmailService.send_birthday_email", email_mock)

    assert process_birthday_push(user, 2026) == "completed"
    assert BirthdayNotificationLog.query.filter_by(user_id=user.id, year=2026).count() == 1
    push_mock.assert_called_once()
    email_mock.assert_called_once_with(user)
