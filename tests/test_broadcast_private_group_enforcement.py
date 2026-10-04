import json
import uuid
from datetime import date


def make_user(
    db,
    *,
    admin=False,
    super_admin=False,
    active=True,
    ai=False,
    permissions=None,
    promotional_email=True,
):
    from models import User

    token = uuid.uuid4().hex
    account = User(
        first_name="Privacy",
        last_name=token[:8],
        email=f"privacy-{token}@example.com",
        phone_number=f"+2347{uuid.uuid4().int % 10**9:09d}",
        dob=date(1990, 1, 1),
        gender="Other",
        city="Lagos",
        state="Lagos",
        country="Nigeria",
        marital_status="Single",
        is_active=active,
        is_admin=admin,
        is_super_admin=super_admin,
        is_ai_persona=ai,
        admin_permissions=json.dumps(permissions or []),
        receive_promotional_emails=promotional_email,
    )
    account.set_password("StrongPassw0rd!")
    db.session.add(account)
    db.session.flush()
    return account


def login(client, account):
    from flask import g

    with client.session_transaction() as session:
        session.clear()
        session["_user_id"] = str(account.id)
        session["_fresh"] = True
    g.pop("_login_user", None)


def make_group(db, creator, *, private, name=None):
    from models import Group

    group = Group(
        name=name or f"Group {uuid.uuid4().hex[:8]}",
        created_by=creator.id,
        is_private=private,
        is_active=True,
    )
    db.session.add(group)
    db.session.flush()
    group.members.append(creator)
    db.session.commit()
    return group


def test_broadcast_requires_permission_and_super_admin_is_allowed(db, client):
    ordinary_admin = make_user(db, admin=True)
    permitted_admin = make_user(
        db,
        admin=True,
        permissions=["broadcast_messages", "groups_manage"],
    )
    super_admin = make_user(db, admin=True, super_admin=True)
    db.session.commit()

    login(client, ordinary_admin)
    assert client.get("/admin/broadcast").status_code == 403
    assert client.post(
        "/admin/broadcast",
        data={"subject": "Denied", "message": "Denied"},
    ).status_code == 403

    login(client, permitted_admin)
    permitted_page = client.get("/admin/broadcast")
    assert permitted_page.status_code == 200
    assert b'name="csrf_token"' in permitted_page.data
    assert b"confirm('Send this broadcast" in permitted_page.data
    groups_page = client.get("/admin/groups")
    assert groups_page.status_code == 200
    assert b'href="/admin/broadcast"' in groups_page.data

    login(client, super_admin)
    assert client.get("/admin/broadcast").status_code == 200


def test_super_admin_assigns_existing_broadcast_permission(db, client):
    super_admin = make_user(db, admin=True, super_admin=True)
    sub_admin = make_user(db, admin=True, permissions=["groups_manage"])
    ordinary_user = make_user(db)
    db.session.commit()
    login(client, super_admin)

    response = client.post(
        f"/admin/users/{sub_admin.id}/permissions/broadcast",
        json={"enabled": True},
    )
    assert response.status_code == 200
    db.session.refresh(sub_admin)
    assert set(json.loads(sub_admin.admin_permissions)) == {
        "broadcast_messages",
        "groups_manage",
    }

    response = client.post(
        f"/admin/users/{sub_admin.id}/permissions/broadcast",
        json={"enabled": False},
    )
    assert response.status_code == 200
    db.session.refresh(sub_admin)
    assert json.loads(sub_admin.admin_permissions) == ["groups_manage"]

    assert client.post(
        f"/admin/users/{ordinary_user.id}/permissions/broadcast",
        json={"enabled": True},
    ).status_code == 400


def test_broadcast_isolated_delivery_respects_eligibility_and_email_opt_out(
    app,
    db,
    client,
    monkeypatch,
):
    from models import PushSubscription

    sender = make_user(
        db,
        admin=True,
        permissions=["broadcast_messages"],
    )
    successful = make_user(db)
    failed = make_user(db)
    opted_out = make_user(db, promotional_email=False)
    inactive = make_user(db, active=False)
    automated = make_user(db, ai=True)
    db.session.add_all(
        PushSubscription(
            user_id=account.id,
            endpoint=f"https://push.example/{uuid.uuid4().hex}",
            p256dh="p256dh",
            auth="auth",
        )
        for account in (successful, failed, opted_out, inactive, automated)
    )
    db.session.commit()

    email_calls = []

    def send_email(**kwargs):
        email_calls.append(kwargs)
        return kwargs["to_email"] != failed.email

    push_calls = []

    def send_push(user_ids, payload):
        push_calls.append((set(user_ids), payload))
        return True

    audit_calls = []
    monkeypatch.setattr(
        app.logger,
        "info",
        lambda message, *args, **_kwargs: audit_calls.append((message, args)),
    )
    monkeypatch.setattr("admin.admin.EmailService.send_email", send_email)
    monkeypatch.setattr("utils.push_service.send_push_notifications", send_push)
    login(client, sender)

    response = client.post(
        "/admin/broadcast",
        data={
            "subject": "Safe announcement",
            "message": "Hello <script>alert(1)</script>\nSecond line",
        },
    )
    assert response.status_code == 302

    called_addresses = [call["to_email"] for call in email_calls]
    assert successful.email in called_addresses
    assert failed.email in called_addresses
    assert opted_out.email not in called_addresses
    assert inactive.email not in called_addresses
    assert automated.email not in called_addresses
    assert all(isinstance(address, str) for address in called_addresses)
    successful_call = next(
        call for call in email_calls if call["to_email"] == successful.email
    )
    assert "&lt;script&gt;" in successful_call["html_content"]
    assert "<script>" not in successful_call["html_content"]

    pushed_ids = set().union(*(ids for ids, _payload in push_calls))
    assert {successful.id, failed.id, opted_out.id}.issubset(pushed_ids)
    assert inactive.id not in pushed_ids
    assert automated.id not in pushed_ids
    assert all(payload["url"] == "/user_dashboard" for _ids, payload in push_calls)
    assert all(payload["event_type"] == "admin_broadcast" for _ids, payload in push_calls)
    audit_formats = " ".join(message for message, _args in audit_calls)
    assert "Admin broadcast created" in audit_formats
    assert "Admin broadcast completed" in audit_formats
    assert all("<script>" not in str(call) for call in audit_calls)


def test_broadcast_post_is_csrf_protected_when_protection_enabled(
    app,
    db,
    client,
    monkeypatch,
):
    admin = make_user(
        db,
        admin=True,
        permissions=["broadcast_messages"],
    )
    db.session.commit()
    login(client, admin)
    email_mock = []
    monkeypatch.setattr(
        "admin.admin.EmailService.send_email",
        lambda **kwargs: email_mock.append(kwargs),
    )

    previous = app.config["WTF_CSRF_ENABLED"]
    app.config["WTF_CSRF_ENABLED"] = True
    try:
        response = client.post(
            "/admin/broadcast",
            data={"subject": "Missing token", "message": "Must be rejected"},
        )
    finally:
        app.config["WTF_CSRF_ENABLED"] = previous

    assert response.status_code in {302, 400}
    assert not email_mock


def test_private_group_access_posting_and_data_leak_guards(app, db, client):
    from models import Group, Notification, NotificationType, Post
    from users.user import get_groups_data_for_user

    creator = make_user(db)
    member = make_user(db)
    outsider = make_user(db)
    admin = make_user(db, admin=True)
    private_group = make_group(
        db,
        creator,
        private=True,
        name=f"Secret {uuid.uuid4().hex[:8]}",
    )
    public_group = make_group(db, creator, private=False)
    private_group.members.append(member)
    public_group.members.append(member)
    private_post = Post(
        content=f"private-marker-{uuid.uuid4().hex}",
        author_id=member.id,
        group_id=private_group.id,
    )
    db.session.add(private_post)
    db.session.flush()
    legacy_public_share = Post(
        content=f"legacy-wrapper-{uuid.uuid4().hex}",
        author_id=outsider.id,
        shared_post_id=private_post.id,
        share_type="share",
    )
    db.session.add(legacy_public_share)
    db.session.add(
        Notification(
            user_id=outsider.id,
            actor_id=member.id,
            type=NotificationType.NEW_POST,
            entity_id=private_post.id,
            entity_type="group_post",
            message="Private notification must not leak",
        )
    )
    db.session.commit()

    anonymous = app.test_client()
    assert anonymous.get(f"/groups/{private_group.id}").status_code in {302, 401, 403}

    login(client, outsider)
    assert client.get(f"/groups/{private_group.id}").status_code == 403
    assert client.get(f"/groups/{private_group.id}/posts").status_code == 403
    assert client.post(f"/groups/{private_group.id}/join").status_code == 403
    assert client.get(f"/get_post/{private_post.id}").status_code == 403
    assert client.get(f"/post/{private_post.public_id}").status_code == 403
    assert private_post.content.encode() not in client.get(
        f"/search?q={private_post.content}"
    ).data
    assert private_post.content.encode() not in client.get(
        f"/profile/{member.public_id}"
    ).data
    assert private_post.content.encode() not in client.get(
        "/user_dashboard?limit=50"
    ).data
    assert legacy_public_share.content.encode() not in client.get(
        "/user_dashboard?limit=50"
    ).data
    assert legacy_public_share.content.encode() not in client.get(
        f"/profile/{outsider.public_id}"
    ).data
    assert client.get(f"/post/{legacy_public_share.public_id}").status_code == 403
    assert client.get(f"/get_post/{legacy_public_share.id}").status_code == 403
    assert legacy_public_share.content.encode() not in client.get(
        f"/search?q={legacy_public_share.content}"
    ).data
    assert not any(
        group["id"] == private_group.id
        for group in client.get("/groups/all?per_page=100").get_json()
    )
    assert not any(
        group["id"] == private_group.id
        for group in get_groups_data_for_user(outsider.id)
    )
    assert all(
        item["message"] != "Private notification must not leak"
        for item in client.get("/notifications").get_json()
    )

    login(client, member)
    assert client.get(f"/groups/{private_group.id}").status_code == 200
    assert client.post(f"/repost/{legacy_public_share.public_id}").status_code == 403
    assert client.post(f"/share_post/{legacy_public_share.public_id}").status_code == 403
    assert any(
        group["id"] == private_group.id
        for group in client.get("/groups/all?per_page=100").get_json()
    )
    assert client.post(
        f"/groups/{private_group.id}/post",
        data={"post_content": "member bypass"},
    ).status_code == 403
    assert client.post(
        f"/edit_post/{private_post.id}",
        data={"post_content": "member edit bypass"},
    ).status_code == 403
    private_page = client.get(f"/groups/{private_group.id}")
    assert f"deletePost({private_post.id})".encode() in private_page.data
    assert client.post(f"/delete_post/{private_post.id}").status_code == 200
    assert db.session.get(Post, private_post.id) is None
    assert client.post(
        f"/groups/{public_group.id}/post",
        data={"post_content": "public group member post"},
    ).status_code == 200

    login(client, creator)
    assert client.post(
        f"/groups/{private_group.id}/post",
        data={"post_content": "creator admin post"},
    ).status_code == 200

    private_group.members.append(admin)
    db.session.commit()
    login(client, admin)
    assert client.post(
        f"/groups/{private_group.id}/post",
        data={"post_content": "global admin post"},
    ).status_code == 200


def test_matchmaking_group_stable_id_remains_stricter_than_private_group(
    app,
    db,
    client,
    monkeypatch,
):
    from models import Post

    creator = make_user(db)
    normal_member = make_user(db)
    admin = make_user(db, admin=True)
    ai_member = make_user(db, ai=True)
    protected = make_group(
        db,
        creator,
        private=False,
        name=f"Renamed protected {uuid.uuid4().hex[:6]}",
    )
    protected.members.append(normal_member)
    protected.members.append(ai_member)
    db.session.commit()
    monkeypatch.setitem(app.config, "MATCHMAKING_GROUP_ID", protected.id)

    login(client, creator)
    assert client.post(
        f"/groups/{protected.id}/post",
        data={"post_content": "creator is not enough"},
    ).status_code == 403

    login(client, normal_member)
    assert client.post(
        f"/groups/{protected.id}/post",
        data={"post_content": "ordinary bypass"},
    ).status_code == 403

    login(client, ai_member)
    assert client.post(
        f"/groups/{protected.id}/post",
        data={"post_content": "AI bypass"},
    ).status_code == 403

    login(client, admin)
    assert client.post(
        f"/groups/{protected.id}/post",
        data={"post_content": "trusted matchmaking post"},
    ).status_code == 200
    protected_post = Post.query.filter_by(
        group_id=protected.id,
        content="trusted matchmaking post",
    ).one()
    assert protected_post.group_id == protected.id

    login(client, creator)
    assert client.post(f"/repost/{protected_post.public_id}").status_code == 403


def test_ai_profile_cannot_create_or_pay_for_matchmaking_boost(db, client):
    ai_user = make_user(db, ai=True)
    db.session.commit()
    login(client, ai_user)
    assert client.post("/create-request", json={}).status_code == 403
    assert client.post("/initiate-matchmaking-payment", json={}).status_code == 403


def test_matchmaking_payment_success_activates_entitlement_without_public_post(
    db,
    monkeypatch,
):
    from models import MatchmakingPackage, MatchmakingPayments, MatchmakingRequest, Post
    from payments.payment_service import MatchmakingPaymentService
    from utils.matchmaking_boosts import (
        featured_boosts_for_viewer,
        has_boost_group_consent,
    )

    account = make_user(db)
    viewer = make_user(db)
    package = MatchmakingPackage(
        name=f"Package {uuid.uuid4().hex[:8]}",
        price=2,
        duration_days=30,
        is_active=True,
    )
    db.session.add(package)
    db.session.flush()
    request_row = MatchmakingRequest(
        user_id=account.id,
        package_id=package.id,
        about_you="About this member",
        ideal_partner="A compatible partner",
        status="pending",
        payment_status="pending",
    )
    db.session.add(request_row)
    db.session.flush()
    payment = MatchmakingPayments(
        user_id=account.id,
        matchmaking_request_id=request_row.id,
        package_id=package.id,
        amount=2,
        currency="USD",
        status="pending",
        payment_status="pending",
        gateway="flutterwave",
        gateway_reference=f"MM-{uuid.uuid4().hex}",
    )
    db.session.add(payment)
    db.session.commit()
    post_count = Post.query.count()
    monkeypatch.setenv("FLW_SECRET_KEY", "FLWSECK_TEST-local")
    monkeypatch.setenv("FLW_PUBLIC_KEY", "FLWPUBK_TEST-local")
    service = MatchmakingPaymentService()
    emails = []
    monkeypatch.setattr(
        service,
        "send_matchmaking_payment_success_email",
        lambda *_args, **_kwargs: emails.append("sent") or True,
    )

    assert service.handle_matchmaking_payment_success(
        payment,
        {"status": "successful", "id": f"gateway-{uuid.uuid4().hex}"},
    )
    db.session.refresh(request_row)
    assert request_row.status == "active"
    assert request_row.payment_status == "completed"
    assert request_row.end_date is not None
    assert has_boost_group_consent(request_row.id) is True
    assert request_row.id in {
        item.id for item in featured_boosts_for_viewer(viewer).items
    }
    assert Post.query.count() == post_count

    first_end_date = request_row.end_date
    assert service.handle_matchmaking_payment_success(
        payment,
        {"status": "successful", "id": f"gateway-{uuid.uuid4().hex}"},
    )
    db.session.refresh(request_row)
    assert request_row.end_date == first_end_date
    assert emails == ["sent"]
    assert Post.query.count() == post_count
