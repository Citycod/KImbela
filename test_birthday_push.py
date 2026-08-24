import sys
import os

# Initialize environment for eventlet
os.environ.setdefault("EVENTLET_NO_GREENDNS", "yes")
import eventlet
eventlet.monkey_patch()

from app_config import app
from models import User
from extensions import db
from utils.push_service import send_push_notification
from email_service import EmailService

def test_push_and_email(email):
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        if not user:
            print(f"❌ User with email '{email}' not found.")
            return
            
        print(f"Found user: {user.first_name} {user.last_name}")
        
        # 1. Test Push Notification
        subs = user.push_subscriptions.all()
        if not subs:
            print(f"⚠️ User has NO active push subscriptions.")
            print("Please log in on your device, tap 'Turn On' notifications in the dashboard banner, and try again.")
        else:
            print(f"Found {len(subs)} push subscriptions. Sending test push...")
            payload = {
                "title": "🎉 Test Push Notification!",
                "body": f"Hi {user.first_name}, this is a test from your new PWA setup! 🎂",
                "icon": "/static/assets/img/kimbela_icon_512.png",
                "url": "/user_dashboard"
            }
            
            success = send_push_notification(user.id, payload)
            if success:
                print("✅ Push sent successfully!")
            else:
                print("❌ Push failed. Check VAPID keys or subscription status.")

        # 2. Test Email
        print("\nSending test email...")
        email_success = EmailService.send_birthday_email(user)
        if email_success:
            print("✅ Email sent successfully! Check your inbox.")
        else:
            print("❌ Email failed to send. Check mail server configuration.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_birthday_push.py <user_email>")
        sys.exit(1)
        
    test_push_and_email(sys.argv[1])
