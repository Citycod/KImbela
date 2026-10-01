from unittest.mock import Mock
import uuid
from datetime import date, datetime
from contextlib import contextmanager

import pytz


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


def test_birthday_email_and_push_success_create_annual_log(
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


def test_email_success_and_push_transient_failure_retry_both_channels(
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
    email_mock.assert_called_once_with(user)

    assert process_birthday_push(user, 2026) == "completed"
    assert push_mock.call_count == 2
    assert BirthdayNotificationLog.query.filter_by(user_id=user.id, year=2026).count() == 1
    assert email_mock.call_count == 2


def test_push_success_and_email_failure_retry_both_channels(
    user, db, monkeypatch
):
    from models import BirthdayNotificationLog
    from scheduler import process_birthday_push

    add_push_subscription(db, user)
    push_mock = Mock(return_value=True)
    email_mock = Mock(side_effect=[False, True])
    monkeypatch.setattr("utils.push_service.send_push_notification", push_mock)
    monkeypatch.setattr("email_service.EmailService.send_birthday_email", email_mock)

    assert process_birthday_push(user, 2026) == "retry"
    push_mock.assert_called_once()
    email_mock.assert_called_once_with(user)
    assert BirthdayNotificationLog.query.filter_by(user_id=user.id, year=2026).count() == 0

    assert process_birthday_push(user, 2026) == "completed"
    assert push_mock.call_count == 2
    assert email_mock.call_count == 2
    assert BirthdayNotificationLog.query.filter_by(user_id=user.id, year=2026).count() == 1


def test_same_year_birthday_completion_is_deduplicated(user, db, monkeypatch):
    from models import BirthdayNotificationLog
    from scheduler import process_birthday_push

    add_push_subscription(db, user)
    push_mock = Mock(return_value=True)
    monkeypatch.setattr("utils.push_service.send_push_notification", push_mock)
    email_mock = Mock(return_value=True)
    monkeypatch.setattr("email_service.EmailService.send_birthday_email", email_mock)

    assert process_birthday_push(user, 2026) == "completed"
    assert process_birthday_push(user, 2026) == "already_completed"
    assert push_mock.call_count == 1
    assert email_mock.call_count == 1
    assert BirthdayNotificationLog.query.filter_by(user_id=user.id, year=2026).count() == 1


def test_birthday_delivery_skips_when_another_scheduler_holds_lock(
    user,
    db,
    monkeypatch,
):
    from models import BirthdayNotificationLog
    from scheduler import process_birthday_push

    @contextmanager
    def unavailable_lock(_user_id, _year):
        yield False

    push_mock = Mock(return_value=True)
    monkeypatch.setattr("scheduler.birthday_delivery_lock", unavailable_lock)
    monkeypatch.setattr("utils.push_service.send_push_notification", push_mock)

    assert process_birthday_push(user, 2026) == "already_processing"
    push_mock.assert_not_called()
    assert BirthdayNotificationLog.query.filter_by(user_id=user.id, year=2026).count() == 0


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
    push_mock.assert_not_called()
    email_mock.assert_called_once_with(user)


def test_birthday_delivery_due_uses_active_state_dob_and_local_timezone(user):
    from scheduler import birthday_delivery_due

    user.dob = date(1990, 6, 15)
    user.timezone = "Africa/Lagos"
    user.is_active = True
    assert birthday_delivery_due(
        user,
        datetime(2026, 6, 15, 8, 0, tzinfo=pytz.UTC),
    ) == 2026
    assert birthday_delivery_due(
        user,
        datetime(2026, 6, 15, 7, 59, tzinfo=pytz.UTC),
    ) is None

    user.is_active = False
    assert birthday_delivery_due(
        user,
        datetime(2026, 6, 15, 9, 0, tzinfo=pytz.UTC),
    ) is None
    user.is_active = True
    user.dob = None
    assert birthday_delivery_due(
        user,
        datetime(2026, 6, 15, 9, 0, tzinfo=pytz.UTC),
    ) is None


def test_birthday_delivery_due_handles_nonbirthday_and_invalid_timezone(user):
    from scheduler import birthday_delivery_due

    user.dob = date(1990, 6, 15)
    user.timezone = "Invalid/Timezone"
    user.is_active = True
    assert birthday_delivery_due(
        user,
        datetime(2026, 6, 14, 12, 0, tzinfo=pytz.UTC),
    ) is None
    assert birthday_delivery_due(
        user,
        datetime(2026, 6, 15, 9, 0, tzinfo=pytz.UTC),
    ) == 2026


def test_inactive_birthday_user_skips_both_delivery_channels(user, monkeypatch):
    from scheduler import process_due_birthday_delivery

    user.dob = date(1990, 6, 15)
    user.is_active = False
    process_mock = Mock()
    monkeypatch.setattr("scheduler.process_birthday_push", process_mock)

    result = process_due_birthday_delivery(
        user,
        datetime(2026, 6, 15, 9, 0, tzinfo=pytz.UTC),
    )

    assert result == "not_due"
    process_mock.assert_not_called()


def test_non_birthday_user_skips_both_delivery_channels(user, monkeypatch):
    from scheduler import process_due_birthday_delivery

    user.dob = date(1990, 6, 15)
    user.is_active = True
    process_mock = Mock()
    monkeypatch.setattr("scheduler.process_birthday_push", process_mock)

    result = process_due_birthday_delivery(
        user,
        datetime(2026, 6, 14, 9, 0, tzinfo=pytz.UTC),
    )

    assert result == "not_due"
    process_mock.assert_not_called()


def test_missing_dob_skips_both_delivery_channels(user, monkeypatch):
    from scheduler import process_due_birthday_delivery

    user.dob = None
    user.is_active = True
    process_mock = Mock()
    monkeypatch.setattr("scheduler.process_birthday_push", process_mock)

    result = process_due_birthday_delivery(
        user,
        datetime(2026, 6, 15, 9, 0, tzinfo=pytz.UTC),
    )

    assert result == "not_due"
    process_mock.assert_not_called()
