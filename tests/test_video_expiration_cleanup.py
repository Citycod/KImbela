"""Integration tests for automated 10-day video expiration and cleanup.

Verifies:
1. Videos uploaded 9 days ago are preserved (not expired, files remain on disk).
2. Videos uploaded exactly 10 days ago are deleted and marked expired.
3. Videos uploaded more than 10 days ago are deleted and marked expired.
4. Both main feed videos and group videos are cleaned up.
5. Missing files on disk are handled gracefully without crashing.
6. Duplicate cleanup executions are strictly idempotent.
7. Filesystem permission errors do not update the DB, preserving the post for retry.
8. Database commit failures trigger session rollback without crashing.
9. Posts, text content, comments, and reactions are completely preserved.
10. Ordinary images and unrelated files are never deleted.
11. Frontend templates display the expired-video placeholder.
12. The background scheduler registers the video cleanup job.
"""

from datetime import date, datetime, timedelta
import io
import os
import shutil
import struct
import uuid
from unittest.mock import patch
import pytest
from flask import g
from sqlalchemy.exc import SQLAlchemyError

from extensions import db
from models import Comment, Group, Like, Post, User
from time_utils import utcnow
from utils.video_service import (
    DEFAULT_EXPIRATION_DAYS,
    VIDEO_EXPIRED_SENTINEL,
    cleanup_expired_videos,
    get_video_upload_dirs,
)


def make_user(db, *, first_name="ExpiryUser"):
    token = uuid.uuid4().hex[:8]
    user = User(
        first_name=first_name,
        last_name=token,
        email=f"expiry-{token}@example.com",
        phone_number=f"+23480{token[:7]}",
        city="Lagos",
        country="Nigeria",
        dob=date(1995, 5, 10),
        gender="Female",
        marital_status="Single",
        is_active=True,
    )
    user.set_password("SecurePassword123!")
    db.session.add(user)
    db.session.commit()
    return user


def make_group(db, creator, *, private=False):
    group = Group(
        name=f"Group {uuid.uuid4().hex[:8]}",
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


def create_physical_video_file(filename: str) -> str:
    """Create a dummy physical video file in the video upload directory."""
    video_dir, _ = get_video_upload_dirs()
    target_path = os.path.join(video_dir, filename)
    with open(target_path, "wb") as f:
        f.write(b"\x00\x00\x00\x20ftypisom" + b"\x00" * 64)
    return target_path


@pytest.fixture(autouse=True)
def cleanup_test_disk_files():
    yield
    video_dir, tmp_dir = get_video_upload_dirs()
    tracked_samples = {
        "32ec032582674fdaa3954163a95c21f8.mp4",
        "764f563064494ea3adac049c390696ac.mp4",
        "d4c50f65c71f4b05af891091760b8310.mp4",
    }
    if os.path.exists(video_dir):
        for fname in os.listdir(video_dir):
            if fname not in tracked_samples and fname != "tmp":
                try:
                    fpath = os.path.join(video_dir, fname)
                    if os.path.isfile(fpath):
                        os.remove(fpath)
                except OSError:
                    pass
    if os.path.exists(tmp_dir):
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_videos_uploaded_9_days_ago_are_not_deleted(db):
    """Videos younger than 10 days are not deleted or marked expired."""
    user = make_user(db)
    filename = f"{uuid.uuid4().hex}.mp4"
    disk_path = create_physical_video_file(filename)

    nine_days_ago = utcnow() - timedelta(days=9, hours=23)
    post = Post(
        content="Recent video post",
        video=f"/uploads/video/{filename}",
        author_id=user.id,
        created_at=nine_days_ago,
    )
    db.session.add(post)
    db.session.commit()

    stats = cleanup_expired_videos()

    assert stats["expired"] == 0
    assert os.path.isfile(disk_path)
    refreshed = db.session.get(Post, post.id)
    assert refreshed.video == f"/uploads/video/{filename}"
    assert not refreshed.is_video_expired


def test_videos_uploaded_exactly_10_days_ago_are_deleted(db):
    """Videos uploaded exactly 10 days ago (or slightly earlier) are deleted and marked expired."""
    user = make_user(db)
    filename = f"{uuid.uuid4().hex}.mp4"
    disk_path = create_physical_video_file(filename)

    ten_days_ago = utcnow() - timedelta(days=10)
    post = Post(
        content="Ten days old video post",
        video=f"/uploads/video/{filename}",
        author_id=user.id,
        created_at=ten_days_ago,
    )
    db.session.add(post)
    db.session.commit()

    stats = cleanup_expired_videos()

    assert stats["expired"] == 1
    assert not os.path.exists(disk_path)
    refreshed = db.session.get(Post, post.id)
    assert refreshed.video == VIDEO_EXPIRED_SENTINEL
    assert refreshed.is_video_expired


def test_videos_uploaded_more_than_10_days_ago_and_derivatives_are_deleted(db):
    """Videos uploaded >10 days ago and associated thumbnail derivatives are cleaned up."""
    user = make_user(db)
    video_uuid = uuid.uuid4().hex
    filename = f"{video_uuid}.mp4"
    disk_path = create_physical_video_file(filename)

    video_dir, _ = get_video_upload_dirs()
    thumb_path = os.path.join(video_dir, f"{video_uuid}.jpg")
    with open(thumb_path, "wb") as f:
        f.write(b"dummy thumbnail bytes")

    fifteen_days_ago = utcnow() - timedelta(days=15)
    post = Post(
        content="Old video post",
        video=f"/uploads/video/{filename}",
        author_id=user.id,
        created_at=fifteen_days_ago,
    )
    db.session.add(post)
    db.session.commit()

    stats = cleanup_expired_videos()

    assert stats["expired"] == 1
    assert not os.path.exists(disk_path)
    assert not os.path.exists(thumb_path)
    refreshed = db.session.get(Post, post.id)
    assert refreshed.video == VIDEO_EXPIRED_SENTINEL


def test_main_feed_and_group_videos_both_expired(db):
    """Cleanup processes both main feed posts (group_id=None) and group posts (group_id is set)."""
    user = make_user(db)
    group = make_group(db, user)

    feed_file = f"{uuid.uuid4().hex}.mp4"
    group_file = f"{uuid.uuid4().hex}.mp4"
    feed_path = create_physical_video_file(feed_file)
    group_path = create_physical_video_file(group_file)

    eleven_days_ago = utcnow() - timedelta(days=11)
    feed_post = Post(
        content="Feed video",
        video=f"/uploads/video/{feed_file}",
        author_id=user.id,
        group_id=None,
        created_at=eleven_days_ago,
    )
    group_post = Post(
        content="Group video",
        video=f"/uploads/video/{group_file}",
        author_id=user.id,
        group_id=group.id,
        created_at=eleven_days_ago,
    )
    db.session.add_all([feed_post, group_post])
    db.session.commit()

    stats = cleanup_expired_videos()

    assert stats["expired"] == 2
    assert not os.path.exists(feed_path)
    assert not os.path.exists(group_path)

    assert db.session.get(Post, feed_post.id).video == VIDEO_EXPIRED_SENTINEL
    assert db.session.get(Post, group_post.id).video == VIDEO_EXPIRED_SENTINEL


def test_missing_physical_file_handled_gracefully(db):
    """Missing physical files do not crash the cleanup process and the post is still marked expired."""
    user = make_user(db)
    non_existent_file = f"missing_{uuid.uuid4().hex}.mp4"

    twelve_days_ago = utcnow() - timedelta(days=12)
    post = Post(
        content="Post whose file was already deleted manually",
        video=f"/uploads/video/{non_existent_file}",
        author_id=user.id,
        created_at=twelve_days_ago,
    )
    db.session.add(post)
    db.session.commit()

    stats = cleanup_expired_videos()

    assert stats["missing_files_handled"] == 1
    assert stats["expired"] == 1
    assert stats["failed"] == 0
    refreshed = db.session.get(Post, post.id)
    assert refreshed.video == VIDEO_EXPIRED_SENTINEL


def test_duplicate_cleanup_execution_is_idempotent(db):
    """Running cleanup multiple times in succession causes no redundant work or errors."""
    user = make_user(db)
    filename = f"{uuid.uuid4().hex}.mp4"
    disk_path = create_physical_video_file(filename)

    ten_days_ago = utcnow() - timedelta(days=10, minutes=5)
    post = Post(
        content="Idempotency test post",
        video=f"/uploads/video/{filename}",
        author_id=user.id,
        created_at=ten_days_ago,
    )
    db.session.add(post)
    db.session.commit()

    # Pass 1
    first_stats = cleanup_expired_videos()
    assert first_stats["expired"] == 1
    assert not os.path.exists(disk_path)

    # Pass 2 - duplicate execution
    second_stats = cleanup_expired_videos()
    assert second_stats["expired"] == 0
    assert second_stats["checked"] == 0
    assert second_stats["failed"] == 0

    refreshed = db.session.get(Post, post.id)
    assert refreshed.video == VIDEO_EXPIRED_SENTINEL


def test_filesystem_permission_error_preserves_post_for_retry(db):
    """Filesystem errors prevent updating the DB so the file can be retried on next execution."""
    user = make_user(db)
    filename = f"{uuid.uuid4().hex}.mp4"
    disk_path = create_physical_video_file(filename)

    eleven_days_ago = utcnow() - timedelta(days=11)
    post = Post(
        content="Permission error test post",
        video=f"/uploads/video/{filename}",
        author_id=user.id,
        created_at=eleven_days_ago,
    )
    db.session.add(post)
    db.session.commit()

    with patch("os.remove", side_effect=PermissionError("Permission denied")):
        stats = cleanup_expired_videos()

    assert stats["failed"] >= 1
    assert stats["expired"] == 0

    # Confirm post.video was NOT updated so next run can retry deletion
    refreshed = db.session.get(Post, post.id)
    assert refreshed is not None
    assert refreshed.video == f"/uploads/video/{filename}"

    db.session.delete(refreshed)
    db.session.commit()


def test_database_failure_rolls_back_safely(db):
    """Database commit errors rollback cleanly without crashing the cleanup loop."""
    user = make_user(db)
    filename = f"{uuid.uuid4().hex}.mp4"
    disk_path = create_physical_video_file(filename)

    eleven_days_ago = utcnow() - timedelta(days=11)
    post = Post(
        content="DB error test post",
        video=f"/uploads/video/{filename}",
        author_id=user.id,
        created_at=eleven_days_ago,
    )
    db.session.add(post)
    db.session.commit()

    with patch("extensions.db.session.commit", side_effect=SQLAlchemyError("Connection dropped")):
        stats = cleanup_expired_videos()

    assert stats["failed"] >= 1
    assert stats["expired"] == 0
    refreshed = db.session.get(Post, post.id)
    if refreshed:
        db.session.delete(refreshed)
        db.session.commit()


def test_preservation_of_posts_content_and_interactions(db):
    """Expiring a video never deletes the post, comments, likes, or reactions."""
    author = make_user(db, first_name="Author")
    commenter = make_user(db, first_name="Commenter")

    filename = f"{uuid.uuid4().hex}.mp4"
    create_physical_video_file(filename)

    ten_days_ago = utcnow() - timedelta(days=10, hours=1)
    post = Post(
        content="This is an important memory with comments and likes",
        video=f"/uploads/video/{filename}",
        author_id=author.id,
        created_at=ten_days_ago,
    )
    db.session.add(post)
    db.session.flush()

    comment = Comment(
        content="Great video!",
        author_id=commenter.id,
        post_id=post.id,
    )
    like = Like(
        user_id=commenter.id,
        post_id=post.id,
    )
    db.session.add_all([comment, like])
    db.session.commit()

    post_id = post.id
    cleanup_expired_videos()

    # Post row still exists
    refreshed_post = db.session.get(Post, post_id)
    assert refreshed_post is not None
    assert refreshed_post.content == "This is an important memory with comments and likes"
    assert refreshed_post.author_id == author.id
    assert refreshed_post.video == VIDEO_EXPIRED_SENTINEL

    # Interactions are intact
    assert Comment.query.filter_by(post_id=post_id).count() == 1
    assert Like.query.filter_by(post_id=post_id).count() == 1


def test_never_deletes_images_or_unrelated_files(db):
    """Ordinary images and unrelated files are never deleted by video cleanup."""
    user = make_user(db)
    fifteen_days_ago = utcnow() - timedelta(days=15)

    # Post with image
    image_post = Post(
        content="Image post from 15 days ago",
        image="https://res.cloudinary.com/demo/image/upload/sample.jpg",
        video=None,
        author_id=user.id,
        created_at=fifteen_days_ago,
    )
    db.session.add(image_post)
    db.session.commit()

    # Create unrelated file in uploads/video
    video_dir, _ = get_video_upload_dirs()
    unrelated_path = os.path.join(video_dir, "unrelated_document.pdf")
    with open(unrelated_path, "wb") as f:
        f.write(b"unrelated binary")

    cleanup_expired_videos()

    assert os.path.isfile(unrelated_path)
    refreshed = db.session.get(Post, image_post.id)
    assert refreshed.image == "https://res.cloudinary.com/demo/image/upload/sample.jpg"
    assert refreshed.video is None


def test_frontend_renders_expired_video_placeholder(client, db):
    """Feeds and group pages display the expired video placeholder when post.video == 'expired'."""
    user = make_user(db)
    group = make_group(db, user)

    # Expired feed post placed at head of feed
    feed_post = Post(
        content="Main feed post with expired video",
        video=VIDEO_EXPIRED_SENTINEL,
        author_id=user.id,
        created_at=utcnow() + timedelta(seconds=10),
    )
    # Expired group post placed at head of group feed
    group_post = Post(
        content="Group post with expired video",
        video=VIDEO_EXPIRED_SENTINEL,
        author_id=user.id,
        group_id=group.id,
        created_at=utcnow() + timedelta(seconds=10),
    )
    db.session.add_all([feed_post, group_post])
    db.session.commit()

    login_client(client, user)

    # Check dashboard feed
    dash_res = client.get("/user_dashboard")
    assert dash_res.status_code == 200
    dash_html = dash_res.get_data(as_text=True)
    assert "video-expired-placeholder" in dash_html
    assert "Video expired" in dash_html
    assert "Uploaded videos are automatically deleted after 10 days" in dash_html

    # Check group feed
    group_res = client.get(f"/groups/{group.id}")
    assert group_res.status_code == 200
    group_html = group_res.get_data(as_text=True)
    assert "video-expired-placeholder" in group_html
    assert "Video expired" in group_html


def test_scheduler_registers_video_cleanup_job(app, monkeypatch):
    """The background scheduler registers the video_expiration_cleanup job."""
    import scheduler as scheduler_module

    monkeypatch.setattr(scheduler_module, "scheduler", None)
    scheduler_instance = scheduler_module.init_scheduler(app)
    try:
        job = scheduler_instance.get_job("video_expiration_cleanup")
        assert job is not None
        assert "video_expiration_cleanup" in {j.id for j in scheduler_instance.get_jobs()}
    finally:
        scheduler_instance.shutdown(wait=True)
        scheduler_module.scheduler = None
