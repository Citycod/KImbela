from datetime import date
from pathlib import Path
import uuid

from models import Group, Post, ReportedContent, User
from users.user import format_group_member_count
import users.user as user_routes


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


def _make_group(
    db, owner, name="Community", *members, display_member_count=None
):
    group = Group(
        name=name,
        description="A test group",
        category="social",
        created_by=owner.id,
        member_count=999,
        display_member_count=display_member_count,
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


def test_report_modal_has_explicit_guarded_send_action(app):
    shared = app.jinja_env.get_template("partials/report_modal.html").render(
        csrf_token=lambda: "test-csrf"
    )
    group = (REPO_ROOT / "templates/group_detail.html").read_text()

    for markup in (shared, group):
        assert "Send Report" in markup
        assert markup.count('id="sendReportBtn"') == 1
        assert "background-color: #ea580c" in markup
        assert "color: #ffffff" in markup
        assert "function openReportModal()" in markup
        assert "reportForm').addEventListener('submit'" in markup
        assert 'id="otherReason"' in markup
        assert "if (sendButton.disabled) return" in markup
        assert "sendButton.disabled = true" in markup
        assert "if (!reason)" in markup
        assert "X-CSRFToken" in markup


def test_public_group_surfaces_use_configured_count_and_hide_actual_membership(
    client, db, user, login
):
    second_member = _make_user(db)
    group = _make_group(
        db, user, "Community", second_member, display_member_count="500+"
    )
    login()

    detail = client.get(f"/groups/{group.id}")
    assert detail.status_code == 200
    assert b"500+ members" in detail.data
    assert b"2 members" not in detail.data
    assert b"999 members" not in detail.data
    assert b"Recent Members" not in detail.data
    assert b"Cancel" in detail.data
    assert b"Send Report" in detail.data

    groups_page = client.get("/groups")
    assert groups_page.status_code == 200

    member_api = client.get(f"/groups/{group.id}/members")
    assert member_api.status_code == 403
    assert member_api.get_json()["error"] == "Administrator access required"

    groups_api = client.get("/groups/all")
    item = next(item for item in groups_api.get_json() if item["id"] == group.id)
    assert "member_count" not in item
    assert item["member_count_label"] == "500+ members"

    user_groups_api = client.get("/groups/user_groups")
    user_group = next(
        item for item in user_groups_api.get_json() if item["id"] == group.id
    )
    assert "member_count" not in user_group
    assert user_group["member_count_label"] == "500+ members"

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
    assert b"Community" in response.data
    assert b"1 member" not in response.data
    public_item = next(
        item
        for item in client.get("/groups/all").get_json()
        if item["id"] == group.id
    )
    assert public_item["member_count_label"] == "Community"
    assert "member_count" not in public_item


def test_admin_can_create_group_with_public_count(client, db):
    admin = _make_user(db, super_admin=True)
    _login(client, admin)

    response = client.post(
        "/admin/groups/create",
        data={
            "name": "New Public Count Group",
            "description": "Created from group management",
            "category": "social",
            "is_private": "false",
            "display_member_count": "5k+",
        },
    )

    assert response.status_code == 200
    group = db.session.get(Group, response.get_json()["group_id"])
    assert group.display_member_count == "5K+"
    assert group.public_member_count_label == "5K+ members"


def test_admin_can_change_public_count_without_changing_real_membership(client, db):
    admin = _make_user(db, super_admin=True)
    member = _make_user(db)
    group = _make_group(
        db, admin, "Managed Group", member, display_member_count="300+"
    )
    actual_member_ids = {account.id for account in group.members.all()}
    _login(client, admin)

    management_page = client.get("/admin/groups")
    assert management_page.status_code == 200
    assert b"Public member count" in management_page.data
    assert b"300+" in management_page.data

    edit = client.get(f"/admin/groups/{group.id}/edit")
    assert edit.status_code == 200
    assert edit.get_json()["group"]["display_member_count"] == "300+"

    updated = client.post(
        f"/admin/groups/{group.id}/update",
        data={
            "name": group.name,
            "description": group.description,
            "category": group.category,
            "is_private": "false",
            "display_member_count": "1.5k+",
        },
    )
    assert updated.status_code == 200
    db.session.refresh(group)
    assert group.display_member_count == "1.5K+"
    assert {account.id for account in group.members.all()} == actual_member_ids

    public_item = next(
        item
        for item in client.get("/groups/all").get_json()
        if item["id"] == group.id
    )
    assert public_item["member_count_label"] == "1.5K+ members"
    assert "member_count" not in public_item


def test_normal_user_cannot_edit_group_public_count(client, db):
    owner = _make_user(db)
    group = _make_group(db, owner, display_member_count="300+")
    _login(client, owner)

    response = client.post(
        f"/admin/groups/{group.id}/update",
        data={"display_member_count": "900+"},
    )
    assert response.status_code == 403
    db.session.refresh(group)
    assert group.display_member_count == "300+"


def test_invalid_public_count_is_rejected(client, db):
    admin = _make_user(db, super_admin=True)
    group = _make_group(db, admin)
    _login(client, admin)

    response = client.post(
        f"/admin/groups/{group.id}/update",
        data={
            "name": group.name,
            "category": group.category,
            "display_member_count": "about five hundred",
        },
    )
    assert response.status_code == 400
    assert "must look like" in response.get_json()["error"]


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


def test_group_serialization_hides_actual_count_by_default(db, user):
    group = _make_group(db, user, display_member_count="2K+")

    public_data = group.to_dict()
    assert public_data["member_count_label"] == "2K+ members"
    assert "member_count" not in public_data
    assert group.to_dict(include_actual_member_count=True)["member_count"] == 999


def test_cached_group_metadata_drops_legacy_actual_count(db, user, monkeypatch):
    group = _make_group(db, user, display_member_count="700+")
    monkeypatch.setattr(
        user_routes,
        "safe_cache_get",
        lambda _key: [
            {
                "id": group.id,
                "name": group.name,
                "member_count": 999,
                "member_count_label": "999 members",
                "is_member": True,
            }
        ],
    )

    result = user_routes.get_groups_data_for_user(user.id)

    assert result[0]["member_count_label"] == "700+ members"
    assert "member_count" not in result[0]


def test_dashboard_sidebar_priority_and_banner_order_are_preserved(client, user):
    with client.session_transaction() as session:
        session["_user_id"] = str(user.id)
        session["_fresh"] = True
    response = client.get("/user_dashboard")
    assert response.status_code == 200
    dashboard = response.get_data(as_text=True)
    primary_sidebar = dashboard.split('<aside class="kb-left-sidebar">', 1)[1].split(
        "</aside>", 1
    )[0]
    assert primary_sidebar.index("Home") < primary_sidebar.index("Sponsored Ads")
    assert primary_sidebar.index("Sponsored Ads") < primary_sidebar.index(
        "Find Your Match"
    )
    assert primary_sidebar.index("Find Your Match") < primary_sidebar.index(
        "Boost Your Profile"
    )
    assert primary_sidebar.index("Boost Your Profile") < primary_sidebar.index(
        "Install Kimbela"
    )
    assert primary_sidebar.index("Install Kimbela") < primary_sidebar.index("Marketplace")
    assert primary_sidebar.index("Marketplace") < primary_sidebar.index("Partner")
    assert primary_sidebar.index("Partner") < primary_sidebar.index("Messages")
    assert primary_sidebar.count("Find Your Match") == 1
    assert primary_sidebar.count("Boost Your Profile") == 1
    assert primary_sidebar.count("Install Kimbela") == 1
    assert primary_sidebar.count('class="kb-install-nav"') == 1
    assert primary_sidebar.count("kb-install-nav-badge") == 1
    assert "bi-phone-fill" in primary_sidebar
    assert primary_sidebar.count("Sponsored Ads") == 1
    assert primary_sidebar.count("Marketplace") == 1
    assert primary_sidebar.count("Partner") == 1
    assert primary_sidebar.index("Partner") < primary_sidebar.index(
        "vertical-ad-banner"
    )
    assert primary_sidebar.index("Logout") < primary_sidebar.index(
        "vertical-ad-banner"
    )

    mobile_sidebar = dashboard.split("<!-- MOBILE SIDEBAR -->", 1)[1].split(
        "<!-- DASHBOARD CONTAINER -->", 1
    )[0]
    assert mobile_sidebar.index("Home") < mobile_sidebar.index("Sponsored Ads")
    assert mobile_sidebar.index("Sponsored Ads") < mobile_sidebar.index(
        "Find Your Match"
    )
    assert mobile_sidebar.index("Find Your Match") < mobile_sidebar.index(
        "Boost Your Profile"
    )
    assert mobile_sidebar.index("Boost Your Profile") < mobile_sidebar.index(
        "Install Kimbela"
    )
    assert mobile_sidebar.index("Install Kimbela") < mobile_sidebar.index("Marketplace")
    assert mobile_sidebar.index("Marketplace") < mobile_sidebar.index("Partner")
    assert mobile_sidebar.index("Partner") < mobile_sidebar.index("Messages")
    assert mobile_sidebar.index("Messages") < mobile_sidebar.index("Notifications")
    assert mobile_sidebar.index("Notifications") < mobile_sidebar.index(
        "bi-person mr-3"
    )
    assert mobile_sidebar.index("bi-person mr-3") < mobile_sidebar.index(
        "bi-people mr-3"
    )
    assert mobile_sidebar.index("Notification sounds") < mobile_sidebar.index(
        "Logout"
    )
    assert mobile_sidebar.count("Sponsored Ads") == 1
    assert mobile_sidebar.count("Find Your Match") == 1
    assert mobile_sidebar.count("Boost Your Profile") == 1
    assert mobile_sidebar.count("Install Kimbela") == 1
    assert mobile_sidebar.count("kb-install-mobile-nav") == 1
    assert mobile_sidebar.count("Marketplace") == 1
    assert mobile_sidebar.count("Partner") == 1
    assert mobile_sidebar.count('>Messages</span>') == 1
    assert mobile_sidebar.count('>Notifications</span>') == 1
    assert "window.openMessenger(); toggleMobileMenu();" in mobile_sidebar
    assert "document.getElementById('notificationDropdown').click()" in mobile_sidebar

    assert "<!-- DASHBOARD CONTAINER -->" not in dashboard
    assert 'class="pt-16 flex"' not in dashboard
    assert "w-85 h-screen sticky top-16" not in dashboard
    assert "w-96 h-screen sticky top-16" not in dashboard
    assert dashboard.count('id="mobileFeedAdCandidates"') == 1
    assert dashboard.count('<aside class="kb-left-sidebar">') == 1
    assert dashboard.count('<aside class="kb-right-sidebar">') == 1
    assert dashboard.count('class="marketplace-banner mb-4"') == 1
    assert dashboard.count('class="matchmaking-banner mt-4"') == 1

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
    dashboard_source = (REPO_ROOT / "templates/user_dashboard.html").read_text()
    right_sidebar_source = dashboard_source.split(
        '<aside class="kb-right-sidebar">', 1
    )[1].split("</aside>", 1)[0]
    assert "spotlight_banner.target_url" in right_sidebar_source
    assert "dashboard-spotlight" in right_sidebar_source
    assert 'class="dashboard-ad-link"' in right_sidebar_source
