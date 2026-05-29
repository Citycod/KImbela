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
    assert b'<meta property="og:image:width" content="1200">' in response.data
    assert b'<meta property="og:image:height" content="630">' in response.data
    assert b'<meta name="twitter:image:alt" content="Post by ' in response.data


def test_shared_post_page_rewrites_cloudinary_images_for_social_preview(client, db, user):
    from models import Post

    post = Post(
        content="Cloudinary preview",
        author_id=user.id,
        image="https://res.cloudinary.com/demo/image/upload/v123456/kimbela/posts/example.webp",
    )
    db.session.add(post)
    db.session.commit()

    response = client.get(f"/post/{post.public_id}", base_url="https://www.kimbela.com")
    assert response.status_code == 200
    assert b'https://res.cloudinary.com/demo/image/upload/f_jpg,q_auto,w_1200,c_limit/v123456/kimbela/posts/example.webp' in response.data


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
