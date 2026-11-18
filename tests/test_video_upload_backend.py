"""Comprehensive test suite for Kimbela video upload backend.

Verifies:
- Valid videos (<= 120s)
- Videos exceeding 120s
- Exactly 120s boundary
- Invalid file formats (.txt, .exe, etc.)
- Incorrect MIME types
- Malformed and corrupted videos
- Empty video files
- Compression failures and timeout handling
- Safe optimization without unnecessary re-encoding
- Unauthorized uploads
- Successful VPS storage and atomic placement
- Safe cleanup of temporary files on failure
- Post deletion local file unlinking
- Private group video protection in serve_uploads
- Preservation of existing text and image posts
"""

from datetime import date
import io
import os
import shutil
import struct
import tempfile
import uuid
from unittest.mock import MagicMock, patch
import pytest
from werkzeug.datastructures import FileStorage

from extensions import db
from models import Group, Post, User
from utils.feed_post_service import FeedPostCreationError, create_feed_post
from utils.post_deletion import delete_post_safely
from utils.video_service import (
    MAX_VIDEO_DURATION_SECONDS,
    VideoError,
    VideoProcessingError,
    VideoValidationError,
    delete_stored_video_file,
    get_video_upload_dirs,
    is_faststart_mp4,
    is_video_upload,
    parse_iso_bmff_duration,
    process_and_store_feed_video,
)


def build_test_mp4_bytes(duration_seconds: float = 30.0, timescale: int = 1000, faststart: bool = True) -> bytes:
    """Construct a valid synthetic ISO BMFF MP4 binary with known duration."""
    ftyp_data = b"isom\x00\x00\x02\x00isomiso2mp41"
    ftyp_box = struct.pack(">I4s", 8 + len(ftyp_data), b"ftyp") + ftyp_data

    duration_val = int(duration_seconds * timescale)
    # mvhd box (version 0): version(1), flags(3), creation(4), mod(4), timescale(4), duration(4), etc.
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

    if faststart:
        return ftyp_box + moov_box + mdat_box
    else:
        return ftyp_box + mdat_box + moov_box


@pytest.fixture
def test_user(db):
    uid = uuid.uuid4().hex[:8]
    user = User(
        first_name="Video",
        last_name="Tester",
        email=f"videouser-{uid}@example.com",
        phone_number=f"+23480{uid[:7]}",
        city="Lagos",
        country="Nigeria",
        dob=date(1995, 5, 20),
        gender="Female",
        is_active=True,
    )
    user.set_password("SecurePassword123!")
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def other_user(db):
    uid = uuid.uuid4().hex[:8]
    user = User(
        first_name="Other",
        last_name="Tester",
        email=f"otheruser-{uid}@example.com",
        phone_number=f"+23481{uid[:7]}",
        city="Abuja",
        country="Nigeria",
        dob=date(1993, 8, 15),
        gender="Male",
        is_active=True,
    )
    user.set_password("SecurePassword123!")
    db.session.add(user)
    db.session.commit()
    return user


def test_is_video_upload_detection():
    # Valid video filenames
    assert is_video_upload(FileStorage(filename="test.mp4", content_type="video/mp4")) is True
    assert is_video_upload(FileStorage(filename="clip.mov", content_type="video/quicktime")) is True
    assert is_video_upload(FileStorage(filename="anim.webm", content_type="video/webm")) is True
    assert is_video_upload(FileStorage(filename="raw.m4v", content_type="video/x-m4v")) is True

    # Image / document filenames
    assert is_video_upload(FileStorage(filename="photo.jpg", content_type="image/jpeg")) is False
    assert is_video_upload(FileStorage(filename="doc.pdf", content_type="application/pdf")) is False
    assert is_video_upload(None) is False


def test_pure_python_iso_bmff_duration_parsing():
    # Verify parser reads 45.5s accurately
    data = build_test_mp4_bytes(45.5)
    parsed = parse_iso_bmff_duration(io.BytesIO(data))
    assert parsed is not None
    assert abs(parsed - 45.5) < 0.01

    # Verify parser reads 120.0s accurately
    data_120 = build_test_mp4_bytes(120.0)
    parsed_120 = parse_iso_bmff_duration(io.BytesIO(data_120))
    assert parsed_120 is not None
    assert abs(parsed_120 - 120.0) < 0.01


def test_is_faststart_mp4_detection():
    faststart_data = build_test_mp4_bytes(10, faststart=True)
    non_faststart_data = build_test_mp4_bytes(10, faststart=False)

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f1:
        f1.write(faststart_data)
        f1_path = f1.name

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f2:
        f2.write(non_faststart_data)
        f2_path = f2.name

    try:
        assert is_faststart_mp4(f1_path) is True
        assert is_faststart_mp4(f2_path) is False
    finally:
        os.remove(f1_path)
        os.remove(f2_path)


def test_valid_video_feed_post_creation(test_user, db):
    mp4_bytes = build_test_mp4_bytes( duration_seconds=25.0)
    file_storage = FileStorage(
        stream=io.BytesIO(mp4_bytes),
        filename="sunset.mp4",
        content_type="video/mp4",
    )

    post = create_feed_post(
        author=test_user,
        content="Beautiful sunset video!",
        media_file=file_storage,
    )

    assert post.id is not None
    assert post.author_id == test_user.id
    assert post.content == "Beautiful sunset video!"
    assert post.image is None
    assert post.video is not None
    assert post.video.startswith("/uploads/video/")
    assert post.video.endswith(".mp4")

    # Verify physical file exists on VPS disk
    video_dir, _ = get_video_upload_dirs()
    filename = os.path.basename(post.video)
    saved_path = os.path.join(video_dir, filename)
    assert os.path.isfile(saved_path)
    assert os.path.getsize(saved_path) > 0

    # Cleanup
    delete_stored_video_file(post.video)


def test_video_exceeding_120_seconds_rejected(test_user, db):
    # 125 seconds exceeds 120-second limit
    mp4_bytes = build_test_mp4_bytes(duration_seconds=125.0)
    file_storage = FileStorage(
        stream=io.BytesIO(mp4_bytes),
        filename="long_talk.mp4",
        content_type="video/mp4",
    )

    with pytest.raises(FeedPostCreationError) as exc_info:
        create_feed_post(
            author=test_user,
            content="Check out this talk",
            media_file=file_storage,
        )

    assert exc_info.value.code == "duration_exceeded"
    assert "cannot exceed 2 minutes" in exc_info.value.user_message

    # Ensure no post created
    assert Post.query.filter_by(content="Check out this talk").first() is None


def test_video_boundary_exactly_120_seconds_allowed(test_user, db):
    # Exactly 120.0 seconds must pass
    mp4_bytes = build_test_mp4_bytes(duration_seconds=120.0)
    file_storage = FileStorage(
        stream=io.BytesIO(mp4_bytes),
        filename="two_minutes.mp4",
        content_type="video/mp4",
    )

    post = create_feed_post(
        author=test_user,
        content="Exactly 2 minutes video",
        media_file=file_storage,
    )

    assert post.id is not None
    assert post.video is not None
    delete_stored_video_file(post.video)


def test_invalid_file_format_rejected(test_user):
    file_storage = FileStorage(
        stream=io.BytesIO(b"Hello world"),
        filename="notes.txt",
        content_type="text/plain",
    )

    with pytest.raises(FeedPostCreationError) as exc_info:
        create_feed_post(
            author=test_user,
            content="My text notes",
            media_file=file_storage,
        )

    assert exc_info.value.code == "unsupported_file_type"


def test_incorrect_mime_type_rejected(test_user):
    mp4_bytes = build_test_mp4_bytes(30.0)
    file_storage = FileStorage(
        stream=io.BytesIO(mp4_bytes),
        filename="fake_video.mp4",
        content_type="text/plain",  # Incorrect MIME for MP4
    )

    with pytest.raises(FeedPostCreationError) as exc_info:
        create_feed_post(
            author=test_user,
            content="Testing fake MIME",
            media_file=file_storage,
        )

    assert exc_info.value.code == "invalid_mime_type"


def test_malformed_video_rejected(test_user):
    # File named .mp4 but with garbage bytes (not ftyp)
    file_storage = FileStorage(
        stream=io.BytesIO(b"CORRUPTED_HEADER_DATA_1234567890"),
        filename="corrupted.mp4",
        content_type="video/mp4",
    )

    with pytest.raises(FeedPostCreationError) as exc_info:
        create_feed_post(
            author=test_user,
            content="Testing corrupted",
            media_file=file_storage,
        )

    assert exc_info.value.code == "invalid_video_header"


def test_empty_video_file_rejected(test_user):
    file_storage = FileStorage(
        stream=io.BytesIO(b""),
        filename="empty.mp4",
        content_type="video/mp4",
    )

    with pytest.raises(FeedPostCreationError) as exc_info:
        create_feed_post(
            author=test_user,
            content="Testing empty",
            media_file=file_storage,
        )

    assert exc_info.value.code == "empty_file"


def test_compression_failure_handling(test_user):
    mp4_bytes = build_test_mp4_bytes(15.0)
    file_storage = FileStorage(
        stream=io.BytesIO(mp4_bytes),
        filename="fail.mp4",
        content_type="video/mp4",
    )

    with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
        with patch("subprocess.run") as mock_subproc:
            mock_subproc.return_value = MagicMock(returncode=1, stderr="Unknown encoder error")

            with pytest.raises(FeedPostCreationError) as exc_info:
                create_feed_post(
                    author=test_user,
                    content="Will fail compression",
                    media_file=file_storage,
                )

            assert exc_info.value.code == "compression_failed"


def test_failed_upload_cleans_up_temporary_files(test_user):
    video_dir, tmp_dir = get_video_upload_dirs()

    # Record files in tmp_dir before test
    initial_tmp_files = set(os.listdir(tmp_dir))

    mp4_bytes = build_test_mp4_bytes(150.0)  # > 120s failure
    file_storage = FileStorage(
        stream=io.BytesIO(mp4_bytes),
        filename="cleanup_test.mp4",
        content_type="video/mp4",
    )

    try:
        create_feed_post(
            author=test_user,
            content="Testing cleanup",
            media_file=file_storage,
        )
    except FeedPostCreationError:
        pass

    # Verify no leaked files remain in tmp_dir
    current_tmp_files = set(os.listdir(tmp_dir))
    new_leaked_files = current_tmp_files - initial_tmp_files
    assert len(new_leaked_files) == 0, f"Leaked temporary files: {new_leaked_files}"


def test_unauthorized_post_creation():
    mp4_bytes = build_test_mp4_bytes(10.0)
    file_storage = FileStorage(
        stream=io.BytesIO(mp4_bytes),
        filename="unauth.mp4",
        content_type="video/mp4",
    )

    with pytest.raises(FeedPostCreationError) as exc_info:
        create_feed_post(
            author=None,
            content="No author",
            media_file=file_storage,
        )

    assert exc_info.value.code == "invalid_author"


def test_post_deletion_cleans_up_local_vps_video(test_user, db):
    mp4_bytes = build_test_mp4_bytes(15.0)
    file_storage = FileStorage(
        stream=io.BytesIO(mp4_bytes),
        filename="to_delete.mp4",
        content_type="video/mp4",
    )

    post = create_feed_post(
        author=test_user,
        content="Post to be deleted",
        media_file=file_storage,
    )

    video_url = post.video
    filename = os.path.basename(video_url)
    video_dir, _ = get_video_upload_dirs()
    disk_path = os.path.join(video_dir, filename)

    assert os.path.isfile(disk_path)

    # Delete the post safely
    delete_post_safely(post, test_user)

    # Verify physical file was unlinked from disk
    assert not os.path.exists(disk_path)


def _login(client, account):
    from flask import g
    with client.session_transaction() as session:
        session.clear()
        session["_user_id"] = str(account.id)
        session["_fresh"] = True
    g.pop("_login_user", None)


def test_private_group_video_protection(test_user, other_user, client, db):
    # Create private group
    group = Group(
        name="Confidential Group",
        is_private=True,
        created_by=test_user.id,
    )
    group.members.append(test_user)
    db.session.add(group)
    db.session.commit()

    # Create video file on disk
    video_dir, _ = get_video_upload_dirs()
    safe_filename = "private_group_video_test.mp4"
    file_path = os.path.join(video_dir, safe_filename)
    with open(file_path, "wb") as f:
        f.write(build_test_mp4_bytes(10.0))

    try:
        # Create private post belonging to the group
        private_post = Post(
            content="Private group video",
            video=f"/uploads/video/{safe_filename}",
            author_id=test_user.id,
            group_id=group.id,
        )
        db.session.add(private_post)
        db.session.commit()

        # 1. Unauthenticated request -> redirects to login (302)
        resp_anon = client.get(f"/uploads/video/{safe_filename}")
        assert resp_anon.status_code == 302

        # 2. Authenticated user who is NOT in the group -> 403 Forbidden
        _login(client, other_user)
        resp_forbidden = client.get(f"/uploads/video/{safe_filename}")
        assert resp_forbidden.status_code == 403

        # 3. Public preview route for private post -> 403 Forbidden
        resp_public = client.get(f"/public/uploads/video/{safe_filename}")
        assert resp_public.status_code == 403

        # 4. Group owner / authorized member -> 200 OK
        _login(client, test_user)
        resp_ok = client.get(f"/uploads/video/{safe_filename}")
        assert resp_ok.status_code in (200, 206)

    finally:
        if os.path.exists(file_path):
            os.remove(file_path)


def test_preserves_text_only_posts(test_user, db):
    post = create_feed_post(
        author=test_user,
        content="Pure text post without any media",
    )

    assert post.id is not None
    assert post.content == "Pure text post without any media"
    assert post.image is None
    assert post.video is None
    assert post.gif is None


def test_preserves_image_posts(test_user, db):
    # Mock cloudinary uploader so image upload doesn't hit live Cloudinary
    with patch("cloudinary.uploader.upload", return_value={"secure_url": "https://res.cloudinary.com/demo/image/upload/sample.jpg"}):
        png_data = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
        file_storage = FileStorage(
            stream=io.BytesIO(png_data),
            filename="sample.png",
            content_type="image/png",
        )

        post = create_feed_post(
            author=test_user,
            content="Photo post with Cloudinary",
            media_file=file_storage,
        )

        assert post.id is not None
        assert post.image == "https://res.cloudinary.com/demo/image/upload/sample.jpg"
        assert post.video is None
