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
    assert b'https://cdn.example.com/profile.jpg' not in response.data
    assert b'/static/assets/img/kim.png' in response.data


def test_public_profile_accepts_user_uuid(client, db, user, login):
    login()

    response = client.get(f"/profile/{user.public_id}")
    assert response.status_code == 200
    assert user.first_name.encode() in response.data
