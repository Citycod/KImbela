import requests as http_requests
import json
import socket
from flask import current_app, url_for
from requests.exceptions import (
    ConnectionError as RequestsConnectionError,
    RequestException,
    Timeout,
)
from extensions import db
from models import (
    PaymentTransaction,
    AdCampaign,
    User,
    MatchmakingRequest,
    MatchmakingPackage,
)
import logging
import os, time
from .payment_service_ad import AdCampaignPaymentService
from datetime import datetime, timedelta
from extensions import mail
from resend_mail import Message
from models import (
    PaymentTransaction,
    AdCampaign,
    User,
    MatchmakingRequest,
    MatchmakingPackage,
    MatchmakingPayments,
    MarketplacePayment,
)
from .email_service import MarketplaceEmailService


from time_utils import utcnow
logger = logging.getLogger(__name__)


class UpstreamServiceError(Exception):
    """Transient upstream/network failure while calling a payment provider."""

    pass


class BasePaymentService:
    """Base payment service with common functionality"""

    def __init__(self):
        # Use the correct environment variable names that actually exist
        self.flutterwave_public_key = os.getenv("FLW_PUBLIC_KEY")
        self.flutterwave_secret_key = os.getenv("FLW_SECRET_KEY")
        self.flutterwave_base_url = "https://api.flutterwave.com/v3"

        print(
            f"🟡 [BASE PAYMENT INIT] Public Key configured: {self.flutterwave_public_key is not None}"
        )
        print(
            f"🟡 [BASE PAYMENT INIT] Secret Key configured: {self.flutterwave_secret_key is not None}"
        )

        if self.flutterwave_public_key:
            print(
                f"🟡 [BASE PAYMENT INIT] Public Key: {self.flutterwave_public_key[:20]}..."
            )
        if self.flutterwave_secret_key:
            print(
                f"🟡 [BASE PAYMENT INIT] Secret Key: {self.flutterwave_secret_key[:20]}..."
            )

    def _http_request(self, method, url, **kwargs):
        """HTTP request wrapper with retries for transient upstream failures."""
        import requests as http_requests

        method_func = getattr(http_requests, method.lower())
        kwargs.setdefault("timeout", 30)

        max_attempts = 4
        last_error = None

        for attempt in range(1, max_attempts + 1):
            try:
                response = method_func(url, **kwargs)

                if response.status_code in {429, 502, 503, 504}:
                    last_error = RuntimeError(
                        f"HTTP {response.status_code} from upstream service"
                    )
                    logger.warning(
                        "Transient upstream HTTP status calling %s %s (attempt %s/%s): %s",
                        method.upper(),
                        url,
                        attempt,
                        max_attempts,
                        response.status_code,
                    )
                    if attempt == max_attempts:
                        break
                    time.sleep(min(0.75 * attempt, 2.5))
                    continue

                return response
            except (RequestsConnectionError, Timeout, RequestException, socket.gaierror) as exc:
                if not self._is_transient_network_error(exc):
                    raise
                last_error = exc
                logger.warning(
                    "Transient upstream error calling %s %s (attempt %s/%s): %s",
                    method.upper(),
                    url,
                    attempt,
                    max_attempts,
                    exc,
                )
                if attempt == max_attempts:
                    break
                time.sleep(min(0.75 * attempt, 2.5))

        raise UpstreamServiceError(
            f"Unable to reach upstream payment service after {max_attempts} attempts: {self._describe_network_error(last_error)}"
        ) from last_error

    @staticmethod
    def _is_transient_network_error(exc):
        message = str(exc).lower()
        transient_markers = (
            "name resolution",
            "failed to resolve",
            "temporary failure in name resolution",
            "lookup timed out",
            "dns",
            "max retries exceeded",
            "connection aborted",
            "connection reset",
            "connection refused",
            "timed out",
            "timeout",
            "enetunreach",
            "network is unreachable",
            "ehostunreach",
            "host is unreachable",
            "remote end closed connection",
            "503",
            "502",
            "504",
            "429",
        )
        return isinstance(
            exc, (RequestsConnectionError, Timeout, socket.gaierror)
        ) or any(marker in message for marker in transient_markers)

    @staticmethod
    def _describe_network_error(exc):
        if exc is None:
            return "unknown upstream error"

        message = str(exc)
        normalized = message.lower()
        if "failed to resolve" in normalized or "lookup timed out" in normalized:
            return "DNS lookup failed while contacting the upstream service"
        if "enetunreach" in normalized or "network is unreachable" in normalized:
            return "network route to the upstream service was unavailable"
        if "timed out" in normalized or "timeout" in normalized:
            return "request to the upstream service timed out"
        return message

    def verify_flutterwave_payment(self, transaction_id):
        """Verify Flutterwave payment using transaction ID"""
        try:
            headers = {
                "Authorization": f"Bearer {self.flutterwave_secret_key}",
                "Content-Type": "application/json",
            }

            response = self._http_request(
                "GET",
                f"{self.flutterwave_base_url}/transactions/{transaction_id}/verify",
                headers=headers,
                timeout=30,
            )

            print(f"🟡 [VERIFY PAYMENT] Response status: {response.status_code}")

            if response.status_code == 200:
                result = response.json()
                print(f"🟡 [VERIFY PAYMENT] Verification result: {result}")
                return {
                    "success": result.get("status") == "success",
                    "data": result.get("data", {}),
                }

            print(
                f"🔴 [VERIFY PAYMENT] HTTP Error: {response.status_code} - {response.text}"
            )
            return {
                "success": False,
                "error": f"HTTP {response.status_code}",
                "data": {},
            }

        except Exception as e:
            print(f"🔴 [VERIFY PAYMENT] Exception: {str(e)}")
            return {"success": False, "error": str(e), "data": {}}

    def _send_email(self, subject, recipient, html_body):
        """Helper method to send emails"""
        try:
            msg = Message(
                subject=subject,
                recipients=[recipient],
                html=html_body,
                sender=current_app.config.get("MAIL_DEFAULT_SENDER"),
            )
            mail.send(msg)
            print(f"✅ [EMAIL] Sent to {recipient}")
            return True
        except Exception as e:
            print(f"❌ [EMAIL] Failed to send: {str(e)}")
            return False


class MatchmakingPaymentService(BasePaymentService):
    """Payment service specifically for matchmaking requests"""

    def __init__(self):
        super().__init__()
        self._validate_keys()

    def _validate_keys(self):
        """Validate that Flutterwave keys are properly configured"""
        print(
            f"🔑 [KEY VALIDATION] Public Key: {'✅ SET' if self.flutterwave_public_key else '❌ MISSING'}"
        )
        print(
            f"🔑 [KEY VALIDATION] Secret Key: {'✅ SET' if self.flutterwave_secret_key else '❌ MISSING'}"
        )

        if not self.flutterwave_secret_key:
            raise ValueError("Flutterwave secret key is not configured")

        # Test key format (Flutterwave keys typically start with specific prefixes)
        if self.flutterwave_secret_key and not self.flutterwave_secret_key.startswith(
            ("FLWSECK-", "FLWSECK_TEST-")
        ):
            print("⚠️ [KEY VALIDATION] Secret key format may be incorrect")

        if self.flutterwave_public_key and not self.flutterwave_public_key.startswith(
            ("FLWPUBK-", "FLWPUBK_TEST-")
        ):
            print("⚠️ [KEY VALIDATION] Public key format may be incorrect")

        print(f"✅ [KEY VALIDATION] Keys validated successfully")

    def create_matchmaking_payment(
        self, user, matchmaking_request, package, currency="USD", amount=None
    ):
        """Create Flutterwave payment for matchmaking request"""
        try:
            print(f"🟡 [MATCHMAKING PAYMENT] Starting payment process")
            print(
                f"🟡 [MATCHMAKING PAYMENT] User: {user.id}, Request: {matchmaking_request.id}, Package: {package.name}"
            )

            # Use provided amount or fallback to package price
            payment_amount = amount if amount is not None else package.price

            # Generate unique transaction reference
            tx_ref = f"KIMBELA_MATCH_{matchmaking_request.id}_{int(time.time())}"

            # Prepare payment data for matchmaking
            payment_data = {
                "tx_ref": tx_ref,
                "amount": str(float(payment_amount)),
                "currency": currency,
                "redirect_url": url_for("match.payment_callback", _external=True),
                "customer": {
                    "email": user.email,
                    "name": user.full_name
                    or user.first_name
                    or user.email.split("@")[0],
                },
                "meta": {
                    "user_id": user.id,
                    "matchmaking_request_id": matchmaking_request.id,
                    "package_id": package.id,
                    "transaction_type": "matchmaking",
                },
                "customizations": {
                    "title": "Kimbela Matchmaking",
                    "description": f"Matchmaking Package: {package.name}",
                },
            }

            # Add phone number if available
            if hasattr(user, "phone_number") and user.phone_number:
                payment_data["customer"]["phone_number"] = user.phone_number

            headers = {
                "Authorization": f"Bearer {self.flutterwave_secret_key}",
                "Content-Type": "application/json",
            }

            print(f"🟡 [MATCHMAKING PAYMENT] Sending request to Flutterwave...")
            print(
                f"🟡 [MATCHMAKING PAYMENT] Using Secret Key: {self.flutterwave_secret_key[:20]}..."
            )
            print(
                f"🟡 [MATCHMAKING PAYMENT] Request data: {json.dumps(payment_data, indent=2)}"
            )

            response = self._http_request(
                "POST",
                f"{self.flutterwave_base_url}/payments",
                headers=headers,
                json=payment_data,
                timeout=30,
            )

            print(f"🟡 [MATCHMAKING PAYMENT] Response status: {response.status_code}")
            print(
                f"🟡 [MATCHMAKING PAYMENT] Response headers: {dict(response.headers)}"
            )

            if response.status_code == 200:
                result = response.json()
                print(
                    f"🟡 [MATCHMAKING PAYMENT] Flutterwave response: {json.dumps(result, indent=2)}"
                )

                if result.get("status") == "success":
                    payment_url = result["data"]["link"]
                    print(
                        f"✅ [MATCHMAKING PAYMENT] Payment URL generated: {payment_url}"
                    )

                    # Create matchmaking payment record
                    matchmaking_payment = MatchmakingPayments(
                        user_id=user.id,
                        matchmaking_request_id=matchmaking_request.id,
                        package_id=package.id,
                        amount=package.price,
                        currency=currency,
                        gateway="flutterwave",
                        gateway_reference=tx_ref,
                        gateway_payment_id=result["data"].get("id"),
                        gateway_status="initiated",
                        status="pending",
                        payment_status="pending",
                        description=f"Matchmaking Package: {package.name}",
                    )
                    db.session.add(matchmaking_payment)
                    db.session.commit()

                    return {
                        "success": True,
                        "payment_url": payment_url,
                        "payment_id": matchmaking_payment.id,
                        "gateway_reference": tx_ref,
                        "message": "Matchmaking payment initiated successfully",
                    }
                else:
                    error_msg = result.get("message", "Unknown Flutterwave error")
                    print(f"🔴 [MATCHMAKING PAYMENT] Flutterwave error: {error_msg}")
                    return {
                        "success": False,
                        "error": f"Payment gateway error: {error_msg}",
                    }
            else:
                error_text = response.text
                print(
                    f"🔴 [MATCHMAKING PAYMENT] HTTP error {response.status_code}: {error_text}"
                )

                # More specific error handling
                if response.status_code == 401:
                    return {
                        "success": False,
                        "error": "Invalid Flutterwave API keys. Please check your environment variables.",
                    }
                elif response.status_code == 400:
                    try:
                        error_data = response.json()
                        return {
                            "success": False,
                            "error": f'Bad request: {error_data.get("message", "Unknown error")}',
                        }
                    except:
                        return {"success": False, "error": f"Bad request: {error_text}"}
                else:
                    return {
                        "success": False,
                        "error": f"Payment gateway returned error: {response.status_code}",
                    }

        except Exception as e:
            print(f"🔴 [MATCHMAKING PAYMENT] Exception: {str(e)}")
            import traceback

            print(f"🔴 [MATCHMAKING PAYMENT] Traceback: {traceback.format_exc()}")
            return {"success": False, "error": f"Payment processing error: {str(e)}"}

    def handle_matchmaking_payment_success(self, matchmaking_payment, flutterwave_data):
        """Handle successful matchmaking payment"""
        try:
            print(
                f"🟡 [PAYMENT SUCCESS] Starting to handle successful payment for payment ID: {matchmaking_payment.id}"
            )

            # Update matchmaking payment record
            matchmaking_payment.status = "completed"
            matchmaking_payment.payment_status = "paid"
            matchmaking_payment.gateway_status = flutterwave_data.get(
                "status", "successful"
            )
            matchmaking_payment.gateway_payment_id = flutterwave_data.get("id")
            matchmaking_payment.gateway_metadata = json.dumps(flutterwave_data)
            matchmaking_payment.paid_at = utcnow()
            matchmaking_payment.updated_at = utcnow()

            print(
                f"🟡 [PAYMENT SUCCESS] Updated payment record: {matchmaking_payment.to_dict()}"
            )

            # Get matchmaking request
            matchmaking_request = matchmaking_payment.matchmaking_request
            if not matchmaking_request:
                print(
                    f"🔴 [PAYMENT SUCCESS] No matchmaking request found for payment {matchmaking_payment.id}"
                )
                return False

            print(
                f"🟡 [PAYMENT SUCCESS] Found matchmaking request: {matchmaking_request.id}"
            )

            # Update matchmaking request
            matchmaking_request.payment_status = "completed"
            matchmaking_request.status = "active"
            matchmaking_request.payment_gateway = "flutterwave"

            # Calculate end date based on package duration
            if matchmaking_request.package:
                duration_days = matchmaking_request.package.duration_days
                matchmaking_request.end_date = utcnow() + timedelta(
                    days=duration_days
                )
                print(
                    f"🟡 [PAYMENT SUCCESS] Set end date to: {matchmaking_request.end_date}"
                )

            matchmaking_request.updated_at = utcnow()

            db.session.commit()
            print(f"✅ [PAYMENT SUCCESS] Database committed successfully")

            # Send success email
            email_sent = self.send_matchmaking_payment_success_email(
                matchmaking_payment.user_id, matchmaking_request, matchmaking_payment
            )

            print(f"🟡 [PAYMENT SUCCESS] Email sent: {email_sent}")

            return True

        except Exception as e:
            db.session.rollback()
            print(f"🔴 [PAYMENT SUCCESS] Exception: {str(e)}")
            import traceback

            print(f"🔴 [PAYMENT SUCCESS] Traceback: {traceback.format_exc()}")
            return False

    def handle_matchmaking_payment_failure(self, matchmaking_payment, flutterwave_data):
        """Handle failed matchmaking payment"""
        try:
            # Update matchmaking payment record
            matchmaking_payment.status = "failed"
            matchmaking_payment.payment_status = "failed"
            matchmaking_payment.gateway_status = flutterwave_data.get(
                "status", "failed"
            )
            matchmaking_payment.gateway_metadata = json.dumps(flutterwave_data)
            matchmaking_payment.updated_at = utcnow()

            # Update matchmaking request
            matchmaking_request = matchmaking_payment.matchmaking_request
            if matchmaking_request:
                matchmaking_request.payment_status = "failed"
                matchmaking_request.status = "pending"
                matchmaking_request.updated_at = utcnow()

            db.session.commit()

            # Send failure email
            self.send_matchmaking_payment_failed_email(
                matchmaking_payment.user_id, matchmaking_request, matchmaking_payment
            )

            return True

        except Exception as e:
            db.session.rollback()
            return False

    def get_payment_by_reference(self, gateway_reference):
        """Get matchmaking payment by gateway reference"""
        return MatchmakingPayments.query.filter_by(
            gateway_reference=gateway_reference
        ).first()

    def get_payment_by_id(self, payment_id):
        """Get matchmaking payment by ID"""
        return MatchmakingPayments.query.get(payment_id)

    def get_user_payments(self, user_id):
        """Get all matchmaking payments for a user"""
        return (
            MatchmakingPayments.query.filter_by(user_id=user_id)
            .order_by(MatchmakingPayments.created_at.desc())
            .all()
        )

    def get_payment_by_gateway_id(self, gateway_payment_id):
        """Get matchmaking payment by gateway payment ID"""
        return MatchmakingPayments.query.filter_by(
            gateway_payment_id=gateway_payment_id
        ).first()

    def send_matchmaking_payment_success_email(
        self, user_id, matchmaking_request, payment
    ):
        """Send payment success email for matchmaking"""
        try:
            user = User.query.get(user_id)
            if not user:
                return False

            expiry_date = (
                matchmaking_request.end_date.strftime("%B %d, %Y")
                if matchmaking_request.end_date
                else "Not set"
            )
            package_name = (
                matchmaking_request.package.name
                if matchmaking_request.package
                else "Standard"
            )
            duration_days = (
                matchmaking_request.package.duration_days
                if matchmaking_request.package
                else 30
            )

            subject = "💖 Your Kimbela Matchmaking Request is Active!"

            html_body = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background: linear-gradient(135deg, #B76E79 0%, #DCAE96 100%); color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0; }}
                    .content {{ background: #fdf6f0; padding: 20px; border-radius: 0 0 10px 10px; }}
                    .details {{ background: white; padding: 15px; border-radius: 5px; margin: 10px 0; border-left: 4px solid #B76E79; }}
                    .footer {{ text-align: center; margin-top: 20px; color: #666; font-size: 12px; }}
                    .heart {{ color: #B76E79; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>💖 Matchmaking Request Activated!</h1>
                        <p>Your journey to find meaningful connections begins now</p>
                    </div>
                    <div class="content">
                        <p>Hello {user.full_name},</p>
                        <p>Wonderful news! Your matchmaking request has been successfully activated and is now visible to potential matches on Kimbela.</p>
                        
                        <div class="details">
                            <h3>📋 Request Details</h3>
                            <p><strong>Package:</strong> {package_name}</p>
                            <p><strong>Total Amount:</strong> {payment.amount:.2f} {payment.currency}</p>
                            <p><strong>Duration:</strong> {duration_days} days</p>
                            <p><strong>Start Date:</strong> {matchmaking_request.created_at.strftime('%B %d, %Y')}</p>
                            <p><strong>Expiry Date:</strong> {expiry_date}</p>
                        </div>
                        
                        <div class="details">
                            <h3>✨ What's Next?</h3>
                            <p><span class="heart">❤️</span> Your profile is now visible to compatible matches</p>
                            <p><span class="heart">❤️</span> Receive likes and messages from interested users</p>
                            <p><span class="heart">❤️</span> Browse through potential matches in your criteria</p>
                            <p><span class="heart">❤️</span> Build meaningful connections with like-minded people</p>
                        </div>
                        
                        <div class="details">
                            <h3>💌 Tips for Success</h3>
                            <p>• Keep your profile updated with recent photos</p>
                            <p>• Be responsive to messages and likes</p>
                            <p>• Be genuine in your interactions</p>
                            <p>• Don't hesitate to make the first move!</p>
                        </div>
                        
                        <p>Ready to start connecting? <a href="{current_app.config.get('BASE_URL', 'http://localhost:5000')}/view_requests" style="color: #B76E79; font-weight: bold;">View your matches now</a></p>
                        
                        <p>Wishing you the best in your journey to find love,<br>The Kimbela Matchmaking Team</p>
                    </div>
                    <div class="footer">
                        <p>© 2024 Kimbela Matchmaking. Connecting hearts worldwide.</p>
                    </div>
                </div>
            </body>
            </html>
            """

            return self._send_email(subject, user.email, html_body)

        except Exception as e:
            print(f"❌ Failed to send matchmaking success email: {str(e)}")
            return False

    def send_matchmaking_payment_failed_email(
        self, user_id, matchmaking_request, payment
    ):
        """Send payment failure email for matchmaking"""
        try:
            user = User.query.get(user_id)
            if not user:
                return False

            subject = "❌ Payment Failed - Kimbela Matchmaking Request"

            html_body = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background: #dc3545; color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0; }}
                    .content {{ background: #fdf6f0; padding: 20px; border-radius: 0 0 10px 10px; }}
                    .footer {{ text-align: center; margin-top: 20px; color: #666; font-size: 12px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>❌ Matchmaking Payment Failed</h1>
                        <p>We couldn't process your matchmaking request payment</p>
                    </div>
                    <div class="content">
                        <p>Hello {user.full_name},</p>
                        <p>We were unable to process the payment for your matchmaking request. Your request has been saved but will not be activated until payment is completed.</p>
                        
                        <p><strong>Package:</strong> {matchmaking_request.package.name if matchmaking_request.package else 'Standard'}</p>
                        <p><strong>Amount:</strong> {payment.amount:.2f} {payment.currency}</p>
                        
                        <p>You can retry the payment from your <a href="{current_app.config.get('BASE_URL', 'http://localhost:5000')}/requests" style="color: #B76E79; font-weight: bold;">matchmaking dashboard</a> or try a different payment method.</p>
                        
                        <div style="background: #fff3cd; padding: 15px; border-radius: 5px; margin: 15px 0; border-left: 4px solid #ffc107;">
                            <h4 style="margin-top: 0; color: #856404;">💡 Need Help?</h4>
                            <p style="margin-bottom: 0; color: #856404;">
                                If you're experiencing payment issues, please:
                                <br>• Check your payment method details
                                <br>• Ensure sufficient funds are available
                                <br>• Try a different payment method
                                <br>• Contact our support team for assistance
                            </p>
                        </div>
                        
                        <p>Don't let this setback stop your journey to finding meaningful connections. We're here to help you get started!</p>
                        
                        <p>Best regards,<br>The Kimbela Matchmaking Team</p>
                    </div>
                    <div class="footer">
                        <p>© 2024 Kimbela Matchmaking. Connecting hearts worldwide.</p>
                    </div>
                </div>
            </body>
            </html>
            """

            return self._send_email(subject, user.email, html_body)

        except Exception as e:
            print(f"❌ Failed to send matchmaking failure email: {str(e)}")
            return False

    def retry_payment(self, payment_id, currency="USD"):
        """Retry a failed matchmaking payment"""
        try:
            matchmaking_payment = self.get_payment_by_id(payment_id)
            if not matchmaking_payment:
                return {"success": False, "error": "Payment not found"}

            # Get related objects
            user = User.query.get(matchmaking_payment.user_id)
            matchmaking_request = MatchmakingRequest.query.get(
                matchmaking_payment.matchmaking_request_id
            )
            package = MatchmakingPackage.query.get(matchmaking_payment.package_id)

            if not all([user, matchmaking_request, package]):
                return {"success": False, "error": "Missing payment details"}

            # Generate new transaction reference
            tx_ref = f"KIMBELA_MATCH_RETRY_{matchmaking_request.id}_{int(time.time())}"

            # Prepare payment data
            payment_data = {
                "tx_ref": tx_ref,
                "amount": str(float(package.price)),
                "currency": currency,
                "redirect_url": url_for("match.payment_callback", _external=True),
                "customer": {
                    "email": user.email,
                    "name": user.full_name
                    or user.first_name
                    or user.email.split("@")[0],
                },
                "meta": {
                    "user_id": user.id,
                    "matchmaking_request_id": matchmaking_request.id,
                    "package_id": package.id,
                    "transaction_type": "matchmaking_retry",
                },
                "customizations": {
                    "title": "Kimbela Matchmaking",
                    "description": f"Matchmaking Package: {package.name} (Retry)",
                },
            }

            headers = {
                "Authorization": f"Bearer {self.flutterwave_secret_key}",
                "Content-Type": "application/json",
            }

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

                    # Update the existing payment record for retry
                    matchmaking_payment.gateway_reference = tx_ref
                    matchmaking_payment.gateway_payment_id = result["data"].get("id")
                    matchmaking_payment.gateway_status = "retry_initiated"
                    matchmaking_payment.status = "pending"
                    matchmaking_payment.payment_status = "pending"
                    matchmaking_payment.updated_at = utcnow()

                    db.session.commit()

                    return {
                        "success": True,
                        "payment_url": payment_url,
                        "payment_id": matchmaking_payment.id,
                        "gateway_reference": tx_ref,
                        "message": "Payment retry initiated successfully",
                    }
                else:
                    error_msg = result.get("message", "Unknown Flutterwave error")
                    return {
                        "success": False,
                        "error": f"Payment gateway error: {error_msg}",
                    }
            else:
                return {
                    "success": False,
                    "error": f"Payment gateway returned error: {response.status_code}",
                }

        except Exception as e:
            return {"success": False, "error": f"Payment retry error: {str(e)}"}


class PaymentService:
    """Legacy payment service for backward compatibility"""

    def __init__(self):
        self.ad_service = AdCampaignPaymentService()
        self.matchmaking_service = MatchmakingPaymentService()
        self.marketplace_service = MarketplacePaymentService()

    def create_marketplace_payment(self, user, plan, currency="USD"):
        """Create payment for marketplace subscription"""
        return self.marketplace_service.create_marketplace_payment(
            user=user, plan=plan, currency=currency
        )

    def handle_marketplace_payment_success(self, transaction_id, payment_data):
        """Handle successful marketplace payment"""
        transaction = PaymentTransaction.query.get(transaction_id)
        if not transaction:
            return False

        return self.marketplace_service.handle_marketplace_payment_success(
            transaction=transaction, flutterwave_data=payment_data
        )

    def create_flutterwave_transaction(
        self, user, campaign=None, amount=0, currency="USD", request_id=None
    ):
        """Legacy method - redirect to appropriate service"""
        if request_id:
            # This is a matchmaking payment
            matchmaking_request = MatchmakingRequest.query.get(request_id)
            if matchmaking_request and matchmaking_request.package:
                return self.matchmaking_service.create_matchmaking_payment(
                    user=user,
                    matchmaking_request=matchmaking_request,
                    package=matchmaking_request.package,
                    currency=currency,
                    amount=amount,
                )
        else:
            # This is an ad campaign payment
            if campaign:
                return self.ad_service.create_ad_campaign_payment(
                    user=user, campaign=campaign, currency=currency
                )

        return {"success": False, "error": "Invalid payment request"}

    def handle_successful_payment(self, transaction_id, payment_data=None):
        """Legacy method - redirect to appropriate service"""
        transaction = PaymentTransaction.query.get(transaction_id)
        if not transaction:
            return False

        if transaction.transaction_type == "ad_campaign":
            return self.ad_service.handle_ad_payment_success(
                transaction_id, payment_data
            )
        elif transaction.transaction_type == "matchmaking":
            return self.matchmaking_service.handle_matchmaking_payment_success(
                self.matchmaking_service.get_payment_by_gateway_id(
                    transaction.gateway_payment_id
                ),
                payment_data,
            )
        return False

    def handle_failed_payment(self, transaction_id, payment_data=None):
        """Legacy method - redirect to appropriate service"""
        transaction = PaymentTransaction.query.get(transaction_id)
        if not transaction:
            return False

        if transaction.transaction_type == "ad_campaign":
            return self.ad_service.handle_ad_payment_failure(
                transaction_id, payment_data
            )
        elif transaction.transaction_type == "matchmaking":
            return self.matchmaking_service.handle_matchmaking_payment_failure(
                self.matchmaking_service.get_payment_by_gateway_id(
                    transaction.gateway_payment_id
                ),
                payment_data,
            )
        return False


class MarketplacePaymentService(BasePaymentService):

    def __init__(self):
        super().__init__()
        self.email_service = None  # Will be created when needed

    def _get_email_service(self):
        """Get or create email service"""
        if self.email_service is None:
            from .email_service import MarketplaceEmailService

            self.email_service = MarketplaceEmailService()
        return self.email_service

    """Payment service for marketplace subscriptions"""

    def create_marketplace_payment(self, user, plan, currency="USD"):
        """Create Flutterwave payment for marketplace subscription - FIXED VERSION"""
        try:
            print(f"🟡 [MARKETPLACE PAYMENT] Starting payment for plan: {plan.name}")
            print(
                f"🟡 [MARKETPLACE PAYMENT] User: {user.id}, Amount: ${plan.price} {currency}"
            )

            # Generate transaction reference
            import time

            tx_ref = f"KIMBELA_MARKET_{user.id}_{int(time.time())}"
            payment_amount = plan.price

            print(f"🟡 [MARKETPLACE PAYMENT] TX Ref: {tx_ref}")
            print(f"🟡 [MARKETPLACE PAYMENT] Amount: ${payment_amount}")

            # Prepare payment data
            payment_data = {
                "tx_ref": tx_ref,
                "amount": str(float(payment_amount)),
                "currency": currency,
                "redirect_url": url_for("market.subscription_callback", _external=True),
                "customer": {
                    "email": user.email,
                    "name": user.full_name
                    or user.first_name
                    or user.email.split("@")[0],
                },
                "meta": {
                    "user_id": user.id,
                    "plan_id": plan.id,
                    "plan_name": plan.name,
                    "transaction_type": "marketplace_subscription",
                },
                "customizations": {
                    "title": "Kimbela Marketplace",
                    "description": f"Subscription Plan: {plan.name}",
                },
            }

            # Add phone number if available
            if hasattr(user, "phone_number") and user.phone_number:
                payment_data["customer"]["phone_number"] = user.phone_number

            headers = {
                "Authorization": f"Bearer {self.flutterwave_secret_key}",
                "Content-Type": "application/json",
            }

            print(f"🟡 [MARKETPLACE PAYMENT] Sending request to Flutterwave...")
            print(f"🟡 [MARKETPLACE PAYMENT] URL: {self.flutterwave_base_url}/payments")
            print(f"🟡 [MARKETPLACE PAYMENT] Headers: {headers}")

            # Make the request
            response = self._http_request(
                "POST",
                f"{self.flutterwave_base_url}/payments",
                headers=headers,
                json=payment_data,
                timeout=30,
            )

            print(f"🟡 [MARKETPLACE PAYMENT] Response status: {response.status_code}")
            print(
                f"🟡 [MARKETPLACE PAYMENT] Response headers: {dict(response.headers)}"
            )

            # Parse response
            response_text = response.text
            print(f"🟡 [MARKETPLACE PAYMENT] Response text: {response_text[:500]}...")

            if response.status_code == 200:
                try:
                    result = response.json()
                    print(f"🟡 [MARKETPLACE PAYMENT] Parsed JSON: {result}")

                    if result.get("status") == "success":
                        payment_url = result["data"]["link"]
                        print(
                            f"✅ [MARKETPLACE PAYMENT] Payment URL generated: {payment_url}"
                        )

                        # Create MarketplacePayment record
                        marketplace_payment = MarketplacePayment(
                            user_id=user.id,
                            subscription_id=plan.id,
                            amount=payment_amount,
                            currency=currency,
                            tokens_paid=int(payment_amount * 100),
                            gateway="flutterwave",
                            gateway_reference=tx_ref,
                            gateway_payment_id=result["data"].get("id"),
                            gateway_status="initiated",
                            gateway_metadata=json.dumps(result.get("data", {})),
                            status="pending",
                            payment_method="card",
                            description=f"Marketplace Subscription: {plan.name}",
                            start_date=utcnow(),
                            end_date=utcnow()
                            + timedelta(days=getattr(plan, "duration_days", 30)),
                        )

                        db.session.add(marketplace_payment)
                        db.session.commit()

                        print(
                            f"✅ [MARKETPLACE PAYMENT] Payment record created: {marketplace_payment.id}"
                        )

                        return {
                            "success": True,
                            "payment_url": payment_url,
                            "payment_id": marketplace_payment.id,
                            "gateway_reference": tx_ref,
                            "message": "Marketplace subscription payment initiated successfully",
                        }
                    else:
                        error_msg = result.get("message", "Unknown Flutterwave error")
                        print(
                            f"🔴 [MARKETPLACE PAYMENT] Flutterwave error: {error_msg}"
                        )
                        return {
                            "success": False,
                            "error": f"Payment gateway error: {error_msg}",
                        }

                except json.JSONDecodeError as e:
                    print(f"🔴 [MARKETPLACE PAYMENT] Failed to parse JSON: {e}")
                    print(f"🔴 [MARKETPLACE PAYMENT] Raw response: {response_text}")
                    return {
                        "success": False,
                        "error": f"Invalid response from payment gateway: {response_text[:200]}",
                    }
            else:
                error_text = (
                    response.text[:500]
                    if hasattr(response, "text")
                    else "No response text"
                )
                print(
                    f"🔴 [MARKETPLACE PAYMENT] HTTP error {response.status_code}: {error_text}"
                )
                return {
                    "success": False,
                    "error": f"Payment gateway returned error: {response.status_code} - {error_text}",
                }

        except Exception as e:
            print(f"🔴 [MARKETPLACE PAYMENT] Exception: {str(e)}")
            import traceback

            print(f"🔴 [MARKETPLACE PAYMENT] Traceback:\n{traceback.format_exc()}")
            if isinstance(e, UpstreamServiceError):
                return {
                    "success": False,
                    "error": "Payment provider is temporarily unreachable. Please try again in a moment.",
                    "error_type": "upstream_unavailable",
                }
            return {"success": False, "error": f"Payment processing error: {str(e)}"}

    def handle_marketplace_payment_success(self, marketplace_payment, flutterwave_data):
        """Handle successful marketplace payment"""
        try:
            print(
                f"🟡 [PAYMENT SUCCESS] Starting to handle successful payment for payment ID: {marketplace_payment.id}"
            )

            # Update marketplace payment record
            marketplace_payment.status = "completed"
            marketplace_payment.gateway_status = flutterwave_data.get(
                "status", "successful"
            )
            marketplace_payment.gateway_payment_id = flutterwave_data.get("id")
            marketplace_payment.gateway_metadata = json.dumps(flutterwave_data)
            marketplace_payment.paid_at = utcnow()
            marketplace_payment.updated_at = utcnow()

            print(
                f"🟡 [PAYMENT SUCCESS] Updated payment record: {marketplace_payment.id}"
            )

            # Update user subscription
            user = marketplace_payment.user
            if user:
                user.marketplace_subscription_id = marketplace_payment.subscription_id
                user.marketplace_subscription_status = "active"
                user.marketplace_subscription_expires = utcnow() + timedelta(
                    days=30
                )  # Adjust as needed

                # Set featured until date if plan includes featured status
                # You might need to check the subscription plan details

                print(f"✅ [PAYMENT SUCCESS] User subscription updated: {user.id}")

            db.session.commit()
            print(f"✅ [PAYMENT SUCCESS] Database committed successfully")

            # Send success email
            self.send_marketplace_payment_success_email(marketplace_payment)

            return True

        except Exception as e:
            db.session.rollback()
            print(f"🔴 [PAYMENT SUCCESS] Exception: {str(e)}")
            import traceback

            print(f"🔴 [PAYMENT SUCCESS] Traceback: {traceback.format_exc()}")
            return False

    def send_marketplace_payment_success_email(self, transaction):
        """Send payment success email for marketplace subscription"""
        try:
            user = transaction.user
            if not user:
                return False

            # Parse plan info from meta
            meta_data = (
                json.loads(transaction.meta_data) if transaction.meta_data else {}
            )
            meta = meta_data.get("meta", {})
            plan_name = meta.get("plan_name", "Marketplace Subscription")

            subject = "🎉 Your Kimbela Marketplace Subscription is Active!"

            html_body = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background: linear-gradient(135deg, #D97706 0%, #FBBF24 100%); color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0; }}
                    .content {{ background: #FFFBEB; padding: 20px; border-radius: 0 0 10px 10px; }}
                    .details {{ background: white; padding: 15px; border-radius: 5px; margin: 10px 0; border-left: 4px solid #D97706; }}
                    .footer {{ text-align: center; margin-top: 20px; color: #666; font-size: 12px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>🎉 Welcome to Kimbela Marketplace!</h1>
                        <p>Your seller subscription is now active</p>
                    </div>
                    <div class="content">
                        <p>Hello {user.full_name},</p>
                        <p>Congratulations! Your Kimbela Marketplace subscription has been successfully activated. You can now start selling your services and digital products.</p>
                        
                        <div class="details">
                            <h3>📋 Subscription Details</h3>
                            <p><strong>Plan:</strong> {plan_name}</p>
                            <p><strong>Amount Paid:</strong> {transaction.amount:.2f} {transaction.currency}</p>
                            <p><strong>Transaction ID:</strong> {transaction.gateway_reference}</p>
                            <p><strong>Activation Date:</strong> {utcnow().strftime('%B %d, %Y %I:%M %p')}</p>
                            <p><strong>Status:</strong> <span style="color: #10B981; font-weight: bold;">Active ✅</span></p>
                        </div>
                        
                        <div class="details">
                            <h3>🚀 Next Steps</h3>
                            <p>1. <a href="{current_app.config.get('BASE_URL', 'http://localhost:5000')}/market/create_service" style="color: #D97706; font-weight: bold;">Create your first service listing</a></p>
                            <p>2. Complete your seller profile</p>
                            <p>3. Add your contact information</p>
                            <p>4. Start promoting your services</p>
                        </div>
                        
                        <div class="details">
                            <h3>💡 Tips for Success</h3>
                            <p>• Use high-quality images for your services</p>
                            <p>• Write detailed descriptions</p>
                            <p>• Set competitive prices</p>
                            <p>• Respond quickly to inquiries</p>
                            <p>• Ask satisfied clients for reviews</p>
                        </div>
                        
                        <p>Need help getting started? Visit our <a href="{current_app.config.get('BASE_URL', 'http://localhost:5000')}/help/marketplace" style="color: #D97706; font-weight: bold;">Marketplace Seller Guide</a> for tips and best practices.</p>
                        
                        <p>Happy selling!<br>The Kimbela Marketplace Team</p>
                    </div>
                    <div class="footer">
                        <p>© {utcnow().year} Kimbela Marketplace. Empowering African creators and professionals.</p>
                    </div>
                </div>
            </body>
            </html>
            """

            return self._send_email(subject, user.email, html_body)

        except Exception as e:
            print(f"❌ Failed to send marketplace success email: {str(e)}")
            return False


class MarketplacePaymentService(BasePaymentService):
    """Payment service for marketplace subscriptions"""

    def __init__(self):
        super().__init__()
        self.email_service = MarketplaceEmailService()  # Add email service

    def create_marketplace_payment(self, user, plan, currency="USD"):
        """Create Flutterwave payment for marketplace subscription"""
        try:
            print(f"🟡 [MARKETPLACE PAYMENT] Starting payment for plan: {plan.name}")
            print(
                f"🟡 [MARKETPLACE PAYMENT] User: {user.id}, Amount: ${plan.price_usd} {currency}"
            )

            # Generate transaction reference
            import time

            tx_ref = f"KIMBELA_MARKET_{user.id}_{int(time.time())}"
            payment_amount = plan.price_usd

            # Prepare payment data
            payment_data = {
                "tx_ref": tx_ref,
                "amount": str(float(payment_amount)),
                "currency": currency,
                "redirect_url": url_for("market.subscription_callback", _external=True),
                "customer": {
                    "email": user.email,
                    "name": user.full_name
                    or user.first_name
                    or user.email.split("@")[0],
                },
                "meta": {
                    "user_id": user.id,
                    "plan_id": plan.id,
                    "plan_name": plan.name,
                    "transaction_type": "marketplace_subscription",
                },
                "customizations": {
                    "title": "Kimbela Marketplace",
                    "description": f"Subscription Plan: {plan.name}",
                },
            }

            # Add phone number if available
            if hasattr(user, "phone_number") and user.phone_number:
                payment_data["customer"]["phone_number"] = user.phone_number

            headers = {
                "Authorization": f"Bearer {self.flutterwave_secret_key}",
                "Content-Type": "application/json",
            }

            print(f"🟡 [MARKETPLACE PAYMENT] Sending request to Flutterwave...")

            response = self._http_request(
                "POST",
                f"{self.flutterwave_base_url}/payments",
                headers=headers,
                json=payment_data,
                timeout=30,
            )

            print(f"🟡 [MARKETPLACE PAYMENT] Response status: {response.status_code}")

            if response.status_code == 200:
                result = response.json()
                print(
                    f"🟡 [MARKETPLACE PAYMENT] Flutterwave response: {json.dumps(result, indent=2)}"
                )

                if result.get("status") == "success":
                    payment_url = result["data"]["link"]
                    print(
                        f"✅ [MARKETPLACE PAYMENT] Payment URL generated: {payment_url}"
                    )

                    # Create MarketplacePayment record
                    marketplace_payment = MarketplacePayment(
                        user_id=user.id,
                        subscription_id=plan.id,
                        amount=payment_amount,
                        currency=currency,
                        tokens_paid=int(payment_amount * 100),
                        gateway="flutterwave",
                        gateway_reference=tx_ref,
                        gateway_payment_id=result["data"].get("id"),
                        gateway_status="initiated",
                        gateway_metadata=json.dumps(result.get("data", {})),
                        status="pending",
                        payment_method="card",
                        description=f"Marketplace Subscription: {plan.name}",
                        start_date=utcnow(),
                        end_date=utcnow()
                        + timedelta(days=getattr(plan, "duration_days", 30)),
                    )

                    db.session.add(marketplace_payment)
                    db.session.commit()

                    return {
                        "success": True,
                        "payment_url": payment_url,
                        "payment_id": marketplace_payment.id,
                        "gateway_reference": tx_ref,
                        "message": "Marketplace subscription payment initiated successfully",
                    }
                else:
                    error_msg = result.get("message", "Unknown Flutterwave error")
                    print(f"🔴 [MARKETPLACE PAYMENT] Flutterwave error: {error_msg}")
                    return {
                        "success": False,
                        "error": f"Payment gateway error: {error_msg}",
                    }
            else:
                print(
                    f"🔴 [MARKETPLACE PAYMENT] HTTP error {response.status_code}: {response.text}"
                )
                return {
                    "success": False,
                    "error": f"Payment gateway returned error: {response.status_code}",
                }

        except Exception as e:
            print(f"🔴 [MARKETPLACE PAYMENT] Exception: {str(e)}")
            import traceback

            print(f"🔴 [MARKETPLACE PAYMENT] Traceback:\n{traceback.format_exc()}")
            if isinstance(e, UpstreamServiceError):
                return {
                    "success": False,
                    "error": "Payment provider is temporarily unreachable. Please try again in a moment.",
                    "error_type": "upstream_unavailable",
                }
            return {"success": False, "error": f"Payment processing error: {str(e)}"}

    def handle_marketplace_payment_success(self, marketplace_payment, flutterwave_data):
        """Handle successful marketplace payment"""
        try:
            print(f"🟡 [PAYMENT SUCCESS] Starting to handle successful payment")

            # Update payment record
            marketplace_payment.status = "completed"
            marketplace_payment.gateway_status = flutterwave_data.get(
                "status", "successful"
            )
            marketplace_payment.gateway_payment_id = flutterwave_data.get("id")
            marketplace_payment.gateway_metadata = json.dumps(flutterwave_data)
            marketplace_payment.paid_at = utcnow()
            marketplace_payment.updated_at = utcnow()

            # Update user subscription
            user = marketplace_payment.user
            if user:
                user.marketplace_subscription_status = "active"
                user.marketplace_subscription_id = marketplace_payment.subscription_id
                user.marketplace_subscription_expires = (
                    marketplace_payment.end_date
                    or utcnow() + timedelta(days=30)
                )

                # Set subscription tier
                plan = marketplace_payment.subscription
                if plan:
                    user.marketplace_subscription_tier = getattr(plan, "slug", "basic")

            db.session.commit()
            print(f"✅ [PAYMENT SUCCESS] Database updated")

            # Send success email (if not already sent)
            try:
                plan = marketplace_payment.subscription
                if plan:
                    email_sent = self.email_service.send_payment_success_email(
                        user=user, marketplace_payment=marketplace_payment, plan=plan
                    )
                    print(f"✅ [PAYMENT SUCCESS] Success email sent: {email_sent}")
            except Exception as e:
                print(f"⚠️ [PAYMENT SUCCESS] Email error (non-critical): {e}")

            return True

        except Exception as e:
            db.session.rollback()
            print(f"🔴 [PAYMENT SUCCESS] Exception: {str(e)}")
            import traceback

            print(f"🔴 [PAYMENT SUCCESS] Traceback: {traceback.format_exc()}")
            return False

    def handle_marketplace_payment_failure(self, marketplace_payment, flutterwave_data):
        """Handle failed marketplace payment"""
        try:
            print(f"🟡 [PAYMENT FAILURE] Handling failed payment")

            # Update payment record
            marketplace_payment.status = "failed"
            marketplace_payment.gateway_status = flutterwave_data.get(
                "status", "failed"
            )
            marketplace_payment.gateway_metadata = json.dumps(flutterwave_data)
            marketplace_payment.updated_at = utcnow()

            db.session.commit()

            # Send failure email
            try:
                plan = marketplace_payment.subscription
                user = marketplace_payment.user
                if plan and user:
                    error_reason = flutterwave_data.get("message", "Payment failed")
                    email_sent = self.email_service.send_payment_failed_email(
                        user=user,
                        marketplace_payment=marketplace_payment,
                        plan=plan,
                        error_reason=error_reason,
                    )
                    print(f"✅ [PAYMENT FAILURE] Failure email sent: {email_sent}")
            except Exception as e:
                print(f"⚠️ [PAYMENT FAILURE] Email error: {e}")

            return True

        except Exception as e:
            db.session.rollback()
            print(f"🔴 [PAYMENT FAILURE] Exception: {str(e)}")
            import traceback

            print(f"🔴 [PAYMENT FAILURE] Traceback: {traceback.format_exc()}")
            return False

    def verify_flutterwave_payment(self, transaction_id):
        """Verify Flutterwave payment using transaction ID"""
        try:
            headers = {
                "Authorization": f"Bearer {self.flutterwave_secret_key}",
                "Content-Type": "application/json",
            }

            response = self._http_request(
                "GET",
                f"{self.flutterwave_base_url}/transactions/{transaction_id}/verify",
                headers=headers,
                timeout=30,
            )

            print(f"🟡 [VERIFY PAYMENT] Response status: {response.status_code}")

            if response.status_code == 200:
                result = response.json()
                print(f"🟡 [VERIFY PAYMENT] Verification result: {result}")
                return {
                    "success": result.get("status") == "success",
                    "data": result.get("data", {}),
                }

            print(
                f"🔴 [VERIFY PAYMENT] HTTP Error: {response.status_code} - {response.text}"
            )
            return {
                "success": False,
                "error": f"HTTP {response.status_code}",
                "data": {},
            }

        except Exception as e:
            print(f"🔴 [VERIFY PAYMENT] Exception: {str(e)}")
            return {"success": False, "error": str(e), "data": {}}

    def get_marketplace_payment_by_reference(self, gateway_reference):
        """Get marketplace payment by gateway reference"""
        return MarketplacePayment.query.filter_by(
            gateway_reference=gateway_reference
        ).first()

    def get_marketplace_payment_by_id(self, payment_id):
        """Get marketplace payment by ID"""
        return MarketplacePayment.query.get(payment_id)

    def get_user_marketplace_payments(self, user_id):
        """Get all marketplace payments for a user"""
        return (
            MarketplacePayment.query.filter_by(user_id=user_id)
            .order_by(MarketplacePayment.created_at.desc())
            .all()
        )

    def cancel_marketplace_subscription(self, user_id):
        """Cancel user's marketplace subscription"""
        try:
            user = User.query.get(user_id)
            if not user:
                return {"success": False, "error": "User not found"}

            # Update user subscription status
            user.marketplace_subscription_status = "inactive"
            user.marketplace_subscription_expires = utcnow()
            user.marketplace_featured_until = None

            db.session.commit()

            return {"success": True, "message": "Subscription cancelled successfully"}

        except Exception as e:
            db.session.rollback()
            return {"success": False, "error": str(e)}

    def extend_marketplace_subscription(self, user_id, days=30):
        """Extend user's marketplace subscription"""
        try:
            user = User.query.get(user_id)
            if not user:
                return {"success": False, "error": "User not found"}

            # Calculate new expiration date
            if user.marketplace_subscription_expires:
                new_expiry = user.marketplace_subscription_expires + timedelta(
                    days=days
                )
            else:
                new_expiry = utcnow() + timedelta(days=days)

            user.marketplace_subscription_expires = new_expiry

            # Update featured until if applicable
            if user.marketplace_featured_until:
                user.marketplace_featured_until = new_expiry

            db.session.commit()

            return {
                "success": True,
                "message": f"Subscription extended by {days} days",
                "new_expiry": new_expiry.isoformat(),
            }

        except Exception as e:
            db.session.rollback()
            return {"success": False, "error": str(e)}

    def check_subscription_status(self, user_id):
        """Check user's subscription status"""
        try:
            user = User.query.get(user_id)
            if not user:
                return {"success": False, "error": "User not found"}

            is_active = user.has_active_marketplace_subscription
            is_featured = False

            if user.marketplace_featured_until:
                is_featured = user.marketplace_featured_until > utcnow()

            # Get active payment
            active_payment = (
                MarketplacePayment.query.filter_by(user_id=user_id, status="completed")
                .order_by(MarketplacePayment.paid_at.desc())
                .first()
            )

            return {
                "success": True,
                "is_active": is_active,
                "is_featured": is_featured,
                "status": user.marketplace_subscription_status,
                "tier": user.marketplace_subscription_tier,
                "expires": (
                    user.marketplace_subscription_expires.isoformat()
                    if user.marketplace_subscription_expires
                    else None
                ),
                "featured_until": (
                    user.marketplace_featured_until.isoformat()
                    if user.marketplace_featured_until
                    else None
                ),
                "active_payment": (
                    {
                        "id": active_payment.id if active_payment else None,
                        "amount": active_payment.amount if active_payment else None,
                        "paid_at": (
                            active_payment.paid_at.isoformat()
                            if active_payment and active_payment.paid_at
                            else None
                        ),
                    }
                    if active_payment
                    else None
                ),
            }

        except Exception as e:
            return {"success": False, "error": str(e)}
