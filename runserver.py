# from app_config import create_app
# from models import User, Post, Comment, Like, FriendRequest, friendship
# import eventlet
# eventlet.monkey_patch()

# from extensions import socketio


# app = create_app()

# # if __name__ == "__main__":
# #     app.run(host="0.0.0.0", port=5000, debug=True)


# if __name__ == '__main__':
    
#     socketio.run(app, debug=True, host='0.0.0.0', port=5000)




from app_config import create_app
from extensions import socketio

app = create_app()

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
