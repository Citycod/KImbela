import os
import json
from pywebpush import webpush, WebPushException
from models import PushSubscription
from extensions import db
import traceback

def send_push_notification(user_id, payload_dict):
    """
    Sends a push notification to all registered devices for a given user.
    payload_dict: dict containing the push notification data (e.g. title, body, url)
    """
    vapid_private_key = os.environ.get("VAPID_PRIVATE_KEY")
    vapid_public_key = os.environ.get("VAPID_PUBLIC_KEY")
    vapid_claims = {
        "sub": "mailto:no-reply@kimbela.com"
    }

    if not vapid_private_key:
        print("VAPID keys not configured, skipping push.")
        return False

    subscriptions = PushSubscription.query.filter_by(user_id=user_id).all()
    if not subscriptions:
        return False

    success_count = 0
    payload = json.dumps(payload_dict)

    for sub in subscriptions:
        try:
            subscription_info = {
                "endpoint": sub.endpoint,
                "keys": {
                    "p256dh": sub.p256dh,
                    "auth": sub.auth
                }
            }
            webpush(
                subscription_info=subscription_info,
                data=payload,
                vapid_private_key=vapid_private_key,
                vapid_claims=vapid_claims
            )
            sub.last_seen_at = db.func.now()
            db.session.commit()
            success_count += 1
        except WebPushException as ex:
            print(f"WebPushException: {repr(ex)}")
            # If the subscription is expired or the user revoked permission, the server returns 410 or 404
            if ex.response is not None and ex.response.status_code in [404, 410]:
                print(f"Subscription for endpoint {sub.endpoint} is dead (status {ex.response.status_code}). Removing from DB.")
                db.session.delete(sub)
                db.session.commit()
        except Exception as e:
            print(f"Failed to send push to {sub.endpoint}: {e}")
            traceback.print_exc()

    return success_count > 0
