import os
import json
import logging
from pywebpush import webpush, WebPushException
from models import PushSubscription
from extensions import db


logger = logging.getLogger(__name__)


def _send_to_subscriptions(subscriptions, payload_dict, vapid_private_key):
    vapid_claims = {
        "sub": "mailto:no-reply@kimbela.com"
    }
    success_count = 0
    payload = json.dumps(payload_dict)

    for sub in subscriptions:
        user_id = sub.user_id
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
            # If the subscription is expired or the user revoked permission, the server returns 410 or 404
            if ex.response is not None and ex.response.status_code in [404, 410]:
                try:
                    db.session.delete(sub)
                    db.session.commit()
                except Exception:
                    db.session.rollback()
                    logger.exception(
                        "Failed to remove expired push subscription for user %s",
                        user_id,
                    )
            else:
                logger.warning(
                    "Push provider rejected a subscription for user %s: %s",
                    user_id,
                    ex,
                )
        except Exception:
            db.session.rollback()
            logger.exception("Failed to send push notification for user %s", user_id)

    return success_count > 0


def send_push_notification(user_id, payload_dict):
    """
    Send a push notification to every registered device for one user.
    """
    vapid_private_key = os.environ.get("VAPID_PRIVATE_KEY")
    if not vapid_private_key:
        logger.warning("VAPID private key not configured, skipping push")
        return False

    try:
        subscriptions = PushSubscription.query.filter_by(user_id=user_id).all()
    except Exception:
        db.session.rollback()
        logger.exception("Failed to load push subscriptions for user %s", user_id)
        return False

    if not subscriptions:
        return False

    return _send_to_subscriptions(subscriptions, payload_dict, vapid_private_key)


def send_push_notifications(user_ids, payload_dict):
    """Bulk-load subscriptions and fan one payload out to unique users."""
    recipient_ids = {int(user_id) for user_id in user_ids if user_id is not None}
    if not recipient_ids:
        return False

    vapid_private_key = os.environ.get("VAPID_PRIVATE_KEY")
    if not vapid_private_key:
        logger.warning("VAPID private key not configured, skipping push")
        return False

    try:
        subscriptions = (
            PushSubscription.query
            .filter(PushSubscription.user_id.in_(recipient_ids))
            .all()
        )
    except Exception:
        db.session.rollback()
        logger.exception(
            "Failed to bulk-load push subscriptions for %s users",
            len(recipient_ids),
        )
        return False

    if not subscriptions:
        return False

    return _send_to_subscriptions(subscriptions, payload_dict, vapid_private_key)
