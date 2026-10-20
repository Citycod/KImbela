from pathlib import Path
from datetime import date

from models import Post, User


ROOT = Path(__file__).resolve().parents[1]


def _login(client, user):
    with client.session_transaction() as session:
        session['_user_id'] = str(user.id)
        session['_fresh'] = True


def _user(db, email):
    account = User(
        first_name='Delete',
        last_name='Tester',
        email=email,
        phone_number='+15555550123',
        city='Lagos',
        state='Lagos',
        country='Nigeria',
        dob=date(1985, 1, 1),
        gender='Female',
        marital_status='Single',
        is_active=True,
    )
    account.set_password('StrongPassw0rd!')
    db.session.add(account)
    db.session.commit()
    return account


def test_profile_delete_commits_requeries_and_disappears_after_reload(db, client):
    owner = _user(db, 'profile-delete-owner@example.test')
    post = Post(content='Permanent profile deletion marker', author_id=owner.id)
    db.session.add(post)
    db.session.commit()
    post_id = post.id
    _login(client, owner)

    response = client.post(f'/delete_post/{post_id}')

    assert response.status_code == 200
    assert response.is_json
    assert response.get_json() == {'success': True, 'post_id': post_id}
    db.session.expire_all()
    assert db.session.get(Post, post_id) is None
    profile = client.get(f'/{owner.id}')
    assert profile.status_code == 200
    assert b'Permanent profile deletion marker' not in profile.data


def test_profile_delete_non_owner_is_forbidden(db, client):
    owner = _user(db, 'profile-delete-owner-2@example.test')
    stranger = _user(db, 'profile-delete-stranger@example.test')
    post = Post(content='Owner only post', author_id=owner.id)
    db.session.add(post)
    db.session.commit()
    post_id = post.id
    _login(client, stranger)

    response = client.post(f'/delete_post/{post_id}')

    assert response.status_code == 403
    db.session.expire_all()
    assert db.session.get(Post, post_id) is not None


def test_profile_delete_commit_failure_never_reports_success(
    db, client, monkeypatch
):
    owner = _user(db, 'profile-delete-failure@example.test')
    post = Post(content='Survives failed commit', author_id=owner.id)
    db.session.add(post)
    db.session.commit()
    post_id = post.id
    _login(client, owner)

    import utils.post_deletion as deletion

    monkeypatch.setattr(
        deletion.db.session,
        'commit',
        lambda: (_ for _ in ()).throw(RuntimeError('forced commit failure')),
    )
    response = client.post(f'/delete_post/{post_id}')

    assert response.status_code == 500
    assert response.get_json()['error'] == 'Unable to delete post'
    db.session.rollback()
    assert db.session.get(Post, post_id) is not None


def test_profile_and_post_detail_render_desktop_copy_link_with_public_uuid(
    db, client
):
    owner = _user(db, 'profile-share-owner@example.test')
    post = Post(content='Share this profile post', author_id=owner.id)
    db.session.add(post)
    db.session.commit()
    _login(client, owner)

    for url in (f'/{owner.id}', f'/profile/{owner.public_id}', f'/post/{post.public_id}'):
        response = client.get(url)
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert 'data-copy-post-link' in html
        assert f'data-post-id="{post.public_id}"' in html
        assert f'data-url="/post/{post.public_id}"' in html

    feed = client.get('/user_dashboard')
    assert feed.status_code == 200
    feed_html = feed.get_data(as_text=True)
    assert 'id="shareModal"' in feed_html
    assert f'data-post-id="{post.public_id}"' in feed_html
    assert f'data-url="/post/{post.public_id}"' in feed_html
    assert 'onclick="copyPostLink()"' in feed_html

    template = (ROOT / 'templates' / '_post_card.html').read_text()
    assert 'type="button"' in template
    assert 'data-copy-post-link' in template
    assert "post.public_id" in template


def test_delete_clients_require_json_success_before_showing_success():
    for path in (
        ROOT / 'static' / 'assets' / 'js' / 'dashboard.js',
        ROOT / 'static' / 'assets' / 'js' / 'modules' / 'posts' / 'index.js',
        ROOT / 'static' / 'assets' / 'js' / 'profile_post_actions.js',
    ):
        source = path.read_text()
        assert "contentType.includes('application/json')" in source
        assert (
            'data.success !== true' in source
            or 'payload.success !== true' in source
        )
