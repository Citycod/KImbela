from app_config import create_app
from models import User, Post, Comment, Like, FriendRequest, friendship



app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
