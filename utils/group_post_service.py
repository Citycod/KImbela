"""Shared group-post persistence with explicit authorship.

HTTP authentication, CSRF validation, request parsing, and response formatting
remain in the group route. Scheduler callers provide the author directly and
never impersonate a browser session.
"""

from __future__ import annotations

import cloudinary.uploader

from extensions import db
from models import Post
from time_utils import utcnow
from utils.matchmaking_group import can_create_group_post


ALLOWED_GROUP_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp", "bmp"}
GROUP_VIDEO_EXTENSIONS = (".mp4", ".mov", ".avi", ".mkv", ".webm")


class GroupPostCreationError(Exception):
    """A safe group-post creation failure suitable for route or job logging."""

    def __init__(self, code: str, user_message: str, status_code: int = 200):
        super().__init__(user_message)
        self.code = code
        self.user_message = user_message
        self.status_code = status_code


def _has_allowed_group_image_extension(filename: str) -> bool:
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_GROUP_IMAGE_EXTENSIONS
    )


def _upload_group_media(media_file) -> str:
    filename = media_file.filename
    filename_lower = filename.lower()
    content_type = (getattr(media_file, "content_type", "") or "").lower()

    if content_type.startswith("video/") or filename_lower.endswith(
        GROUP_VIDEO_EXTENSIONS
    ):
        raise GroupPostCreationError(
            "video_not_allowed",
            "Video uploads are not allowed.",
        )
    if not _has_allowed_group_image_extension(filename):
        raise GroupPostCreationError(
            "unsupported_file_type",
            "Unsupported file type. Please upload an image or GIF.",
        )

    try:
        result = cloudinary.uploader.upload(
            media_file,
            folder="kimbela/groups/posts",
            resource_type="image",
            transformation=[
                {"width": 800, "crop": "limit"},
                {"quality": "auto", "fetch_format": "auto"},
            ],
        )
        return result["secure_url"]
    except GroupPostCreationError:
        raise
    except Exception as exc:
        raise GroupPostCreationError(
            "media_upload_failed",
            "Failed to create post",
        ) from exc


def create_group_post(*, author, group, content: str = "", media_file=None) -> Post:
    """Validate, create, and commit one group post for ``author``."""
    if author is None or getattr(author, "id", None) is None:
        raise GroupPostCreationError(
            "invalid_author",
            "A valid post author is required.",
            status_code=403,
        )
    if group is None or getattr(group, "id", None) is None:
        raise GroupPostCreationError(
            "invalid_group",
            "A valid group is required.",
        )
    if not can_create_group_post(group, author):
        raise GroupPostCreationError(
            "group_post_forbidden",
            "Only administrators can post in this group",
            status_code=403,
        )

    content = (content or "").strip()
    has_media = bool(media_file and getattr(media_file, "filename", ""))
    if not content and not has_media:
        raise GroupPostCreationError(
            "empty_post",
            "Post content or media is required",
        )

    try:
        image_url = _upload_group_media(media_file) if has_media else None
        post = Post(
            content=content,
            image=image_url,
            video=None,
            author_id=author.id,
            group_id=group.id,
            created_at=utcnow(),
        )
        db.session.add(post)
        db.session.commit()
        return post
    except GroupPostCreationError:
        db.session.rollback()
        raise
    except Exception as exc:
        db.session.rollback()
        raise GroupPostCreationError(
            "persistence_failed",
            "Failed to create post",
        ) from exc
