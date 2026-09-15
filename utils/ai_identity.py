"""Single source of truth for administrator-managed AI identity."""

from __future__ import annotations

import os

import cloudinary.uploader

from models import SiteSetting


AI_IDENTITY_CUSTOMIZED_PREFIX = "ai_identity_customized:"
AI_AVATAR_MAX_BYTES = 5 * 1024 * 1024
AI_AVATAR_EXTENSIONS = {"gif", "jpeg", "jpg", "png", "webp"}


def identity_customized_key(persona_id):
    return f"{AI_IDENTITY_CUSTOMIZED_PREFIX}{int(persona_id)}"


def is_ai_identity_customized(persona_id):
    return SiteSetting.get_value(identity_customized_key(persona_id), "0") == "1"


def _mark_customized(persona_id):
    SiteSetting.set_value(identity_customized_key(persona_id), "1")


def update_ai_display_name(persona, first_name, last_name):
    first_name = (first_name or "").strip()
    last_name = (last_name or "").strip()
    display_name = " ".join((first_name, last_name))
    if (
        not first_name
        or not last_name
        or len(first_name) > 50
        or len(last_name) > 50
        or len(display_name) > 50
    ):
        raise ValueError(
            "Enter a first and last name with a combined length of 50 characters or fewer."
        )
    persona.user.first_name = first_name
    persona.user.last_name = last_name
    persona.name = display_name
    _mark_customized(persona.id)
    return display_name


def _validated_image_size(file_storage):
    stream = file_storage.stream
    original_position = stream.tell()
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    stream.seek(original_position)
    if size <= 0 or size > AI_AVATAR_MAX_BYTES:
        raise ValueError("Profile picture must be a non-empty image no larger than 5 MB.")


def upload_ai_avatar(persona, file_storage):
    filename = (getattr(file_storage, "filename", "") or "").strip()
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    content_type = (getattr(file_storage, "content_type", "") or "").lower()
    if extension not in AI_AVATAR_EXTENSIONS or not content_type.startswith("image/"):
        raise ValueError("Upload a PNG, JPEG, GIF, or WebP image.")
    _validated_image_size(file_storage)

    result = cloudinary.uploader.upload(
        file_storage,
        folder="kimbela/profiles",
        resource_type="image",
        transformation=[
            {"width": 400, "height": 400, "crop": "fill", "gravity": "face"},
            {"quality": "auto", "fetch_format": "auto"},
        ],
    )
    secure_url = result.get("secure_url")
    if not secure_url:
        raise RuntimeError("Profile image provider returned no secure URL.")
    persona.user.profile_pic = secure_url
    _mark_customized(persona.id)
    return secure_url
