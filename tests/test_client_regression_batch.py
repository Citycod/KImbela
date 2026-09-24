from datetime import date
from io import BytesIO
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


def _listing_form(category, listing, **overrides):
    values = {
        "title": listing.title,
        "category_id": str(category.id),
        "description": listing.description,
        "short_description": listing.short_description,
        "service_type": "service",
        "pricing_mode": listing.pricing_mode,
        "price": str(listing.price or ""),
        "currency": listing.currency,
        "country": listing.country,
        "state": listing.state,
        "city": listing.city,
        "status": listing.status,
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
    updated = client.post(
        f"/edit/{listing.id}",
        data=_listing_form(category, listing, status="paused"),
    )
    assert updated.status_code == 302
    db.session.refresh(listing)
    assert listing.status == "paused"

    invalid = client.post(
        f"/edit/{listing.id}",
        data=_listing_form(category, listing, status="approved-by-seller"),
    )
    assert invalid.status_code == 400
    db.session.refresh(listing)
    assert listing.status == "paused"

    _login(client, stranger)
    denied = client.post(
        f"/edit/{listing.id}", data=_listing_form(category, listing)
    )
    assert denied.status_code == 403


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
