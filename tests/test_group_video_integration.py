"""Integration tests for Kimbela group video sharing functionality.

Verifies:
1. Video uploads in public and private group posts reusing the video service pipeline.
2. Server-side validation rejecting videos exceeding 120 seconds.
3. Native video controls, metadata preload, playsinline, and aspect ratio in group feed partials.
4. Fallback markup rendered when a video cannot load.
5. Strict authorization for private group media (403 Forbidden for non-members, 200 for members/admins).
6. Posting permissions preserved (non-members blocked, matchmaking group admin-only posting preserved).
7. Preservation of existing text and image posts in group feeds.
8. Group post deletion safely removing video files from disk.
9. Single-playback and video picker support in group detail interface.
"""

from datetime import date
import io
import os
import shutil
import struct
import uuid
import pytest
from flask import g

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


def make_user(db, *, admin=False, super_admin=False, first_name="GroupUser"):
    token = uuid.uuid4().hex[:8]
    user = User(
        first_name=first_name,
        last_name=token,
        email=f"group-{token}@example.com",
        phone_number=f"+23480{token[:7]}",
        city="Lagos",
        country="Nigeria",
        dob=date(1995, 5, 10),
        gender="Female",
        marital_status="Single",
        is_active=True,
        is_admin=admin,
        is_super_admin=super_admin,
    )
    user.set_password("SecurePassword123!")
    db.session.add(user)
    db.session.commit()
    return user


def make_group(db, creator, *, private=False, name=None):
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


def test_public_group_video_post_creation_and_rendering(client, db):
    """Users can post videos in public groups and see native video players rendered."""
    creator = make_user(db, first_name="Creator")
    member = make_user(db, first_name="Member")
    group = make_group(db, creator, private=False)
    group.members.append(member)
    db.session.commit()

    login_client(client, member)
    video_bytes = build_test_mp4(20.0)

    data = {
        "post_content": "Community video showcase!",
        "media": (io.BytesIO(video_bytes), "community_clip.mp4", "video/mp4"),
    }

    response = client.post(
        f"/groups/{group.id}/post",
        data=data,
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data["success"] is True
    assert json_data["post_id"] is not None
    assert json_data["video_url"] is not None
    assert "/uploads/video/" in json_data["video_url"]

    # Verify database persistence
    post = Post.query.filter_by(id=json_data["post_id"]).first()
    assert post is not None
    assert post.author_id == member.id
    assert post.group_id == group.id
    assert post.video == json_data["video_url"]
    assert post.image is None

    # Fetch group detail page and verify HTML rendering of video player
    page_res = client.get(f"/groups/{group.id}")
    assert page_res.status_code == 200
    html = page_res.get_data(as_text=True)

    assert post.video in html
    assert 'preload="metadata"' in html
    assert "playsinline" in html
    assert "max-h-96" in html
    assert "object-contain" in html
    assert "bg-black" in html
    assert "video-error-fallback" in html


def test_group_video_rejects_exceeding_120_seconds(client, db):
    """Group video posts exceeding 120 seconds are rejected on the server."""
    creator = make_user(db)
    member = make_user(db)
    group = make_group(db, creator, private=False)
    group.members.append(member)
    db.session.commit()

    login_client(client, member)
    too_long_video = build_test_mp4(125.0)

    data = {
        "post_content": "Long clip that exceeds duration",
        "media": (io.BytesIO(too_long_video), "too_long.mp4", "video/mp4"),
    }

    response = client.post(
        f"/groups/{group.id}/post",
        data=data,
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data["success"] is False
    assert "2 minutes" in json_data["error"] or "120 seconds" in json_data["error"]

    # Verify no post was committed
    assert Post.query.filter_by(group_id=group.id).count() == 0


def test_private_group_video_authorization(client, db):
    """Private group videos are strictly protected from non-members."""
    creator = make_user(db, first_name="Owner")
    member = make_user(db, first_name="Insider")
    outsider = make_user(db, first_name="Outsider")
    admin = make_user(db, admin=True, first_name="Admin")

    group = make_group(db, creator, private=True)
    group.members.append(member)
    db.session.commit()

    # 1. Non-creator normal member cannot post in private group
    login_client(client, member)
    video_bytes = build_test_mp4(10.0)
    member_post_res = client.post(
        f"/groups/{group.id}/post",
        data={
            "post_content": "Member trying to post in secret group",
            "media": (io.BytesIO(video_bytes), "member_secret.mp4", "video/mp4"),
        },
        content_type="multipart/form-data",
    )
    assert member_post_res.status_code == 403

    # 2. Creator uploads a video to private group
    login_client(client, creator)
    res = client.post(
        f"/groups/{group.id}/post",
        data={
            "post_content": "Secret group video update",
            "media": (io.BytesIO(video_bytes), "secret.mp4", "video/mp4"),
        },
        content_type="multipart/form-data",
    )
    assert res.status_code == 200
    video_url = res.get_json()["video_url"]
    assert video_url is not None

    # 3. Member can access video file
    login_client(client, member)
    member_fetch = client.get(video_url)
    assert member_fetch.status_code == 200

    # 4. Outsider (authenticated non-member) is rejected with 403 Forbidden
    login_client(client, outsider)
    outsider_fetch = client.get(video_url)
    assert outsider_fetch.status_code == 403

    # 5. Admin can access private video file
    login_client(client, admin)
    admin_fetch = client.get(video_url)
    assert admin_fetch.status_code == 200

    # 6. Public upload preview route blocks private group video
    public_url = video_url.replace("/uploads/", "/public/uploads/")
    public_res = client.get(public_url)
    assert public_res.status_code == 403


def test_non_member_cannot_post_in_group(client, db):
    """Non-members cannot create posts with or without videos in groups."""
    creator = make_user(db)
    outsider = make_user(db)
    group = make_group(db, creator, private=False)

    login_client(client, outsider)
    video_bytes = build_test_mp4(15.0)

    data = {
        "post_content": "Attempting to post without joining",
        "media": (io.BytesIO(video_bytes), "clip.mp4", "video/mp4"),
    }

    response = client.post(
        f"/groups/{group.id}/post",
        data=data,
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data["success"] is False
    assert "Must be a member to post" in json_data["error"]


def test_matchmaking_group_posting_permissions_preserved(client, db, monkeypatch, app):
    """Matchmaking group preserves admin-only posting; normal members are rejected."""
    creator = make_user(db)
    normal_member = make_user(db, first_name="NormalMember")
    admin_user = make_user(db, admin=True, first_name="AdminPoster")

    matchmaking_group = make_group(db, creator, private=False, name="Official Matchmaking")
    matchmaking_group.members.append(normal_member)
    matchmaking_group.members.append(admin_user)
    db.session.commit()

    monkeypatch.setitem(app.config, "MATCHMAKING_GROUP_ID", matchmaking_group.id)

    # Normal member posting is rejected
    login_client(client, normal_member)
    video_bytes = build_test_mp4(12.0)
    data = {
        "post_content": "Normal member post in matchmaking group",
        "media": (io.BytesIO(video_bytes), "test.mp4", "video/mp4"),
    }

    member_res = client.post(
        f"/groups/{matchmaking_group.id}/post",
        data=data,
        content_type="multipart/form-data",
    )
    assert member_res.status_code == 403
    assert "Only administrators can post" in member_res.get_json()["error"]

    # Admin posting succeeds
    login_client(client, admin_user)
    admin_res = client.post(
        f"/groups/{matchmaking_group.id}/post",
        data={
            "post_content": "Admin post in matchmaking group",
            "media": (io.BytesIO(video_bytes), "test_admin.mp4", "video/mp4"),
        },
        content_type="multipart/form-data",
    )
    assert admin_res.status_code == 200
    assert admin_res.get_json()["success"] is True
    assert admin_res.get_json()["video_url"] is not None


def test_group_post_deletion_removes_video_file_safely(client, db):
    """Deleting a group video post removes the video file from disk."""
    creator = make_user(db)
    group = make_group(db, creator, private=False)
    group.members.append(creator)
    db.session.commit()

    login_client(client, creator)
    video_bytes = build_test_mp4(15.0)

    create_res = client.post(
        f"/groups/{group.id}/post",
        data={
            "post_content": "Post to be deleted",
            "media": (io.BytesIO(video_bytes), "delete_me.mp4", "video/mp4"),
        },
        content_type="multipart/form-data",
    )
    assert create_res.status_code == 200
    post_id = create_res.get_json()["post_id"]
    video_url = create_res.get_json()["video_url"]

    upload_dir, _ = get_video_upload_dirs()
    filename = os.path.basename(video_url)
    disk_file_path = os.path.join(upload_dir, filename)
    assert os.path.isfile(disk_file_path)

    # Delete the post
    del_res = client.post(
        f"/delete_post/{post_id}",
        headers={"Content-Type": "application/json"},
    )
    assert del_res.status_code == 200
    assert del_res.get_json()["success"] is True

    # Confirm database deletion and file unlink
    assert db.session.get(Post, post_id) is None
    assert not os.path.exists(disk_file_path)


def test_preserves_text_and_image_posts_in_group_feed(client, db):
    """Existing text-only and image posts in group feeds render properly alongside videos."""
    creator = make_user(db)
    group = make_group(db, creator, private=False)
    group.members.append(creator)

    # Create text post
    text_post = Post(
        content="Pure text announcement in group",
        author_id=creator.id,
        group_id=group.id,
    )
    # Create image post
    image_post = Post(
        content="Image post announcement",
        image="https://res.cloudinary.com/demo/image/upload/sample.jpg",
        author_id=creator.id,
        group_id=group.id,
    )
    db.session.add_all([text_post, image_post])
    db.session.commit()

    login_client(client, creator)
    page_res = client.get(f"/groups/{group.id}")
    assert page_res.status_code == 200
    html = page_res.get_data(as_text=True)

    assert "Pure text announcement in group" in html
    assert "https://res.cloudinary.com/demo/image/upload/sample.jpg" in html


def test_group_detail_template_elements_and_single_playback(client, db):
    """Group detail page includes video action buttons, pickers, duration checks, and playback coordination."""
    creator = make_user(db)
    group = make_group(db, creator, private=False)

    login_client(client, creator)
    page_res = client.get(f"/groups/{group.id}")
    assert page_res.status_code == 200
    html = page_res.get_data(as_text=True)

    # Video action button in composer card
    assert "openGroupPostModalWithAction('video')" in html
    # Video action button in modal
    assert "openGroupVideoPicker()" in html
    assert "openGroupImagePicker()" in html
    # Accept attribute includes video formats
    assert 'accept="image/*,video/mp4,video/quicktime,video/webm,.mp4,.mov,.webm"' in html
    # 2 minute hint
    assert "Videos up to 2 min" in html
    # Single-playback coordinator listener
    assert "document.addEventListener('play'" in html
    # Duration limit check in script
    assert "tempVideo.duration > 120" in html
