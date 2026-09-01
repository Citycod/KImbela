import os
import json
import logging
import time
from urllib.parse import urlparse
from pywebpush import webpush, WebPushException
from models import PushSubscription
from extensions import db


logger = logging.getLogger(__name__)
# Keep push delivery diagnostics visible under production's WARNING root logger
# without changing logging verbosity for the rest of the application.
logger.setLevel(logging.INFO)
KIMBELA_NOTIFICATION_ICON = "/static/img/icons/icon-192x192.png"
KIMBELA_NOTIFICATION_BADGE = "/static/img/icons/icon-192x192.png"


def prepare_push_payload(payload_dict):
    """Apply shared display metadata without changing delivery semantics."""
    payload = dict(payload_dict or {})
    payload["icon"] = KIMBELA_NOTIFICATION_ICON
    payload["badge"] = KIMBELA_NOTIFICATION_BADGE
    payload.setdefault("timestamp", int(time.time() * 1000))

    # Birthday construction lives with the dedicated scheduler. Preserve that
    # boundary while giving retries for the same annual event one stable group.
    if not payload.get("tag") and "birthday" in str(payload.get("title", "")).lower():
        payload["tag"] = "birthday"
        payload["renotify"] = False

    return payload


def _push_log_context(subscription, event_type):
    """Return non-secret identifiers suitable for production diagnostics."""
    try:
        endpoint_host = urlparse(subscription.endpoint).hostname or "unknown"
    except (TypeError, ValueError):
        endpoint_host = "invalid"

    return {
        "user_id": subscription.user_id,
        "subscription_id": subscription.id,
        "endpoint_host": endpoint_host,
        "event_type": event_type,
    }


def _send_to_subscriptions(subscriptions, payload_dict, vapid_private_key):
    vapid_claims = {
        "sub": "mailto:no-reply@kimbela.com"
    }
    success_count = 0
    prepared_payload = prepare_push_payload(payload_dict)
    payload = json.dumps(prepared_payload)
    event_type = prepared_payload.get("event_type", "notification")

    for sub in subscriptions:
        context = _push_log_context(sub, event_type)
        try:
            subscription_info = {
                "endpoint": sub.endpoint,
                "keys": {
                    "p256dh": sub.p256dh,
                    "auth": sub.auth
                }
            }
            logger.info(
                "Push provider send attempted user_id=%s subscription_id=%s "
                "event_type=%s",
                context["user_id"],
                context["subscription_id"],
                context["event_type"],
            )
            provider_response = webpush(
                subscription_info=subscription_info,
                data=payload,
                vapid_private_key=vapid_private_key,
                vapid_claims=vapid_claims
            )
            sub.last_seen_at = db.func.now()
            db.session.commit()
            success_count += 1
            logger.info(
                "Push delivery succeeded user_id=%s subscription_id=%s "
                "endpoint_host=%s event_type=%s provider_status=%s",
                context["user_id"],
                context["subscription_id"],
                context["endpoint_host"],
                context["event_type"],
                getattr(provider_response, "status_code", "unknown"),
            )
        except WebPushException as ex:
            # If the subscription is expired or the user revoked permission, the server returns 410 or 404
            provider_status = (
                ex.response.status_code if ex.response is not None else "unknown"
            )
            if provider_status in [404, 410]:
                try:
                    db.session.delete(sub)
                    db.session.commit()
                    logger.info(
                        "Expired push subscription pruned user_id=%s subscription_id=%s "
                        "endpoint_host=%s event_type=%s provider_status=%s",
                        context["user_id"],
                        context["subscription_id"],
                        context["endpoint_host"],
                        context["event_type"],
                        provider_status,
                    )
                except Exception:
                    db.session.rollback()
                    logger.exception(
                        "Failed to remove expired push subscription for user %s",
                        context["user_id"],
                    )
            else:
                logger.warning(
                    "Push delivery failed user_id=%s subscription_id=%s "
                    "endpoint_host=%s event_type=%s provider_status=%s exception=%s",
                    context["user_id"],
                    context["subscription_id"],
                    context["endpoint_host"],
                    context["event_type"],
                    provider_status,
                    type(ex).__name__,
                )
        except Exception as ex:
            db.session.rollback()
            logger.error(
                "Push delivery failed user_id=%s subscription_id=%s "
                "endpoint_host=%s event_type=%s provider_status=unknown exception=%s",
                context["user_id"],
                context["subscription_id"],
                context["endpoint_host"],
                context["event_type"],
                type(ex).__name__,
            )

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

    event_type = (payload_dict or {}).get("event_type", "notification")
    logger.info(
        "Push subscription lookup user_id=%s subscription_count=%s event_type=%s",
        user_id,
        len(subscriptions),
        event_type,
    )
    if not subscriptions:
        logger.warning(
            "Push delivery skipped user_id=%s subscription_count=0 "
            "event_type=%s reason=no_subscriptions",
            user_id,
            event_type,
        )
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
