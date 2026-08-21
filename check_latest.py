from app_config import app
from extensions import db
from models import Post, AILog

with app.app_context():
    p = Post.query.order_by(Post.id.desc()).first()
    if p:
        print(f"Latest Post ID: {p.id}")
        print(f"Content: {p.content}")
        
    l = AILog.query.order_by(AILog.id.desc()).first()
    if l:
        print(f"\nLatest AILog ID: {l.id}")
        print(f"Generated Content: {l.generated_content}")
