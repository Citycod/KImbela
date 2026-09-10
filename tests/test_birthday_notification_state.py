from datetime import date
import uuid

from models import BirthdayNotification, User


def _birthday_user(db):
    today = date.today()
    token = uuid.uuid4().hex[:10]
    account = User(
        first_name="Birthday",
        last_name="Friend",
        email=f"birthday-state-{token}@example.com",
        phone_number=f"+2347{uuid.uuid4().int % 10**9:09d}",
        dob=date(1990, today.month, today.day),
        gender="Female",
        city="Lagos",
        state="Lagos",
        country="Nigeria",
        marital_status="Single",
        is_active=True,
    )
    account.set_password("StrongPassw0rd!")
    db.session.add(account)
    db.session.commit()
    return account


def test_birthday_wish_changes_today_notification_state(client, user, db):
    friend = _birthday_user(db)
    with client.session_transaction() as session:
        session["_user_id"] = str(user.id)
        session["_fresh"] = True

    before = client.get("/api/birthdays/today")
    before_friend = next(
        item for item in before.get_json()["birthdays"] if item["id"] == friend.id
    )
    assert before_friend["is_wished"] is False

    wished = client.post(
        "/api/birthday/wish",
        json={"friend_id": friend.id, "message": "Happy birthday!"},
    )
    assert wished.status_code == 200
    assert wished.get_json()["is_wished"] is True

    after = client.get("/api/birthdays/today")
    after_friend = next(
        item for item in after.get_json()["birthdays"] if item["id"] == friend.id
    )
    assert after_friend["is_wished"] is True

    notification = BirthdayNotification.query.filter_by(
        user_id=user.id,
        birthday_user_id=friend.id,
        birthday_date=date.today(),
    ).one()
    assert notification.is_wished is True
    assert notification.is_seen is True
