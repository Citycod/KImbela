import eventlet

eventlet.monkey_patch()

import threading
import time

from flask_migrate import Migrate

from app_config import app, socketio
from extensions import db


print(">>> MIGRATE REGISTERING <<<")
Migrate(app, db)


def init_background_tasks():
    """Initialize background tasks after server starts."""
    time.sleep(5)

    with app.app_context():
        try:
            from models import MatchmakingPackage

            existing = MatchmakingPackage.query.filter_by(name="Matchmaking").first()

            if not existing:
                package = MatchmakingPackage(
                    name="Matchmaking",
                    description="Premium matchmaking service to find your perfect partner",
                    price=10.00,
                    duration_days=30,
                    features="Enhanced Profile Listing,30 Days Duration,Advanced Matching Algorithm,Priority Placement,Message Responses,Personalized Recommendations",
                )
                db.session.add(package)
                db.session.commit()
                print("✓ Matchmaking package initialized")
            elif existing.price != 10.00:
                existing.price = 10.00
                db.session.commit()
                print("✓ Matchmaking package price updated")
        except Exception as exc:
            db.session.rollback()
            print(f"Background task init failed: {exc}")


if __name__ == "__main__":
    background_thread = threading.Thread(target=init_background_tasks, daemon=True)
    background_thread.start()

    print("=" * 50)
    print("🚀 Starting Kimbela Server")
    print("📡 Web: http://localhost:5001")
    print("🔌 Socket.IO: Ready")
    print("=" * 50)

    socketio.run(app, host="0.0.0.0", port=5001, debug=True)
