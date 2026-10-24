"""Narrow request classification for metadata-only social post previews."""

SOCIAL_PREVIEW_USER_AGENT_TOKENS = (
    "facebookexternalhit",
    "facebot",
    "whatsapp",
)


def is_social_post_preview_request(request) -> bool:
    """Return whether this request may receive the metadata-only representation.

    This must never be used to authorize full post content. A caller that spoofs
    one of these user agents receives only the deliberately public preview tags.
    """
    if request.method not in {"GET", "HEAD"}:
        return False
    if not (request.path or "").startswith("/post/"):
        return False

    user_agent = (request.headers.get("User-Agent") or "").lower()
    return any(token in user_agent for token in SOCIAL_PREVIEW_USER_AGENT_TOKENS)
