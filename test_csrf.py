from app_config import app
from models import AIPersona
from flask_wtf.csrf import generate_csrf
from flask import session

with app.app_context():
    persona = AIPersona.query.first()
    
    with app.test_client() as client:
        with app.test_request_context("/"):
            csrf_token = generate_csrf()
            csrf_session = dict(session)
            
        with client.session_transaction() as sess:
            sess["_user_id"] = str(persona.user_id)
            sess["_fresh"] = True
            for k, v in csrf_session.items():
                sess[k] = v
                
        res = client.post(
            "/user_dashboard",
            data={"post_content": "This is a CSRF test post", "csrf_token": csrf_token},
            follow_redirects=True
        )
        print("Status code:", res.status_code)
        
        # Check if it was created
        from models import Post
        p = Post.query.order_by(Post.id.desc()).first()
        print("Latest post ID:", p.id if p else None)
        print("Content:", p.content if p else None)
