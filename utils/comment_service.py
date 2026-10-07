"""Comment persistence with explicit authorship and no HTTP/session impersonation."""

from extensions import db
from models import Comment, Post, User


class CommentCreationError(Exception):
    """A safe, classified comment-creation failure."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def create_comment_for_author(
    *,
    author_id: int,
    post_id: int,
    content: str,
    parent_comment_id: int | None = None,
) -> Comment:
    """Build and flush one comment for an explicitly identified active author.

    The caller owns the transaction so related audit data can be committed
    atomically. No request, login session, or CSRF state is involved.
    """
    author = db.session.get(User, int(author_id))
    post = db.session.get(Post, int(post_id))
    if author is None or not author.is_active:
        raise CommentCreationError("invalid_author")
    if post is None:
        raise CommentCreationError("invalid_post")

    normalized_content = (content or "").strip()
    if not normalized_content:
        raise CommentCreationError("empty_comment")

    parent_comment = None
    if parent_comment_id is not None:
        parent_comment = Comment.query.filter_by(
            id=int(parent_comment_id),
            post_id=post.id,
        ).first()
        if parent_comment is None:
            raise CommentCreationError("invalid_parent")

    comment = Comment(
        content=normalized_content,
        author_id=author.id,
        post_id=post.id,
        parent_id=parent_comment.id if parent_comment else None,
    )
    db.session.add(comment)
    db.session.flush()
    return comment
