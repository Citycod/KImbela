from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_active_feed_and_group_surfaces_use_chime_copy_and_icon():
    sources = {
        relative: (PROJECT_ROOT / relative).read_text()
        for relative in (
            "templates/user_dashboard.html",
            "templates/_posts_partial.html",
            "templates/_post_card.html",
            "templates/_post_item.html",
            "templates/group_detail.html",
        )
    }

    assert "microphone2.png" in sources["templates/user_dashboard.html"]
    assert "microphone2.png" in sources["templates/_posts_partial.html"]
    assert "microphone2.png" in sources["templates/_post_card.html"]
    assert "microphone2.png" in sources["templates/_post_item.html"]
    assert "microphone2.png" in sources["templates/group_detail.html"]
    assert 'aria-label="Send Chime"' in sources["templates/user_dashboard.html"]
    assert 'aria-label="Send Chime"' in sources["templates/_posts_partial.html"]
    assert 'aria-label="Send Chime"' in sources["templates/group_detail.html"]

    combined = "\n".join(sources.values())
    for obsolete_copy in (
        ">Comment<",
        "Write a comment...",
        'aria-label="Send comment"',
        "No comments yet",
        "View all {{ post.comments_list|length }} comments",
    ):
        assert obsolete_copy not in combined


def test_active_client_feedback_uses_chime_terminology():
    combined = "\n".join(
        (PROJECT_ROOT / relative).read_text()
        for relative in (
            "static/assets/js/dashboard.js",
            "static/assets/js/comment_composer.js",
            "static/assets/js/network_resilience.js",
            "static/assets/js/modules/posts/comments.js",
            "static/assets/js/modules/posts/index.js",
        )
    )

    assert "Chime added!" in combined
    assert "No Chimes yet" in combined
    for obsolete_copy in (
        "Comment added!",
        "Comment deleted",
        "Failed to add comment",
        "Failed to load comments",
        "No comments yet",
        "post your comment",
    ):
        assert obsolete_copy not in combined


def test_comment_backend_contract_remains_intact():
    source = (PROJECT_ROOT / "users" / "user.py").read_text()
    models_source = (PROJECT_ROOT / "models.py").read_text()

    assert 'class Comment(db.Model):' in models_source
    assert '@user.route("/add_comment/<int:post_id>", methods=["POST"])' in source
    assert '@user.route("/get_comments/<int:post_id>")' in source
    assert "comment_id" in source
