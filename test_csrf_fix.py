import os
import sys
sys.path.insert(0, '/home/uplix/uplix/KImbela')
from app_config import app
from flask_login import login_user, UserMixin
from flask_wtf.csrf import generate_csrf
from flask import session

class MockUser(UserMixin):
    id = 64

with app.app_context():
    with app.test_client() as client:
        # Step 1: Make a GET request to establish client session cookie
        client.get("/")
        
        # Step 2: Inject user login into client session
        with client.session_transaction() as sess:
            # We can use Flask-Login session keys
            sess["_user_id"] = "64"
            sess["_fresh"] = True
            
        # Step 3: Now generate CSRF token using client's session
        with client.session_transaction() as sess:
            # Check what's in session
            print("Session in client before generate_csrf:", dict(sess))
            
        # To generate CSRF for client, we use test_request_context with client's session
        # In Flask test_client, client.post automatically passes session if session has csrf_token!
