"""Tests for Kimbela's 18+ age eligibility and validation policy."""

from datetime import date, timedelta
import pytest
from utils.age_policy import (
    MIN_ACCOUNT_AGE,
    MIN_PLAUSIBLE_DOB,
    MAX_PREFERENCE_AGE,
    calculate_age,
    adult_cutoff,
    validate_account_dob,
    validate_preferred_age_range,
)


def test_calculate_age_various_adult_ages():
    today = date(2026, 11, 4)

    assert calculate_age(None, today) is None
    assert calculate_age(date(2008, 11, 4), today) == 18
    assert calculate_age(date(2008, 11, 5), today) == 17  # Turns 18 tomorrow
    assert calculate_age(date(2007, 11, 4), today) == 19
    assert calculate_age(date(1996, 11, 4), today) == 30
    assert calculate_age(date(1976, 11, 4), today) == 50
    assert calculate_age(date(1956, 11, 4), today) == 70
    assert calculate_age(date(1936, 11, 4), today) == 90
    assert calculate_age(date(1926, 11, 4), today) == 100
    assert calculate_age(date(1916, 11, 4), today) == 110


def test_calculate_age_leap_year_february_29():
    # Born on Feb 29, 2008 (leap year)
    dob = date(2008, 2, 29)

    # In 2026 (non-leap year):
    # Feb 28 -> still 17
    assert calculate_age(dob, date(2026, 2, 28)) == 17
    # March 1 -> turns 18
    assert calculate_age(dob, date(2026, 3, 1)) == 18

    # In 2028 (leap year, 20th birthday):
    assert calculate_age(dob, date(2028, 2, 28)) == 19
    assert calculate_age(dob, date(2028, 2, 29)) == 20
    assert calculate_age(dob, date(2028, 3, 1)) == 20


def test_adult_cutoff_calculation():
    # Regular day
    today = date(2026, 11, 4)
    assert adult_cutoff(today, 18) == date(2008, 11, 4)

    # Leap day today (e.g. Feb 29, 2028)
    leap_today = date(2028, 2, 29)
    # 2028 - 18 = 2010 (not a leap year) -> falls back to Feb 28, 2010
    assert adult_cutoff(leap_today, 18) == date(2010, 2, 28)


def test_validate_account_dob_boundaries():
    today = date(2026, 11, 4)

    # Exactly 18 -> valid
    valid, err = validate_account_dob(date(2008, 11, 4), today)
    assert valid is True
    assert err is None

    # Age 17 (one day before 18th birthday) -> rejected
    valid, err = validate_account_dob(date(2008, 11, 5), today)
    assert valid is False
    assert "at least 18 years old" in err

    # Age 19, 30, 70, 100 -> valid
    for y in (2007, 1996, 1956, 1926):
        valid, err = validate_account_dob(date(y, 1, 1), today)
        assert valid is True, f"Failed for year {y}"
        assert err is None

    # Future date -> rejected
    valid, err = validate_account_dob(today + timedelta(days=1), today)
    assert valid is False
    assert "cannot be in the future" in err

    # Pre-1900 date -> rejected
    valid, err = validate_account_dob(date(1899, 12, 31), today)
    assert valid is False
    assert "earlier than 1900-01-01" in err

    # Plausible floor (1900-01-01) -> valid
    valid, err = validate_account_dob(date(1900, 1, 1), today)
    assert valid is True
    assert err is None

    # None or non-date -> rejected
    valid, err = validate_account_dob(None, today)
    assert valid is False
    assert "required" in err


def test_validate_preferred_age_range():
    # Valid ranges
    assert validate_preferred_age_range(18, 18) == (18, 18, None)
    assert validate_preferred_age_range(18, 120) == (18, 120, None)
    assert validate_preferred_age_range(70, 110) == (70, 110, None)
    assert validate_preferred_age_range("25", "40") == (25, 40, None)

    # Below 18 -> rejected
    _, _, err = validate_preferred_age_range(17, 30)
    assert "at least 18" in err

    # Above 120 -> rejected
    _, _, err = validate_preferred_age_range(25, 121)
    assert "greater than 120" in err

    # Reversed -> rejected
    _, _, err = validate_preferred_age_range(40, 25)
    assert "greater than or equal to minimum" in err

    # Invalid types: booleans, floats, strings with letters
    for bad in (True, False, 25.5, "abc", "1e2", None, ""):
        _, _, err = validate_preferred_age_range(bad, 30)
        assert err == "Please enter a valid whole-number age."


# ==============================================================================
# INTEGRATION TESTS: Registration, Profile Editing, Ads, and Privacy API
# ==============================================================================

def _reg_payload(email, dob_str):
    return {
        "first_name": "Test",
        "last_name": "Adult",
        "email": email,
        "password": "StrongPassword123!",
        "confirm_password": "StrongPassword123!",
        "dob": dob_str,
        "gender": "Female",
        "marital_status": "Single",
        "country": "Nigeria",
        "state": "Lagos",
        "city": "Ikeja",
        "educational_level": "Bachelor's Degree",
        "occupation": "Engineer",
        "terms": "on",
    }


def test_registration_age_boundaries(client, db):
    from models import User
    from time_utils import utcnow

    today = utcnow().date()
    under_18_dob = (today - timedelta(days=17 * 365)).strftime("%Y-%m-%d")
    exact_18_dob = adult_cutoff(today, 18).strftime("%Y-%m-%d")

    # 1. Age 17 -> rejected
    resp17 = client.post("/register", data=_reg_payload("reg-17@example.com", under_18_dob))
    assert resp17.status_code == 200
    assert b"at least 18 years old" in resp17.data
    assert User.query.filter_by(email="reg-17@example.com").first() is None

    # 2. Exactly 18 -> accepted
    resp18 = client.post("/register", data=_reg_payload("reg-18@example.com", exact_18_dob))
    assert resp18.status_code == 302
    u18 = User.query.filter_by(email="reg-18@example.com").first()
    assert u18 is not None
    assert u18.is_active is False
    assert u18.age >= 18

    # 3. Future DOB -> rejected
    future_dob = (today + timedelta(days=10)).strftime("%Y-%m-%d")
    resp_fut = client.post("/register", data=_reg_payload("reg-fut@example.com", future_dob))
    assert resp_fut.status_code == 200
    assert b"cannot be in the future" in resp_fut.data

    # 4. Pre-1900 DOB -> rejected
    resp_old = client.post("/register", data=_reg_payload("reg-old@example.com", "1899-12-31"))
    assert resp_old.status_code == 200
    assert b"cannot be earlier than 1900-01-01" in resp_old.data


def _login_user(client, account, password="Pass12345!"):
    return client.post(
        "/login",
        data={"email": account.email, "password": password},
        follow_redirects=True,
    )


def test_profile_edit_option_a_behavior(client, db):
    from models import User

    # Create active user
    u = User(
        first_name="Edit",
        last_name="Tester",
        email="edit-tester@example.com",
        dob=date(1995, 5, 20),
        gender="Male",
        city="Lagos",
        country="Nigeria",
        marital_status="Single",
        phone_number="+234800000001",
        is_active=True,
    )
    u.set_password("Pass12345!")
    db.session.add(u)
    db.session.commit()

    _login_user(client, u)

    # 1. Attempt to set under-18 DOB -> rejected, stored DOB unchanged
    client.post(f"/{u.id}/edit", data={
        "first_name": "Edit",
        "last_name": "Tester",
        "dob": "2020-01-01",
        "bio": "Attempted underage change",
    })
    db.session.refresh(u)
    assert u.dob == date(1995, 5, 20)
    assert u.bio == "Attempted underage change"  # Other valid field saved

    # 2. Attempt future DOB -> rejected, stored DOB unchanged
    client.post(f"/{u.id}/edit", data={
        "first_name": "Edit",
        "last_name": "Tester",
        "dob": "2099-01-01",
    })
    db.session.refresh(u)
    assert u.dob == date(1995, 5, 20)

    # 3. Valid adult DOB change -> saved
    client.post(f"/{u.id}/edit", data={
        "first_name": "Edit",
        "last_name": "Tester",
        "dob": "1998-10-15",
    })
    db.session.refresh(u)
    assert u.dob == date(1998, 10, 15)

    # 4. Legacy under-18 user editing other fields
    client.get("/logout")
    legacy = User(
        first_name="Legacy",
        last_name="Minor",
        email="legacy-minor@example.com",
        dob=date(2015, 6, 1),
        gender="Female",
        city="Abuja",
        country="Nigeria",
        marital_status="Single",
        phone_number="+234800000002",
        is_active=True,
    )
    legacy.set_password("Pass12345!")
    db.session.add(legacy)
    db.session.commit()

    _login_user(client, legacy)

    # Legacy user submits same DOB or blank DOB while changing bio
    client.post(f"/{legacy.id}/edit", data={
        "first_name": "Legacy",
        "last_name": "Minor",
        "dob": "2015-06-01",
        "bio": "Updated bio without changing DOB",
    })
    db.session.refresh(legacy)
    assert legacy.dob == date(2015, 6, 1)
    assert legacy.bio == "Updated bio without changing DOB"

    # 5. Unauthorized edit of another user -> 403
    unauth_resp = client.get(f"/{u.id}/edit")
    assert unauth_resp.status_code == 403


def test_ad_targeting_validation(client, db):
    from models import User

    client.get("/logout")
    advertiser = User(
        first_name="Ad",
        last_name="Manager",
        email="ad-manager@example.com",
        dob=date(1990, 1, 1),
        gender="Female",
        city="Lagos",
        country="Nigeria",
        marital_status="Single",
        phone_number="+234800000003",
        is_active=True,
    )
    advertiser.set_password("Pass12345!")
    db.session.add(advertiser)
    db.session.commit()

    _login_user(client, advertiser)

    base_payload = {
        "title": "Special Promotion",
        "description": "Exclusive offer for community members",
        "target_url": "https://example.com/promo",
        "budget": 20,
        "daily_budget": 5,
        "duration_days": 4,
        "currency": "USD",
        "placement": "sponsored",
    }

    # 1. Valid adult targeting (18 to 120)
    p1 = {**base_payload, "targeting": {"age_min": 18, "age_max": 120}}
    r1 = client.post("/create-campaign", json=p1)
    assert r1.status_code == 200
    assert r1.get_json()["success"] is True

    # 2. Min age below 18 -> 400
    p2 = {**base_payload, "targeting": {"age_min": 17, "age_max": 65}}
    r2 = client.post("/create-campaign", json=p2)
    assert r2.status_code == 400
    assert r2.get_json()["error"] == "Invalid age range"

    # 3. Max age above 120 -> 400
    p3 = {**base_payload, "targeting": {"age_min": 25, "age_max": 125}}
    r3 = client.post("/create-campaign", json=p3)
    assert r3.status_code == 400
    assert r3.get_json()["error"] == "Invalid age range"

    # 4. Reversed age range -> 400
    p4 = {**base_payload, "targeting": {"age_min": 50, "age_max": 30}}
    r4 = client.post("/create-campaign", json=p4)
    assert r4.status_code == 400
    assert r4.get_json()["error"] == "Invalid age range"


def test_get_user_profile_privacy_and_security(client, db):
    from models import User

    alice = User(
        first_name="Alice",
        last_name="Member",
        email="alice@example.com",
        dob=date(1992, 4, 15),
        gender="Female",
        city="Lagos",
        country="Nigeria",
        marital_status="Single",
        phone_number="+234800000004",
        is_active=True,
    )
    alice.set_password("Pass12345!")

    bob = User(
        first_name="Bob",
        last_name="Viewer",
        email="bob@example.com",
        dob=date(1988, 8, 22),
        gender="Male",
        city="Abuja",
        country="Nigeria",
        marital_status="Single",
        phone_number="+234800000005",
        is_active=True,
    )
    bob.set_password("Pass12345!")

    db.session.add_all([alice, bob])
    db.session.commit()

    # Log in as Bob
    _login_user(client, bob)

    # Bob views Alice's profile via API:
    # Full DOB MUST be None/omitted, but age must be present!
    resp = client.get(f"/get_user_profile/{alice.id}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["dob"] is None
    assert data["age"] == alice.age
    assert data["first_name"] == "Alice"

    # Bob views his OWN profile via API:
    # DOB is returned for self
    self_resp = client.get(f"/get_user_profile/{bob.id}")
    assert self_resp.status_code == 200
    self_data = self_resp.get_json()
    assert self_data["dob"] == "1988-08-22"
    assert self_data["age"] == bob.age

    # Alice blocks Bob
    alice.block(bob)
    db.session.commit()

    # Bob attempts to access Alice's profile -> 403 Forbidden
    blocked_resp = client.get(f"/get_user_profile/{alice.id}")
    assert blocked_resp.status_code == 403


def test_registration_above_18_and_marital_status_options(client, db):
    from models import User
    from time_utils import utcnow

    today = utcnow().date()
    # Age 25
    dob_25 = (today - timedelta(days=25 * 365 + 6)).strftime("%Y-%m-%d")
    payload_married = _reg_payload("reg-married@example.com", dob_25)
    payload_married["marital_status"] = "Married"

    resp_m = client.post("/register", data=payload_married)
    assert resp_m.status_code == 302
    u_m = User.query.filter_by(email="reg-married@example.com").first()
    assert u_m is not None
    assert u_m.marital_status == "Married"
    assert u_m.age >= 18

    # Age 35 with "Prefer not to say"
    dob_35 = (today - timedelta(days=35 * 365 + 8)).strftime("%Y-%m-%d")
    payload_pnts = _reg_payload("reg-pnts@example.com", dob_35)
    payload_pnts["marital_status"] = "Prefer not to say"

    resp_p = client.post("/register", data=payload_pnts)
    assert resp_p.status_code == 302
    u_p = User.query.filter_by(email="reg-pnts@example.com").first()
    assert u_p is not None
    assert u_p.marital_status == "Prefer not to say"
    assert u_p.age >= 18

    # Alumni is rejected on registration
    payload_alumni = _reg_payload("reg-alumni@example.com", dob_25)
    payload_alumni["marital_status"] = "Alumni"
    resp_alumni = client.post("/register", data=payload_alumni)
    assert resp_alumni.status_code == 200
    assert b"Please select a valid marital status." in resp_alumni.data
    assert User.query.filter_by(email="reg-alumni@example.com").first() is None


def test_user_age_visibility_controls(client, db):
    from models import User

    client.get("/logout")
    carol = User(
        first_name="Carol",
        last_name="Private",
        email="carol@example.com",
        dob=date(1991, 7, 11),
        gender="Female",
        city="Lagos",
        country="Nigeria",
        marital_status="Single",
        phone_number="+234800000006",
        is_active=True,
    )
    carol.set_password("Pass12345!")

    viewer = User(
        first_name="Viewer",
        last_name="Person",
        email="viewer@example.com",
        dob=date(1989, 3, 14),
        gender="Male",
        city="Lagos",
        country="Nigeria",
        marital_status="Single",
        phone_number="+234800000007",
        is_active=True,
    )
    viewer.set_password("Pass12345!")

    admin = User(
        first_name="Admin",
        last_name="User",
        email="admin-age@example.com",
        dob=date(1985, 1, 1),
        gender="Male",
        city="Lagos",
        country="Nigeria",
        marital_status="Single",
        phone_number="+234800000008",
        is_active=True,
        is_admin=True,
    )
    admin.set_password("Pass12345!")

    db.session.add_all([carol, viewer, admin])
    db.session.commit()

    # 1. Default for user is True
    assert carol.show_age_on_profile is True

    # 2. Log in as Carol and turn off age visibility via edit_profile form
    _login_user(client, carol)
    client.post(
        f"/{carol.id}/edit",
        data={
            "first_name": "Carol",
            "last_name": "Private",
            "has_age_visibility_toggle": "1",
            # show_age_on_profile omitted = checkbox unchecked
        },
    )
    db.session.refresh(carol)
    assert carol.show_age_on_profile is False

    # 3. Turn back on via API
    resp_api = client.post(
        "/api/user/privacy/age_visibility",
        json={"show_age_on_profile": True},
    )
    assert resp_api.status_code == 200
    assert resp_api.get_json()["show_age_on_profile"] is True
    db.session.refresh(carol)
    assert carol.show_age_on_profile is True

    # 4. Toggle via API (omitting value toggles it to False)
    resp_toggle = client.post("/api/user/privacy/age_visibility", json={})
    assert resp_toggle.status_code == 200
    assert resp_toggle.get_json()["show_age_on_profile"] is False
    db.session.refresh(carol)
    assert carol.show_age_on_profile is False

    # 5. Log in as Viewer: check Carol's profile via API and public HTML
    client.get("/logout")
    _login_user(client, viewer)

    api_resp = client.get(f"/get_user_profile/{carol.id}")
    assert api_resp.status_code == 200
    api_data = api_resp.get_json()
    assert api_data["age"] is None
    assert api_data["dob"] is None
    assert api_data["show_age_on_profile"] is False

    html_resp = client.get(f"/profile/{carol.public_id}")
    assert html_resp.status_code == 200
    # Age card/badge should NOT appear in rendered HTML
    assert b">Age</p>" not in html_resp.data

    # 6. Carol views her own profile via API
    client.get("/logout")
    _login_user(client, carol)
    self_resp = client.get(f"/get_user_profile/{carol.id}")
    assert self_resp.status_code == 200
    self_data = self_resp.get_json()
    assert self_data["age"] == carol.age
    assert self_data["dob"] == "1991-07-11"

    # 7. Admin views Carol's profile via API
    client.get("/logout")
    _login_user(client, admin)
    admin_resp = client.get(f"/get_user_profile/{carol.id}")
    assert admin_resp.status_code == 200
    admin_data = admin_resp.get_json()
    assert admin_data["age"] == carol.age
    assert admin_data["dob"] == "1991-07-11"


def test_marital_status_privacy_and_alumni_preservation(client, db):
    from models import User

    client.get("/logout")

    # A. Verify Alumni is NOT offered in register form
    reg_page = client.get("/register")
    assert reg_page.status_code == 200
    assert b'<option value="Alumni"' not in reg_page.data
    assert b'<option value="Married"' in reg_page.data
    assert b'<option value="Prefer not to say"' in reg_page.data

    alumni_user = User(
        first_name="Alum",
        last_name="Grad",
        email="alum-grad@example.com",
        dob=date(1993, 2, 20),
        gender="Male",
        city="Lagos",
        country="Nigeria",
        marital_status="Alumni",
        phone_number="+234800000009",
        is_active=True,
    )
    alumni_user.set_password("Pass12345!")

    viewer = User(
        first_name="Viewer2",
        last_name="Test",
        email="viewer2@example.com",
        dob=date(1994, 6, 12),
        gender="Female",
        city="Lagos",
        country="Nigeria",
        marital_status="Single",
        phone_number="+234800000010",
        is_active=True,
    )
    viewer.set_password("Pass12345!")

    db.session.add_all([alumni_user, viewer])
    db.session.commit()

    # B. Verify edit_profile and packages do not offer Alumni dropdown option
    _login_user(client, alumni_user)
    edit_page = client.get("/profile/edit")
    assert edit_page.status_code == 200
    assert b'<option value="Alumni"' not in edit_page.data
    assert b'<option value="Married"' in edit_page.data
    assert b'<option value="Prefer not to say"' in edit_page.data

    packages_page = client.get("/ad-packages")
    assert packages_page.status_code == 200
    assert b'<option value="Alumni">Alumni</option>' not in packages_page.data
    assert b'<option value="Married">Married</option>' in packages_page.data
    assert b'<option value="Prefer not to say">Prefer not to say</option>' in packages_page.data

    # C. Existing user with Alumni retains legacy Alumni value when saving form with placeholder/empty status
    client.post(
        "/profile/edit",
        data={
            "first_name": "Alum",
            "last_name": "Grad",
            "bio": "Updated bio text",
            "marital_status": "",  # Unselected in dropdown, placeholder submitted
        },
    )
    db.session.refresh(alumni_user)
    assert alumni_user.marital_status == "Alumni"
    assert alumni_user.bio == "Updated bio text"

    # D. Viewer sees legacy Alumni status rendered on public profile and API without regression
    client.get("/logout")
    _login_user(client, viewer)
    resp_alumni = client.get(f"/get_user_profile/{alumni_user.id}")
    assert resp_alumni.status_code == 200
    assert resp_alumni.get_json()["marital_status"] == "Alumni"

    html_alumni = client.get(f"/profile/{alumni_user.public_id}")
    assert html_alumni.status_code == 200
    assert b"Alumni" in html_alumni.data

    # E. User can cleanly update from legacy Alumni to Married
    client.get("/logout")
    _login_user(client, alumni_user)
    client.post(
        "/profile/edit",
        data={
            "first_name": "Alum",
            "last_name": "Grad",
            "marital_status": "Married",
        },
    )
    db.session.refresh(alumni_user)
    assert alumni_user.marital_status == "Married"

    # F. Viewer sees Married in API
    client.get("/logout")
    _login_user(client, viewer)
    resp_v1 = client.get(f"/get_user_profile/{alumni_user.id}")
    assert resp_v1.status_code == 200
    assert resp_v1.get_json()["marital_status"] == "Married"

    # G. User changes to Prefer not to say
    client.get("/logout")
    _login_user(client, alumni_user)
    client.post(
        "/profile/edit",
        data={
            "first_name": "Alum",
            "last_name": "Grad",
            "marital_status": "Prefer not to say",
        },
    )
    db.session.refresh(alumni_user)
    assert alumni_user.marital_status == "Prefer not to say"

    # H. Viewer cannot see Prefer not to say via API (masked to None) and public page suppresses status badge
    client.get("/logout")
    _login_user(client, viewer)
    resp_v2 = client.get(f"/get_user_profile/{alumni_user.id}")
    assert resp_v2.status_code == 200
    assert resp_v2.get_json()["marital_status"] is None

    html_resp = client.get(f"/profile/{alumni_user.public_id}")
    assert html_resp.status_code == 200
    assert b">Status</p>" not in html_resp.data

    # I. Alumni user sees their own status via API
    client.get("/logout")
    _login_user(client, alumni_user)
    resp_self = client.get(f"/get_user_profile/{alumni_user.id}")
    assert resp_self.status_code == 200
    assert resp_self.get_json()["marital_status"] == "Prefer not to say"

