# Ensure eventlet patches are applied before any other imports
import eventlet

eventlet.monkey_patch()

# from app_config import create_app
# from extensions import socketio
# from models import MatchmakingPackage
# from extensions import db

# app = create_app()


# # def create_sample_packages():
# #     """Create single matchmaking package if it doesn't exist"""
# #     with app.app_context():
# #         existing_packages = MatchmakingPackage.query.count()
# #         if existing_packages == 0:
# #             # Create only one package - $10/month
# #             package = MatchmakingPackage(
# #                 name="Matchmaking",
# #                 description="Premium matchmaking service to find your perfect partner",
# #                 price=10.00,  # Fixed $10 price
# #                 duration_days=30,  # 30 days duration
# #                 features="Enhanced Profile Listing,30 Days Duration,Advanced Matching Algorithm,Priority Placement,Message Responses,Personalized Recommendations",
# #             )

# #             db.session.add(package)
# #             db.session.commit()
# #             print("✓ Single matchmaking package created: $10/month for 30 days")

# #             return package
# #         else:
# #             # Check if we have multiple packages and consolidate to single $10 package
# #             packages = MatchmakingPackage.query.all()

# #             # If there are multiple packages, delete them and create single one
# #             if len(packages) > 1:
# #                 print(
# #                     f"⚠️ Found {len(packages)} packages, consolidating to single $10 package..."
# #                 )

# #                 # Delete all existing packages
# #                 for package in packages:
# #                     db.session.delete(package)

# #                 # Create single package
# #                 package = MatchmakingPackage(
# #                     name="Matchmaking",
# #                     description="Premium matchmaking service to find your perfect partner",
# #                     price=10.00,  # Fixed $10 price
# #                     duration_days=30,  # 30 days duration
# #                     features="Enhanced Profile Listing,30 Days Duration,Advanced Matching Algorithm,Priority Placement,Message Responses,Personalized Recommendations",
# #                 )

# #                 db.session.add(package)
# #                 db.session.commit()
# #                 print(
# #                     "✓ Consolidated to single matchmaking package: $10/month for 30 days"
# #                 )

# #             # If there's exactly one package, ensure it's the correct $10 one
# #             elif len(packages) == 1:
# #                 package = packages[0]
# #                 if package.price != 10.00 or package.name != "Matchmaking":
# #                     print(f"⚠️ Updating existing package to $10/month...")
# #                     package.name = "Matchmaking"
# #                     package.description = (
# #                         "Premium matchmaking service to find your perfect partner"
# #                     )
# #                     package.price = 10.00
# #                     package.duration_days = 30
# #                     package.features = "Enhanced Profile Listing,30 Days Duration,Advanced Matching Algorithm,Priority Placement,Message Responses,Personalized Recommendations"
# #                     db.session.commit()
# #                     print("✓ Updated existing package to $10/month for 30 days")

# #             return MatchmakingPackage.query.first()


# if __name__ == "__main__":
#     # Create sample packages on startup
#     # create_sample_packages()

#     # Run the application
#     socketio.run(app, host="0.0.0.0", port=5000, debug=True)


import eventlet

eventlet.monkey_patch()
## runserver.py - SIMPLIFIED
from app_config import app, socketio
from extensions import socketio
import threading
import time

from flask_migrate import Migrate
from extensions import db
from app_config import app, socketio
import eventlet


print(">>> MIGRATE REGISTERING <<<")
Migrate(app, db)


def init_background_tasks():
    """Initialize background tasks after server starts"""
    time.sleep(5)  # Wait for server to fully initialize

    with app.app_context():
        try:
            # Import inside function to avoid circular imports
            from models import MatchmakingPackage
            from extensions import db

            # Check if package exists
            existing = MatchmakingPackage.query.filter_by(name="Matchmaking").first()

            if not existing:
                # Create only one package
                package = MatchmakingPackage(
                    name="Matchmaking",
                    description="Premium matchmaking service to find your perfect partner",
                    price=10.00,
                    duration_days=30,
                    features="Enhanced Profile Listing,30 Days Duration,Advanced Matching Algorithm,Priority Placement,Message Responses,Personalized Recommendations",
                )
                db.session.add(package)
                db.session.commit()
                print("✓ Single matchmaking package created: $10/month for 30 days")
            else:
                # Quick update if needed
                if existing.price != 10.00:
                    existing.price = 10.00
                    existing.duration_days = 30
                    db.session.commit()
                    print("✓ Updated package to $10/month")
                else:
                    print("✓ Package already exists")

        except Exception as e:
            print(f"✗ Error initializing background tasks: {e}")


if __name__ == "__main__":
    print("=" * 50)
    print("🚀 Starting Kimbela Server")
    print("📡 Web: http://localhost:5001")
    print("🔌 Socket.IO: Ready")
    print("=" * 50)

    # Run with the SAME parameters as the working test
    socketio.run(
        app,
        host="0.0.0.0",
        port=5001,
        debug=False,
        allow_unsafe_werkzeug=True,
        use_reloader=False,  # Keep this False to avoid issues
    )
