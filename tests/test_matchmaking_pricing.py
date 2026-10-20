import json
import uuid
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from models import MatchmakingPackage, MatchmakingPayments, MatchmakingRequest
from payments.payment_service import MatchmakingPaymentService
from payments.pricing import (
    MATCHMAKING_ACCESS_PRICE_USD,
    MATCHMAKING_PRODUCT_PRICE_USD,
    PROFILE_BOOST_PRICE_USD,
)
from time_utils import utcnow


ROOT = Path(__file__).resolve().parents[1]


class _ProviderResponse:
    status_code = 200
    text = ""

    def json(self):
        return {
            "status": "success",
            "data": {
                "id": f"checkout-{uuid.uuid4().hex}",
                "link": "https://checkout.example/boost",
            },
        }


def _login(client, user):
    with client.session_transaction() as session:
        session["_user_id"] = str(user.id)
        session["_fresh"] = True


def _boost_rows(db, user, *, package_price=10.0, duration_days=30):
    package = MatchmakingPackage(
        name=f"Boost {uuid.uuid4().hex[:8]}",
        description="Pricing regression package",
        price=package_price,
        duration_days=duration_days,
        is_active=True,
    )
    db.session.add(package)
    db.session.flush()
    request_row = MatchmakingRequest(
        user_id=user.id,
        package_id=package.id,
        about_you="About me",
        ideal_partner="Ideal partner",
        status="pending",
        payment_status="pending",
    )
    db.session.add(request_row)
    db.session.commit()
    return package, request_row


def _provider_data(payment, *, amount="4800.00", currency="NGN", **overrides):
    data = {
        "id": f"provider-{uuid.uuid4().hex}",
        "status": "successful",
        "tx_ref": payment.gateway_reference,
        "amount": amount,
        "currency": currency,
        "meta": {
            "user_id": payment.user_id,
            "matchmaking_request_id": payment.matchmaking_request_id,
            "package_id": payment.package_id,
            "transaction_type": "matchmaking",
            "product": "profile_boost",
        },
    }
    data.update(overrides)
    return data


def _payment(db, user, package, request_row):
    payment = MatchmakingPayments(
        user_id=user.id,
        matchmaking_request_id=request_row.id,
        package_id=package.id,
        amount=3.0,
        currency="USD",
        gateway="flutterwave",
        gateway_reference=f"KIMBELA_MATCH_{request_row.id}_{uuid.uuid4().hex}",
        gateway_status="initiated",
        status="pending",
        payment_status="pending",
        gateway_metadata=json.dumps(
            {
                "expected_checkout_amount": "4800.00",
                "expected_checkout_currency": "NGN",
                "expected_product": "profile_boost",
                "expected_transaction_type": "matchmaking",
            }
        ),
    )
    db.session.add(payment)
    db.session.commit()
    return payment


def _configure_service(monkeypatch):
    monkeypatch.setenv("FLW_SECRET_KEY", "FLWSECK_TEST-local")
    monkeypatch.setenv("FLW_PUBLIC_KEY", "FLWPUBK_TEST-local")
    monkeypatch.setattr(
        MatchmakingPaymentService,
        "get_ngn_rate",
        lambda self, *_args, **_kwargs: 1600,
    )


def test_matchmaking_products_share_exact_decimal_three_dollar_price():
    assert MATCHMAKING_PRODUCT_PRICE_USD == Decimal("3.00")
    assert MATCHMAKING_ACCESS_PRICE_USD is MATCHMAKING_PRODUCT_PRICE_USD
    assert PROFILE_BOOST_PRICE_USD is MATCHMAKING_PRODUCT_PRICE_USD


def test_find_match_and_profile_boost_display_authoritative_price(client, user, db):
    _boost_rows(db, user, package_price=99.99)
    _login(client, user)

    find_page = client.get("/view_requests")
    boost_page = client.get("/requests")

    assert find_page.status_code == 200
    assert boost_page.status_code == 200
    assert b"$3.00 USD" in find_page.data
    assert b"Boost Your Profile - $3.00 USD/month" in boost_page.data
    assert b"Fixed price - $3.00 USD/month" in boost_page.data
    assert b"$99.99" not in boost_page.data
    assert b"$10" not in boost_page.data


def test_boost_checkout_ignores_browser_and_package_prices(
    client, user, db, monkeypatch
):
    package, request_row = _boost_rows(db, user, package_price=47.25)
    _login(client, user)
    _configure_service(monkeypatch)
    provider_payloads = []

    def fake_request(self, method, url, **kwargs):
        provider_payloads.append(kwargs["json"])
        return _ProviderResponse()

    monkeypatch.setattr(MatchmakingPaymentService, "_http_request", fake_request)

    response = client.post(
        "/initiate-matchmaking-payment",
        json={
            "request_id": request_row.id,
            "campaign_id": package.id,
            "amount": "0.01",
            "currency": "NGN",
            "campaign_title": "tampered product",
            "gateway": "flutterwave",
        },
    )

    assert response.status_code == 200
    payload = provider_payloads[0]
    assert payload["amount"] == "4800.00"
    assert payload["currency"] == "NGN"
    assert payload["meta"] == {
        "user_id": user.id,
        "matchmaking_request_id": request_row.id,
        "package_id": package.id,
        "transaction_type": "matchmaking",
        "product": "profile_boost",
    }
    payment = MatchmakingPayments.query.get(response.get_json()["payment_id"])
    assert Decimal(str(payment.amount)).quantize(Decimal("0.01")) == Decimal("3.00")
    assert payment.currency == "USD"
    metadata = json.loads(payment.gateway_metadata)
    assert metadata["expected_checkout_amount"] == "4800.00"
    assert metadata["expected_checkout_currency"] == "NGN"


@pytest.mark.parametrize(
    ("change", "value"),
    [
        ("amount", "4799.99"),
        ("currency", "USD"),
        ("tx_ref", "KIMBELA_MATCH_WRONG"),
        ("product", "find_your_match"),
        ("request", "999999"),
    ],
)
def test_boost_verification_rejects_wrong_payment_proof(
    db, user, monkeypatch, change, value
):
    package, request_row = _boost_rows(db, user)
    payment = _payment(db, user, package, request_row)
    _configure_service(monkeypatch)
    service = MatchmakingPaymentService()
    provider_data = _provider_data(payment)
    if change in {"product", "request"}:
        key = "product" if change == "product" else "matchmaking_request_id"
        provider_data["meta"][key] = value
    else:
        provider_data[change] = value

    assert service.handle_matchmaking_payment_success(payment, provider_data) is False
    db.session.refresh(payment)
    db.session.refresh(request_row)
    assert payment.status == "pending"
    assert request_row.status == "pending"


def test_verified_three_dollar_boost_preserves_existing_duration(
    db, user, monkeypatch
):
    package, request_row = _boost_rows(db, user, package_price=88, duration_days=45)
    payment = _payment(db, user, package, request_row)
    _configure_service(monkeypatch)
    service = MatchmakingPaymentService()
    monkeypatch.setattr(
        service,
        "send_matchmaking_payment_success_email",
        lambda *_args, **_kwargs: True,
    )
    before = utcnow()

    assert service.handle_matchmaking_payment_success(
        payment, _provider_data(payment)
    ) is True

    db.session.refresh(payment)
    db.session.refresh(request_row)
    assert payment.status == "completed"
    assert payment.payment_status == "paid"
    assert request_row.status == "active"
    assert request_row.payment_status == "completed"
    assert before + timedelta(days=45) <= request_row.end_date
    assert request_row.end_date <= utcnow() + timedelta(days=45)


def test_boost_callback_does_not_trust_success_query_parameter(
    client, db, user, monkeypatch
):
    package, request_row = _boost_rows(db, user)
    payment = _payment(db, user, package, request_row)
    _login(client, user)
    _configure_service(monkeypatch)
    monkeypatch.setattr(
        MatchmakingPaymentService,
        "resolve_flutterwave_verification",
        lambda self, **_kwargs: {
            "success": False,
            "verified_status": "successful",
            "data": {},
            "error": "provider verification unavailable",
        },
    )

    response = client.get(
        "/matchmaking/payment-callback",
        query_string={
            "status": "successful",
            "tx_ref": payment.gateway_reference,
            "transaction_id": "unverified-id",
        },
    )

    assert response.status_code == 302
    db.session.refresh(payment)
    db.session.refresh(request_row)
    assert payment.status == "pending"
    assert request_row.status == "pending"


def test_legacy_failed_payment_retry_keeps_history_and_creates_three_dollar_row(
    app, db, user, monkeypatch
):
    package, request_row = _boost_rows(db, user, package_price=10)
    legacy = MatchmakingPayments(
        user_id=user.id,
        matchmaking_request_id=request_row.id,
        package_id=package.id,
        amount=10,
        currency="USD",
        gateway="flutterwave",
        gateway_reference=f"LEGACY-{uuid.uuid4().hex}",
        gateway_status="failed",
        status="failed",
        payment_status="failed",
        description="$10 legacy boost",
    )
    db.session.add(legacy)
    db.session.commit()
    original = legacy.to_dict().copy()
    _configure_service(monkeypatch)
    monkeypatch.setattr(
        MatchmakingPaymentService,
        "_http_request",
        lambda *_args, **_kwargs: _ProviderResponse(),
    )
    service = MatchmakingPaymentService()

    with app.test_request_context():
        result = service.retry_payment(legacy.id)

    assert result["success"] is True
    db.session.refresh(legacy)
    retry = MatchmakingPayments.query.get(result["payment_id"])
    assert legacy.id != retry.id
    assert legacy.amount == original["amount"] == 10
    assert legacy.status == original["status"] == "failed"
    assert retry.amount == 3
    assert retry.currency == "USD"
    assert json.loads(retry.gateway_metadata)["retry_of_payment_id"] == legacy.id


def test_pending_legacy_payment_is_not_rewritten_by_retry(db, user, monkeypatch):
    package, request_row = _boost_rows(db, user)
    pending = MatchmakingPayments(
        user_id=user.id,
        matchmaking_request_id=request_row.id,
        package_id=package.id,
        amount=10,
        currency="USD",
        gateway="flutterwave",
        gateway_reference=f"PENDING-{uuid.uuid4().hex}",
        status="pending",
        payment_status="pending",
    )
    db.session.add(pending)
    db.session.commit()
    _configure_service(monkeypatch)

    result = MatchmakingPaymentService().retry_payment(pending.id)

    assert result == {
        "success": False,
        "error": "Only failed payments can be retried",
    }
    db.session.refresh(pending)
    assert pending.amount == 10
    assert pending.status == "pending"


def test_payment_history_keeps_legacy_amount_and_reports_new_three_dollar_amount(
    client, db, user, monkeypatch
):
    package, request_row = _boost_rows(db, user)
    legacy = MatchmakingPayments(
        user_id=user.id,
        matchmaking_request_id=request_row.id,
        package_id=package.id,
        amount=10,
        currency="USD",
        gateway="flutterwave",
        gateway_reference=f"HISTORY-OLD-{uuid.uuid4().hex}",
        status="completed",
        payment_status="paid",
    )
    current = _payment(db, user, package, request_row)
    db.session.add(legacy)
    db.session.commit()
    _login(client, user)
    _configure_service(monkeypatch)

    response = client.get("/api/my-payments")

    assert response.status_code == 200
    by_id = {entry["id"]: entry for entry in response.get_json()["payments"]}
    assert by_id[legacy.id]["amount"] == 10
    assert by_id[current.id]["amount"] == 3


def test_package_api_reports_product_price_not_legacy_database_price(
    client, user, db
):
    package, _request_row = _boost_rows(db, user, package_price=76.54)
    _login(client, user)

    response = client.get("/packages")

    assert response.status_code == 200
    entry = next(item for item in response.get_json()["packages"] if item["id"] == package.id)
    assert entry["price"] == 3.0


def test_boost_frontend_has_no_independent_or_submitted_price():
    source = (ROOT / "templates" / "requests.html").read_text()

    assert "packages[0].price" not in source
    assert "profile_boost_price_usd" in source
    payment_payload = source[source.index(
        "checkout.requestJson('/initiate-matchmaking-payment'"
    ):source.index("if (!paymentData.success")]
    assert "amount:" not in payment_payload
    assert "$10" not in source
    assert "id=\"clearPreferencesBtn\"" in source
    assert "Preferred Match Age" in source
    assert "boost_checkout.js" in source


def test_unrelated_marketplace_price_model_is_unchanged():
    source = (ROOT / "payments" / "pricing.py").read_text()

    assert "MARKETPLACE" not in source
