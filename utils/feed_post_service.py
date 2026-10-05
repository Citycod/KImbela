"""Shared feed-post creation with explicit authorship.

HTTP concerns such as authentication, CSRF, request parsing, flashes, and
redirects intentionally remain in the calling route.
"""

from __future__ import annotations

import cloudinary.uploader

from flask import current_app

from extensions import cache, db
from models import Post
from time_utils import utcnow


MAX_FEED_MEDIA_SIZE = 100 * 1024 * 1024
ALLOWED_FEED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp", "bmp"}
VIDEO_EXTENSIONS = (".mp4", ".mov", ".avi", ".mkv", ".webm")


class FeedPostCreationError(Exception):
    """A safe, user-facing feed-post creation failure."""

    def __init__(self, code: str, user_message: str, category: str = "danger"):
        super().__init__(user_message)
        self.code = code
        self.user_message = user_message
        self.category = category


def _has_allowed_image_extension(filename: str) -> bool:
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_FEED_IMAGE_EXTENSIONS
    )


def _invalidate_author_feed_cache(author_id: int) -> None:
    for cache_key in (
        f"user_dashboard_{author_id}",
        f"posts_feed_{author_id}",
    ):
        try:
            cache.delete(cache_key)
        except Exception as exc:
            try:
                current_app.logger.warning(
                    "Cache delete skipped for %s: %s", cache_key, exc
                )
            except Exception:
                pass


def _upload_feed_media(
    media_file,
    *,
    image_transformations=None,
    gif_transformations=None,
) -> str:
    filename = media_file.filename
    filename_lower = filename.lower()
    content_type = (getattr(media_file, "content_type", "") or "").lower()

    if content_type.startswith("video/") or filename_lower.endswith(VIDEO_EXTENSIONS):
        raise FeedPostCreationError(
            "video_not_allowed",
            "Video uploads are not allowed.",
        )
    if not _has_allowed_image_extension(filename):
        raise FeedPostCreationError(
            "unsupported_file_type",
            "Unsupported file type. Please upload an image or GIF.",
        )

    try:
        media_file.seek(0, 2)
        file_size = media_file.tell()
        media_file.seek(0)
    except Exception as exc:
        raise FeedPostCreationError(
            "media_upload_failed",
            "Failed to upload media. Please try again.",
        ) from exc

    if file_size > MAX_FEED_MEDIA_SIZE:
        raise FeedPostCreationError(
            "file_too_large",
            "File too large! Maximum size is 100MB.",
        )

    resource_type = (
        "image"
        if filename_lower.endswith((".gif", ".png", ".jpg", ".jpeg", ".webp", ".bmp"))
        else "auto"
    )
    upload_options = {
        "folder": "kimbela/posts",
        "resource_type": resource_type,
        "transformation": image_transformations
        or [
            {"width": 1000, "crop": "limit"},
            {"quality": "auto", "fetch_format": "auto"},
        ],
    }
    if filename_lower.endswith(".gif"):
        upload_options["transformation"] = gif_transformations or [
            {"quality": "auto", "fetch_format": "gif"},
        ]

    try:
        result = cloudinary.uploader.upload(media_file, **upload_options)
        return result["secure_url"]
    except Exception as exc:
        raise FeedPostCreationError(
            "media_upload_failed",
            "Failed to upload media. Please try again.",
        ) from exc


def _validated_giphy_url(gif_url: str) -> str:
    gif_url = gif_url.strip()
    if not gif_url.startswith("https://"):
        raise FeedPostCreationError(
            "insecure_gif_url",
            "GIF URL must use HTTPS.",
        )
    if ".giphy.com/" not in gif_url:
        raise FeedPostCreationError(
            "unsupported_gif_host",
            "Only GIPHY GIFs are allowed.",
        )
    return gif_url


def create_feed_post(
    *,
    author,
    content: str = "",
    media_file=None,
    gif_url: str = "",
    location: str = "",
    emoji_data=None,
    image_transformations=None,
    gif_transformations=None,
) -> Post:
    """Create and commit one feed post for the explicitly supplied author."""
    if author is None or getattr(author, "id", None) is None:
        raise FeedPostCreationError(
            "invalid_author",
            "An active post author is required.",
        )

    content = (content or "").strip()
    gif_url = (gif_url or "").strip()
    location = (location or "").strip()
    has_media = bool(media_file and getattr(media_file, "filename", ""))

    if not (content or has_media or gif_url):
        raise FeedPostCreationError(
            "empty_post",
            "Please add text, a photo, or a GIF to your post.",
            category="warning",
        )

    try:
        image_url = (
            _upload_feed_media(
                media_file,
                image_transformations=image_transformations,
                gif_transformations=gif_transformations,
            )
            if has_media
            else None
        )
        saved_gif_url = None
        if not has_media and gif_url:
            saved_gif_url = _validated_giphy_url(gif_url)

        post = Post(
            content=content,
            image=image_url,
            video=None,
            gif=saved_gif_url,
            location=location or None,
            author_id=author.id,
            created_at=utcnow(),
            emoji_data=emoji_data,
        )
        db.session.add(post)
        db.session.commit()
    except FeedPostCreationError:
        db.session.rollback()
        raise
    except Exception:
        db.session.rollback()
        raise

    _invalidate_author_feed_cache(author.id)
    return post
