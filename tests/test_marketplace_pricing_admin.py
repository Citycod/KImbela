from datetime import date
from io import BytesIO
from pathlib import Path
import uuid


def _make_user(db, *, super_admin=False, admin=False, test_user=False, ai=False):
    from models import User

    token = uuid.uuid4().hex[:10]
    user = User(
        first_name="Market",
        last_name="Tester",
        email=f"market-{token}@example.com",
        phone_number=f"+1555{token[:7]}",
        dob=date(1990, 6, 15),
        gender="Female",
        city="Lagos",
        state="Lagos",
        country="Nigeria",
        marital_status="Single",
        is_active=True,
        is_super_admin=super_admin,
        is_admin=admin,
        is_test_user=test_user,
        is_ai_persona=ai,
    )
    user.set_password("StrongPassw0rd!")
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, user):
    with client.session_transaction() as session:
        session["_user_id"] = str(user.id)
        session["_fresh"] = True
    from flask import g

    g._login_user = user


def _category(db):
    from models import MarketplaceCategory

    token = uuid.uuid4().hex[:8]
    category = MarketplaceCategory(name=f"Goods {token}", slug=f"goods-{token}", is_active=True)
    db.session.add(category)
    db.session.commit()
    return category


def _listing(db, seller, category, **overrides):
    from models import MarketplaceService

    token = uuid.uuid4().hex[:10]
    values = {
        "seller_id": seller.id,
        "category_id": category.id,
        "title": f"Listing {token}",
        "slug": f"listing-{token}",
        "description": "A marketplace listing",
        "short_description": "Marketplace listing",
        "status": "active",
        "subscription_status": "free",
        "pricing_mode": "fixed",
        "price": 25,
        "currency": "USD",
        "country": "Nigeria",
        "state": "Lagos",
        "city": "Lagos",
    }
    values.update(overrides)
    service = MarketplaceService(**values)
    db.session.add(service)
    db.session.commit()
    return service


def _listing_form(category, **overrides):
    data = {
        "title": "Handmade Item",
        "category_id": str(category.id),
        "description": "A carefully made item",
        "short_description": "Carefully made",
        "service_type": "service",
        "pricing_mode": "fixed",
        "price": "25.00",
        "currency": "USD",
        "country": "Nigeria",
        "state": "Lagos",
        "city": "Lagos",
        "contact_messenger": "on",
    }
    data.update(overrides)
    return data


def test_fixed_price_requires_positive_number_and_valid_price_saves(db, client):
    from models import MarketplaceService

    seller = _make_user(db)
    category = _category(db)
    _login(client, seller)

    response = client.post("/create_service", data=_listing_form(category, price=""))
    assert response.status_code == 302
    assert MarketplaceService.query.filter_by(title="Handmade Item", seller_id=seller.id).count() == 0

    response = client.post("/create_service", data=_listing_form(category, price="29.50"))
    assert response.status_code == 302
    service = MarketplaceService.query.filter_by(
        title="Handmade Item", seller_id=seller.id
    ).order_by(MarketplaceService.id.desc()).first()
    assert service.pricing_mode == "fixed"
    assert float(service.price) == 29.50


def test_contact_price_create_card_detail_and_safe_message_link(app, db, client, monkeypatch):
    from models import MarketplaceService

    seller = _make_user(db)
    buyer = _make_user(db)
    category = _category(db)
    title = f"Contact Handmade {uuid.uuid4().hex[:8]}"
    _login(client, seller)
    response = client.post(
        "/create_service",
        data=_listing_form(category, title=title, pricing_mode="contact", price=""),
    )
    assert response.status_code == 302
    service = MarketplaceService.query.filter_by(
        title=title, seller_id=seller.id
    ).order_by(MarketplaceService.id.desc()).first()
    assert service.pricing_mode == "contact"
    assert service.price is None
    buyer.friends.append(seller)
    db.session.commit()

    buyer_client = app.test_client()
    _login(buyer_client, buyer)
    # The suite keeps one application context open; update Flask-Login's context cache.
    from flask import g
    g._login_user = buyer
    detail = buyer_client.get(f"/service/{service.slug}")
    assert detail.status_code == 200
    assert b"Contact for Price" in detail.data
    assert f'/user_dashboard?chat={seller.id}'.encode() in detail.data
    assert b"Nothing is sent automatically" in detail.data
    assert b"$0.00" not in detail.data
    assert b"None" not in detail.data

    import importlib
    market_module = importlib.import_module("marketplace.market")
    monkeypatch.setattr(market_module.cache, "get", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(market_module.cache, "set", lambda *_args, **_kwargs: True)
    market = buyer_client.get("/main_market")
    assert market.status_code == 200
    assert b"Contact for Price" in market.data


def test_edit_pricing_mode_transitions_and_owner_authorization(db, client):
    seller = _make_user(db)
    stranger = _make_user(db)
    category = _category(db)
    service = _listing(db, seller, category)

    _login(client, seller)
    response = client.post(
        f"/edit/{service.id}",
        data=_listing_form(category, title=service.title, pricing_mode="contact", price=""),
    )
    assert response.status_code == 302
    db.session.refresh(service)
    assert service.pricing_mode == "contact"
    assert service.price is None

    response = client.post(
        f"/edit/{service.id}",
        data=_listing_form(category, title=service.title, pricing_mode="fixed", price=""),
    )
    assert response.status_code == 302
    db.session.refresh(service)
    assert service.pricing_mode == "contact"

    response = client.post(
        f"/edit/{service.id}",
        data=_listing_form(category, title=service.title, pricing_mode="fixed", price="44"),
    )
    assert response.status_code == 302
    db.session.refresh(service)
    assert service.pricing_mode == "fixed"
    assert float(service.price) == 44

    client.get("/logout")
    _login(client, stranger)
    denied = client.post(f"/edit/{service.id}", data=_listing_form(category))
    assert denied.status_code == 403
    db.session.refresh(service)
    assert float(service.price) == 44


def test_seller_can_edit_all_owner_managed_listing_fields(db, client, monkeypatch):
    import importlib

    seller = _make_user(db)
    category = _category(db)
    service = _listing(
        db,
        seller,
        category,
        service_type="service",
        features='["Original feature"]',
        contact_methods='["messenger"]',
        country="Legacy Country",
        state="Legacy State",
        city="Legacy City",
    )
    _login(client, seller)

    edit_page = client.get(f"/edit/{service.id}")
    assert edit_page.status_code == 200
    body = edit_page.get_data(as_text=True)
    assert 'name="service_type" value="service"' in body
    assert 'name="service_type" value="digital"' in body
    assert 'name="currency"' in body
    assert 'name="digital_file"' in body
    assert 'name="contact_messenger"' in body
    assert '<option value="Legacy Country" selected>' in body
    assert '<option value="Legacy State" selected>' in body
    assert '<option value="Legacy City" selected>' in body
    assert body.index('id="editServiceForm"') < body.index('id="updateBtn"') < body.index("</form>")

    market_module = importlib.import_module("marketplace.market")
    monkeypatch.setattr(
        market_module,
        "upload_to_cloudinary",
        lambda _file, folder="marketplace": f"https://cdn.example/{folder}.pdf",
    )

    response = client.post(
        f"/edit/{service.id}",
        data={
            "title": "Updated Digital Product",
            "category_id": str(category.id),
            "description": "Updated complete description",
            "short_description": "Updated short description",
            "service_type": "digital",
            "pricing_mode": "fixed",
            "price": "79.50",
            "currency": "EUR",
            "features": '["Downloadable", "Lifetime access"]',
            "feature_count": "2",
            "duration": "Should be ignored for products",
            "availability": "Always available",
            "country": "Ghana",
            "state": "Greater Accra",
            "city": "Accra",
            "contact_phone": "on",
            "contact_whatsapp": "on",
            "contact_messenger": "on",
            "phone_number": "+233200000000",
            "whatsapp_number": "+233200000001",
            "email": "seller-listing@example.com",
            "status": "paused",
            "digital_file": (BytesIO(b"digital product"), "guide.pdf"),
            # Seller-controlled editing must never include moderation fields.
            "seller_id": "999999",
            "is_featured": "true",
            "subscription_status": "active",
            "earnings": "999999",
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/seller_dashboard")
    db.session.refresh(service)
    assert service.title == "Updated Digital Product"
    assert service.description == "Updated complete description"
    assert service.short_description == "Updated short description"
    assert service.service_type == "digital"
    assert service.pricing_mode == "fixed"
    assert float(service.price) == 79.50
    assert service.currency == "EUR"
    assert service.features_list == ["Downloadable", "Lifetime access"]
    assert service.availability == "Always available"
    assert service.country == "Ghana"
    assert service.state == "Greater Accra"
    assert service.city == "Accra"
    assert set(service.contact_methods_list) == {"phone", "whatsapp", "messenger"}
    assert service.phone_number == "+233200000000"
    assert service.whatsapp_number == "+233200000001"
    assert service.email == "seller-listing@example.com"
    assert service.status == "paused"
    assert service.digital_file == "https://cdn.example/services/digital.pdf"
    assert service.file_name == "guide.pdf"
    assert service.file_type == "pdf"
    assert service.seller_id == seller.id
    assert service.is_featured is False
    assert service.subscription_status == "free"
    assert float(service.earnings or 0) == 0


def test_seller_edit_rejects_unrecognized_type_and_currency(db, client):
    seller = _make_user(db)
    category = _category(db)
    service = _listing(db, seller, category)
    _login(client, seller)

    invalid_type = client.post(
        f"/edit/{service.id}",
        data=_listing_form(category, service_type="admin-only"),
    )
    assert invalid_type.status_code == 400

    invalid_currency = client.post(
        f"/edit/{service.id}",
        data=_listing_form(category, currency="INVALID"),
    )
    assert invalid_currency.status_code == 400
    db.session.refresh(service)
    assert service.service_type == "service"
    assert service.currency == "USD"

def test_contact_price_nonfriend_uses_enabled_seller_contact_method(db, client):
    seller = _make_user(db)
    category = _category(db)
    service = _listing(
        db,
        seller,
        category,
        pricing_mode="contact",
        price=None,
        contact_methods='["email"]',
        email="seller@example.com",
    )
    response = client.get(f"/service/{service.slug}")
    assert response.status_code == 200
    assert b"Email Seller for Price" in response.data
    assert b"mailto:seller@example.com" in response.data
    assert f'/user_dashboard?chat={seller.id}'.encode() not in response.data

def test_product_viewer_uses_contain_and_responsive_bounds():
    source = Path("templates/service_detail.html").read_text()
    assert ".service-image" in source
    assert "object-fit: contain" in source
    assert "max-height: 90%" in source
    assert "@media (max-width: 768px)" in source


def test_super_admin_marketplace_search_and_archive_preserves_payment(db, client):
    from models import MarketplacePayment, MarketplaceSubscription

    super_admin = _make_user(db, super_admin=True)
    seller = _make_user(db)
    category = _category(db)
    service = _listing(db, seller, category, title="Moderate This Product")
    plan = MarketplaceSubscription(
        name="Test Plan",
        slug=f"test-plan-{uuid.uuid4().hex[:8]}",
        price_tokens=10,
        price_usd=2.0,
    )
    db.session.add(plan)
    db.session.flush()
    payment = MarketplacePayment(
        user_id=seller.id,
        subscription_id=plan.id,
        service_id=service.id,
        amount=2,
        tokens_paid=10,
        status="completed",
        gateway_reference=f"test-{uuid.uuid4().hex}",
    )
    db.session.add(payment)
    db.session.commit()

    _login(client, super_admin)
    page = client.get("/admin/marketplace?search=Moderate&pricing_mode=fixed")
    assert page.status_code == 200
    assert b"Moderate This Product" in page.data
    assert b"Inspect" in page.data
    assert b"Archive" in page.data

    response = client.post(f"/admin/marketplace/{service.id}/archive")
    assert response.status_code == 302
    db.session.refresh(service)
    assert service.status == "archived"
    assert MarketplacePayment.query.filter_by(id=payment.id, service_id=service.id).one()


def test_marketplace_moderation_denies_normal_and_limited_admin(db, client):
    for actor in (_make_user(db), _make_user(db, admin=True)):
        _login(client, actor)
        assert client.get("/admin/marketplace").status_code in {302, 403}


def test_admin_marketplace_pagination_is_bounded(app, db, client):
    super_admin = _make_user(db, super_admin=True)
    seller = _make_user(db)
    category = _category(db)
    for index in range(26):
        _listing(db, seller, category, title=f"Paged Product {index:02d}")
    _login(client, super_admin)
    from flask import g
    g._login_user = super_admin

    first = client.get("/admin/marketplace?search=Paged+Product&page=1")
    second = client.get("/admin/marketplace?search=Paged+Product&page=2")
    assert first.status_code == second.status_code == 200
    assert b"Paged Product 25" in first.data
    assert b"Paged Product 00" in second.data
    assert first.data.count(b"/archive") == 25
    assert second.data.count(b"/archive") == 1


def test_seller_delete_archives_listing_with_payment_history(db, client):
    from models import MarketplacePayment, MarketplaceService, MarketplaceSubscription

    seller = _make_user(db)
    category = _category(db)
    service = _listing(db, seller, category)
    plan = MarketplaceSubscription(
        name="Delete Safety Plan",
        slug=f"delete-safety-{uuid.uuid4().hex[:8]}",
        price_tokens=10,
        price_usd=2.0,
    )
    db.session.add(plan)
    db.session.flush()
    payment = MarketplacePayment(
        user_id=seller.id,
        subscription_id=plan.id,
        service_id=service.id,
        amount=2,
        tokens_paid=10,
        status="completed",
        gateway_reference=f"delete-safety-{uuid.uuid4().hex}",
    )
    db.session.add(payment)
    db.session.commit()
    _login(client, seller)

    response = client.post(f"/delete_service/{service.id}")
    assert response.status_code == 200
    assert response.get_json()["archived"] is True
    assert db.session.get(MarketplaceService, service.id).status == "archived"
    assert db.session.get(MarketplacePayment, payment.id).service_id == service.id


def test_contact_price_digital_download_is_not_treated_as_free(db, client):
    seller = _make_user(db)
    category = _category(db)
    service = _listing(
        db,
        seller,
        category,
        pricing_mode="contact",
        price=None,
        digital_file="https://example.invalid/file.pdf",
    )
    response = client.get(f"/download/{service.id}")
    assert response.status_code == 302
    assert response.location.endswith(f"/service/{service.id}")


def test_test_user_deletion_is_marker_gated_and_dependency_safe(db, client):
    from models import Post, User

    super_admin = _make_user(db, super_admin=True)
    clean_test = _make_user(db, test_user=True)
    dependent_test = _make_user(db, test_user=True)
    real_user = _make_user(db)
    post = Post(content="Test history", author_id=dependent_test.id)
    db.session.add(post)
    db.session.commit()
    _login(client, super_admin)

    clean_response = client.post(f"/admin/users/{clean_test.id}/delete-test")
    assert clean_response.status_code == 200
    assert clean_response.get_json()["outcome"] == "deleted"
    assert db.session.get(User, clean_test.id) is None

    dependent_response = client.post(f"/admin/users/{dependent_test.id}/delete-test")
    assert dependent_response.status_code == 200
    assert dependent_response.get_json()["outcome"] == "anonymized"
    db.session.refresh(dependent_test)
    assert dependent_test.is_active is False
    assert dependent_test.is_test_user is False
    assert dependent_test.email.endswith("@invalid.kimbela.local")
    assert db.session.get(Post, post.id).author_id == dependent_test.id

    real_response = client.post(f"/admin/users/{real_user.id}/delete-test")
    assert real_response.status_code == 403
    assert db.session.get(User, real_user.id) is not None


def test_test_user_deletion_denies_non_super_admin(db, client):
    actor = _make_user(db, admin=True)
    target = _make_user(db, test_user=True)
    _login(client, actor)
    assert client.post(f"/admin/users/{target.id}/delete-test").status_code == 403


def test_generated_ai_portraits_are_local_and_ai_identity_stays_admin_only():
    seed_source = Path("seed_ai_personas.py").read_text()
    for filename in (
        "emily-carter-v1.webp",
        "daniel-brooks-v1.webp",
        "ngozi-eze-v1.webp",
        "emeka-obi-v1.webp",
    ):
        assert f"/static/assets/img/ai-personas/{filename}" in seed_source
        assert Path("static/assets/img/ai-personas", filename).is_file()
    assert "res.cloudinary.com/demo" not in seed_source
    assert "AI · Automated" in Path("templates/admin_ai_users.html").read_text()
    assert "AI · Automated" not in Path("templates/public_profile.html").read_text()


def test_new_migration_extends_the_single_previous_head():
    import ast

    versions = Path("migrations/versions")
    revisions = {}
    parents = set()
    for path in versions.glob("*.py"):
        tree = ast.parse(path.read_text())
        values = {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                if node.targets[0].id in {"revision", "down_revision"}:
                    values[node.targets[0].id] = ast.literal_eval(node.value)
        if "revision" in values:
            revisions[values["revision"]] = path
            parent = values.get("down_revision")
            if isinstance(parent, tuple):
                parents.update(parent)
            elif parent:
                parents.add(parent)
    assert set(revisions) - parents == {"e8f1a2b3c4d5"}
    migration = revisions["e8f1a2b3c4d5"].read_text()
    assert 'down_revision = "c7e8f9a0b1c2"' in migration
    assert '"pricing_mode"' in migration
    assert '"is_test_user"' in migration
