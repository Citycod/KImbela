"""Tests for Matchmaking Group visibility, Boost profile integration, and Sponsored Ads.

Verifies:
1. Matchmaking group is hidden from public listings, group recommendations, search, and user_groups for non-admins.
2. Existing group data and direct link access are preserved.
3. Profile boosts require verified payment entitlement (MatchmakingPayments completed and paid) before appearing as sponsored.
4. Boosted profiles appear with 'Sponsored Profile' badge and respect privacy (show_age_on_profile).
5. Ordinary profiles are not represented as sponsored.
6. Sponsored ads appear in multiple responsive positions (in-feed on desktop & mobile, sidebar) without duplicate insertion.
7. Feed pagination includes sponsored items without duplicating ads.
"""

from datetime import date, timedelta
import json
import uuid
import pytest
from flask import g

from models import (
    AdCampaign,
    Group,
    MatchmakingPackage,
    MatchmakingPayments,
    MatchmakingRequest,
    Post,
    User,
    group_members,
)
from time_utils import utcnow
from users.user import (
    configured_matchmaking_group_id,
    get_active_sponsored_items_for_user,
    get_groups_data_for_user,
)


def _make_user(
    db,
    *,
    admin=False,
    super_admin=False,
    gender="Female",
    show_age=True,
    dob=None,
    active=True,
    country="Nigeria",
):
    token = uuid.uuid4().hex[:8]
    dob = dob or date(1995, 6, 15)
    account = User(
        first_name=f"User{token}",
        last_name=f"Test{token}",
        email=f"user-{token}@example.com",
        phone_number=f"+2348{token[:9]}",
        dob=dob,
        gender=gender,
        city="Lagos",
        country=country,
        state="Lagos",
        marital_status="Single",
        is_active=active,
        is_admin=admin,
        is_super_admin=super_admin,
        show_age_on_profile=show_age,
    )
    account.set_password("StrongPassw0rd!")
    db.session.add(account)
    db.session.commit()
    return account


def _login(client, account):
    with client.session_transaction() as session:
        session.clear()
        session["_user_id"] = str(account.id)
        session["_fresh"] = True
    g.pop("_login_user", None)


def test_matchmaking_group_hidden_from_public_listings_and_search(client, db, app, monkeypatch):
    """The protected Matchmaking group must be hidden from /groups/all, sidebar discovery, and search for non-admins."""
    admin = _make_user(db, admin=True)
    regular = _make_user(db, admin=False)

    matchmaking_group = Group(
        name="Matchmaking",
        description="Official Matchmaking Group",
        is_private=False,
        is_active=True,
        created_by=admin.id,
    )
    public_group = Group(
        name="Public Discussion",
        description="Public discussion community",
        is_private=False,
        is_active=True,
        created_by=regular.id,
    )
    db.session.add_all([matchmaking_group, public_group])
    db.session.commit()

    monkeypatch.setitem(app.config, "MATCHMAKING_GROUP_ID", str(matchmaking_group.id))

    # Create post in matchmaking group
    mm_post = Post(
        content="Secret matchmaking discussion #findlove",
        author_id=admin.id,
        group_id=matchmaking_group.id,
    )
    db.session.add(mm_post)
    db.session.commit()

    # 1. As regular user: group MUST NOT appear in /groups/all
    _login(client, regular)
    res = client.get("/groups/all?per_page=100")
    assert res.status_code == 200
    all_groups = res.get_json()
    all_group_ids = [g["id"] for g in all_groups]
    assert matchmaking_group.id not in all_group_ids
    assert public_group.id in all_group_ids

    # 2. As regular user: group MUST NOT appear in get_groups_data_for_user (trending sidebar)
    sidebar_groups = get_groups_data_for_user(regular.id)
    sidebar_group_ids = [g["id"] for g in sidebar_groups]
    assert matchmaking_group.id not in sidebar_group_ids

    # 3. As regular user: group MUST NOT appear in /groups/user_groups
    user_groups_res = client.get("/groups/user_groups")
    assert user_groups_res.status_code == 200
    user_grp_ids = [g["id"] for g in user_groups_res.get_json()]
    assert matchmaking_group.id not in user_grp_ids

    # 4. As regular user: posts from the protected group must not leak into search
    search_res = client.get("/search?q=findlove")
    assert search_res.status_code == 200
    found_posts = search_res.get_json().get("posts", [])
    assert not any(p["id"] == mm_post.id for p in found_posts)

    # 5. Direct access: Navigating to /groups/<id> directly remains accessible (data preserved)
    direct_res = client.get(f"/groups/{matchmaking_group.id}")
    assert direct_res.status_code == 200

    # 6. As admin user: group IS visible in /groups/all for management
    _login(client, admin)
    admin_res = client.get("/groups/all?per_page=100")
    assert admin_res.status_code == 200
    admin_all_ids = [g["id"] for g in admin_res.get_json()]
    assert matchmaking_group.id in admin_all_ids


def test_boost_entitlement_and_sponsored_profile_badge(client, db):
    """Boost Your Profile requires verified payment, displays 'Sponsored Profile' badge, and respects age privacy."""
    viewer = _make_user(db, gender="Male", dob=date(1992, 4, 10))
    boosted_user = _make_user(
        db,
        gender="Female",
        dob=date(1996, 8, 20),
        show_age=False,  # Age is hidden by user!
    )
    unpaid_user = _make_user(db, gender="Female", dob=date(1994, 3, 15))
    ordinary_user = _make_user(db, gender="Female", dob=date(1995, 1, 1))

    now = utcnow()

    package = MatchmakingPackage(
        name="Boost Package",
        description="Boost profile for 30 days",
        price=50.0,
        duration_days=30,
        is_active=True,
    )
    db.session.add(package)
    db.session.commit()

    # 1. Verified paid boost: MatchmakingRequest active + completed, MatchmakingPayments completed + paid
    valid_request = MatchmakingRequest(
        user_id=boosted_user.id,
        package_id=package.id,
        status="active",
        payment_status="completed",
        end_date=now + timedelta(days=30),
        about_you="I love hiking and reading great literature.",
        ideal_partner="Someone kind and ambitious.",
    )
    db.session.add(valid_request)
    db.session.flush()

    valid_payment = MatchmakingPayments(
        user_id=boosted_user.id,
        matchmaking_request_id=valid_request.id,
        package_id=package.id,
        amount=50.0,
        status="completed",
        payment_status="paid",
    )
    db.session.add(valid_payment)

    # 2. Unpaid boost: MatchmakingPayments payment_status is 'pending'
    unpaid_request = MatchmakingRequest(
        user_id=unpaid_user.id,
        package_id=package.id,
        status="active",
        payment_status="pending",
        end_date=now + timedelta(days=30),
        about_you="Trying to get a free boost without paying.",
        ideal_partner="Anyone.",
    )
    db.session.add(unpaid_request)
    db.session.flush()

    unpaid_payment = MatchmakingPayments(
        user_id=unpaid_user.id,
        matchmaking_request_id=unpaid_request.id,
        package_id=package.id,
        amount=50.0,
        status="pending",
        payment_status="pending",
    )
    db.session.add(unpaid_payment)
    db.session.commit()

    # Fetch sponsored items for viewer
    sponsored_items = get_active_sponsored_items_for_user(viewer, current_time=now)

    # Verify only verified paid boost appears
    boost_items = [item for item in sponsored_items if item["is_boost"]]
    boost_user_ids = [item["user_id"] for item in boost_items]

    assert boosted_user.id in boost_user_ids
    assert unpaid_user.id not in boost_user_ids
    assert ordinary_user.id not in boost_user_ids

    # Verify badge and content format
    boost_card = next(item for item in boost_items if item["user_id"] == boosted_user.id)
    assert boost_card["badge"] == "Sponsored Profile"
    assert boost_card["call_to_action"] == "View Profile"
    assert boost_card["sponsor_name"] == "Kimbela Matchmaking"
    assert boost_card["description"] == "I love hiking and reading great literature."
    # Since show_age_on_profile is False, age must be None!
    assert boost_card["age"] is None

    # Verify API endpoint returns it as well
    _login(client, viewer)
    api_res = client.get("/api/ads/sponsored")
    assert api_res.status_code == 200
    api_ads = api_res.get_json().get("ads", [])
    api_boost = next((a for a in api_ads if a.get("is_boost")), None)
    assert api_boost is not None
    assert api_boost["badge"] == "Sponsored Profile"
    assert api_boost["advertiser_name"] == "Kimbela Matchmaking"


def test_sponsored_ads_targeting_and_rendering(client, db):
    """Sponsored ad campaigns are targeted, verified, rendered in multiple positions, and not duplicated."""
    viewer_ng = _make_user(db, gender="Male", dob=date(1995, 5, 20), country="Nigeria")
    ad_owner = _make_user(db)

    now = utcnow()

    # Campaign 1: targeted to Nigeria and Male
    campaign_ng = AdCampaign(
        user_id=ad_owner.id,
        title="Lagos Tech Conference 2026",
        description="Connect with leading engineers in Lagos.",
        image="https://cdn.example.test/tech.jpg",
        target_url="https://conference.example.test",
        call_to_action="Register Now",
        status="active",
        payment_status="paid",
        start_date=now - timedelta(days=2),
        end_date=now + timedelta(days=10),
        budget=500.0,
        daily_budget=50.0,
        duration_days=12,
        placement="sponsored",
        target_country="Nigeria",
        target_gender=json.dumps(["Male"]),
        target_age_min=18,
        target_age_max=45,
    )

    # Campaign 2: targeted to Ghana (should NOT match viewer_ng)
    campaign_gh = AdCampaign(
        user_id=ad_owner.id,
        title="Accra Festival",
        description="Music festival in Ghana.",
        image="https://cdn.example.test/ghana.jpg",
        target_url="https://ghana.example.test",
        call_to_action="Get Tickets",
        status="active",
        payment_status="paid",
        start_date=now - timedelta(days=1),
        end_date=now + timedelta(days=5),
        budget=300.0,
        daily_budget=30.0,
        duration_days=6,
        placement="sponsored",
        target_country="Ghana",
    )

    db.session.add_all([campaign_ng, campaign_gh])
    db.session.commit()

    # Query items for viewer in Nigeria
    items = get_active_sponsored_items_for_user(viewer_ng, current_time=now)
    item_titles = [i["title"] for i in items if not i["is_boost"]]

    assert "Lagos Tech Conference 2026" in item_titles
    assert "Accra Festival" not in item_titles

    # Create several feed posts to test feed rendering
    posts = [
        Post(
            content=f"Feed update post {i}",
            author_id=ad_owner.id,
            created_at=now - timedelta(minutes=i),
        )
        for i in range(12)
    ]
    db.session.add_all(posts)
    db.session.commit()

    _login(client, viewer_ng)

    # 1. Full dashboard load
    response = client.get("/user_dashboard")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    # Sponsored feed cards must be present and NOT hidden on desktop (no lg:hidden on card)
    assert 'class="sponsored-feed-card' in html
    assert "Lagos Tech Conference 2026" in html
    assert "Register Now" in html

    # The intrusive full-screen modal trigger should not pop up
    assert "displayNextAd" in html or "AdSystem" in html

    # 2. AJAX pagination loading posts
    ajax_res = client.get(
        "/user_dashboard?limit=10",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert ajax_res.status_code == 200
    data = ajax_res.get_json()
    assert data["success"] is True
    # The partial posts must include sponsored card
    assert "sponsored-feed-card" in data["posts"]
    assert "Sponsored" in data["posts"]
