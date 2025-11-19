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
from models import MatchmakingPackage

app = create_app()

def create_sample_packages():
    packages = [
        MatchmakingPackage(
            name='Basic',
            description='Perfect for casual matchmaking',
            price=9.99,
            duration_days=7,
            features='Basic Profile Listing,7 Days Duration,Basic Matching,Limited Visibility'
        ),
        MatchmakingPackage(
            name='Standard',
            description='Great for serious connections',
            price=24.99,
            duration_days=14,
            features='Enhanced Profile Listing,14 Days Duration,Advanced Matching,Priority Placement,Message Responses'
        ),
        MatchmakingPackage(
            name='Premium',
            description='Maximum visibility and matches',
            price=49.99,
            duration_days=30,
            features='Premium Profile Listing,30 Days Duration,Advanced Matching,Top Placement,Unlimited Messages,Personal Matchmaker'
        ),
        MatchmakingPackage(
            name='Elite',
            description='For exclusive matchmaking',
            price=99.99,
            duration_days=60,
            features='Elite Profile Listing,60 Days Duration,VIP Matching,Featured Placement,Unlimited Messages,Dedicated Matchmaker,Background Verification'
        )
    ]
    
    for package in packages:
        db.session.add(package)
    
    db.session.commit()


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)
