"""Transactional deletion path shared by owner and AI-admin post deletion."""

from __future__ import annotations

import logging
from urllib.parse import urlparse

import cloudinary.uploader
from sqlalchemy import and_, or_

from extensions import db
from models import AILog, Comment, Like, Notification, Post, Reaction
from time_utils import utcnow


logger = logging.getLogger(__name__)


def _cloudinary_public_id(url):
    if not url:
        return None
    parsed = urlparse(url)
    if "cloudinary.com" not in parsed.netloc or "/upload/" not in parsed.path:
        return None
    path = parsed.path.split("/upload/", 1)[1].lstrip("/")
    parts = path.split("/")
    if parts and parts[0].startswith("v") and parts[0][1:].isdigit():
        parts = parts[1:]
    public_id = "/".join(parts)
    if "." in public_id.rsplit("/", 1)[-1]:
        public_id = public_id.rsplit(".", 1)[0]
    return public_id or None


def _destroy_media_after_commit(media):
    for url, resource_type in media:
        public_id = _cloudinary_public_id(url)
        if not public_id:
            continue
        try:
            cloudinary.uploader.destroy(public_id, resource_type=resource_type)
        except Exception:
            logger.exception("Post deleted but Cloudinary cleanup failed for %s", public_id)


def delete_post_safely(post, actor, *, ai_admin_persona=None):
    """Delete one authorized post and related records in one DB transaction.

    External media cleanup happens only after the database commit and is best
    effort, so a provider outage cannot resurrect or partially delete content.
    """
    if post is None:
        raise LookupError("Post not found")
    is_owner = actor.id == post.author_id
    is_ai_admin = bool(
        ai_admin_persona
        and getattr(actor, "is_super_admin", False)
        and ai_admin_persona.user_id == post.author_id
        and getattr(post.author, "is_ai_persona", False)
    )
    if not (is_owner or is_ai_admin):
        raise PermissionError("Unauthorized")

    post_id = post.id
    deleted_content = post.content
    comment_ids = [
        row[0]
        for row in db.session.query(Comment.id).filter(Comment.post_id == post_id).all()
    ]
    media = ((post.image, "image"), (post.gif, "image"), (post.video, "video"))

    try:
        Post.query.filter(Post.shared_post_id == post_id).update(
            {Post.shared_post_id: None}, synchronize_session=False
        )
        Notification.query.filter(
            or_(
                and_(
                    Notification.entity_id == post_id,
                    Notification.entity_type.in_(("post", "group_post")),
                ),
                Notification.entity_type.in_(
                    (f"comment:{post_id}", f"group_comment:{post_id}")
                ),
                and_(
                    Notification.entity_id.in_(comment_ids or [-1]),
                    Notification.entity_type.like("%comment%"),
                ),
            )
        ).delete(synchronize_session=False)
        Reaction.query.filter(Reaction.post_id == post_id).delete(
            synchronize_session=False
        )
        Like.query.filter(Like.post_id == post_id).delete(synchronize_session=False)
        Comment.query.filter(Comment.post_id == post_id).delete(
            synchronize_session=False
        )
        db.session.delete(post)
        if ai_admin_persona:
            db.session.add(
                AILog(
                    persona_id=ai_admin_persona.id,
                    action_type="DELETE_POST_MANUAL",
                    target_id=post_id,
                    prompt_context=f"Deleted by super admin user_id={actor.id}",
                    generated_content=deleted_content,
                    provider_used="admin",
                    is_escalated=False,
                    timestamp=utcnow(),
                )
            )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    _destroy_media_after_commit(media)
    return post_id
