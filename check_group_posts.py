from runserver import app
from extensions import db
from models import Post

with app.app_context():
    group_posts = Post.query.filter(Post.group_id.isnot(None)).count()
    print("Posts with group_id:", group_posts)
    posts_with_group = Post.query.filter(Post.group_id.isnot(None)).all()
    for p in posts_with_group:
        print(f"Post {p.id} has group_id {p.group_id}")
