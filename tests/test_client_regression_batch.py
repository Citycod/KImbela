from datetime import date, timedelta
from io import BytesIO
from pathlib import Path
import uuid


def _user(db, *, admin=False, super_admin=False, ai=False):
    from models import User

    token = uuid.uuid4().hex[:10]
    account = User(
        first_name="Client",
        last_name="Regression",
        email=f"client-{token}@example.com",
        phone_number=f"+1555{token[:7]}",
        dob=date(1990, 1, 1),
        gender="Female",
        city="Lagos",
        state="Lagos",
        country="Nigeria",
        marital_status="Single",
        is_active=True,
        is_admin=admin,
        is_super_admin=super_admin,
        is_ai_persona=ai,
    )
    account.set_password("StrongPassw0rd!")
    db.session.add(account)
    db.session.commit()
    return account


def _login(client, account):
    with client.session_transaction() as session:
        session["_user_id"] = str(account.id)
        session["_fresh"] = True
    from flask import g

    g._login_user = account


def _category(db):
    from models import MarketplaceCategory

    token = uuid.uuid4().hex[:8]
    category = MarketplaceCategory(
        name=f"Regression {token}", slug=f"regression-{token}", is_active=True
    )
    db.session.add(category)
    db.session.commit()
    return category


def _listing(db, seller, category, **overrides):
    from models import MarketplaceService

    token = uuid.uuid4().hex[:8]
    values = {
        "seller_id": seller.id,
        "category_id": category.id,
        "title": f"Regression Listing {token}",
        "slug": f"regression-listing-{token}",
        "description": "Regression listing description",
        "short_description": "Regression listing",
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
    listing = MarketplaceService(**values)
    db.session.add(listing)
    db.session.commit()
    return listing


def _listing_form(category, listing=None, **overrides):
    values = {
        "title": listing.title if listing else "Regression Listing Form",
        "category_id": str(category.id),
        "description": listing.description if listing else "Regression description",
        "short_description": listing.short_description if listing else "Regression listing",
        "service_type": "service",
        "pricing_mode": listing.pricing_mode if listing else "fixed",
        "price": str(listing.price or "") if listing else "25",
        "currency": listing.currency if listing else "USD",
        "country": listing.country if listing else "Nigeria",
        "state": listing.state if listing else "Lagos",
        "city": listing.city if listing else "Lagos",
        "status": listing.status if listing else "active",
    }
    values.update(overrides)
    return values


def test_marketplace_uses_stable_canonical_detail_url_and_keeps_legacy_links(db, client, monkeypatch):
    import importlib

    market_module = importlib.import_module("marketplace.market")
    monkeypatch.setattr(market_module.cache, "get", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(market_module.cache, "set", lambda *_args, **_kwargs: True)
    seller = _user(db)
    category = _category(db)
    legacy = _listing(db, seller, category, slug="legacy/listing-path")

    page = client.get("/main_market")
    assert page.status_code == 200
    assert f'href="/service/{legacy.id}"'.encode() in page.data
    assert b'href="/service/legacy/listing-path"' not in page.data
    assert client.get(f"/service/{legacy.id}").status_code == 200
    assert client.get("/service/legacy/listing-path").status_code == 200
    assert client.get("/service/999999999").status_code == 404

    seller_page = client.get(f"/seller/{seller.id}")
    assert f'href="/service/{legacy.id}"'.encode() in seller_page.data


def test_marketplace_admin_and_dashboard_links_use_canonical_detail_url(db, client, monkeypatch):
    import importlib

    class NoopCache:
        def get(self, *_args, **_kwargs):
            return None

        def set(self, *_args, **_kwargs):
            return True

    cache_module = importlib.import_module("cache_utils")
    monkeypatch.setattr(cache_module, "get_cache", lambda: NoopCache())
    seller = _user(db)
    admin = _user(db, super_admin=True)
    category = _category(db)
    listing = _listing(db, seller, category)

    _login(client, seller)
    dashboard = client.get("/seller_dashboard")
    assert f'href="/service/{listing.id}"'.encode() in dashboard.data
    api = client.get("/api/dashboard/services?page=1").get_json()
    assert api["services"][0]["detail_url"] == f"/service/{listing.id}"

    _login(client, admin)
    moderation = client.get("/admin/marketplace")
    assert f'href="/service/{listing.id}"'.encode() in moderation.data


def test_archived_listing_is_hidden_from_buyer_but_manageable_by_owner(db, client):
    seller = _user(db)
    buyer = _user(db)
    category = _category(db)
    listing = _listing(db, seller, category, status="archived")

    _login(client, buyer)
    denied = client.get(f"/service/{listing.id}")
    assert denied.status_code == 302
    assert denied.location.endswith("/main_market")

    _login(client, seller)
    assert client.get(f"/service/{listing.id}").status_code == 200


def test_seller_call_and_whatsapp_are_visible_for_both_pricing_modes(db, client):
    seller = _user(db)
    category = _category(db)
    fixed = _listing(
        db,
        seller,
        category,
        phone_number="0801 234 5678",
        whatsapp_number="+234 802 345 6789",
        contact_methods="[]",
    )
    contact = _listing(
        db,
        seller,
        category,
        pricing_mode="contact",
        price=None,
        phone_number="0801 234 5678",
        whatsapp_number="+234 802 345 6789",
        contact_methods="[]",
    )

    for listing in (fixed, contact):
        response = client.get(f"/service/{listing.id}")
        assert response.status_code == 200
        assert b"Seller Contact" in response.data
        assert b"Call Seller" in response.data
        assert b'href="tel:+2348012345678"' in response.data
        assert b"WhatsApp Seller" in response.data
        assert b'href="https://wa.me/2348023456789?' in response.data


def test_invalid_or_missing_listing_phone_has_safe_fallback(db, client):
    seller = _user(db)
    seller.phone_number = "invalid-private-account-number"
    db.session.commit()
    category = _category(db)
    listing = _listing(
        db,
        seller,
        category,
        phone_number="not-a-number",
        whatsapp_number="123",
        email=None,
        contact_methods="[]",
    )
    response = client.get(f"/service/{listing.id}")
    assert response.status_code == 200
    assert b"has not added a valid Marketplace phone number" in response.data
    assert b"tel:" not in response.data
    assert b"wa.me/" not in response.data
    assert seller.email.encode() not in response.data


def test_legacy_listing_uses_existing_public_seller_phone_fallback(db, client):
    seller = _user(db)
    seller.phone_number = "+234 803 456 7890"
    db.session.commit()
    category = _category(db)
    fixed = _listing(
        db,
        seller,
        category,
        phone_number=None,
        whatsapp_number=None,
        contact_methods='["phone", "whatsapp"]',
    )
    contact = _listing(
        db,
        seller,
        category,
        pricing_mode="contact",
        price=None,
        phone_number="",
        whatsapp_number="",
        contact_methods='["phone", "whatsapp"]',
    )

    for listing in (fixed, contact):
        response = client.get(f"/service/{listing.id}")
        assert response.status_code == 200
        assert b'href="tel:+2348034567890"' in response.data
        assert b'href="https://wa.me/2348034567890?' in response.data
        assert b"+2348034567890" in response.data


def test_public_phone_fallback_respects_whatsapp_contact_consent(db, client):
    seller = _user(db)
    seller.phone_number = "+234 804 567 8901"
    db.session.commit()
    category = _category(db)
    listing = _listing(
        db,
        seller,
        category,
        phone_number=None,
        whatsapp_number=None,
        contact_methods="[]",
    )

    response = client.get(f"/service/{listing.id}")
    assert response.status_code == 200
    assert b'href="tel:+2348045678901"' in response.data
    assert b"wa.me/2348045678901" not in response.data


def test_listing_never_uses_unrelated_viewer_phone_as_contact_fallback(db, client):
    seller = _user(db)
    buyer = _user(db)
    seller.phone_number = "+234 805 678 9012"
    buyer.phone_number = "+234 999 999 9999"
    db.session.commit()
    category = _category(db)
    listing = _listing(
        db,
        seller,
        category,
        phone_number=None,
        whatsapp_number=None,
        contact_methods='["phone", "whatsapp"]',
    )
    _login(client, buyer)

    response = client.get(f"/service/{listing.id}")
    assert response.status_code == 200
    assert b"+2348056789012" in response.data
    assert b"2349999999999" not in response.data


def test_listing_status_update_is_owned_and_validated(db, client):
    seller = _user(db)
    stranger = _user(db)
    category = _category(db)
    listing = _listing(db, seller, category)

    _login(client, seller)
    dashboard = client.get("/seller_dashboard")
    body = dashboard.get_data(as_text=True)
    assert dashboard.status_code == 200
    assert f'action="/toggle-status/{listing.id}"' in body
    assert 'method="POST"' in body
    assert 'name="status"' in body
    assert "Update Status" in body
    dashboard_api = client.get("/api/dashboard/services?page=1").get_json()
    api_listing = next(
        item for item in dashboard_api["services"] if item["id"] == listing.id
    )
    assert api_listing["status_update_url"] == f"/toggle-status/{listing.id}"
    assert api_listing["allowed_statuses"] == ["active", "paused", "draft", "pending"]

    updated = client.post(
        f"/toggle-status/{listing.id}",
        data={"status": "paused", "dashboard_form": "1"},
        follow_redirects=True,
    )
    assert updated.status_code == 200
    assert b"Listing status updated successfully!" in updated.data
    db.session.refresh(listing)
    assert listing.status == "paused"

    invalid = client.post(
        f"/toggle-status/{listing.id}",
        data={"status": "approved-by-seller"},
    )
    assert invalid.status_code == 400
    db.session.refresh(listing)
    assert listing.status == "paused"
    invalid_form = client.post(
        f"/toggle-status/{listing.id}",
        data={"status": "approved-by-seller", "dashboard_form": "1"},
        follow_redirects=True,
    )
    assert invalid_form.status_code == 200
    assert b"That status change is not allowed for this listing." in invalid_form.data
    db.session.refresh(listing)
    assert listing.status == "paused"

    awaiting_subscription = _listing(
        db,
        seller,
        category,
        status="awaiting_subscription",
        subscription_status="pending",
    )
    blocked_transition = client.post(
        f"/toggle-status/{awaiting_subscription.id}",
        data={"status": "active"},
    )
    assert blocked_transition.status_code == 400
    db.session.refresh(awaiting_subscription)
    assert awaiting_subscription.status == "awaiting_subscription"

    _login(client, stranger)
    denied = client.post(
        f"/toggle-status/{listing.id}", data={"status": "active"}
    )
    assert denied.status_code == 403


def test_listing_type_is_explicit_mutually_exclusive_and_pricing_independent(db, client):
    from models import MarketplaceService

    seller = _user(db)
    category = _category(db)
    _login(client, seller)

    create_page = client.get("/create_service")
    body = create_page.get_data(as_text=True)
    assert create_page.status_code == 200
    assert 'name="service_type" value="service" class="hidden" required' in body
    assert 'name="service_type" value="service" class="hidden" checked' not in body
    assert body.count('<input type="radio" name="service_type"') == 2

    missing_type = client.post(
        "/create_service",
        data=_listing_form(category, service_type="", title="Missing Type"),
    )
    assert missing_type.status_code == 302
    assert MarketplaceService.query.filter_by(
        seller_id=seller.id, title="Missing Type"
    ).count() == 0

    service_fixed = client.post(
        "/create_service",
        data=_listing_form(
            category,
            title="Fixed Service",
            service_type="service",
            pricing_mode="fixed",
            price="35",
        ),
    )
    assert service_fixed.status_code == 302
    stored_service = MarketplaceService.query.filter_by(
        seller_id=seller.id, title="Fixed Service"
    ).one()
    assert stored_service.service_type == "service"
    assert stored_service.listing_type == "service"
    assert stored_service.listing_type_label == "Service"
    assert stored_service.fulfilment_type is None
    assert stored_service.pricing_mode == "fixed"

    product_contact = client.post(
        "/create_service",
        data=_listing_form(
            category,
            title="Contact Product",
            service_type="digital",
            pricing_mode="contact",
            price="",
        ),
    )
    assert product_contact.status_code == 302
    stored_product = MarketplaceService.query.filter_by(
        seller_id=seller.id, title="Contact Product"
    ).one()
    assert stored_product.service_type == "digital"
    assert stored_product.listing_type == "product"
    assert stored_product.listing_type_label == "Product"
    assert stored_product.fulfilment_type == "physical"
    assert stored_product.fulfilment_type_label == "Physical"
    assert stored_product.pricing_mode == "contact"
    assert stored_product.price is None

    edited = client.post(
        f"/edit/{stored_product.id}",
        data=_listing_form(
            category,
            stored_product,
            title=stored_product.title,
            service_type="service",
            pricing_mode="contact",
            price="",
        ),
    )
    assert edited.status_code == 302
    db.session.refresh(stored_product)
    assert stored_product.service_type == "service"
    assert stored_product.listing_type_label == "Service"
    assert stored_product.fulfilment_type is None
    assert stored_product.pricing_mode == "contact"

    switched_back = client.post(
        f"/edit/{stored_product.id}",
        data=_listing_form(
            category,
            stored_product,
            title=stored_product.title,
            service_type="digital",
            pricing_mode="contact",
            price="",
        ),
    )
    assert switched_back.status_code == 302
    db.session.refresh(stored_product)
    assert stored_product.listing_type_label == "Product"
    assert stored_product.fulfilment_type_label == "Physical"
    assert stored_product.pricing_mode == "contact"


def test_marketplace_listing_and_fulfilment_labels_are_distinct_on_all_surfaces(
    db, client, monkeypatch
):
    import importlib

    market_module = importlib.import_module("marketplace.market")
    monkeypatch.setattr(market_module.cache, "get", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(market_module.cache, "set", lambda *_args, **_kwargs: True)

    seller = _user(db)
    super_admin = _user(db, super_admin=True)
    category = _category(db)
    service = _listing(
        db,
        seller,
        category,
        title="Ordinary Service Offering",
        service_type="service",
        digital_file=None,
    )
    physical = _listing(
        db,
        seller,
        category,
        title="Physical Product Offering",
        service_type="digital",
        digital_file=None,
    )
    digital = _listing(
        db,
        seller,
        category,
        title="Downloadable Product Offering",
        service_type="digital",
        digital_file="https://cdn.example/downloadable-guide.pdf",
    )

    assert (service.listing_type_label, service.fulfilment_type_label) == (
        "Service",
        None,
    )
    assert (physical.listing_type_label, physical.fulfilment_type_label) == (
        "Product",
        "Physical",
    )
    assert (digital.listing_type_label, digital.fulfilment_type_label) == (
        "Product",
        "Digital",
    )

    service_detail = client.get(f"/service/{service.id}").get_data(as_text=True)
    assert 'data-primary-listing-type-label>\n                                    Service' in service_detail
    assert "data-primary-fulfilment-type-label" not in service_detail

    physical_detail = client.get(f"/service/{physical.id}").get_data(as_text=True)
    assert 'data-primary-listing-type-label>\n                                    Product' in physical_detail
    assert 'data-primary-fulfilment-type-label>\n                                    Physical' in physical_detail

    digital_detail = client.get(f"/service/{digital.id}").get_data(as_text=True)
    assert 'data-primary-listing-type-label>\n                                    Product' in digital_detail
    assert 'data-primary-fulfilment-type-label>\n                                    Digital' in digital_detail

    market = client.get("/main_market").get_data(as_text=True)
    assert market.count("data-listing-type-label") >= 3
    assert "Ordinary Service Offering" in market
    assert "Physical Product Offering" in market
    assert "Downloadable Product Offering" in market

    seller_page = client.get(f"/seller/{seller.id}").get_data(as_text=True)
    assert seller_page.count("data-listing-type-label") >= 3
    reviews = client.get(f"/service/{service.slug}/reviews").get_data(as_text=True)
    assert 'data-listing-type-label>Service</span>' in reviews

    _login(client, seller)
    dashboard = client.get("/seller_dashboard").get_data(as_text=True)
    assert "data-listing-type-label" in dashboard
    dashboard_api = client.get("/api/dashboard/services?page=1").get_json()
    labels = {
        item["id"]: (
            item["service_type"],
            item["listing_type_label"],
            item["fulfilment_type_label"],
        )
        for item in dashboard_api["services"]
    }
    assert labels[service.id] == ("service", "Service", None)
    assert labels[physical.id] == ("digital", "Product", "Physical")
    assert labels[digital.id] == ("digital", "Product", "Digital")

    _login(client, super_admin)
    moderation = client.get("/admin/marketplace").get_data(as_text=True)
    assert moderation.count("data-listing-type-label") >= 3
    assert moderation.count("data-fulfilment-type-label") >= 2


def test_templates_do_not_title_case_legacy_service_type_as_display_label():
    template_names = (
        "service_detail.html",
        "seller_profile.html",
        "main_market.html",
        "seller_dashboard.html",
        "admin_marketplace.html",
        "service_reviews.html",
    )
    for template_name in template_names:
        source = Path("templates", template_name).read_text()
        assert "service.service_type|title" not in source


def test_public_post_surfaces_hide_ai_labels_and_keep_internal_identity(db, client):
    from models import AIPersona, Comment, Group, Post
    from time_utils import utcnow

    viewer = _user(db)
    ai_user = _user(db, ai=True)
    normal_user = _user(db)
    historical = Post(
        content="Historical managed post",
        author_id=ai_user.id,
        created_at=utcnow() - timedelta(days=30),
    )
    current = Post(content="Current managed post", author_id=ai_user.id)
    normal = Post(content="Normal public post", author_id=normal_user.id)
    group = Group(
        name=f"AI display group {uuid.uuid4().hex[:8]}",
        is_active=True,
        created_by=viewer.id,
    )
    db.session.add_all((historical, current, normal, group))
    db.session.flush()
    group.members.append(viewer)
    group_post = Post(
        content="Managed group post", author_id=ai_user.id, group_id=group.id
    )
    db.session.add(group_post)
    db.session.flush()
    db.session.add(
        Comment(content="Managed group reply", author_id=ai_user.id, post_id=group_post.id)
    )
    persona = AIPersona(
        user_id=ai_user.id,
        name=ai_user.full_name,
        bio_disclosure="Internal managed persona",
        personality="Friendly",
        interests=["community"],
        forbidden_actions=[],
        escalation_rule="Escalate unsafe requests",
        is_active=True,
    )
    db.session.add(persona)
    db.session.commit()
    _login(client, viewer)

    feed = client.get("/user_dashboard?limit=50")
    profile = client.get(f"/profile/{ai_user.public_id}")
    group_page = client.get(f"/groups/{group.id}")
    detail = client.get(f"/post/{current.public_id}")

    assert feed.status_code == profile.status_code == group_page.status_code == detail.status_code == 200
    assert b"Historical managed post" in feed.data
    assert b"Current managed post" in feed.data
    assert b"Normal public post" in feed.data
    assert b"Current managed post" in profile.data
    assert b"Managed group post" in group_page.data
    assert b"Managed group reply" in group_page.data
    assert b"Current managed post" in detail.data

    public_templates = (
        "templates/_post_card.html",
        "templates/_posts_partial.html",
        "templates/user_dashboard.html",
        "templates/group_detail.html",
    )
    for template_name in public_templates:
        source = Path(template_name).read_text()
        assert ">AI</span>" not in source
        assert "AI · Automated" not in source

    assert ai_user.is_ai_persona is True
    assert db.session.get(AIPersona, persona.id).user_id == ai_user.id
    assert "AI · Automated" in Path("templates/admin_ai_users.html").read_text()


def test_feed_post_owner_actions_and_server_authorization(db, client):
    from models import Post

    owner = _user(db)
    stranger = _user(db)
    editable = Post(content="Before edit", author_id=owner.id)
    deletable = Post(content="Delete me", author_id=owner.id)
    db.session.add_all((editable, deletable))
    db.session.commit()

    _login(client, stranger)
    assert client.post("/edit_post", data={"post_id": editable.id, "content": "No"}).status_code == 403
    assert client.post(f"/delete_post/{deletable.id}").status_code == 403

    _login(client, owner)
    assert client.post("/edit_post", data={"post_id": editable.id, "content": "After edit"}).status_code == 200
    db.session.refresh(editable)
    assert editable.content == "After edit"
    assert client.post(f"/delete_post/{deletable.id}").status_code == 200
    assert db.session.get(Post, deletable.id) is None

    profile = client.get(f"/{owner.id}")
    assert b'class="post-text ' in profile.data
    assert b'id="editPostModal"' in profile.data


def test_ai_post_cannot_use_normal_owner_edit_or_delete_routes(db, client):
    from models import Post

    ai = _user(db, ai=True)
    post = Post(content="Managed AI content", author_id=ai.id)
    db.session.add(post)
    db.session.commit()
    _login(client, ai)
    assert client.post("/edit_post", data={"post_id": post.id, "content": "No"}).status_code == 403
    assert client.post(f"/delete_post/{post.id}").status_code == 403


def test_group_post_owner_management_preserves_membership_privacy_and_matchmaking(db, client, app, monkeypatch):
    from models import Group, Post

    owner = _user(db)
    outsider = _user(db)
    admin = _user(db, admin=True)
    group = Group(name="Private Owners", is_private=True, is_active=True, created_by=owner.id)
    matchmaking = Group(name="Renamed Match Group", is_active=True, created_by=admin.id)
    db.session.add_all((group, matchmaking))
    db.session.flush()
    group.members.append(owner)
    matchmaking.members.append(owner)
    matchmaking.members.append(admin)
    group_post = Post(content="Group before", author_id=owner.id, group_id=group.id)
    protected_user_post = Post(content="Protected", author_id=owner.id, group_id=matchmaking.id)
    protected_admin_post = Post(content="Admin protected", author_id=admin.id, group_id=matchmaking.id)
    db.session.add_all((group_post, protected_user_post, protected_admin_post))
    db.session.commit()
    monkeypatch.setitem(app.config, "MATCHMAKING_GROUP_ID", matchmaking.id)

    _login(client, outsider)
    assert client.post(f"/edit_post/{group_post.id}", data={"post_content": "No"}).status_code == 403
    assert client.post(f"/delete_post/{group_post.id}").status_code == 403

    _login(client, owner)
    assert client.post(f"/edit_post/{group_post.id}", data={"post_content": "Group after"}).status_code == 200
    db.session.refresh(group_post)
    assert group_post.content == "Group after"
    assert client.post(f"/edit_post/{protected_user_post.id}", data={"post_content": "No"}).status_code == 403
    assert client.post(f"/delete_post/{protected_user_post.id}").status_code == 403
    page = client.get(f"/groups/{matchmaking.id}")
    assert f"editPost({protected_user_post.id})".encode() not in page.data

    _login(client, admin)
    assert client.post(f"/edit_post/{protected_admin_post.id}", data={"post_content": "Admin after"}).status_code == 200
    assert client.post(f"/delete_post/{protected_admin_post.id}").status_code == 200

    _login(client, owner)
    assert client.post(f"/delete_post/{group_post.id}").status_code == 200


def test_admin_profile_link_uses_dedicated_editor_and_cannot_change_privileges(db, client, monkeypatch):
    import importlib

    admin = _user(db, admin=True, super_admin=True)
    admin.admin_permissions = '["reports_view"]'
    db.session.commit()
    _login(client, admin)

    dashboard = client.get("/admin_dashboard")
    assert f'href="/{admin.id}"'.encode() in dashboard.data
    profile = client.get(f"/{admin.id}")
    assert profile.status_code == 200
    assert f'href="/{admin.id}/edit"'.encode() in profile.data
    assert b'id="editProfileModal"' not in profile.data

    editor = client.get(f"/{admin.id}/edit")
    assert editor.status_code == 200
    assert b'id="profileForm"' in editor.data

    user_module = importlib.import_module("users.user")
    monkeypatch.setattr(
        user_module.cloudinary.uploader,
        "upload",
        lambda *_args, **_kwargs: {"secure_url": "https://cdn.example/admin.webp"},
    )
    response = client.post(
        f"/{admin.id}/edit",
        data={
            "first_name": "Updated",
            "last_name": "Admin",
            "is_super_admin": "true",
            "admin_permissions": '["all"]',
            "profile_pic": (BytesIO(b"image"), "admin.png"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 302
    db.session.refresh(admin)
    assert admin.first_name == "Updated"
    assert admin.profile_pic == "https://cdn.example/admin.webp"
    assert admin.is_super_admin is True
    assert admin.admin_permissions == '["reports_view"]'
