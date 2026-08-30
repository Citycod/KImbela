from datetime import date, datetime, timedelta
import uuid

import pytest
from sqlalchemy import event

from models import (
    MatchmakingLike,
    MatchmakingPackage,
    MatchmakingRequest,
    MatchmakingView,
    User,
)
from time_utils import utcnow


@pytest.fixture(autouse=True)
def clean_browse_test_data(db):
    """Keep this module isolated without disturbing non-Browse fixtures."""

    def clean():
        browse_user_ids = [
            user_id
            for (user_id,) in db.session.query(User.id)
            .filter(User.email.like("browse-%@example.com"))
            .all()
        ]
        request_ids = []
        if browse_user_ids:
            request_ids = [
                request_id
                for (request_id,) in db.session.query(MatchmakingRequest.id)
                .filter(MatchmakingRequest.user_id.in_(browse_user_ids))
                .all()
            ]
        if request_ids:
            MatchmakingLike.query.filter(
                MatchmakingLike.request_id.in_(request_ids)
            ).delete(synchronize_session=False)
            MatchmakingView.query.filter(
                MatchmakingView.request_id.in_(request_ids)
            ).delete(synchronize_session=False)
            MatchmakingRequest.query.filter(
                MatchmakingRequest.id.in_(request_ids)
            ).delete(synchronize_session=False)
        if browse_user_ids:
            blocks = User._blocked_users
            db.session.execute(
                blocks.delete().where(
                    or_(
                        blocks.c.blocker_id.in_(browse_user_ids),
                        blocks.c.blocked_id.in_(browse_user_ids),
                    )
                )
            )
            User.query.filter(User.id.in_(browse_user_ids)).delete(
                synchronize_session=False
            )
        MatchmakingPackage.query.filter(
            MatchmakingPackage.name.like("Browse %")
        ).delete(synchronize_session=False)
        db.session.commit()

    from sqlalchemy import or_

    clean()
    yield
    clean()


def _birth_date(age):
    today = utcnow().date()
    try:
        return today.replace(year=today.year - age)
    except ValueError:
        return date(today.year - age, 2, 28)


def _profile(
    db,
    *,
    name,
    age=30,
    gender="Female",
    country="Nigeria",
    state="Lagos",
    city="Lagos",
    last_seen=None,
    created_at=None,
):
    suffix = uuid.uuid4().hex[:8]
    profile = User(
        first_name=name,
        last_name="Browse",
        email=f"browse-{suffix}@example.com",
        phone_number=f"+23480{int(suffix[:6], 16) % 100000000:08d}",
        dob=_birth_date(age),
        gender=gender,
        city=city,
        state=state,
        country=country,
        marital_status="Single",
        is_active=True,
        last_seen=last_seen or utcnow(),
        created_at=created_at or utcnow(),
    )
    profile.set_password("StrongPassw0rd!")
    db.session.add(profile)
    db.session.flush()
    return profile


def _package(db):
    package = MatchmakingPackage(
        name=f"Browse {uuid.uuid4().hex[:6]}",
        price=1000,
        duration_days=30,
        is_active=True,
    )
    db.session.add(package)
    db.session.flush()
    return package


def _request(
    db,
    package,
    profile,
    *,
    created_at=None,
    status="active",
    payment_status="completed",
    end_date=None,
    partner_country="Ghana",
):
    matchmaking_request = MatchmakingRequest(
        user_id=profile.id,
        package_id=package.id,
        about_you=f"About {profile.first_name}",
        ideal_partner="A kind partner",
        partner_country=partner_country,
        status=status,
        payment_status=payment_status,
        end_date=end_date or utcnow() + timedelta(days=30),
        created_at=created_at or utcnow(),
        views=0,
        likes=0,
        matches=0,
    )
    db.session.add(matchmaking_request)
    db.session.flush()
    return matchmaking_request


def _login(client, user):
    with client.session_transaction() as session:
        session["_user_id"] = str(user.id)
        session["_fresh"] = True


def _browse(client, query=""):
    response = client.get(f"/api/requests{query}")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    return payload


def _ids(payload):
    return [item["id"] for item in payload["requests"]]


def test_default_browse_keeps_newest_first_and_existing_eligibility(client, user, db):
    _login(client, user)
    package = _package(db)
    now = utcnow()
    older = _request(
        db, package, _profile(db, name="Older"), created_at=now - timedelta(days=2)
    )
    newer = _request(
        db, package, _profile(db, name="Newer"), created_at=now - timedelta(days=1)
    )
    inactive = _request(db, package, _profile(db, name="Inactive"), status="cancelled")
    unpaid = _request(
        db, package, _profile(db, name="Unpaid"), payment_status="pending"
    )
    expired = _request(
        db,
        package,
        _profile(db, name="Expired"),
        end_date=now - timedelta(minutes=1),
    )
    db.session.commit()

    result_ids = _ids(_browse(client))

    assert result_ids.index(newer.id) < result_ids.index(older.id)
    assert inactive.id not in result_ids
    assert unpaid.id not in result_ids
    assert expired.id not in result_ids


@pytest.mark.parametrize(
    ("query", "expected_names"),
    [
        ("?age_min=30", {"Thirty", "Forty"}),
        ("?age_max=30", {"Twenty", "Thirty"}),
        ("?age_min=25&age_max=35", {"Thirty"}),
    ],
)
def test_age_filters(client, user, db, query, expected_names):
    _login(client, user)
    package = _package(db)
    requests = {
        name: _request(db, package, _profile(db, name=name, age=age))
        for name, age in (("Twenty", 20), ("Thirty", 30), ("Forty", 40))
    }
    db.session.commit()

    result_ids = set(_ids(_browse(client, query)))

    assert {requests[name].id for name in expected_names}.issubset(result_ids)
    assert {
        request.id for name, request in requests.items() if name not in expected_names
    }.isdisjoint(result_ids)


def test_location_gender_and_combined_filters_use_profile_fields(client, user, db):
    _login(client, user)
    package = _package(db)
    lagos = _request(
        db,
        package,
        _profile(
            db,
            name="LagosWoman",
            age=32,
            gender="Female",
            country="Nigeria",
            state="Lagos",
            city="Ikeja",
        ),
        partner_country="Canada",
    )
    abuja = _request(
        db,
        package,
        _profile(
            db,
            name="AbujaMan",
            age=32,
            gender="Male",
            country="Nigeria",
            state="FCT",
            city="Abuja",
        ),
        partner_country="Nigeria",
    )
    db.session.commit()

    payload = _browse(
        client,
        "?country=Nigeria&state=Lagos&city=Ikeja&gender=female&age_min=30&age_max=35",
    )

    assert lagos.id in _ids(payload)
    assert abuja.id not in _ids(payload)


def test_recent_newest_and_age_sorts(client, user, db):
    _login(client, user)
    package = _package(db)
    now = utcnow()
    old_recent = _request(
        db,
        package,
        _profile(db, name="OldRecent", age=50, last_seen=now),
        created_at=now - timedelta(days=10),
    )
    new_inactive = _request(
        db,
        package,
        _profile(db, name="NewInactive", age=20, last_seen=now - timedelta(days=4)),
        created_at=now,
    )
    db.session.commit()

    assert _ids(_browse(client, "?sort=recent")).index(old_recent.id) < _ids(
        _browse(client, "?sort=recent")
    ).index(new_inactive.id)
    assert _ids(_browse(client, "?sort=newest")).index(new_inactive.id) < _ids(
        _browse(client, "?sort=newest")
    ).index(old_recent.id)
    assert _ids(_browse(client, "?sort=age_asc")).index(new_inactive.id) < _ids(
        _browse(client, "?sort=age_asc")
    ).index(old_recent.id)
    assert _ids(_browse(client, "?sort=age_desc")).index(old_recent.id) < _ids(
        _browse(client, "?sort=age_desc")
    ).index(new_inactive.id)


def test_pagination_with_filters_is_stable_and_has_no_duplicates(client, user, db):
    _login(client, user)
    package = _package(db)
    tied_time = datetime(2026, 1, 1, 12, 0, 0)
    expected_ids = []
    for index in range(7):
        profile = _profile(
            db, name=f"Paged{index}", country="Nigeria", created_at=tied_time
        )
        expected_ids.append(_request(db, package, profile, created_at=tied_time).id)
    db.session.commit()

    page_one = _browse(client, "?country=Nigeria&per_page=3&page=1")
    page_two = _browse(client, "?country=Nigeria&per_page=3&page=2")
    first_ids = [item_id for item_id in _ids(page_one) if item_id in expected_ids]
    second_ids = [item_id for item_id in _ids(page_two) if item_id in expected_ids]

    assert not set(first_ids).intersection(second_ids)
    assert first_ids == sorted(first_ids, reverse=True)
    assert second_ids == sorted(second_ids, reverse=True)
    assert page_one["has_next"] is True


def test_invalid_query_parameters_fall_back_safely(client, user, db):
    _login(client, user)
    package = _package(db)
    request_item = _request(db, package, _profile(db, name="Valid"))
    db.session.commit()

    payload = _browse(
        client,
        "?age_min=old&age_max=999&gender=unknown&sort=random&page=-2&per_page=999",
    )

    assert request_item.id in _ids(payload)
    assert payload["page"] == 1
    assert payload["sort"] == "recommended"


@pytest.mark.parametrize("direction", ["viewer_blocks", "candidate_blocks"])
def test_blocked_users_remain_excluded(client, db, user, direction):
    _login(client, user)
    package = _package(db)
    candidate = _profile(db, name="Blocked")
    request_item = _request(db, package, candidate)
    db.session.commit()
    if direction == "viewer_blocks":
        user.block(candidate)
    else:
        candidate.block(user)

    assert request_item.id not in _ids(_browse(client))


def test_card_state_queries_are_bounded_per_page(client, user, db, app):
    _login(client, user)
    package = _package(db)
    for index in range(12):
        _request(db, package, _profile(db, name=f"Bounded{index}"))
    db.session.commit()

    select_statements = []

    def record_select(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            select_statements.append(statement)

    event.listen(db.engine, "before_cursor_execute", record_select)
    try:
        payload = _browse(client, "?per_page=12")
    finally:
        event.remove(db.engine, "before_cursor_execute", record_select)

    assert len(payload["requests"]) == 12
    assert len(select_statements) <= 7


def test_browse_template_has_reload_safe_mobile_controls(client, user):
    _login(client, user)

    response = client.get("/view_requests?age_min=25&location=Lagos&sort=recent")

    assert response.status_code == 200
    assert b'id="filterToggle"' in response.data
    assert b'id="filtersPanel"' in response.data
    assert b"readFiltersFromUrl" in response.data
    assert b"syncFiltersToUrl" in response.data
    assert b'<option value="recommended">Recommended</option>' in response.data
    assert b'<option value="recent">Recently Active</option>' in response.data
