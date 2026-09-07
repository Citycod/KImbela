import json
import uuid
from datetime import date, timedelta
from decimal import Decimal

from models import PaymentTransaction, User
from payments.browse_access import (
    BROWSE_ACCESS_DAYS,
    BROWSE_ACCESS_PRICE_USD,
    BROWSE_TRANSACTION_TYPE,
    BrowseAccessPaymentService,
    get_browse_access_status,
)
from payments.payment_service import BasePaymentService
from time_utils import utcnow


class _ProviderResponse:
    status_code = 200

    def json(self):
        return {
            "status": "success",
            "data": {"id": "checkout-123", "link": "https://checkout.example/browse"},
        }


def _login(client, user):
    with client.session_transaction() as session:
        session["_user_id"] = str(user.id)
        session["_fresh"] = True


def _eligible_discovery_user(db):
    suffix = uuid.uuid4().hex[:10]
    candidate = User(
        first_name="Explore",
        last_name="Candidate",
        email=f"explore-{suffix}@example.com",
        phone_number=f"+2347{uuid.uuid4().int % 10**9:09d}",
        dob=date(1992, 4, 12),
        gender="Female",
        city="Explore City",
        state="Explore State",
        country=f"Explore-{suffix}",
        marital_status="Single",
        is_active=True,
    )
    candidate.set_password("StrongPassw0rd!")
    db.session.add(candidate)
    db.session.commit()
    return candidate


def _browse_transaction(db, user, *, status="completed", completed_at=None):
    completed_at = completed_at or utcnow()
    reference = f"KIMBELA_BROWSE_{user.id}_{uuid.uuid4().hex.upper()}"
    transaction = PaymentTransaction(
        user_id=user.id,
        amount=BROWSE_ACCESS_PRICE_USD,
        currency="USD",
        gateway="flutterwave",
        gateway_reference=reference,
        gateway_status="successful" if status == "completed" else "initiated",
        status=status,
        transaction_type=BROWSE_TRANSACTION_TYPE,
        description="$3 Find Your Match access for 30 days",
        gateway_metadata=json.dumps(
            {
                "expected_checkout_amount": "4800.00",
                "expected_checkout_currency": "NGN",
                "access_days": BROWSE_ACCESS_DAYS,
            }
        ),
        created_at=completed_at,
        updated_at=completed_at,
    )
    db.session.add(transaction)
    db.session.commit()
    return transaction


def _successful_verification(transaction, user, provider_id="provider-123"):
    return {
        "success": True,
        "verified_status": "successful",
        "data": {
            "id": provider_id,
            "status": "successful",
            "tx_ref": transaction.gateway_reference,
            "amount": 4800,
            "currency": "NGN",
            "meta": {"user_id": user.id},
        },
    }


def test_unpaid_find_page_shows_filters_but_discovery_api_requires_access(
    client, user
):
    _login(client, user)

    page_response = client.get("/view_requests")
    discovery_response = client.get("/api/browse/users")
    requests_response = client.get("/api/requests")

    assert page_response.status_code == 200
    assert b"Find Your Match" in page_response.data
    assert b'id="filterToggle"' in page_response.data
    assert b'id="minAgeFilter"' in page_response.data
    assert b'id="genderFilter"' in page_response.data
    assert b'id="seeEveryoneButton"' in page_response.data
    assert b"Unlock Find Your Match" in page_response.data
    assert b"$3.00 USD" in page_response.data
    assert b"for 30 days" in page_response.data
    assert b"if (hasMatchmakingAccess)" in page_response.data
    assert b"showMatchmakingAccessGate(false)" in page_response.data
    assert discovery_response.status_code == 402
    assert discovery_response.get_json()["code"] == "browse_access_required"
    assert discovery_response.get_json()["price_usd"] == "3.00"
    assert discovery_response.get_json()["duration_days"] == 30
    assert requests_response.status_code == 200
    assert requests_response.get_json()["success"] is True


def test_unpaid_explore_users_redirects_without_rendering_legacy_directory(
    client, user, db
):
    candidate = _eligible_discovery_user(db)
    _login(client, user)

    response = client.get("/explore_users", follow_redirects=False)
    destination = client.get("/explore_users", follow_redirects=True)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/view_requests")
    assert candidate.full_name.encode() not in response.data
    assert destination.status_code == 200
    assert b"Unlock Find Your Match" in destination.data
    assert client.get("/api/browse/users").status_code == 402


def test_paid_explore_users_uses_protected_discovery_and_safe_serialization(
    client, user, db
):
    candidate = _eligible_discovery_user(db)
    _browse_transaction(db, user)
    _login(client, user)

    redirect_response = client.get("/explore_users", follow_redirects=False)
    api_response = client.get(
        "/api/browse/users",
        query_string={"country": candidate.country},
    )

    assert redirect_response.status_code == 302
    assert redirect_response.headers["Location"].endswith("/view_requests")
    assert api_response.status_code == 200
    payload = api_response.get_json()
    assert [entry["id"] for entry in payload["users"]] == [candidate.id]
    assert {
        "email",
        "password",
        "password_hash",
        "phone_number",
        "authentication_token",
        "push_subscriptions",
    }.isdisjoint(payload["users"][0])


def test_expired_access_cannot_use_explore_discovery(client, user, db):
    _browse_transaction(db, user, completed_at=utcnow() - timedelta(days=31))
    _login(client, user)

    response = client.get("/explore_users", follow_redirects=True)

    assert response.status_code == 200
    assert b"Unlock Find Your Match" in response.data
    assert client.get("/api/browse/users").status_code == 402


def test_valid_legacy_two_dollar_access_still_unlocks_explore_discovery(
    client, user, db
):
    transaction = _browse_transaction(db, user)
    transaction.amount = Decimal("2.00")
    transaction.description = "$2 Browse Match access for 30 days"
    db.session.commit()
    _login(client, user)

    response = client.get("/explore_users", follow_redirects=True)
    api_response = client.get("/api/browse/users")

    assert response.status_code == 200
    assert b"let hasMatchmakingAccess = true;" in response.data
    assert api_response.status_code == 200


def test_active_access_opens_browse_and_expires_at_exactly_30_days(
    client, user, db
):
    _login(client, user)
    completed_at = utcnow()
    _browse_transaction(db, user, completed_at=completed_at)

    just_before_expiry = get_browse_access_status(
        user.id,
        now=completed_at + timedelta(days=30) - timedelta(microseconds=1),
    )
    at_expiry = get_browse_access_status(
        user.id,
        now=completed_at + timedelta(days=30),
    )
    page_response = client.get("/view_requests")

    assert just_before_expiry["active"] is True
    assert at_expiry["active"] is False
    assert page_response.status_code == 200
    assert b'id="filterToggle"' in page_response.data
    assert b'id="matchmakingAccessGate"' in page_response.data
    assert b"text-center hidden" in page_response.data


def test_expired_access_returns_to_paywall(client, user, db):
    _login(client, user)
    _browse_transaction(db, user, completed_at=utcnow() - timedelta(days=31))

    page_response = client.get("/view_requests")
    api_response = client.get("/api/browse/users")

    assert b"Unlock Find Your Match" in page_response.data
    assert api_response.status_code == 402


def test_checkout_uses_server_fixed_price_and_ignores_client_amount(
    client, user, db, monkeypatch
):
    _login(client, user)
    provider_payloads = []

    monkeypatch.setattr(
        BrowseAccessPaymentService,
        "get_ngn_rate",
        lambda self, *_args, **_kwargs: 1600,
    )

    def fake_request(self, method, url, **kwargs):
        provider_payloads.append(kwargs["json"])
        return _ProviderResponse()

    monkeypatch.setattr(BrowseAccessPaymentService, "_http_request", fake_request)

    response = client.post(
        "/api/browse/access/payment",
        json={"amount": "0.01", "duration_days": 9999},
    )

    assert response.status_code == 200
    assert response.get_json()["payment_url"] == "https://checkout.example/browse"
    assert provider_payloads[0]["amount"] == "4800.00"
    assert provider_payloads[0]["currency"] == "NGN"
    assert provider_payloads[0]["meta"]["access_days"] == 30
    transaction = PaymentTransaction.query.filter_by(
        gateway_reference=response.get_json()["gateway_reference"]
    ).one()
    assert transaction.amount == Decimal("3.00")
    assert transaction.currency == "USD"
    assert transaction.status == "pending"
    assert transaction.transaction_type == BROWSE_TRANSACTION_TYPE


def test_active_access_does_not_create_or_stack_another_checkout(
    client, user, db, monkeypatch
):
    _login(client, user)
    transaction = _browse_transaction(db, user)

    def unexpected_request(*_args, **_kwargs):
        raise AssertionError("provider must not be called for active access")

    monkeypatch.setattr(BrowseAccessPaymentService, "_http_request", unexpected_request)

    response = client.post("/api/browse/access/payment")

    assert response.status_code == 200
    assert response.get_json()["already_active"] is True
    assert PaymentTransaction.query.filter_by(
        user_id=user.id,
        transaction_type=BROWSE_TRANSACTION_TYPE,
    ).count() == 1
    assert response.get_json()["expires_at"] == (
        transaction.updated_at + timedelta(days=30)
    ).isoformat()


def test_verified_callback_grants_access_for_30_days(
    client, user, db, monkeypatch
):
    _login(client, user)
    transaction = _browse_transaction(db, user, status="pending")
    verification = _successful_verification(transaction, user)
    monkeypatch.setattr(
        BasePaymentService,
        "resolve_flutterwave_verification",
        lambda self, **_kwargs: verification,
    )

    response = client.get(
        "/browse/payment-callback",
        query_string={
            "status": "successful",
            "tx_ref": transaction.gateway_reference,
            "transaction_id": "provider-123",
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/view_requests")
    db.session.refresh(transaction)
    assert transaction.status == "completed"
    assert transaction.gateway_payment_id == "provider-123"
    access = get_browse_access_status(user.id)
    assert access["active"] is True
    assert timedelta(days=29, hours=23, minutes=59) < (
        access["expires_at"] - utcnow()
    ) <= timedelta(days=30)


def test_callback_rejects_underpayment_without_granting_access(
    client, user, db, monkeypatch
):
    _login(client, user)
    transaction = _browse_transaction(db, user, status="pending")
    verification = _successful_verification(transaction, user)
    verification["data"]["amount"] = 4799.99
    monkeypatch.setattr(
        BasePaymentService,
        "resolve_flutterwave_verification",
        lambda self, **_kwargs: verification,
    )

    response = client.get(
        "/browse/payment-callback",
        query_string={
            "status": "successful",
            "tx_ref": transaction.gateway_reference,
            "transaction_id": "provider-123",
        },
    )

    assert response.status_code == 302
    db.session.refresh(transaction)
    assert transaction.status == "pending"
    assert get_browse_access_status(user.id)["active"] is False


def test_verified_webhook_grants_access_without_browser_return(
    client, user, db, app, monkeypatch
):
    transaction = _browse_transaction(db, user, status="pending")
    verification = _successful_verification(transaction, user, "provider-webhook")
    monkeypatch.setitem(app.config, "FLUTTERWAVE_WEBHOOK_HASH", "browse-secret")
    monkeypatch.setattr(
        BasePaymentService,
        "resolve_flutterwave_verification",
        lambda self, **_kwargs: verification,
    )

    response = client.post(
        "/flutterwave/webhook",
        json={
            "event": "charge.completed",
            "data": {"tx_ref": transaction.gateway_reference, "id": "provider-webhook"},
        },
        headers={"verif-hash": "browse-secret"},
    )

    assert response.status_code == 200
    assert response.get_json()["status"] == "success"
    db.session.refresh(transaction)
    assert transaction.status == "completed"
    assert get_browse_access_status(user.id)["active"] is True

    completed_at = transaction.updated_at
    duplicate_response = client.post(
        "/flutterwave/webhook",
        json={
            "event": "charge.completed",
            "data": {"tx_ref": transaction.gateway_reference, "id": "provider-webhook"},
        },
        headers={"verif-hash": "browse-secret"},
    )
    assert duplicate_response.status_code == 200
    db.session.refresh(transaction)
    assert transaction.updated_at == completed_at


def test_webhook_provider_verification_failure_does_not_grant_access(
    client, user, db, app, monkeypatch
):
    transaction = _browse_transaction(db, user, status="pending")
    monkeypatch.setitem(app.config, "FLUTTERWAVE_WEBHOOK_HASH", "browse-secret")
    monkeypatch.setattr(
        BasePaymentService,
        "resolve_flutterwave_verification",
        lambda self, **_kwargs: {
            "success": False,
            "verified_status": "successful",
            "data": {
                "id": "unverified-provider-id",
                "status": "successful",
                "tx_ref": transaction.gateway_reference,
                "amount": 4800,
                "currency": "NGN",
            },
        },
    )

    response = client.post(
        "/flutterwave/webhook",
        json={
            "event": "charge.completed",
            "data": {
                "tx_ref": transaction.gateway_reference,
                "id": "unverified-provider-id",
            },
        },
        headers={"verif-hash": "browse-secret"},
    )

    assert response.status_code == 500
    db.session.refresh(transaction)
    assert transaction.status == "pending"
    assert get_browse_access_status(user.id)["active"] is False


def test_browse_paywall_checkout_script_sends_no_client_price(client, user):
    _login(client, user)

    response = client.get("/view_requests")

    assert response.status_code == 200
    assert b"/api/browse/access/payment" in response.data
    assert b"enablePushNotifications" not in response.data
    assert b'json: {"amount"' not in response.data
