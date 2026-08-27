import re
import uuid
from contextlib import contextmanager
from datetime import date, timedelta

import pytest
from flask import render_template
from sqlalchemy import event, or_
from sqlalchemy.orm import joinedload


@contextmanager
def count_sql_statements(db):
    statements = []

    def record_statement(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(db.engine, "before_cursor_execute", record_statement)
    try:
        yield statements
    finally:
        event.remove(db.engine, "before_cursor_execute", record_statement)


@pytest.fixture()
def dashboard_factory(db):
    from models import (
        ActivityLog,
        AdCampaign,
        FriendRequest,
        Like,
        Post,
        Reaction,
        User,
        friendship,
    )
    from time_utils import utcnow

    suffix = uuid.uuid4().hex
    user_ids = []
    post_ids = []

    class Factory:
        def user(self, *, active=False, label=None):
            index = len(user_ids)
            label = label or f"User{index}"
            user = User(
                first_name=label,
                last_name="Dashboard",
                email=f"dashboard-query-{suffix}-{index}@example.test",
                password_hash="query-test-only",
                phone_number=f"+23470{index:08d}",
                dob=date(1990, 1, 1),
                gender="Other",
                city="Lagos",
                country="Nigeria",
                state="Lagos",
                marital_status="Single",
                is_active=active,
                last_seen=utcnow(),
            )
            db.session.add(user)
            db.session.flush()
            user_ids.append(user.id)
            return user

        def post(self, author, *, content="Dashboard query post", created_at=None):
            post = Post(
                content=content,
                author_id=author.id,
                created_at=created_at or utcnow(),
            )
            db.session.add(post)
            db.session.flush()
            post_ids.append(post.id)
            return post

        def campaign(
            self,
            owner,
            *,
            placement,
            title,
            current_time,
            budget=100,
            status="active",
            starts_in_days=-1,
            ends_in_days=1,
        ):
            campaign = AdCampaign(
                user_id=owner.id,
                title=title,
                image=f"https://cdn.example.test/{title}.jpg",
                target_url=f"https://ads.example.test/{title}",
                status=status,
                start_date=current_time + timedelta(days=starts_in_days),
                end_date=current_time + timedelta(days=ends_in_days),
                budget=budget,
                daily_budget=10,
                duration_days=2,
                placement=placement,
            )
            db.session.add(campaign)
            db.session.flush()
            return campaign

    yield Factory()

    db.session.rollback()
    if user_ids:
        ActivityLog.query.filter(ActivityLog.user_id.in_(user_ids)).delete(
            synchronize_session=False
        )
        Reaction.query.filter(
            or_(Reaction.user_id.in_(user_ids), Reaction.post_id.in_(post_ids))
        ).delete(synchronize_session=False)
        Like.query.filter(
            or_(Like.user_id.in_(user_ids), Like.post_id.in_(post_ids))
        ).delete(synchronize_session=False)
        FriendRequest.query.filter(
            or_(
                FriendRequest.sender_id.in_(user_ids),
                FriendRequest.receiver_id.in_(user_ids),
            )
        ).delete(synchronize_session=False)
        AdCampaign.query.filter(AdCampaign.user_id.in_(user_ids)).delete(
            synchronize_session=False
        )
        db.session.execute(
            User._blocked_users.delete().where(
                or_(
                    User._blocked_users.c.blocker_id.in_(user_ids),
                    User._blocked_users.c.blocked_id.in_(user_ids),
                )
            )
        )
        db.session.execute(
            friendship.delete().where(
                or_(
                    friendship.c.user_id.in_(user_ids),
                    friendship.c.friend_id.in_(user_ids),
                )
            )
        )
    if post_ids:
        Post.query.filter(Post.id.in_(post_ids)).delete(synchronize_session=False)
    if user_ids:
        User.query.filter(User.id.in_(user_ids)).delete(synchronize_session=False)
    db.session.commit()


def login_dashboard_user(client, user_id):
    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True


def test_bulk_reaction_data_preserves_counts_types_and_viewer_state(
    db, dashboard_factory
):
    from models import Reaction
    from users.user import get_dashboard_reaction_data

    viewer = dashboard_factory.user()
    reactor = dashboard_factory.user()
    author = dashboard_factory.user()
    zero_post = dashboard_factory.post(author, content="Zero reactions")
    one_post = dashboard_factory.post(author, content="One reaction")
    multiple_post = dashboard_factory.post(author, content="Multiple reactions")
    db.session.add_all(
        [
            Reaction(user_id=reactor.id, post_id=one_post.id, reaction_type="like"),
            Reaction(user_id=viewer.id, post_id=multiple_post.id, reaction_type="love"),
            Reaction(user_id=reactor.id, post_id=multiple_post.id, reaction_type="wow"),
        ]
    )
    viewer_id = viewer.id
    zero_post_id = zero_post.id
    one_post_id = one_post.id
    multiple_post_id = multiple_post.id
    db.session.commit()

    with count_sql_statements(db) as statements:
        counts, types, viewer_reactions = get_dashboard_reaction_data(
            [zero_post_id, one_post_id, multiple_post_id], viewer_id
        )

    assert len(statements) == 2
    assert counts.get(zero_post_id, 0) == 0
    assert counts[one_post_id] == 1
    assert counts[multiple_post_id] == 2
    assert types.get(zero_post_id, {}) == {}
    assert types[one_post_id] == {"like": 1}
    assert types[multiple_post_id] == {"love": 1, "wow": 1}
    assert viewer_reactions.get(zero_post_id) is None
    assert viewer_reactions.get(one_post_id) is None
    assert viewer_reactions[multiple_post_id] == "love"

    with count_sql_statements(db) as empty_statements:
        assert get_dashboard_reaction_data([], viewer_id) == ({}, {}, {})
    assert empty_statements == []


def test_bulk_friend_request_states_preserve_direction_and_precedence(
    db, dashboard_factory
):
    from models import FriendRequest
    from users.user import get_dashboard_friend_request_states

    viewer = dashboard_factory.user()
    no_relationship = dashboard_factory.user()
    outgoing = dashboard_factory.user()
    incoming = dashboard_factory.user()
    accepted_friend = dashboard_factory.user()
    blocked = dashboard_factory.user()
    opposite_pending = dashboard_factory.user()

    viewer.friends.append(accepted_friend)
    db.session.add_all(
        [
            FriendRequest(
                sender_id=viewer.id, receiver_id=outgoing.id, status="pending"
            ),
            FriendRequest(
                sender_id=incoming.id, receiver_id=viewer.id, status="pending"
            ),
            FriendRequest(
                sender_id=viewer.id,
                receiver_id=accepted_friend.id,
                status="accepted",
            ),
            FriendRequest(
                sender_id=viewer.id,
                receiver_id=opposite_pending.id,
                status="pending",
            ),
            FriendRequest(
                sender_id=opposite_pending.id,
                receiver_id=viewer.id,
                status="pending",
            ),
        ]
    )
    db.session.execute(
        viewer._blocked_users.insert().values(
            blocker_id=viewer.id,
            blocked_id=blocked.id,
        )
    )
    viewer_id = viewer.id
    suggestion_ids = [
        no_relationship.id,
        outgoing.id,
        incoming.id,
        accepted_friend.id,
        blocked.id,
        opposite_pending.id,
    ]
    accepted_friend_id = accepted_friend.id
    expected_states = {
        no_relationship.id: "none",
        outgoing.id: "sent",
        incoming.id: "received",
        accepted_friend_id: "friends",
        blocked.id: "none",
        opposite_pending.id: "sent",
    }
    db.session.commit()

    with count_sql_statements(db) as statements:
        states = get_dashboard_friend_request_states(
            viewer_id, suggestion_ids, {accepted_friend_id}
        )

    assert len(statements) == 1
    assert states == expected_states


def test_dashboard_banner_campaigns_returns_no_ineligible_ads(db, dashboard_factory):
    from time_utils import utcnow
    from users.user import get_dashboard_banner_campaigns

    current_time = utcnow() + timedelta(days=3650)

    with count_sql_statements(db) as statements:
        campaigns = get_dashboard_banner_campaigns(current_time)

    assert len(statements) == 1
    assert campaigns == {}


def test_dashboard_banner_campaigns_preserves_dates_and_status(
    db, dashboard_factory
):
    from time_utils import utcnow
    from users.user import get_dashboard_banner_campaigns

    owner = dashboard_factory.user()
    current_time = utcnow() + timedelta(days=3650)
    active = dashboard_factory.campaign(
        owner,
        placement="dashboard-top",
        title="active-top",
        current_time=current_time,
    )
    dashboard_factory.campaign(
        owner,
        placement="dashboard-sidebar",
        title="expired",
        current_time=current_time,
        starts_in_days=-3,
        ends_in_days=-1,
    )
    dashboard_factory.campaign(
        owner,
        placement="dashboard-vertical",
        title="future",
        current_time=current_time,
        starts_in_days=1,
        ends_in_days=3,
    )
    dashboard_factory.campaign(
        owner,
        placement="dashboard-spotlight",
        title="inactive",
        current_time=current_time,
        status="inactive",
    )
    dashboard_factory.campaign(
        owner,
        placement="dashboard-bottom",
        title="unapproved",
        current_time=current_time,
        status="pending",
    )
    dashboard_factory.campaign(
        owner,
        placement="sponsored",
        title="sponsored-separate",
        current_time=current_time,
    )
    db.session.commit()

    campaigns = get_dashboard_banner_campaigns(current_time)

    assert campaigns == {"top_banner": active}


def test_dashboard_banner_campaigns_groups_placements_by_highest_budget(
    db, dashboard_factory
):
    from time_utils import utcnow
    from users.user import get_dashboard_banner_campaigns

    owner = dashboard_factory.user()
    current_time = utcnow() + timedelta(days=3650)
    dashboard_factory.campaign(
        owner,
        placement="dashboard-top",
        title="lower-top",
        current_time=current_time,
        budget=10,
    )
    higher_top = dashboard_factory.campaign(
        owner,
        placement="dashboard-top",
        title="higher-top",
        current_time=current_time,
        budget=100,
    )
    sidebar = dashboard_factory.campaign(
        owner,
        placement="dashboard-sidebar",
        title="sidebar",
        current_time=current_time,
        budget=50,
    )
    vertical = dashboard_factory.campaign(
        owner,
        placement="dashboard-vertical",
        title="vertical",
        current_time=current_time,
        budget=25,
    )
    db.session.commit()

    with count_sql_statements(db) as statements:
        campaigns = get_dashboard_banner_campaigns(current_time)

    assert len(statements) == 1
    assert campaigns == {
        "top_banner": higher_top,
        "sidebar_banner": sidebar,
        "vertical_banner": vertical,
    }


def test_ajax_partial_preserves_legacy_liked_output_without_render_queries(
    app, db, dashboard_factory
):
    from models import Like, Post, User

    viewer = dashboard_factory.user()
    author = dashboard_factory.user()
    liked_post = dashboard_factory.post(author, content="Liked legacy post")
    unliked_post = dashboard_factory.post(author, content="Unliked legacy post")
    db.session.add(Like(user_id=viewer.id, post_id=liked_post.id))
    db.session.commit()
    db.session.expire_all()

    posts = (
        Post.query.options(
            joinedload(Post.author),
            joinedload(Post.comments),
            joinedload(Post.likes),
        )
        .filter(Post.id.in_([liked_post.id, unliked_post.id]))
        .order_by(Post.id)
        .all()
    )
    viewer = db.session.get(User, viewer.id)
    liked_ids = {
        post.id
        for post in posts
        if any(like.user_id == viewer.id for like in post.likes)
    }

    with app.test_request_context("/user_dashboard"):
        with count_sql_statements(db) as statements:
            html = render_template(
                "_posts_partial.html",
                posts=posts,
                current_user=viewer,
                current_user_liked_post_ids=liked_ids,
            )

    assert statements == []
    assert re.search(
        rf'<button\s+class="[^"]*text-blue-600[^"]*"\s+data-post-id="{liked_post.id}"',
        html,
    )
    assert not re.search(
        rf'<button\s+class="[^"]*text-blue-600[^"]*"\s+data-post-id="{unliked_post.id}"',
        html,
    )
    assert html.count("bi-hand-thumbs-up-fill") == 1


def test_dashboard_route_query_count_is_bounded_across_post_counts(
    client, db, dashboard_factory
):
    from models import AdCampaign, Reaction
    from time_utils import utcnow

    viewer = dashboard_factory.user(active=True, label="ScalingViewer")
    author = dashboard_factory.user(active=False, label="ScalingAuthor")
    suggestions = [
        dashboard_factory.user(active=True, label=f"Suggestion{index}")
        for index in range(20)
    ]
    created_at = utcnow() + timedelta(days=730)
    posts = [
        dashboard_factory.post(
            author,
            content=f"Scaling post {index}",
            created_at=created_at - timedelta(seconds=index),
        )
        for index in range(100)
    ]
    for post in posts:
        db.session.add_all(
            [
                Reaction(user_id=viewer.id, post_id=post.id, reaction_type="love"),
                Reaction(
                    user_id=suggestions[0].id,
                    post_id=post.id,
                    reaction_type="like",
                ),
                Reaction(
                    user_id=suggestions[1].id,
                    post_id=post.id,
                    reaction_type="wow",
                ),
            ]
        )

    current_time = utcnow()
    for index, placement in enumerate(
        [
            "dashboard-top",
            "dashboard-sidebar",
            "dashboard-vertical",
            "dashboard-spotlight",
            "dashboard-bottom",
            "sponsored",
        ]
    ):
        dashboard_factory.campaign(
            viewer,
            placement=placement,
            title=f"scaling-{placement}",
            current_time=current_time,
            budget=1000 - index,
        )
    db.session.commit()
    login_dashboard_user(client, viewer.id)

    warm_response = client.get("/user_dashboard?limit=0")
    assert warm_response.status_code == 200

    query_counts = {}
    for post_count in [0, 10, 50, 100]:
        with count_sql_statements(db) as statements:
            response = client.get(f"/user_dashboard?limit={post_count}")
        assert response.status_code == 200
        query_counts[post_count] = len(statements)

    assert query_counts[10] == query_counts[50] == query_counts[100]
    assert query_counts[10] - query_counts[0] <= 3
