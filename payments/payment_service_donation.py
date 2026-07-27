from time_utils import utcnow
import json
from flask import url_for, current_app
from extensions import db
from models import Donation, PaymentTransaction, User
import time
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class DonationPaymentService:
    def __init__(self):
        from .payment_service import BasePaymentService
        self.base = BasePaymentService()
        self.FLW_SECRET_KEY = self.base.flutterwave_secret_key
        self.flutterwave_base_url = self.base.flutterwave_base_url

    def _http_request(self, method, url, **kwargs):
        """Delegate HTTP requests to base service"""
        return self.base._http_request(method, url, **kwargs)

    def create_donation_payment(self, donation, gateway="flutterwave"):
        """Create payment for donation using Flutterwave"""
        try:
            currency = self.base.normalize_currency(donation.currency)
            print(f"🟡 [DONATION] Starting payment for donation: {donation.id}, Gateway: {gateway}")
            
            # Generate unique transaction reference
            tx_ref = f"KIMBELA_DONATION_{donation.id}_{int(time.time())}"
            
            checkout_currency = currency
            checkout_amount = float(donation.amount)

            if checkout_currency == "USD":
                # Convert USD to NGN for Flutterwave
                checkout_currency = "NGN"
                rate = float(self.base.get_ngn_rate())
                checkout_amount = round(checkout_amount * rate, 2)
                print(f"🟡 [DONATION] Converted USD {donation.amount} to NGN {checkout_amount} at rate {rate}")

            payment_data = {
                "tx_ref": tx_ref,
                "amount": str(checkout_amount),
                "currency": checkout_currency,
                "redirect_url": url_for("payments.payment_callback", _external=True),
                "customer": {
                    "email": donation.email,
                    "name": donation.name or donation.email.split("@")[0],
                },
                "meta": {
                    "donation_id": donation.id,
                    "transaction_type": "donation",
                },
                "customizations": {
                    "title": "Kimbela Donation",
                    "description": f"Donation to Kimbela",
                    "logo": url_for("static", filename="images/logo.png", _external=True),
                },
            }

            headers = {
                "Authorization": f"Bearer {self.FLW_SECRET_KEY}",
                "Content-Type": "application/json",
            }

            print(f"🟡 [DONATION] Sending request to Flutterwave...")

            response = self._http_request(
                "POST",
                f"{self.flutterwave_base_url}/payments",
                headers=headers,
                json=payment_data,
                timeout=30,
            )

            if response.status_code == 200:
                result = response.json()
                if result.get("status") == "success":
                    payment_url = result["data"]["link"]
                    print(f"✅ [DONATION] Payment URL generated: {payment_url}")

                    # Update donation record
                    donation.gateway_reference = tx_ref
                    donation.gateway_payment_id = str(result["data"].get("id") or "")
                    donation.gateway = "flutterwave"
                    db.session.commit()

                    return {
                        "success": True,
                        "payment_url": payment_url,
                        "gateway_payment_id": tx_ref,
                        "message": "Donation payment initiated successfully",
                    }
                else:
                    error_msg = result.get("message", "Unknown Flutterwave error")
                    return {"success": False, "error": f"Payment gateway error: {error_msg}"}
            else:
                return {"success": False, "error": f"Payment gateway returned error: {response.status_code}"}

        except Exception as e:
            print(f"🔴 [DONATION] Exception: {str(e)}")
            return {"success": False, "error": f"Payment processing error: {str(e)}"}

    def handle_donation_payment_success(self, tx_ref, payment_data=None):
        """Handle successful donation payment"""
        try:
            donation = Donation.query.filter_by(gateway_reference=tx_ref).first()
            if not donation:
                return False

            donation.status = "completed"
            if payment_data and payment_data.get("id"):
                donation.gateway_payment_id = str(payment_data.get("id"))
            donation.updated_at = utcnow()
            db.session.commit()
            print(f"✅ [DONATION SUCCESS] Donation {donation.id} marked as completed.")
            return True
        except Exception as e:
            db.session.rollback()
            print(f"🔴 [DONATION SUCCESS] Exception: {str(e)}")
            return False

    def handle_donation_payment_failure(self, tx_ref, payment_data=None):
        """Handle failed donation payment"""
        try:
            donation = Donation.query.filter_by(gateway_reference=tx_ref).first()
            if not donation:
                return False

            gateway_status = payment_data.get("status", "failed") if payment_data else "failed"
            if self.base.is_success_status(gateway_status) or self.base.is_pending_status(gateway_status):
                return True

            donation.status = "failed"
            donation.updated_at = utcnow()
            db.session.commit()
            print(f"🔴 [DONATION FAILURE] Donation {donation.id} marked as failed.")
            return True
        except Exception as e:
            db.session.rollback()
            print(f"🔴 [DONATION FAILURE] Exception: {str(e)}")
            return False
