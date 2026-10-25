"""Request classification for Kimbela's public metadata-only post shares."""


def is_public_post_share_request(request) -> bool:
    """Return whether this is the deliberately public post-share document.

    Classification is route-based, not User-Agent-based. The endpoint exposes
    only the approved metadata representation and never authorizes full posts.
    """
    return (
        request.method in {"GET", "HEAD"}
        and (request.path or "").startswith("/share/post/")
    )
