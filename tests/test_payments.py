from datetime import timedelta


def test_payment_callback_routes_are_unique(app):
    route_map = {rule.endpoint: rule.rule for rule in app.url_map.iter_rules()}

    assert route_map["payments.payment_callback"] == "/payment-callback"
    assert route_map["payments.flutterwave_webhook"] == "/flutterwave/webhook"
    assert route_map["match.payment_callback"] == "/matchmaking/payment-callback"
    assert route_map["market.payment_callback"] == "/marketplace/payment-callback"


def test_ad_payment_callback_recovers_success_via_reference_verification(
    client, db, user, monkeypatch
):
    from models import AdCampaign, PaymentTransaction
    from payments.payment_service import BasePaymentService
    from payments.payment_service_ad import AdCampaignPaymentService
    from time_utils import utcnow

    campaign = AdCampaign(
        user_id=user.id,
        title="Test Campaign",
        description="Campaign for callback test",
        budget=2500.0,
        daily_budget=250.0,
        duration_days=10,
        payment_status="pending",
        status="pending",
    )
    db.session.add(campaign)
    db.session.flush()

    transaction = PaymentTransaction(
        user_id=user.id,
        campaign_id=campaign.id,
        amount=campaign.budget,
        currency="USD",
        gateway="flutterwave",
        gateway_reference="KIMBELA_AD_1_999999",
        gateway_payment_id="",
        status="pending",
        transaction_type="ad_campaign",
    )
    db.session.add(transaction)
    db.session.commit()

    def fake_resolve(self, tx_ref=None, transaction_id=None):
        assert tx_ref == "KIMBELA_AD_1_999999"
        return {
            "success": True,
            "verified_status": "successful",
            "data": {"id": 10101, "status": "successful", "amount": 2500.0},
            "source": "tx_ref",
        }

    def fake_handle_success(self, transaction_id, payment_data=None):
        tx = PaymentTransaction.query.get(transaction_id)
        tx.status = "completed"
        tx.gateway_status = "successful"
        tx.gateway_payment_id = str(payment_data["id"])
        tx.gateway_metadata = "{}"
        tx.updated_at = utcnow()

        ad = AdCampaign.query.get(tx.campaign_id)
        ad.payment_status = "paid"
        ad.status = "active"
        db.session.commit()
        return True

    monkeypatch.setattr(
        BasePaymentService,
        "resolve_flutterwave_verification",
        fake_resolve,
    )
    monkeypatch.setattr(
        AdCampaignPaymentService,
        "handle_ad_payment_success",
        fake_handle_success,
    )

    response = client.get(
        "/payment-callback?tx_ref=KIMBELA_AD_1_999999&status=session_expired",
        follow_redirects=False,
    )

    assert response.status_code == 302
    db.session.refresh(transaction)
    db.session.refresh(campaign)
    assert transaction.status == "completed"
    assert transaction.gateway_status == "successful"
    assert transaction.gateway_payment_id == "10101"
    assert campaign.payment_status == "paid"
    assert campaign.status == "active"


def test_matchmaking_payment_callback_recovers_success_via_reference_verification(
    client, db, user, login, monkeypatch
):
    from models import MatchmakingPackage, MatchmakingPayments, MatchmakingRequest
    from payments.payment_service import MatchmakingPaymentService
    from time_utils import utcnow

    package = MatchmakingPackage(
        name="Premium Match",
        description="Test package",
        price=10.0,
        duration_days=30,
    )
    db.session.add(package)
    db.session.flush()

    matchmaking_request = MatchmakingRequest(
        user_id=user.id,
        package_id=package.id,
        about_you="About me",
        ideal_partner="Ideal partner",
        status="pending",
        payment_status="pending",
    )
    db.session.add(matchmaking_request)
    db.session.flush()

    matchmaking_payment = MatchmakingPayments(
        user_id=user.id,
        matchmaking_request_id=matchmaking_request.id,
        package_id=package.id,
        amount=2756.59,
        currency="USD",
        gateway_reference="KIMBELA_MATCH_1_999999",
        status="pending",
        payment_status="pending",
    )
    db.session.add(matchmaking_payment)
    db.session.commit()

    login()

    def fake_resolve(self, tx_ref=None, transaction_id=None):
        assert tx_ref == "KIMBELA_MATCH_1_999999"
        return {
            "success": True,
            "verified_status": "successful",
            "data": {"id": 20202, "status": "successful"},
            "source": "tx_ref",
        }

    def fake_handle_success(self, payment, flutterwave_data):
        payment.status = "completed"
        payment.payment_status = "paid"
        payment.gateway_status = "successful"
        payment.gateway_payment_id = str(flutterwave_data["id"])
        payment.paid_at = utcnow()
        payment.matchmaking_request.payment_status = "completed"
        payment.matchmaking_request.status = "active"
        payment.matchmaking_request.end_date = utcnow() + timedelta(days=30)
        db.session.commit()
        return True

    monkeypatch.setattr(
        MatchmakingPaymentService,
        "resolve_flutterwave_verification",
        fake_resolve,
    )
    monkeypatch.setattr(
        MatchmakingPaymentService,
        "handle_matchmaking_payment_success",
        fake_handle_success,
    )

    response = client.get(
        "/matchmaking/payment-callback?tx_ref=KIMBELA_MATCH_1_999999&status=session_expired",
        follow_redirects=False,
    )

    assert response.status_code == 302
    db.session.refresh(matchmaking_payment)
    db.session.refresh(matchmaking_request)
    assert matchmaking_payment.status == "completed"
    assert matchmaking_payment.payment_status == "paid"
    assert matchmaking_payment.gateway_status == "successful"
    assert matchmaking_request.payment_status == "completed"
    assert matchmaking_request.status == "active"


def test_marketplace_service_payment_callback_recovers_success_via_reference_verification(
    client, db, user, login, monkeypatch
):
    from models import (
        MarketplaceCategory,
        MarketplacePayment,
        MarketplaceService,
        MarketplaceSubscription,
    )
    from payments.payment_service import MarketplacePaymentService
    from time_utils import utcnow

    category = MarketplaceCategory(name="Design", slug="design")
    db.session.add(category)
    db.session.flush()

    subscription = MarketplaceSubscription(
        name="Starter",
        slug="starter-market",
        price_tokens=100,
        price_usd=2.0,
    )
    db.session.add(subscription)
    db.session.flush()

    service = MarketplaceService(
        seller_id=user.id,
        category_id=category.id,
        title="Logo Design",
        slug="logo-design-test",
        description="Design service",
        price=5000,
        status="awaiting_subscription",
        subscription_status="free",
    )
    db.session.add(service)
    db.session.flush()

    payment = MarketplacePayment(
        user_id=user.id,
        service_id=service.id,
        subscription_id=subscription.id,
        amount=2756.59,
        currency="USD",
        tokens_paid=275659,
        gateway_reference="KIMBELA-MP-999999-1",
        status="pending",
        gateway_status="initiated",
    )
    db.session.add(payment)
    db.session.commit()

    login()

    def fake_resolve(self, tx_ref=None, transaction_id=None):
        assert tx_ref == "KIMBELA-MP-999999-1"
        return {
            "success": True,
            "verified_status": "successful",
            "data": {"id": 30303, "status": "successful"},
            "source": "tx_ref",
        }

    monkeypatch.setattr(
        MarketplacePaymentService,
        "resolve_flutterwave_verification",
        fake_resolve,
    )

    response = client.get(
        "/marketplace/payment-callback?tx_ref=KIMBELA-MP-999999-1&status=session_expired",
        follow_redirects=False,
    )

    assert response.status_code == 302
    db.session.refresh(payment)
    db.session.refresh(service)
    assert payment.status == "completed"
    assert payment.gateway_status == "successful"
    assert payment.gateway_payment_id == "30303"
    assert payment.paid_at is not None
    assert service.subscription_status == "active"
    assert service.status == "pending"


def test_flutterwave_webhook_rejects_invalid_hash(client, app):
    app.config["FLUTTERWAVE_WEBHOOK_HASH"] = "expected-hash"

    response = client.post(
        "/flutterwave/webhook",
        json={"event": "charge.completed", "data": {"tx_ref": "KIMBELA_AD_1_999999"}},
        headers={"verif-hash": "wrong-hash"},
    )

    assert response.status_code == 401
    assert response.get_json()["message"] == "Invalid signature"


def test_flutterwave_webhook_processes_ad_payment(client, db, user, app, monkeypatch):
    from models import AdCampaign, PaymentTransaction
    from payments.payment_service import BasePaymentService
    from payments.payment_service_ad import AdCampaignPaymentService

    campaign = AdCampaign(
        user_id=user.id,
        title="Webhook Campaign",
        description="Campaign for webhook test",
        budget=2500.0,
        daily_budget=250.0,
        duration_days=10,
        payment_status="pending",
        status="pending",
    )
    db.session.add(campaign)
    db.session.flush()

    transaction = PaymentTransaction(
        user_id=user.id,
        campaign_id=campaign.id,
        amount=campaign.budget,
        currency="USD",
        gateway="flutterwave",
        gateway_reference="KIMBELA_AD_1_999999",
        gateway_payment_id="",
        status="pending",
        transaction_type="ad_campaign",
    )
    db.session.add(transaction)
    db.session.commit()

    app.config["FLUTTERWAVE_WEBHOOK_HASH"] = "shared-secret"

    def fake_resolve(self, tx_ref=None, transaction_id=None):
        assert tx_ref == "KIMBELA_AD_1_999999"
        assert transaction_id == 50101
        return {
            "success": True,
            "verified_status": "successful",
            "data": {"id": 50101, "status": "successful", "amount": 2500.0},
        }

    def fake_handle_success(self, transaction_id, payment_data=None):
        tx = PaymentTransaction.query.get(transaction_id)
        tx.status = "completed"
        tx.gateway_status = payment_data["status"]
        tx.gateway_payment_id = str(payment_data["id"])
        db.session.commit()
        return True

    monkeypatch.setattr(
        BasePaymentService, "resolve_flutterwave_verification", fake_resolve
    )
    monkeypatch.setattr(
        AdCampaignPaymentService, "handle_ad_payment_success", fake_handle_success
    )

    response = client.post(
        "/flutterwave/webhook",
        json={
            "event": "charge.completed",
            "data": {"tx_ref": "KIMBELA_AD_1_999999", "id": 50101},
        },
        headers={"verif-hash": "shared-secret"},
    )

    assert response.status_code == 200
    assert response.get_json()["status"] == "success"
    db.session.refresh(transaction)
    assert transaction.status == "completed"
    assert transaction.gateway_status == "successful"
    assert transaction.gateway_payment_id == "50101"


def test_flutterwave_webhook_processes_matchmaking_payment(
    client, db, user, app, monkeypatch
):
    from models import MatchmakingPackage, MatchmakingPayments, MatchmakingRequest
    from payments.payment_service import BasePaymentService, MatchmakingPaymentService

    package = MatchmakingPackage(
        name="Premium Match",
        description="Webhook package",
        price=10.0,
        duration_days=30,
    )
    db.session.add(package)
    db.session.flush()

    matchmaking_request = MatchmakingRequest(
        user_id=user.id,
        package_id=package.id,
        about_you="About me",
        ideal_partner="Ideal partner",
        status="pending",
        payment_status="pending",
    )
    db.session.add(matchmaking_request)
    db.session.flush()

    matchmaking_payment = MatchmakingPayments(
        user_id=user.id,
        matchmaking_request_id=matchmaking_request.id,
        package_id=package.id,
        amount=2756.59,
        currency="USD",
        gateway_reference="KIMBELA_MATCH_1_999999",
        status="pending",
        payment_status="pending",
    )
    db.session.add(matchmaking_payment)
    db.session.commit()

    app.config["FLUTTERWAVE_WEBHOOK_HASH"] = "shared-secret"

    def fake_resolve(self, tx_ref=None, transaction_id=None):
        assert tx_ref == "KIMBELA_MATCH_1_999999"
        return {
            "success": True,
            "verified_status": "successful",
            "data": {"id": 20202, "status": "successful"},
        }

    def fake_handle_success(self, payment, flutterwave_data):
        payment.status = "completed"
        payment.payment_status = "paid"
        payment.gateway_status = flutterwave_data["status"]
        db.session.commit()
        return True

    monkeypatch.setattr(
        BasePaymentService, "resolve_flutterwave_verification", fake_resolve
    )
    monkeypatch.setattr(
        MatchmakingPaymentService,
        "handle_matchmaking_payment_success",
        fake_handle_success,
    )

    response = client.post(
        "/flutterwave/webhook",
        json={
            "event": "charge.completed",
            "data": {"tx_ref": "KIMBELA_MATCH_1_999999", "id": 20202},
        },
        headers={"verif-hash": "shared-secret"},
    )

    assert response.status_code == 200
    assert response.get_json()["status"] == "success"
    db.session.refresh(matchmaking_payment)
    assert matchmaking_payment.status == "completed"
    assert matchmaking_payment.payment_status == "paid"
    assert matchmaking_payment.gateway_status == "successful"


def test_flutterwave_webhook_processes_marketplace_subscription_payment(
    client, db, user, app, monkeypatch
):
    from models import MarketplacePayment, MarketplaceSubscription
    from payments.payment_service import BasePaymentService, MarketplacePaymentService
    from time_utils import utcnow

    subscription = MarketplaceSubscription(
        name="Starter",
        slug="starter-webhook",
        price_tokens=100,
        price_usd=2.0,
    )
    db.session.add(subscription)
    db.session.flush()

    payment = MarketplacePayment(
        user_id=user.id,
        subscription_id=subscription.id,
        amount=2756.59,
        currency="USD",
        tokens_paid=275659,
        gateway="flutterwave",
        gateway_reference="KIMBELA-SUB-999999-1",
        status="pending",
        gateway_status="initiated",
        start_date=utcnow(),
    )
    db.session.add(payment)
    db.session.commit()

    app.config["FLUTTERWAVE_WEBHOOK_HASH"] = "shared-secret"

    def fake_resolve(self, tx_ref=None, transaction_id=None):
        assert tx_ref == "KIMBELA-SUB-999999-1"
        return {
            "success": True,
            "verified_status": "successful",
            "data": {"id": 30303, "status": "successful"},
        }

    def fake_handle_success(self, marketplace_payment, flutterwave_data):
        marketplace_payment.status = "completed"
        marketplace_payment.gateway_status = flutterwave_data["status"]
        marketplace_payment.gateway_payment_id = str(flutterwave_data["id"])
        db.session.commit()
        return True

    monkeypatch.setattr(
        BasePaymentService, "resolve_flutterwave_verification", fake_resolve
    )
    monkeypatch.setattr(
        MarketplacePaymentService,
        "handle_marketplace_payment_success",
        fake_handle_success,
    )

    response = client.post(
        "/flutterwave/webhook",
        json={
            "event": "charge.completed",
            "data": {"tx_ref": "KIMBELA-SUB-999999-1", "id": 30303},
        },
        headers={"verif-hash": "shared-secret"},
    )

    assert response.status_code == 200
    assert response.get_json()["status"] == "success"
    db.session.refresh(payment)
    assert payment.status == "completed"
    assert payment.gateway_status == "successful"
    assert payment.gateway_payment_id == "30303"
