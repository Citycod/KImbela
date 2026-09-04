import json
import secrets
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from flask import current_app, url_for

from extensions import db
from models import PaymentTransaction
from time_utils import utcnow

from .payment_service import BasePaymentService


BROWSE_ACCESS_PRICE_USD = Decimal("2.00")
BROWSE_ACCESS_DAYS = 30
BROWSE_TRANSACTION_TYPE = "matchmaking_browse"
BROWSE_REFERENCE_PREFIX = "KIMBELA_BROWSE_"


def find_browse_payment(tx_ref):
    if not tx_ref:
        return None
    return PaymentTransaction.query.filter_by(
        gateway_reference=tx_ref,
        transaction_type=BROWSE_TRANSACTION_TYPE,
    ).first()


def get_browse_access_status(user_id, now=None):
    now = now or utcnow()
    transaction = (
        PaymentTransaction.query.filter(
            PaymentTransaction.user_id == user_id,
            PaymentTransaction.transaction_type == BROWSE_TRANSACTION_TYPE,
            PaymentTransaction.status == "completed",
        )
        .order_by(PaymentTransaction.updated_at.desc(), PaymentTransaction.id.desc())
        .first()
    )
    if not transaction:
        return {"active": False, "expires_at": None, "transaction": None}

    completed_at = transaction.updated_at or transaction.created_at
    expires_at = completed_at + timedelta(days=BROWSE_ACCESS_DAYS)
    return {
        "active": expires_at > now,
        "expires_at": expires_at,
        "transaction": transaction,
    }


def complete_browse_payment(transaction, verification_data):
    if not transaction or transaction.transaction_type != BROWSE_TRANSACTION_TYPE:
        return False
    if transaction.status == "completed":
        return True

    try:
        initiation = json.loads(transaction.gateway_metadata or "{}")
    except (TypeError, ValueError):
        initiation = {}

    expected_currency = initiation.get("expected_checkout_currency")
    expected_amount = initiation.get("expected_checkout_amount")
    actual_currency = str(verification_data.get("currency") or "").upper()
    actual_reference = verification_data.get("tx_ref")

    try:
        expected_amount = Decimal(str(expected_amount))
        actual_amount = Decimal(str(verification_data.get("amount")))
    except (InvalidOperation, TypeError, ValueError):
        current_app.logger.error(
            "Browse payment %s has invalid verified amount data",
            transaction.gateway_reference,
        )
        return False

    if (
        not expected_amount.is_finite()
        or expected_amount <= 0
        or not actual_amount.is_finite()
    ):
        return False
    if actual_reference and actual_reference != transaction.gateway_reference:
        return False
    if not expected_currency or actual_currency != expected_currency:
        return False
    if actual_amount < expected_amount:
        return False

    provider_meta = verification_data.get("meta") or {}
    if not isinstance(provider_meta, dict):
        return False
    if provider_meta.get("user_id") not in (
        None,
        transaction.user_id,
        str(transaction.user_id),
    ):
        return False

    transaction.status = "completed"
    transaction.gateway_status = str(
        verification_data.get("status") or "successful"
    ).lower()
    transaction.gateway_payment_id = str(
        verification_data.get("id") or transaction.gateway_payment_id or ""
    )
    transaction.gateway_metadata = json.dumps(
        {
            "expected_checkout_amount": str(expected_amount),
            "expected_checkout_currency": expected_currency,
            "access_days": BROWSE_ACCESS_DAYS,
            "verification": verification_data,
        },
        default=str,
    )
    transaction.updated_at = utcnow()
    db.session.commit()
    return True


def record_browse_payment_status(transaction, verification_data, status):
    if not transaction:
        return False
    if transaction.status == "completed":
        return True

    normalized_status = (status or "failed").strip().lower()
    transaction.status = (
        "pending" if normalized_status in {"pending", "processing"} else "failed"
    )
    transaction.gateway_status = normalized_status
    transaction.gateway_payment_id = str(
        verification_data.get("id") or transaction.gateway_payment_id or ""
    )
    transaction.updated_at = utcnow()
    db.session.commit()
    return True


class BrowseAccessPaymentService(BasePaymentService):
    def create_payment(self, user):
        access = get_browse_access_status(user.id)
        if access["active"]:
            return {
                "success": True,
                "already_active": True,
                "redirect_url": url_for("match.view_requests"),
                "expires_at": access["expires_at"].isoformat(),
            }

        checkout_currency = "NGN"
        try:
            rate = Decimal(str(self.get_ngn_rate("USD_TO_NGN_RATE", "1600")))
        except (InvalidOperation, TypeError, ValueError):
            return {"success": False, "error": "Payment exchange rate is unavailable"}
        if not rate.is_finite() or rate <= 0:
            return {"success": False, "error": "Payment exchange rate is unavailable"}
        checkout_amount = (BROWSE_ACCESS_PRICE_USD * rate).quantize(Decimal("0.01"))
        tx_ref = (
            f"{BROWSE_REFERENCE_PREFIX}{user.id}_{secrets.token_hex(8).upper()}"
        )
        payment_data = {
            "tx_ref": tx_ref,
            "amount": str(checkout_amount),
            "currency": checkout_currency,
            "redirect_url": url_for("match.browse_payment_callback", _external=True),
            "payment_options": "card,banktransfer,ussd",
            "customer": {
                "email": user.email,
                "name": user.full_name or user.first_name or user.email.split("@")[0],
            },
            "meta": {
                "user_id": user.id,
                "transaction_type": BROWSE_TRANSACTION_TYPE,
                "access_days": BROWSE_ACCESS_DAYS,
            },
            "customizations": {
                "title": "Kimbela Browse Match",
                "description": "$2 USD for 30 days of Browse Match access",
            },
        }
        if getattr(user, "phone_number", None):
            payment_data["customer"]["phone_number"] = user.phone_number

        try:
            response = self._http_request(
                "POST",
                f"{self.flutterwave_base_url}/payments",
                headers={
                    "Authorization": f"Bearer {self.flutterwave_secret_key}",
                    "Content-Type": "application/json",
                },
                json=payment_data,
                timeout=30,
            )
            if response.status_code != 200:
                return {"success": False, "error": "Payment provider rejected the request"}

            result = response.json()
            if result.get("status") != "success" or not result.get("data", {}).get("link"):
                return {"success": False, "error": "Payment checkout could not be created"}

            transaction = PaymentTransaction(
                user_id=user.id,
                amount=BROWSE_ACCESS_PRICE_USD,
                currency="USD",
                gateway="flutterwave",
                gateway_reference=tx_ref,
                gateway_payment_id=str(result["data"].get("id") or ""),
                gateway_status="initiated",
                status="pending",
                transaction_type=BROWSE_TRANSACTION_TYPE,
                description="$2 Browse Match access for 30 days",
                gateway_metadata=json.dumps(
                    {
                        "expected_checkout_amount": str(checkout_amount),
                        "expected_checkout_currency": checkout_currency,
                        "access_days": BROWSE_ACCESS_DAYS,
                    }
                ),
            )
            db.session.add(transaction)
            db.session.commit()
            return {
                "success": True,
                "payment_url": result["data"]["link"],
                "payment_id": transaction.id,
                "gateway_reference": tx_ref,
            }
        except Exception as exc:
            db.session.rollback()
            current_app.logger.exception("Browse payment initiation failed: %s", exc)
            return {"success": False, "error": "Unable to start payment"}
