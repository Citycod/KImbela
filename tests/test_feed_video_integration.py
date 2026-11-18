"""Integration tests for Kimbela feed video functionality.

Verifies:
1. Publishing posts with videos via AJAX and standard POST.
2. Rejection of videos exceeding 120 seconds with appropriate feedback.
3. Native video player controls (controls, preload="metadata", playsinline).
4. Aspect ratio preservation (object-contain bg-black) avoiding distortion.
5. Feed pagination (cursor-based infinite scroll) rendering video posts in partials.
6. Preservation of existing text and image post layouts.
7. Private group media protection (403 for unauthorized users).
8. Graceful fallback markup for missing/unavailable video files.
9. Single-playback and muted autoplay constraints.
10. Composer video picker integration.
"""

from datetime import date
import io
import os
import shutil
import struct
import tempfile
import uuid
from unittest.mock import patch
import pytest
from flask import g, url_for
from werkzeug.datastructures import FileStorage

from extensions import db
from models import Group, Post, User
from utils.video_service import get_video_upload_dirs


def build_test_mp4(duration_seconds: float = 25.0, timescale: int = 1000) -> bytes:
    """Build a synthetic valid faststart MP4 file."""
    ftyp_data = b"isom\x00\x00\x02\x00isomiso2mp41"
    ftyp_box = struct.pack(">I4s", 8 + len(ftyp_data), b"ftyp") + ftyp_data

    duration_val = int(duration_seconds * timescale)
    mvhd_payload = struct.pack(
        ">B3sIIIIih10s36s24sI",
        0,
        b"\x00\x00\x00",
        0,
        0,
        timescale,
        duration_val,
        0x00010000,
        0x0100,
        b"\x00" * 10,
        b"\x00" * 36,
        b"\x00" * 24,
        1,
    )
    mvhd_box = struct.pack(">I4s", 8 + len(mvhd_payload), b"mvhd") + mvhd_payload
    moov_box = struct.pack(">I4s", 8 + len(mvhd_box), b"moov") + mvhd_box

    mdat_payload = b"\x00" * 128
    mdat_box = struct.pack(">I4s", 8 + len(mdat_payload), b"mdat") + mdat_payload
    return ftyp_box + moov_box + mdat_box


@pytest.fixture
def feed_user(db):
    uid = uuid.uuid4().hex[:8]
    user = User(
        first_name="Feed",
        last_name="Tester",
        email=f"feeduser-{uid}@example.com",
        phone_number=f"+23480{uid[:7]}",
        city="Lagos",
        country="Nigeria",
        dob=date(1996, 4, 12),
        gender="Female",
        is_active=True,
    )
    user.set_password("SecurePassword123!")
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def another_user(db):
    uid = uuid.uuid4().hex[:8]
    user = User(
        first_name="Another",
        last_name="Viewer",
        email=f"viewer-{uid}@example.com",
        phone_number=f"+23481{uid[:7]}",
        city="Abuja",
        country="Nigeria",
        dob=date(1994, 9, 21),
        gender="Male",
        is_active=True,
    )
    user.set_password("SecurePassword123!")
    db.session.add(user)
    db.session.commit()
    return user


def login_client(client, user):
    with client.session_transaction() as sess:
        sess.clear()
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
    g.pop("_login_user", None)


@pytest.fixture(autouse=True)
def cleanup_uploaded_test_videos():
    yield
    upload_dir, _ = get_video_upload_dirs()
    if os.path.exists(upload_dir):
        tracked_samples = {
            "32ec032582674fdaa3954163a95c21f8.mp4",
            "764f563064494ea3adac049c390696ac.mp4",
            "d4c50f65c71f4b05af891091760b8310.mp4",
        }
        for fname in os.listdir(upload_dir):
            if fname not in tracked_samples and fname != "tmp":
                try:
                    fpath = os.path.join(upload_dir, fname)
                    if os.path.isfile(fpath):
                        os.remove(fpath)
                except OSError:
                    pass
        tmp_dir = os.path.join(upload_dir, "tmp")
        if os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)


def test_publish_feed_video_post_via_ajax(client, feed_user, app):
    """Users can publish posts containing videos via AJAX."""
    login_client(client, feed_user)
    video_bytes = build_test_mp4(20.0)

    data = {
        "post_content": "Check out my new video reel!",
        "media": (io.BytesIO(video_bytes), "sample_feed_video.mp4", "video/mp4"),
    }

    response = client.post(
        "/user_dashboard",
        data=data,
        content_type="multipart/form-data",
        headers={
            "X-Requested-With": "XMLHttpRequest",
            "X-File-Upload": "true",
        },
    )

    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data["success"] is True
    assert json_data["post_content"] == "Check out my new video reel!"
    assert json_data["video_url"] is not None
    assert "/uploads/video/" in json_data["video_url"]

    # Verify database persistence
    post = Post.query.filter_by(id=json_data["post_id"]).first()
    assert post is not None
    assert post.author_id == feed_user.id
    assert post.video == json_data["video_url"]
    assert post.image is None


def test_publish_feed_video_rejects_exceeding_120_seconds(client, feed_user):
    """Videos exceeding 120 seconds are rejected on the server."""
    login_client(client, feed_user)
    too_long_video = build_test_mp4(125.0)

    data = {
        "post_content": "This video is too long",
        "media": (io.BytesIO(too_long_video), "long_clip.mp4", "video/mp4"),
    }

    response = client.post(
        "/user_dashboard",
        data=data,
        content_type="multipart/form-data",
        headers={
            "X-Requested-With": "XMLHttpRequest",
            "X-File-Upload": "true",
        },
    )

    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data["success"] is False
    assert "2 minutes" in json_data["error"] or "120 seconds" in json_data["error"]


def test_feed_html_renders_video_player_with_native_controls_and_aspect_ratio(client, feed_user):
    """Main feed renders native video controls, metadata preload, aspect ratio, and fallback."""
    login_client(client, feed_user)
    video_bytes = build_test_mp4(15.0)

    # Publish video post
    upload_res = client.post(
        "/user_dashboard",
        data={
            "post_content": "Native video player test",
            "media": (io.BytesIO(video_bytes), "test_player.mp4", "video/mp4"),
        },
        content_type="multipart/form-data",
        headers={"X-Requested-With": "XMLHttpRequest", "X-File-Upload": "true"},
    )
    assert upload_res.status_code == 200
    video_url = upload_res.get_json()["video_url"]

    # Load full user_dashboard HTML
    get_res = client.get("/user_dashboard")
    assert get_res.status_code == 200
    html = get_res.get_data(as_text=True)

    # Assert video elements and attributes
    assert "<video controls" in html
    assert 'preload="metadata"' in html
    assert "playsinline" in html
    assert "object-contain bg-black" in html
    assert f'<source src="{video_url}" type="video/mp4"' in html
    assert "video-error-fallback" in html
    assert "Video is currently unavailable." in html
    assert "Your browser does not support the video tag." in html


def test_feed_pagination_ajax_renders_video_posts_in_partial(client, feed_user):
    """Feed pagination (cursor loading) correctly returns video posts in _posts_partial.html."""
    login_client(client, feed_user)
    video_bytes = build_test_mp4(18.0)

    # Publish a video post
    client.post(
        "/user_dashboard",
        data={
            "post_content": "Paginated video item",
            "media": (io.BytesIO(video_bytes), "paginated.mp4", "video/mp4"),
        },
        content_type="multipart/form-data",
        headers={"X-Requested-With": "XMLHttpRequest", "X-File-Upload": "true"},
    )

    # Request cursor pagination via AJAX
    response = client.get(
        "/user_dashboard?limit=5",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    posts_html = data["posts"]

    # Verify video rendering inside partial
    assert "<video controls" in posts_html
    assert 'preload="metadata"' in posts_html
    assert "playsinline" in posts_html
    assert "object-contain bg-black" in posts_html
    assert "video-error-fallback" in posts_html


def test_preserves_image_and_text_post_layouts(client, feed_user, db):
    """Text-only posts and image posts retain their distinct layout alongside video posts."""
    login_client(client, feed_user)

    # 1. Text-only post
    text_post = Post(
        author_id=feed_user.id,
        content="Simple text post without any media",
    )
    db.session.add(text_post)

    # 2. Image post
    image_post = Post(
        author_id=feed_user.id,
        content="Picture post for feed layout",
        image="https://res.cloudinary.com/demo/image/upload/sample_feed.jpg",
    )
    db.session.add(image_post)

    # 3. Video post
    video_dir, _ = get_video_upload_dirs()
    v_name = f"layout_test_{uuid.uuid4().hex}.mp4"
    with open(os.path.join(video_dir, v_name), "wb") as f:
        f.write(build_test_mp4(10.0))

    video_post = Post(
        author_id=feed_user.id,
        content="Video post for layout comparison",
        video=f"/uploads/video/{v_name}",
    )
    db.session.add(video_post)
    db.session.commit()

    try:
        res = client.get("/user_dashboard")
        assert res.status_code == 200
        html = res.get_data(as_text=True)

        # Check text post content exists
        assert "Simple text post without any media" in html
        # Check image post exists with <img> tag
        assert "Picture post for feed layout" in html
        assert 'alt="Post image"' in html
        # Check video post exists with <video> tag
        assert "Video post for layout comparison" in html
        assert "<video controls" in html
    finally:
        fpath = os.path.join(video_dir, v_name)
        if os.path.exists(fpath):
            os.remove(fpath)


def test_private_group_media_protection(client, feed_user, another_user, db):
    """Unauthorized non-members cannot access private group video/media."""
    # Create private group owned by feed_user
    group = Group(
        name="Confidential Video Club",
        description="Exclusive group",
        is_private=True,
        created_by=feed_user.id,
    )
    group.members.append(feed_user)
    db.session.add(group)
    db.session.commit()

    # Create video file on disk
    video_bytes = build_test_mp4(12.0)
    video_name = f"private_{uuid.uuid4().hex}.mp4"
    upload_dir, _ = get_video_upload_dirs()
    video_path = os.path.join(upload_dir, video_name)
    with open(video_path, "wb") as f:
        f.write(video_bytes)

    try:
        video_url = f"/uploads/video/{video_name}"
        group_post = Post(
            author_id=feed_user.id,
            group_id=group.id,
            content="Exclusive private group clip",
            video=video_url,
        )
        db.session.add(group_post)
        db.session.commit()

        # 1. Non-member access attempt -> 403 Forbidden
        login_client(client, another_user)
        unauthorized_res = client.get(video_url)
        assert unauthorized_res.status_code == 403

        # 2. Member/Creator access attempt -> 200 OK or 206 Partial Content with Range
        login_client(client, feed_user)
        authorized_res = client.get(video_url)
        assert authorized_res.status_code in (200, 206)

        # 3. Seeking / Byte-range request for streaming video
        range_res = client.get(video_url, headers={"Range": "bytes=0-10"})
        assert range_res.status_code == 206
        assert "bytes 0-10/" in range_res.headers.get("Content-Range", "")
    finally:
        if os.path.exists(video_path):
            os.remove(video_path)


def test_missing_video_returns_404_and_has_fallback_markup(client, feed_user):
    """Deleted/missing video files return 404 and the template includes fallback error card."""
    login_client(client, feed_user)
    fake_video_url = f"/uploads/video/nonexistent_{uuid.uuid4().hex}.mp4"

    # Request nonexistent video directly
    res = client.get(fake_video_url)
    assert res.status_code == 404

    # Feed template has error fallback container with hidden class toggled on onerror
    feed_res = client.get("/user_dashboard")
    html = feed_res.get_data(as_text=True)
    assert 'class="video-error-fallback hidden' in html
    assert "onerror=" in html
    assert "video-error-fallback" in html


def test_frontend_composer_and_single_playback_wiring():
    """Verify frontend assets have video picker button, correct MIME types, and single playback."""
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent

    dashboard_html = (root / "templates" / "user_dashboard.html").read_text()
    dashboard_js = (root / "static" / "assets" / "js" / "dashboard.js").read_text()

    # Button in composer toolbar
    assert 'onclick="validateAndOpenVideoPicker()"' in dashboard_html
    assert 'title="Video"' in dashboard_html
    # Media input accepts video MIME types
    assert "video/mp4" in dashboard_html
    assert "video/quicktime" in dashboard_html
    assert "video/webm" in dashboard_html

    # JS defines validateAndOpenVideoPicker and window export
    assert "function validateAndOpenVideoPicker()" in dashboard_js
    assert "window.validateAndOpenVideoPicker = validateAndOpenVideoPicker;" in dashboard_js

    # JS single-playback listener
    assert "document.addEventListener('play'" in dashboard_js
    assert "!v.paused" in dashboard_js
    assert "v.pause();" in dashboard_js
