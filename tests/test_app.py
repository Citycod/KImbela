def test_home_page(client):
    response = client.get("/")
    assert response.status_code == 200


def test_404(client):
    response = client.get("/this-route-should-not-exist")
    assert response.status_code == 404


def test_socket_test_page(client):
    response = client.get("/socket-test")
    assert response.status_code == 200


def test_uploads_requires_login(client):
    response = client.get("/uploads/somefile.png")
    assert response.status_code in (302, 401)


def test_debug_routes_disabled_by_default(client):
    response = client.get("/debug/requests")
    assert response.status_code == 404


def test_shared_post_page_uses_public_uuid(client, db, user):
    from models import Post

    post = Post(content="Shared link test", author_id=user.id)
    db.session.add(post)
    db.session.commit()

    response = client.get(f"/post/{post.public_id}")
    assert response.status_code == 200
    assert b"Shared link test" in response.data
    assert response.headers["Cache-Control"] == "private, no-store, max-age=0"
    assert "Cookie" in response.headers.get("Vary", "")

    with client.session_transaction() as browser_session:
        browser_session["_user_id"] = str(user.id)
        browser_session["_fresh"] = True
    authenticated_response = client.get(f"/post/{post.public_id}")
    assert authenticated_response.status_code == 200
    assert authenticated_response.headers["Cache-Control"] == (
        "private, no-store, max-age=0"
    )
    assert "Cookie" in authenticated_response.headers.get("Vary", "")


def test_shared_post_page_uses_post_image_for_social_preview(client, db, user):
    from models import Post

    original_post = Post(
        content="Original post",
        author_id=user.id,
        image="https://cdn.example.com/original-post.jpg",
    )
    db.session.add(original_post)
    db.session.flush()

    shared_post = Post(
        content="Look at this",
        author_id=user.id,
        shared_post_id=original_post.id,
        share_type="share",
    )
    db.session.add(shared_post)
    db.session.commit()

    response = client.get(f"/post/{shared_post.public_id}")
    assert response.status_code == 200
    assert b'<meta property="og:image" content="https://cdn.example.com/original-post.jpg">' in response.data
    assert b'<meta name="twitter:image" content="https://cdn.example.com/original-post.jpg">' in response.data


def test_shared_post_page_rewrites_local_uploads_for_public_preview(client, db, user):
    from models import Post

    post = Post(
        content="Local upload preview",
        author_id=user.id,
        image="/uploads/image/example.jpg",
    )
    db.session.add(post)
    db.session.commit()

    response = client.get(f"/post/{post.public_id}", base_url="https://www.kimbela.com")
    assert response.status_code == 200
    assert b'<meta property="og:image" content="https://www.kimbela.com/public/uploads/image/example.jpg">' in response.data


def test_shared_post_page_includes_absolute_preview_metadata(client, db, user):
    from models import Post

    post = Post(
        content="Metadata preview",
        author_id=user.id,
        image="/uploads/image/example.png",
    )
    db.session.add(post)
    db.session.commit()

    response = client.get(f"/post/{post.public_id}", base_url="https://www.kimbela.com")
    assert response.status_code == 200
    assert f'<link rel="canonical" href="https://www.kimbela.com/post/{post.public_id}">'.encode() in response.data
    assert b'<meta property="og:url" content="https://www.kimbela.com/post/' in response.data
    assert b'<meta property="og:image:type" content="image/png">' in response.data
    assert b'<meta property="og:image:width"' not in response.data
    assert b'<meta property="og:image:height"' not in response.data
    assert b'<meta name="twitter:image:alt" content="Post by ' in response.data


def test_shared_post_page_rewrites_cloudinary_images_for_social_preview(client, db, user):
    from models import Post

    post = Post(
        content="Cloudinary preview",
        author_id=user.id,
        image="https://res.cloudinary.com/demo/image/upload/v1312461204/sample.jpg",
    )
    db.session.add(post)
    db.session.commit()

    response = client.get(f"/post/{post.public_id}", base_url="https://www.kimbela.com")
    assert response.status_code == 200
    assert b'https://res.cloudinary.com/demo/image/upload/f_jpg,q_auto,w_1200,h_630,c_fill,g_auto/v1312461204/sample.jpg' in response.data
    assert b'<meta property="og:image:type" content="image/jpeg">' in response.data
    assert b'<meta property="og:image:width" content="1200">' in response.data
    assert b'<meta property="og:image:height" content="630">' in response.data


def test_post_with_non_png_image_never_uses_png_or_fallback_dimensions(
    client, db, user
):
    from models import Post

    post = Post(
        content="Non-PNG image preview",
        author_id=user.id,
        image="https://cdn.example.com/photo.jpg",
    )
    db.session.add(post)
    db.session.commit()

    for path in (f"/post/{post.public_id}", f"/share/post/{post.public_id}?v=1"):
        response = client.get(path, base_url="https://kimbela.com")
        assert response.status_code == 200
        head_html = response.get_data(as_text=True).split("</head>", 1)[0]

        assert '<meta property="og:image:type" content="image/jpeg">' in head_html
        assert 'content="image/png"' not in head_html
        assert 'content="687"' not in head_html
        assert 'content="363"' not in head_html


def test_shared_post_page_rejects_insecure_preview_image_and_uses_public_fallback(
    client, db, user
):
    from models import Post

    post = Post(
        content="Unsafe image fallback",
        author_id=user.id,
        image="http://cdn.example.com/insecure.jpg",
    )
    db.session.add(post)
    db.session.commit()

    response = client.get(
        f"/share/post/{post.public_id}?v=1",
        base_url="https://kimbela.com",
    )
    assert response.status_code == 200
    head_html = response.data.split(b"</head>", 1)[0]
    fallback_url = b"https://kimbela.com/static/assets/img/kim.png"
    assert b'<meta property="og:image" content="' + fallback_url + b'">' in head_html
    assert b'<meta property="og:image:width" content="687">' in head_html
    assert b'<meta property="og:image:height" content="363">' in head_html
    assert b"http://cdn.example.com/insecure.jpg" not in head_html

    image_response = client.get("/static/assets/img/kim.png")
    assert image_response.status_code == 200
    assert image_response.mimetype == "image/png"
    assert not image_response.is_json


def test_public_post_share_is_metadata_only_without_user_agent_detection(
    client, db, user
):
    from models import Post

    post = Post(
        content="Crawler-specific preview marker",
        author_id=user.id,
        image="https://res.cloudinary.com/demo/image/upload/v1/share.jpg",
    )
    db.session.add(post)
    db.session.commit()

    user_agents = (None, "Mozilla/5.0", "WhatsApp/2.26.1", "Facebot")
    for user_agent in user_agents:
        for method in ("GET", "HEAD"):
            headers = {"User-Agent": user_agent} if user_agent else {}
            response = client.open(
                f"/share/post/{post.public_id}?v=1",
                method=method,
                base_url="https://kimbela.com",
                headers=headers,
            )
            assert response.status_code == 200
            assert not response.location
            assert response.content_type == "text/html; charset=utf-8"
            assert response.headers["Cache-Control"] == (
                "public, max-age=300, stale-while-revalidate=600"
            )
            assert "Pragma" not in response.headers
            assert "Set-Cookie" not in response.headers
            assert "Cookie" not in response.headers.get("Vary", "")

            if method == "GET":
                head_html = response.data.split(b"</head>", 1)[0]
                assert b'<meta property="og:type" content="article">' in head_html
                assert b'<meta property="og:site_name" content="Kimbela">' in head_html
                assert b'<meta property="og:title" content="Post by Test User - Kimbela">' in head_html
                assert b'<meta property="og:description" content="Crawler-specific preview marker">' in head_html
                assert b"Crawler-specific preview marker" in head_html
                assert b'<meta name="twitter:card" content="summary_large_image">' in head_html
                assert b'<meta property="og:image:type" content="image/jpeg">' in head_html
                assert b'<meta property="og:image:width" content="1200">' in head_html
                assert b'<meta property="og:image:height" content="630">' in head_html
                assert b"/image/upload/f_jpg,q_auto,w_1200,h_630,c_fill,g_auto/" in head_html
                assert b'<meta name="robots" content="noindex,follow">' in head_html
                assert f'<link rel="canonical" href="https://kimbela.com/share/post/{post.public_id}?v=1">'.encode() in head_html
                assert f'<meta property="og:url" content="https://kimbela.com/share/post/{post.public_id}?v=1">'.encode() in head_html
                assert f'<meta name="twitter:url" content="https://kimbela.com/share/post/{post.public_id}?v=1">'.encode() in head_html
                assert b"share_v=" not in head_html
                assert b"Open post on Kimbela" in response.data
                assert f'window.location.replace("/post/{post.public_id}")'.encode() in response.data

    normal_response = client.get(
        f"/post/{post.public_id}",
        base_url="https://www.kimbela.com",
        headers={"User-Agent": "WhatsApp/2.26.1"},
    )
    assert normal_response.status_code == 200
    assert normal_response.headers["Cache-Control"] == "private, no-store, max-age=0"
    assert "Cookie" in normal_response.headers.get("Vary", "")
    assert "Set-Cookie" in normal_response.headers

def test_shared_post_page_returns_404_for_malformed_or_unknown_identifier(client):
    assert client.get("/post/not-a-valid-post").status_code == 404
    assert client.get("/post/00000000-0000-0000-0000-000000000000").status_code == 404


def test_shared_post_page_does_not_use_profile_picture_as_preview(client, db, user):
    from models import Post

    user.profile_pic = "https://cdn.example.com/profile.jpg"
    post = Post(
        content="Text-only post",
        author_id=user.id,
    )
    db.session.add(post)
    db.session.commit()

    response = client.get(f"/post/{post.public_id}", base_url="https://www.kimbela.com")
    assert response.status_code == 200
    head_html = response.data.split(b"</head>", 1)[0]
    assert b'<meta property="og:image" content="https://www.kimbela.com/static/assets/img/kim.png">' in head_html
    assert b'<meta name="twitter:image" content="https://www.kimbela.com/static/assets/img/kim.png">' in head_html
    assert b'https://cdn.example.com/profile.jpg' not in head_html


def test_public_group_share_uses_public_uuid_and_renders_full_preview(
    app, client, db, user
):
    from models import Group, Post

    group = Group(
        name="Public preview group",
        created_by=user.id,
        is_active=True,
        is_private=False,
    )
    db.session.add(group)
    db.session.flush()
    group.members.append(user)
    post = Post(
        content="Public group preview content",
        author_id=user.id,
        group_id=group.id,
        image="https://cdn.example.com/public-group.jpg",
    )
    db.session.add(post)
    db.session.commit()
    with client.session_transaction() as session:
        session["_user_id"] = str(user.id)
        session["_fresh"] = True

    group_page = client.get(f"/groups/{group.id}")
    assert group_page.status_code == 200
    assert f'data-post-id="{post.public_id}"'.encode() in group_page.data
    assert f'data-url="/post/{post.public_id}"'.encode() in group_page.data
    assert f"openShareModal({post.id})".encode() not in group_page.data
    assert b"const { url } = getSharePayload();" in group_page.data
    assert group_page.data.count(b"const { url, text } = getSharePayload();") == 2
    assert b"navigator.share({ title: 'Kimbela Post', text, url })" in group_page.data
    assert b"window.KimbelaShare.copyText(url)" in group_page.data
    assert b"facebook.com/sharer/sharer.php?u=${encodedUrl}" in group_page.data
    assert b"twitter.com/intent/tweet?url=${encodedUrl}" in group_page.data
    assert b"wa.me/?text=${encodedText}%20${encodedUrl}" in group_page.data
    assert b"linkedin.com/sharing/share-offsite/?url=${encodedUrl}" in group_page.data

    anonymous = app.test_client()
    preview = anonymous.get(
        f"/post/{post.public_id}?share_v=4", base_url="https://www.kimbela.com"
    )
    assert preview.status_code == 200
    assert preview.headers["Cache-Control"] == "private, no-store, max-age=0"
    assert "Cookie" in preview.headers.get("Vary", "")
    assert b'<meta property="og:description" content="Public group preview content">' in preview.data
    assert b'<meta property="og:image" content="https://cdn.example.com/public-group.jpg">' in preview.data
    assert f'<link rel="canonical" href="https://www.kimbela.com/post/{post.public_id}">'.encode() in preview.data
    assert f'<meta property="og:url" content="https://www.kimbela.com/post/{post.public_id}">'.encode() in preview.data


def test_private_group_share_uses_post_metadata_without_group_or_comments(
    app, client, db, user
):
    from models import Comment, Group, Post

    user.first_name = "PrivatePreviewAuthor"
    group = Group(
        name="Confidential preview group",
        created_by=user.id,
        is_active=True,
        is_private=True,
    )
    db.session.add(group)
    db.session.flush()
    group.members.append(user)
    post = Post(
        content="private-preview-secret-marker",
        author_id=user.id,
        group_id=group.id,
        image="https://cdn.example.com/private-secret.jpg",
    )
    db.session.add(post)
    db.session.flush()
    db.session.add(
        Comment(
            content="private-comment-must-not-appear",
            author_id=user.id,
            post_id=post.id,
        )
    )
    db.session.commit()
    with client.session_transaction() as session:
        session["_user_id"] = str(user.id)
        session["_fresh"] = True

    group_page = client.get(f"/groups/{group.id}")
    assert group_page.status_code == 200
    assert f'data-post-id="{post.public_id}"'.encode() in group_page.data
    assert f'data-url="/post/{post.public_id}"'.encode() in group_page.data

    authorized_preview = client.get(f"/post/{post.public_id}")
    assert authorized_preview.status_code == 200
    assert b"private-preview-secret-marker" in authorized_preview.data
    assert b"https://cdn.example.com/private-secret.jpg" in authorized_preview.data

    client.get("/logout")
    anonymous = app.test_client()
    preview = anonymous.get(
        f"/post/{post.public_id}?share_v=4",
        base_url="https://www.kimbela.com",
    )
    assert preview.status_code == 200
    head_html = preview.data.split(b"</head>", 1)[0]
    assert b"Sign in with an account that has access" in preview.data
    assert b"PrivatePreviewAuthor" in head_html
    assert b'<meta property="og:description" content="private-preview-secret-marker">' in head_html
    assert b'<meta property="og:image" content="https://cdn.example.com/private-secret.jpg">' in head_html
    assert f'<link rel="canonical" href="https://www.kimbela.com/post/{post.public_id}">'.encode() in head_html
    assert f'<meta property="og:url" content="https://www.kimbela.com/post/{post.public_id}">'.encode() in head_html
    assert b"share_v=4" not in head_html
    assert b"Confidential preview group" not in preview.data
    assert b"private-comment-must-not-appear" not in preview.data
    assert user.email.encode() not in preview.data
    assert user.phone_number.encode() not in preview.data

    crawler_preview = anonymous.get(
        f"/share/post/{post.public_id}?v=1",
        base_url="https://kimbela.com",
        headers={"User-Agent": "Mozilla/5.0"},
    )
    assert crawler_preview.status_code == 200
    assert crawler_preview.headers["Cache-Control"] == (
        "public, max-age=300, stale-while-revalidate=600"
    )
    assert "Set-Cookie" not in crawler_preview.headers
    assert "Cookie" not in crawler_preview.headers.get("Vary", "")
    assert b"private-preview-secret-marker" in crawler_preview.data
    assert b"Confidential preview group" not in crawler_preview.data
    assert b"private-comment-must-not-appear" not in crawler_preview.data
    assert user.email.encode() not in crawler_preview.data
    assert user.phone_number.encode() not in crawler_preview.data
    assert f"/groups/{group.id}".encode() not in crawler_preview.data
    assert b"data-post-id" not in crawler_preview.data

    from datetime import date
    from models import User

    outsider = User(
        first_name="Restricted",
        last_name="Outsider",
        email="restricted-outsider@example.com",
        phone_number="+19876543210",
        dob=date(1990, 1, 1),
        gender="Female",
        city="Elsewhere",
        country="Testland",
        state="TS",
        marital_status="Single",
        is_active=True,
    )
    outsider.set_password("StrongPassw0rd!")
    db.session.add(outsider)
    db.session.commit()
    login_response = anonymous.post(
        "/login",
        data={
            "email": outsider.email,
            "password": "StrongPassw0rd!",
        },
    )
    assert login_response.status_code in (200, 302)
    assert anonymous.get(f"/post/{post.public_id}").status_code == 403


def test_matchmaking_group_copy_link_renders_anonymous_social_preview(
    app, client, db, user, monkeypatch
):
    from models import Group, Post

    user.first_name = "MatchPreviewAuthor"
    group = Group(
        name="Configured Matchmaking",
        created_by=user.id,
        is_active=True,
        is_private=True,
    )
    db.session.add(group)
    db.session.flush()
    group.members.append(user)
    monkeypatch.setitem(app.config, "MATCHMAKING_GROUP_ID", str(group.id))
    post = Post(
        content="matchmaking-preview-marker",
        author_id=user.id,
        group_id=group.id,
        image="https://cdn.example.com/matchmaking-preview.jpg",
    )
    db.session.add(post)
    db.session.commit()

    with client.session_transaction() as session:
        session["_user_id"] = str(user.id)
        session["_fresh"] = True

    group_page = client.get(f"/groups/{group.id}")
    assert group_page.status_code == 200
    assert f'data-url="/post/{post.public_id}"'.encode() in group_page.data

    client.get("/logout")
    anonymous = app.test_client()
    preview = anonymous.get(
        f"/share/post/{post.public_id}?v=1",
        base_url="https://kimbela.com",
        headers={"User-Agent": "Mozilla/5.0"},
    )
    assert preview.status_code == 200
    head_html = preview.data.split(b"</head>", 1)[0]
    assert b"MatchPreviewAuthor" in head_html
    assert b'<meta name="robots" content="noindex,follow">' in head_html
    assert b'<meta property="og:description" content="matchmaking-preview-marker">' in head_html
    assert b'<meta property="og:image" content="https://cdn.example.com/matchmaking-preview.jpg">' in head_html
    assert f'<link rel="canonical" href="https://kimbela.com/share/post/{post.public_id}?v=1">'.encode() in head_html
    assert f'<meta property="og:url" content="https://kimbela.com/share/post/{post.public_id}?v=1">'.encode() in head_html
    assert f'<meta name="twitter:url" content="https://kimbela.com/share/post/{post.public_id}?v=1">'.encode() in head_html
    assert b"Configured Matchmaking" not in preview.data


def test_android_user_can_list_and_open_public_and_private_group_landings(
    client, db, user
):
    from models import Group

    public_group = Group(
        name="Android public group",
        created_by=user.id,
        is_active=True,
        is_private=False,
    )
    private_group = Group(
        name="Android private group",
        created_by=user.id,
        is_active=True,
        is_private=True,
    )
    db.session.add_all([public_group, private_group])
    db.session.commit()
    with client.session_transaction() as session:
        session["_user_id"] = str(user.id)
        session["_fresh"] = True

    android_headers = {
        "User-Agent": (
            "Mozilla/5.0 (Linux; Android 14; Pixel 8) "
            "AppleWebKit/537.36 Chrome/130.0 Mobile Safari/537.36"
        )
    }
    discovery = client.get("/groups", headers=android_headers)
    assert discovery.status_code == 200

    groups = client.get(
        "/groups/all?per_page=100",
        headers={**android_headers, "Accept": "application/json"},
    ).get_json()
    listed_ids = {group["id"] for group in groups}
    assert {public_group.id, private_group.id} <= listed_ids
    assert client.get(
        f"/groups/{public_group.id}", headers=android_headers
    ).status_code == 200
    private_landing = client.get(
        f"/groups/{private_group.id}", headers=android_headers
    )
    assert private_landing.status_code == 200
    assert b"Private group content" in private_landing.data


def test_subscription_callback_recovers_success_via_reference_verification(
    client, db, user, login, monkeypatch
):
    from datetime import timedelta

    from models import MarketplacePayment, MarketplaceSubscription
    from payments.payment_service import MarketplacePaymentService
    from time_utils import utcnow

    plan = MarketplaceSubscription(
        name="Starter",
        slug="starter-test",
        price_tokens=100,
        price_usd=2.0,
    )
    db.session.add(plan)
    db.session.flush()

    payment = MarketplacePayment(
        user_id=user.id,
        subscription_id=plan.id,
        amount=2756.59,
        currency="USD",
        tokens_paid=275659,
        gateway="flutterwave",
        gateway_reference="KIMBELA_MARKET_TEST_REF",
        status="pending",
        gateway_status="initiated",
        start_date=utcnow(),
        end_date=utcnow() + timedelta(days=30),
    )
    db.session.add(payment)
    db.session.commit()

    login()

    def fake_verify_by_id(self, transaction_id):
        return {"success": False, "data": {}}

    def fake_verify_by_reference(self, tx_ref):
        assert tx_ref == "KIMBELA_MARKET_TEST_REF"
        return {
            "success": True,
            "data": {
                "id": 2018701314,
                "tx_ref": tx_ref,
                "status": "successful",
                "amount": 2756.59,
                "currency": "USD",
                "payment_type": "card",
            },
        }

    def fake_handle_success(self, marketplace_payment, flutterwave_data):
        marketplace_payment.status = "completed"
        marketplace_payment.gateway_status = flutterwave_data["status"]
        marketplace_payment.gateway_payment_id = str(flutterwave_data["id"])
        marketplace_payment.paid_at = utcnow()
        marketplace_payment.user.marketplace_subscription_status = "active"
        marketplace_payment.user.marketplace_subscription_id = (
            marketplace_payment.subscription_id
        )
        marketplace_payment.user.marketplace_subscription_expires = (
            marketplace_payment.end_date
        )
        db.session.commit()
        return True

    monkeypatch.setattr(
        MarketplacePaymentService,
        "verify_flutterwave_payment",
        fake_verify_by_id,
    )
    monkeypatch.setattr(
        MarketplacePaymentService,
        "verify_flutterwave_payment_by_reference",
        fake_verify_by_reference,
    )
    monkeypatch.setattr(
        MarketplacePaymentService,
        "handle_marketplace_payment_success",
        fake_handle_success,
    )

    response = client.get(
        "/subscription-callback?tx_ref=KIMBELA_MARKET_TEST_REF&status=session_expired",
        follow_redirects=False,
    )

    assert response.status_code == 302

    db.session.refresh(payment)
    db.session.refresh(user)
    assert payment.status == "completed"
    assert payment.gateway_status == "successful"
    assert payment.gateway_payment_id == "2018701314"
    assert user.marketplace_subscription_status == "active"
    assert user.marketplace_subscription_id == plan.id


def test_public_profile_accepts_user_uuid(client, db, user, login):
    login()

    response = client.get(f"/profile/{user.public_id}")
    assert response.status_code == 200
    assert user.first_name.encode() in response.data


def test_share_post_self_referencing_urls_and_same_host_with_base_url(
    app, client, db, user, monkeypatch
):
    import html
    import re
    from urllib.parse import urlparse
    from models import Post

    monkeypatch.setitem(app.config, "BASE_URL", "https://kimbela.com")

    post = Post(
        content="Self-referencing share preview test",
        author_id=user.id,
        image="https://www.kimbela.com/uploads/image/post-photo.png",
    )
    db.session.add(post)
    db.session.commit()

    share_resp = client.get(
        f"/share/post/{post.public_id}?v=2",
        base_url="https://www.kimbela.com",
        headers={"User-Agent": "WhatsApp/2.23.20.0"},
    )
    assert share_resp.status_code == 200
    share_head = share_resp.get_data(as_text=True).split("</head>", 1)[0]

    expected_share_url = f"https://kimbela.com/share/post/{post.public_id}?v=2"
    expected_image_url = "https://kimbela.com/public/uploads/image/post-photo.png"

    assert '<meta name="robots" content="noindex,follow">' in share_head
    assert '<link rel="icon" href="/static/assets/img/favy.png">' in share_head
    assert f'<link rel="canonical" href="{expected_share_url}">' in share_head
    assert f'<meta property="og:url" content="{expected_share_url}">' in share_head
    assert f'<meta name="twitter:url" content="{expected_share_url}">' in share_head
    assert f'<meta property="og:image" content="{expected_image_url}">' in share_head

    canonical_href = re.search(r'<link rel="canonical" href="([^"]+)"', share_head).group(1)
    og_url = re.search(r'<meta property="og:url" content="([^"]+)"', share_head).group(1)
    og_image = re.search(r'<meta property="og:image" content="([^"]+)"', share_head).group(1)
    assert urlparse(canonical_href).hostname == "kimbela.com"
    assert urlparse(og_url).hostname == "kimbela.com"
    assert urlparse(og_image).hostname == "kimbela.com"

    for invalid_v in ("too-long-1234567890", "bad<script>", "a/b", "space here"):
        invalid_resp = client.get(
            f"/share/post/{post.public_id}",
            query_string={"v": invalid_v},
            base_url="https://www.kimbela.com",
        )
        assert invalid_resp.status_code == 200
        invalid_head = invalid_resp.get_data(as_text=True).split("</head>", 1)[0]
        unversioned_url = f"https://kimbela.com/share/post/{post.public_id}"
        assert f'<link rel="canonical" href="{unversioned_url}">' in invalid_head
        assert f'<meta property="og:url" content="{unversioned_url}">' in invalid_head
        assert f'<meta name="twitter:url" content="{unversioned_url}">' in invalid_head

    valid_token_resp = client.get(
        f"/share/post/{post.public_id}?v=rev_2-a",
        base_url="https://www.kimbela.com",
    )
    valid_token_head = valid_token_resp.get_data(as_text=True).split("</head>", 1)[0]
    assert (
        f'<meta property="og:url" content="https://kimbela.com/share/post/{post.public_id}?v=rev_2-a">'
        in valid_token_head
    )

    post_resp = client.get(
        f"/post/{post.public_id}",
        base_url="https://www.kimbela.com",
    )
    assert post_resp.status_code == 200
    post_head = post_resp.get_data(as_text=True).split("</head>", 1)[0]
    expected_post_url = f"https://kimbela.com/post/{post.public_id}"
    assert f'<link rel="canonical" href="{expected_post_url}">' in post_head
    assert f'<meta property="og:url" content="{expected_post_url}">' in post_head
    assert f'<meta name="twitter:url" content="{expected_post_url}">' in post_head
    assert f'<meta property="og:image" content="{expected_image_url}">' in post_head


def test_pages_emit_exactly_one_og_set_and_valid_fallback_image(
    app, client, db, user, monkeypatch
):
    import html
    import re
    from urllib.parse import urlparse
    from models import Post

    monkeypatch.setitem(app.config, "BASE_URL", "https://kimbela.com")

    post = Post(content="Text post for single OG tag check", author_id=user.id)
    db.session.add(post)
    db.session.commit()

    expected_titles = {
        "/": "Kimbela - Meet. Connect. Belong",
        "/about": "About Kimbela - For Connections That Make Sense",
        "/features": "Kimbela Features - Marketplace, Community & Trusted Connections",
    }
    paths = [
        "/",
        "/about",
        "/features",
        "/login",
        f"/post/{post.public_id}",
        f"/share/post/{post.public_id}?v=1",
    ]
    for path in paths:
        resp = client.get(path, base_url="https://www.kimbela.com")
        assert resp.status_code == 200, f"Unexpected status for {path}"
        head_html = resp.get_data(as_text=True).split("</head>", 1)[0]

        og_images = re.findall(r'<meta\s+property="og:image"\s+content="([^"]+)"', head_html)
        og_urls = re.findall(r'<meta\s+property="og:url"\s+content="([^"]+)"', head_html)
        og_titles = re.findall(r'<meta\s+property="og:title"\s+content="([^"]+)"', head_html)
        twitter_cards = re.findall(r'<meta\s+name="twitter:card"\s+content="([^"]+)"', head_html)

        assert len(og_images) == 1, f"Expected 1 og:image on {path}, got {og_images}"
        assert len(og_urls) == 1, f"Expected 1 og:url on {path}, got {og_urls}"
        assert len(og_titles) == 1, f"Expected 1 og:title on {path}, got {og_titles}"
        assert len(twitter_cards) == 1, f"Expected 1 twitter:card on {path}, got {twitter_cards}"

        if path in expected_titles:
            assert html.unescape(og_titles[0]) == expected_titles[path]

        assert "kimbela-logo.png" not in head_html
        assert og_images[0] == "https://kimbela.com/static/assets/img/kim.png"
        assert urlparse(og_images[0]).hostname == "kimbela.com"
        assert urlparse(og_urls[0]).hostname == "kimbela.com"
        assert '<meta property="og:image:type" content="image/png">' in head_html
        assert '<meta property="og:image:width" content="687">' in head_html
        assert '<meta property="og:image:height" content="363">' in head_html

