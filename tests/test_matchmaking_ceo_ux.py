from datetime import date
from pathlib import Path
import uuid

from sqlalchemy import event

from models import AIPersona, Group, PaymentTransaction, User
from time_utils import utcnow


ROOT = Path(__file__).resolve().parents[1]


def _login(client, user):
    with client.session_transaction() as session:
        session["_user_id"] = str(user.id)
        session["_fresh"] = True


def _user(db, *, first_name, email=None, admin=False, ai=False):
    suffix = uuid.uuid4().hex[:10]
    candidate = User(
        first_name=first_name,
        last_name="Directory",
        email=email or f"ceo-match-{suffix}@example.com",
        phone_number=f"+2348{uuid.uuid4().int % 10**9:09d}",
        dob=date(1992, 4, 12),
        gender="Female",
        city="Lagos",
        state="Lagos",
        country="Nigeria",
        marital_status="Single",
        is_active=True,
        is_admin=admin,
        is_ai_persona=ai,
    )
    candidate.set_password("StrongPassw0rd!")
    db.session.add(candidate)
    db.session.flush()
    return candidate


def test_unpaid_see_everyone_uses_same_server_access_gate(client, user):
    _login(client, user)

    response = client.get("/api/browse/users?scope=everyone")

    assert response.status_code == 402
    assert response.get_json()["code"] == "browse_access_required"
    assert response.get_json()["price_usd"] == "3.00"


def test_paid_see_everyone_uses_the_protected_eligible_directory(client, user, db):
    target = _user(db, first_name="EveryoneTarget")
    db.session.add(
        PaymentTransaction(
            user_id=user.id,
            amount=3,
            currency="USD",
            gateway="flutterwave",
            gateway_reference=f"KIMBELA_BROWSE_EVERYONE_{uuid.uuid4().hex}",
            gateway_status="successful",
            status="completed",
            transaction_type="matchmaking_browse",
            created_at=utcnow(),
            updated_at=utcnow(),
        )
    )
    db.session.commit()
    _login(client, user)

    response = client.get("/api/browse/users?scope=everyone")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert target.id in {candidate["id"] for candidate in payload["users"]}


def test_find_page_uses_one_entitlement_for_filters_and_see_everyone(client, user):
    _login(client, user)

    response = client.get("/view_requests")

    assert response.status_code == 200
    assert b'id="applyFilters"' in response.data
    assert b"Find Matches" in response.data
    assert b'id="seeEveryoneButton"' in response.data
    assert b"function seeEveryone()" in response.data
    assert b"clearFilters();" in response.data
    assert response.data.count(b"/api/browse/access/payment") == 1
    assert b"one payment" in response.data
    assert b"Find Your Match and See Everyone included" in response.data


def test_admin_matchmaking_directory_rejects_normal_user(client, user):
    _login(client, user)

    response = client.get("/api/admin/matchmaking/users")

    assert response.status_code == 403
    assert response.get_json() == {"success": False, "error": "Access denied"}


def test_admin_matchmaking_directory_is_bounded_and_excludes_sensitive_fields(
    client, db, app
):
    admin = _user(db, first_name="Admin", admin=True)
    target = _user(db, first_name="DirectoryTarget")
    db.session.add(
        PaymentTransaction(
            user_id=target.id,
            amount=3,
            currency="USD",
            gateway="flutterwave",
            gateway_reference=f"KIMBELA_BROWSE_ADMIN_{uuid.uuid4().hex}",
            gateway_status="successful",
            status="completed",
            transaction_type="matchmaking_browse",
            description="$3 Find Your Match access for 30 days",
            created_at=utcnow(),
            updated_at=utcnow(),
        )
    )
    db.session.commit()
    _login(client, admin)
    select_statements = []

    def record_select(_connection, _cursor, statement, _params, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            select_statements.append(statement)

    event.listen(db.engine, "before_cursor_execute", record_select)
    try:
        response = client.get(
            "/api/admin/matchmaking/users",
            query_string={"search": target.email, "per_page": 25},
        )
    finally:
        event.remove(db.engine, "before_cursor_execute", record_select)

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["total"] == 1
    assert payload["users"][0]["id"] == target.id
    assert payload["users"][0]["full_name"] == "DirectoryTarget Directory"
    assert payload["users"][0]["matchmaking_access_active"] is True
    assert payload["users"][0]["matchmaking_access_expires_at"] is not None
    assert payload["users"][0]["active_profile_boosts"] == 0
    assert len(select_statements) <= 6

    forbidden_fields = {
        "password",
        "password_hash",
        "authentication_token",
        "session",
        "payment_secret",
        "push_subscriptions",
        "push_endpoint",
        "p256dh",
        "auth",
    }
    assert forbidden_fields.isdisjoint(payload["users"][0])


def test_group_description_renders_sanitized_html_without_literal_tags(
    client, user, db
):
    group = Group(
        name=f"Description {uuid.uuid4().hex[:8]}",
        description=(
            "<p>Community <strong>garden</strong></p>"
            "<script>window.groupDescriptionXss = true</script>"
        ),
        created_by=user.id,
        is_active=True,
    )
    db.session.add(group)
    db.session.commit()
    _login(client, user)

    response = client.get(f"/groups/{group.id}")

    assert response.status_code == 200
    assert b"<p>Community <strong>garden</strong></p>" in response.data
    assert b"&lt;p&gt;Community" not in response.data
    assert b"<script>window.groupDescriptionXss" not in response.data


def test_matchmaking_names_and_say_hi_behavior_are_preserved():
    dashboard = (ROOT / "templates/user_dashboard.html").read_text()
    find_page = (ROOT / "templates/view_requests.html").read_text()
    boost_page = (ROOT / "templates/requests.html").read_text()
    admin_dashboard = (ROOT / "templates/admin_dashboard_content.html").read_text()
    payment_success = (ROOT / "templates/payment_success.html").read_text()

    assert "Boost Your Profile" in dashboard
    assert "Find Your Match" in dashboard
    assert "Create Match Request" not in dashboard
    assert "Browse Matches" not in dashboard
    assert "increase your matchmaking visibility" in dashboard
    assert "Find Your Match" in find_page
    assert "Boost Your Profile" in boost_page
    assert "Increase your visibility and discoverability" in boost_page
    assert "Active profile boosts" in admin_dashboard
    assert "Create Another Profile Boost" in payment_success

    say_hi_start = dashboard.index("<!-- Say Hi -->")
    say_hi_section = dashboard[say_hi_start : say_hi_start + 1800]
    assert "<h3>Say Hi</h3>" in say_hi_section
    assert "url_for('user.explore_users')" in say_hi_section
    assert "addFriend(" in say_hi_section
    assert "current_user.is_admin" not in say_hi_section


def test_two_persisted_ai_display_names_update_without_new_accounts(app, db):
    emily_user = _user(
        db,
        first_name="Amara",
        email="ai.amara@kimbela.com",
        ai=True,
    )
    daniel_user = _user(
        db,
        first_name="Tunde",
        email="ai.tunde@kimbela.com",
        ai=True,
    )
    emily_user.last_name = "Okafor"
    daniel_user.last_name = "Balogun"
    db.session.add_all(
        [
            AIPersona(
                user_id=emily_user.id,
                name="Amara Okafor",
                bio_disclosure="AI profile",
                personality="Warm",
                is_active=True,
            ),
            AIPersona(
                user_id=daniel_user.id,
                name="Tunde Balogun",
                bio_disclosure="AI profile",
                personality="Easygoing",
                is_active=True,
            ),
        ]
    )
    db.session.commit()

    from update_ai_names import DISPLAY_NAME_UPDATES, update_names

    original_ids = {emily_user.id, daniel_user.id}
    update_names(app)
    db.session.expire_all()

    renamed_users = User.query.filter(
        User.email.in_(DISPLAY_NAME_UPDATES)
    ).order_by(User.id).all()
    assert {candidate.id for candidate in renamed_users} == original_ids
    assert {candidate.full_name for candidate in renamed_users} == {
        "Emily Carter",
        "Daniel Brooks",
    }
    assert {
        persona.name
        for persona in AIPersona.query.filter(
            AIPersona.user_id.in_(original_ids)
        ).all()
    } == {"Emily Carter", "Daniel Brooks"}
    assert all(candidate.is_ai_persona for candidate in renamed_users)
