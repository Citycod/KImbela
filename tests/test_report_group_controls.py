from datetime import date
from pathlib import Path
import uuid

from models import Group, Post, ReportedContent, User
from users.user import format_group_member_count


REPO_ROOT = Path(__file__).resolve().parents[1]


def _make_user(db, *, admin=False, super_admin=False):
    token = uuid.uuid4().hex[:10]
    account = User(
        first_name="Group",
        last_name=token,
        email=f"group-{token}@example.com",
        phone_number=f"+2348{token[:9]}",
        dob=date(1990, 1, 1),
        gender="Female",
        city="Lagos",
        country="Nigeria",
        state="Lagos",
        marital_status="Single",
        is_active=True,
        is_admin=admin,
        is_super_admin=super_admin,
    )
    account.set_password("StrongPassw0rd!")
    db.session.add(account)
    db.session.commit()
    return account


def _login(client, account):
    response = client.post(
        "/login",
        data={"email": account.email, "password": "StrongPassw0rd!"},
        follow_redirects=False,
    )
    assert response.status_code in {302, 303}


def _make_group(db, owner, name="Community", *members):
    group = Group(
        name=name,
        description="A test group",
        category="social",
        created_by=owner.id,
        member_count=999,
        is_active=True,
    )
    group.members.append(owner)
    for member in members:
        group.members.append(member)
    db.session.add(group)
    db.session.commit()
    return group


def test_report_endpoint_requires_authentication(client):
    response = client.post(
        "/report_content",
        json={"content_type": "post", "content_id": 1, "reason": "Spam"},
    )
    assert response.status_code in {302, 401}


def test_report_requires_reason_and_deduplicates_pending_submission(
    client, db, user, login
):
    author = _make_user(db)
    post = Post(content="Report target", author_id=author.id)
    db.session.add(post)
    db.session.commit()
    login()

    empty = client.post(
        "/report_content",
        json={"content_type": "post", "content_id": post.id, "reason": ""},
    )
    assert empty.status_code == 400
    assert empty.get_json()["success"] is False

    invalid = client.post(
        "/report_content",
        json={
            "content_type": "post",
            "content_id": post.id,
            "reason": "Not a supported reason",
        },
    )
    assert invalid.status_code == 400

    payload = {"content_type": "post", "content_id": post.id, "reason": "Spam"}
    first = client.post("/report_content", json=payload)
    duplicate = client.post("/report_content", json=payload)

    assert first.status_code == 200
    assert duplicate.status_code == 200
    assert first.get_json()["success"] is True
    assert duplicate.get_json()["success"] is True
    assert ReportedContent.query.filter_by(
        reporter_id=user.id,
        content_type="post",
        content_id=post.id,
        status="pending",
    ).count() == 1


def test_report_other_reason_requires_details(client, db, user, login):
    author = _make_user(db)
    post = Post(content="Report target", author_id=author.id)
    db.session.add(post)
    db.session.commit()
    login()

    response = client.post(
        "/report_content",
        json={"content_type": "post", "content_id": post.id, "reason": "Other"},
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "Please provide additional details"


def test_report_modal_has_explicit_guarded_send_action():
    shared = (REPO_ROOT / "templates/partials/report_modal.html").read_text()
    group = (REPO_ROOT / "templates/group_detail.html").read_text()

    for markup in (shared, group):
        assert "Send Report" in markup
        assert "function openReportModal()" in markup
        assert "reportForm').addEventListener('submit'" in markup
        assert 'id="otherReason"' in markup
        assert "if (sendButton.disabled) return" in markup
        assert "sendButton.disabled = true" in markup
        assert "if (!reason)" in markup
        assert "X-CSRFToken" in markup


def test_group_member_count_uses_authoritative_membership_and_hides_member_list(
    client, db, user, login
):
    second_member = _make_user(db)
    group = _make_group(db, user, "Community", second_member)
    login()

    detail = client.get(f"/groups/{group.id}")
    assert detail.status_code == 200
    assert b"2 members" in detail.data
    assert b"999 members" not in detail.data
    assert b"Recent Members" not in detail.data

    groups_page = client.get("/groups")
    assert groups_page.status_code == 200

    member_api = client.get(f"/groups/{group.id}/members")
    assert member_api.status_code == 403
    assert member_api.get_json()["error"] == "Administrator access required"

    groups_api = client.get("/groups/all")
    item = next(item for item in groups_api.get_json() if item["id"] == group.id)
    assert item["member_count"] == 2
    assert item["member_count_label"] == "2 members"

    filtered = client.get("/groups/all?category=social&privacy=public")
    assert any(item["id"] == group.id for item in filtered.get_json())


def test_admin_can_retrieve_group_members(client, db):
    admin = _make_user(db, admin=True)
    member = _make_user(db)
    group = _make_group(db, admin, "Admin Group", member)
    _login(client, admin)

    response = client.get(f"/groups/{group.id}/members")
    assert response.status_code == 200
    assert {item["id"] for item in response.get_json()["members"]} == {
        admin.id,
        member.id,
    }
    detail = client.get(f"/groups/{group.id}")
    assert b"Recent Members" in detail.data


def test_group_page_still_works_for_non_member(client, db):
    owner = _make_user(db)
    visitor = _make_user(db)
    group = _make_group(db, owner)
    _login(client, visitor)

    response = client.get(f"/groups/{group.id}")
    assert response.status_code == 200
    assert b"1 member" in response.data


def test_matchmaking_group_posting_is_admin_only(client, db, app, monkeypatch):
    normal = _make_user(db)
    admin = _make_user(db, admin=True)
    group = _make_group(db, normal, "Matchmaking", admin)
    monkeypatch.setitem(app.config, "MATCHMAKING_GROUP_ID", str(group.id))
    monkeypatch.setattr("users.user._notify_group_post_members", lambda *args: None)

    group.name = "Connections Hub"
    db.session.commit()

    _login(client, normal)
    detail = client.get(f"/groups/{group.id}")
    assert detail.status_code == 200
    assert b'id="postModal"' not in detail.data
    denied = client.post(
        f"/groups/{group.id}/post", data={"post_content": "Blocked post"}
    )
    assert denied.status_code == 403
    assert Post.query.filter_by(group_id=group.id).count() == 0

    client.get("/logout")
    _login(client, admin)
    allowed = client.post(
        f"/groups/{group.id}/post", data={"post_content": "Admin post"}
    )
    assert allowed.status_code == 200
    assert allowed.get_json()["success"] is True
    assert Post.query.filter_by(group_id=group.id, author_id=admin.id).count() == 1


def test_similarly_named_unprotected_group_posting_remains_available(
    client, db, app, monkeypatch
):
    member = _make_user(db)
    protected_owner = _make_user(db)
    protected_group = _make_group(db, protected_owner, "Renamed Protected Group")
    group = _make_group(db, member, "Matchmaking")
    monkeypatch.setitem(app.config, "MATCHMAKING_GROUP_ID", protected_group.id)
    monkeypatch.setattr("users.user._notify_group_post_members", lambda *args: None)
    _login(client, member)

    response = client.post(
        f"/groups/{group.id}/post", data={"post_content": "A normal post"}
    )
    assert response.status_code == 200
    assert response.get_json()["success"] is True


def test_group_member_count_compact_formatting():
    assert format_group_member_count(0) == "0 members"
    assert format_group_member_count(1) == "1 member"
    assert format_group_member_count(42) == "42 members"
    assert format_group_member_count(318) == "300+ members"
    assert format_group_member_count(584) == "500+ members"
    assert format_group_member_count(1240) == "1.2K+ members"
    assert format_group_member_count(1999) == "1.9K+ members"


def test_dashboard_sidebar_priority_and_banner_order_are_preserved():
    dashboard = (REPO_ROOT / "templates/user_dashboard.html").read_text()
    primary_sidebar = dashboard.split('<aside class="kb-left-sidebar">', 1)[1].split(
        "</aside>", 1
    )[0]
    assert primary_sidebar.index("Home") < primary_sidebar.index("Find Your Match")
    assert primary_sidebar.index("Find Your Match") < primary_sidebar.index(
        "Boost Your Profile"
    )
    assert primary_sidebar.index("Boost Your Profile") < primary_sidebar.index(
        "Install Kimbela"
    )
    assert primary_sidebar.count("Find Your Match") == 1
    assert primary_sidebar.count("Boost Your Profile") == 1
    assert primary_sidebar.count("Install Kimbela") == 1

    mobile_sidebar = dashboard.split("<!-- MOBILE SIDEBAR -->", 1)[1].split(
        "<!-- DASHBOARD CONTAINER -->", 1
    )[0]
    assert mobile_sidebar.index("Home") < mobile_sidebar.index("Find Your Match")
    assert mobile_sidebar.index("Find Your Match") < mobile_sidebar.index(
        "Boost Your Profile"
    )
    assert mobile_sidebar.index("Boost Your Profile") < mobile_sidebar.index(
        "Install Kimbela"
    )

    legacy_sidebar = dashboard.split("<!-- DASHBOARD CONTAINER -->", 1)[1].split(
        "<!-- MAIN CONTENT -->", 1
    )[0]
    assert legacy_sidebar.index("Find Your Match") < legacy_sidebar.index(
        "Boost Your Profile"
    )
    assert legacy_sidebar.index("Boost Your Profile") < legacy_sidebar.index(
        "Install Kimbela"
    )

    right_sidebar = dashboard.split('<aside class="kb-right-sidebar">', 1)[1].split(
        "</aside>", 1
    )[0]
    assert right_sidebar.index("marketplace-banner") < right_sidebar.index(
        "matchmaking-banner"
    )
    assert right_sidebar.index("matchmaking-banner") < right_sidebar.index(
        "right-ad-banner-2"
    )
    assert right_sidebar.index("right-ad-banner-2") < right_sidebar.index(
        "Trending Groups"
    )
    assert "spotlight_banner.target_url" in right_sidebar
    assert "dashboard-spotlight" in right_sidebar
    assert 'class="dashboard-ad-link"' in right_sidebar
