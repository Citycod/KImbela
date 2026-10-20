import json
import uuid
from datetime import date, datetime, timedelta

from flask import g

from models import (
    Group,
    MatchmakingPackage,
    MatchmakingPayments,
    MatchmakingRequest,
    PaymentTransaction,
    Post,
    User,
)
from payments.browse_access import (
    BROWSE_ACCESS_DAYS,
    BROWSE_TRANSACTION_TYPE,
    complete_browse_payment,
    has_matchmaking_access,
)
from time_utils import utcnow
from utils.matchmaking_boosts import visible_paid_matchmaking_profiles


def _user(db, label, *, active=True, ai=False, admin=False, dob_value=None):
    user = User(
        first_name=label,
        last_name="Profile",
        email=f"{label.lower()}-{uuid.uuid4().hex[:8]}@example.test",
        phone_number="+15555550123",
        city="Lagos",
        state="Lagos",
        country="Nigeria",
        dob=dob_value or date(1990, 1, 1),
        gender="Female",
        marital_status="Single",
        bio=f"{label} public bio",
        interests=json.dumps(["Travel", "Music"]),
        is_active=active,
        is_ai_persona=ai,
        is_admin=admin,
    )
    user.set_password("StrongPassw0rd!")
    db.session.add(user)
    db.session.flush()
    return user


def _group(db, creator, *, name, private=True):
    group = Group(
        name=name,
        description="Private group",
        category="Community",
        is_private=private,
        is_active=True,
        created_by=creator.id,
    )
    db.session.add(group)
    db.session.flush()
    return group


def _boost(db, user, *, now, active=True, verified=True, updated_offset=0):
    package = MatchmakingPackage(
        name=f"Boost-{uuid.uuid4().hex[:8]}",
        price=3,
        duration_days=30,
        is_active=True,
    )
    db.session.add(package)
    db.session.flush()
    request_row = MatchmakingRequest(
        user_id=user.id,
        package_id=package.id,
        about_you=f"{user.first_name} boost profile",
        ideal_partner="A compatible person",
        your_interests=json.dumps(["Reading", "Travel"]),
        status="active" if active else "pending",
        payment_status="completed" if active else "pending",
        end_date=now + timedelta(days=10 if active else -1),
        created_at=now + timedelta(minutes=updated_offset),
        updated_at=now + timedelta(minutes=updated_offset),
    )
    db.session.add(request_row)
    db.session.flush()
    db.session.add(
        MatchmakingPayments(
            user_id=user.id,
            matchmaking_request_id=request_row.id,
            package_id=package.id,
            amount=3,
            currency="USD",
            status="completed" if verified else "pending",
            payment_status="paid" if verified else "pending",
            paid_at=now + timedelta(minutes=updated_offset) if verified else None,
            gateway_reference=f"BOOST-{uuid.uuid4().hex}",
        )
    )
    db.session.flush()
    return request_row


def _find_payment(db, user, *, now, status="completed", days_ago=0):
    completed_at = now - timedelta(days=days_ago)
    payment = PaymentTransaction(
        user_id=user.id,
        amount=3,
        currency="USD",
        transaction_type=BROWSE_TRANSACTION_TYPE,
        status=status,
        gateway_reference=f"FIND-{uuid.uuid4().hex}",
        created_at=completed_at,
        updated_at=completed_at,
    )
    db.session.add(payment)
    db.session.flush()
    return payment


def _setup_group(app, db, monkeypatch):
    owner = _user(db, "Owner", admin=True)
    viewer = _user(db, "Viewer")
    matchmaking = _group(db, owner, name="Protected Matchmaking")
    matchmaking.members.append(viewer)
    monkeypatch.setitem(app.config, "MATCHMAKING_GROUP_ID", str(matchmaking.id))
    db.session.flush()
    return owner, viewer, matchmaking


def _login(client, user):
    g.pop("_login_user", None)
    with client.session_transaction() as session:
        session.clear()
        session["_user_id"] = str(user.id)
        session["_fresh"] = True


def test_verified_boost_and_find_profiles_are_union_deduplicated_and_ordered(
    app, db, monkeypatch
):
    _, viewer, group = _setup_group(app, db, monkeypatch)
    now = utcnow()
    both = _user(db, "Both")
    boost_only = _user(db, "Boostonly")
    find_only = _user(db, "Findonly")
    _boost(db, boost_only, now=now, updated_offset=-5)
    _boost(db, both, now=now, updated_offset=0)
    _find_payment(db, both, now=now)
    _find_payment(db, find_only, now=now)
    db.session.commit()

    page = visible_paid_matchmaking_profiles(viewer, group, now=now)

    target_ids = {both.id, boost_only.id, find_only.id}
    target_profiles = [profile for profile in page.items if profile.user.id in target_ids]
    assert [profile.user.id for profile in target_profiles] == [
        both.id,
        boost_only.id,
        find_only.id,
    ]
    assert [profile.source for profile in target_profiles] == ["boost", "boost", "find"]
    assert target_profiles[0].badge == "Boosted"
    assert len({profile.user.id for profile in target_profiles}) == 3


def test_paid_matchmaking_profiles_preserve_adult_only_rule_for_both_products(
    app, db, monkeypatch
):
    _, viewer, group = _setup_group(app, db, monkeypatch)
    leap_day_now = datetime(2028, 2, 29, 12, 0)
    underage_boost = _user(
        db,
        "Underageboost",
        dob_value=date(2011, 2, 28),
    )
    underage_find = _user(
        db,
        "Underagefind",
        dob_value=date(2010, 3, 1),
    )
    adult_find = _user(
        db,
        "Adultfind",
        dob_value=date(2010, 2, 28),
    )
    _boost(db, underage_boost, now=leap_day_now)
    _find_payment(db, underage_find, now=leap_day_now)
    _find_payment(db, adult_find, now=leap_day_now)
    db.session.commit()

    visible_ids = {
        profile.user.id
        for profile in visible_paid_matchmaking_profiles(
            viewer,
            group,
            now=leap_day_now,
        ).items
    }

    assert underage_boost.id not in visible_ids
    assert underage_find.id not in visible_ids
    assert adult_find.id in visible_ids


def test_expired_pending_inactive_and_ai_profiles_are_excluded_without_cleanup(
    app, db, monkeypatch
):
    _, viewer, group = _setup_group(app, db, monkeypatch)
    now = utcnow()
    expired_boost = _user(db, "Expiredboost")
    unpaid_boost = _user(db, "Unpaidboost")
    expired_find = _user(db, "Expiredfind")
    unpaid_find = _user(db, "Unpaidfind")
    inactive = _user(db, "Inactive", active=False)
    ai_user = _user(db, "Robot", ai=True)
    _boost(db, expired_boost, now=now, active=False)
    _boost(db, unpaid_boost, now=now, verified=False)
    _find_payment(db, expired_find, now=now, days_ago=BROWSE_ACCESS_DAYS)
    _find_payment(db, unpaid_find, now=now, status="pending")
    _find_payment(db, inactive, now=now)
    _find_payment(db, ai_user, now=now)
    db.session.commit()

    page = visible_paid_matchmaking_profiles(viewer, group, now=now)

    excluded_ids = {profile.user.id for profile in page.items}
    assert expired_boost.id not in excluded_ids
    assert unpaid_boost.id not in excluded_ids
    assert expired_find.id not in excluded_ids
    assert unpaid_find.id not in excluded_ids
    assert inactive.id not in excluded_ids
    assert ai_user.id not in excluded_ids
    assert MatchmakingRequest.query.filter_by(user_id=expired_boost.id).count() == 1
    assert PaymentTransaction.query.filter_by(user_id=expired_find.id).count() == 1


def test_expiration_is_evaluated_at_render_time_without_scheduler(
    app, db, monkeypatch
):
    _, viewer, group = _setup_group(app, db, monkeypatch)
    now = utcnow()
    boost_user = _user(db, "Timedboost")
    find_user = _user(db, "Timedfind")
    boost = _boost(db, boost_user, now=now)
    boost.end_date = now + timedelta(minutes=5)
    _find_payment(db, find_user, now=now, days_ago=BROWSE_ACCESS_DAYS - 1)
    db.session.commit()

    visible_now = {
        item.user.id
        for item in visible_paid_matchmaking_profiles(viewer, group, now=now).items
    }
    assert boost_user.id in visible_now
    assert find_user.id in visible_now
    later = now + timedelta(days=2)
    visible_later = {
        item.user.id
        for item in visible_paid_matchmaking_profiles(viewer, group, now=later).items
    }
    assert boost_user.id not in visible_later
    assert find_user.id not in visible_later


def test_bilateral_blocks_exclude_paid_profiles(app, db, monkeypatch):
    _, viewer, group = _setup_group(app, db, monkeypatch)
    now = utcnow()
    viewer_blocked = _user(db, "Viewerblocked")
    candidate_blocked = _user(db, "Candidateblocked")
    visible = _user(db, "Stillvisible")
    for candidate in (viewer_blocked, candidate_blocked, visible):
        _find_payment(db, candidate, now=now)
    db.session.execute(
        User._blocked_users.insert().values(
            blocker_id=viewer.id, blocked_id=viewer_blocked.id
        )
    )
    db.session.execute(
        User._blocked_users.insert().values(
            blocker_id=candidate_blocked.id, blocked_id=viewer.id
        )
    )
    db.session.commit()

    visible_ids = [
        profile.user.id
        for profile in visible_paid_matchmaking_profiles(viewer, group, now=now).items
    ]
    assert viewer_blocked.id not in visible_ids
    assert candidate_blocked.id not in visible_ids
    assert visible.id in visible_ids


def test_private_group_authorization_and_group_scope_are_preserved(
    app, db, client, monkeypatch
):
    owner, viewer, group = _setup_group(app, db, monkeypatch)
    outsider = _user(db, "Outsider")
    candidate = _user(db, "Candidate")
    other_group = _group(db, owner, name="Ordinary group", private=False)
    _find_payment(db, candidate, now=utcnow())
    db.session.commit()

    assert visible_paid_matchmaking_profiles(outsider, group).items == ()
    assert visible_paid_matchmaking_profiles(viewer, other_group).items == ()
    assert candidate.id in {
        profile.user.id
        for profile in visible_paid_matchmaking_profiles(viewer, group).items
    }

    _login(client, outsider)
    outsider_html = client.get(f"/groups/{group.id}").get_data(as_text=True)
    assert candidate.full_name not in outsider_html
    assert "Featured Matchmaking Profiles" not in outsider_html

    _login(client, viewer)
    member_html = client.get(f"/groups/{group.id}").get_data(as_text=True)
    assert candidate.full_name in member_html
    assert "Featured Matchmaking Profiles" in member_html
    ordinary_html = client.get(f"/groups/{other_group.id}").get_data(as_text=True)
    assert candidate.full_name not in ordinary_html
    assert "Featured Matchmaking Profiles" not in ordinary_html


def test_payment_initialization_is_not_visibility_and_verified_find_is(
    app, db, monkeypatch
):
    _, viewer, group = _setup_group(app, db, monkeypatch)
    candidate = _user(db, "Verifiedfind")
    pending_boost = _boost(db, candidate, now=utcnow(), active=False, verified=False)
    payment = PaymentTransaction(
        user_id=candidate.id,
        amount=3,
        currency="NGN",
        transaction_type=BROWSE_TRANSACTION_TYPE,
        status="pending",
        gateway_reference=f"FIND-{uuid.uuid4().hex}",
        gateway_metadata=json.dumps(
            {
                "expected_checkout_amount": "4800.00",
                "expected_checkout_currency": "NGN",
                "expected_product": "find_your_match",
            }
        ),
    )
    db.session.add(payment)
    db.session.commit()

    assert candidate.id not in {
        profile.user.id
        for profile in visible_paid_matchmaking_profiles(viewer, group).items
    }
    assert has_matchmaking_access(candidate) is False

    verification = {
        "status": "successful",
        "id": f"gateway-{uuid.uuid4().hex}",
        "tx_ref": payment.gateway_reference,
        "amount": 4800,
        "currency": "NGN",
        "meta": {
            "user_id": candidate.id,
            "transaction_type": BROWSE_TRANSACTION_TYPE,
            "access_days": BROWSE_ACCESS_DAYS,
            "product": "find_your_match",
        },
    }
    assert complete_browse_payment(payment, verification) is True
    assert has_matchmaking_access(candidate) is True
    profiles = visible_paid_matchmaking_profiles(viewer, group).items
    candidate_profiles = [profile for profile in profiles if profile.user.id == candidate.id]
    assert [(profile.user.id, profile.source) for profile in candidate_profiles] == [
        (candidate.id, "find")
    ]
    db.session.refresh(pending_boost)
    assert pending_boost.status == "pending"
    assert pending_boost.payment_status == "pending"


def test_boost_visibility_does_not_grant_find_access_or_create_rows(
    app, db, monkeypatch
):
    _, viewer, group = _setup_group(app, db, monkeypatch)
    candidate = _user(db, "Boostseparate")
    before_posts = Post.query.count()
    before_members = group.members.count()
    _boost(db, candidate, now=utcnow())
    db.session.commit()

    assert has_matchmaking_access(candidate) is False
    assert candidate.id in {
        profile.user.id
        for profile in visible_paid_matchmaking_profiles(viewer, group).items
    }
    assert Post.query.count() == before_posts
    assert group.members.count() == before_members
    assert group.members.filter_by(id=candidate.id).first() is None


def test_matchmaking_posting_restrictions_remain_for_normal_and_ai_users(
    app, db, client, monkeypatch
):
    _, normal, group = _setup_group(app, db, monkeypatch)
    ai_user = _user(db, "AiPoster", ai=True)
    group.members.append(ai_user)
    db.session.commit()

    for account in (normal, ai_user):
        _login(client, account)
        response = client.post(
            f"/groups/{group.id}/post",
            data={"post_content": "Forbidden Matchmaking post"},
        )
        assert response.status_code == 403
