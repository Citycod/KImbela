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
    MarketplaceService,
)
from .email_service import MarketplaceEmailService


from time_utils import utcnow
logger = logging.getLogger(__name__)
_EXCHANGE_RATE_CACHE = {}


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
        
        # self.paystack_public_key = os.getenv("PAYSTACK_PUBLIC_KEY")
        # self.paystack_secret_key = os.getenv("PAYSTACK_SECRET_KEY")
        # self.paystack_base_url = "https://api.paystack.co"
        
        self.stripe_public_key = os.getenv("STRIPE_PUBLIC_KEY")
        self.stripe_secret_key = os.getenv("STRIPE_SECRET_KEY")
        
        self.monnify_api_key = os.getenv("MONNIFY_API_KEY")
        self.monnify_secret_key = os.getenv("MONNIFY_SECRET_KEY")
        self.monnify_contract_code = os.getenv("MONNIFY_CONTRACT_CODE")
        self.monnify_base_url = os.getenv("MONNIFY_BASE_URL", "https://sandbox.monnify.com/api/v1")
        
        self.default_currency = os.getenv("FLW_DEFAULT_CURRENCY", "USD").upper()

        print(
            f"[INFO] [BASE PAYMENT INIT] Public Key configured: {self.flutterwave_public_key is not None}"
        )
        print(
            f"[INFO] [BASE PAYMENT INIT] Secret Key configured: {self.flutterwave_secret_key is not None}"
        )

        if self.flutterwave_public_key:
            print(
                f"[INFO] [BASE PAYMENT INIT] Public Key: {self.flutterwave_public_key[:20]}..."
            )
        if self.flutterwave_secret_key:
            print(
                f"[INFO] [BASE PAYMENT INIT] Secret Key: {self.flutterwave_secret_key[:20]}..."
            )

    def normalize_currency(self, currency=None):
        return (currency or self.default_currency or "USD").upper()

    @staticmethod
    def is_success_status(status):
        return (status or "").strip().lower() in {"successful", "completed"}

    @staticmethod
    def is_pending_status(status):
        return (status or "").strip().lower() in {"pending", "processing"}

    @staticmethod
    def is_failure_status(status):
        return (status or "").strip().lower() in {
            "failed",
            "cancelled",
            "canceled",
            "session_expired",
            "error",
        }

    def get_ngn_rate(self, env_var="USD_TO_NGN_RATE", fallback="1600"):
        raw_value = os.getenv(env_var)
        try:
            if raw_value:
                return float(raw_value)
        except (TypeError, ValueError):
            logger.warning("Invalid NGN rate override for %s: %r", env_var, raw_value)

        cache_key = f"USD_NGN:{env_var}"
        cache_ttl_seconds = 3600
        now_ts = time.time()
        cached_rate = _EXCHANGE_RATE_CACHE.get(cache_key)
        if cached_rate and (now_ts - cached_rate["timestamp"]) < cache_ttl_seconds:
            return cached_rate["rate"]

        providers = (
            ("https://api.frankfurter.dev/v1/latest?base=USD&symbols=NGN", ("rates", "NGN")),
            ("https://open.er-api.com/v6/latest/USD", ("rates", "NGN")),
        )

        for url, path in providers:
            try:
                response = self._http_request("GET", url, timeout=10)
                if response.status_code != 200:
                    continue
                payload = response.json()
                rate_value = payload
                for key in path:
                    rate_value = rate_value[key]
                rate = float(rate_value)
                if rate <= 0:
                    continue
                _EXCHANGE_RATE_CACHE[cache_key] = {
                    "rate": rate,
                    "timestamp": now_ts,
                    "source": url,
                }
                return rate
            except Exception as exc:
                logger.warning("Failed to fetch live NGN rate from %s: %s", url, exc)

        raw_value = (
            os.getenv("MARKETPLACE_USD_TO_NGN_RATE")
            or os.getenv("MATCHMAKING_USD_TO_NGN_RATE")
            or os.getenv("USD_TO_NGN_RATE")
            or fallback
        )
        try:
            return float(raw_value)
        except (TypeError, ValueError):
            return float(fallback)

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

    def verify_flutterwave_payment_by_reference(self, tx_ref):
        """Verify Flutterwave payment using merchant transaction reference."""
        try:
            headers = {
                "Authorization": f"Bearer {self.flutterwave_secret_key}",
                "Content-Type": "application/json",
            }

            response = self._http_request(
                "GET",
                f"{self.flutterwave_base_url}/transactions/verify_by_reference",
                headers=headers,
                params={"tx_ref": tx_ref},
                timeout=30,
            )

            print(
                f"🟡 [VERIFY PAYMENT BY REFERENCE] Response status: {response.status_code}"
            )

            if response.status_code == 200:
                result = response.json()
                print(
                    f"🟡 [VERIFY PAYMENT BY REFERENCE] Verification result: {result}"
                )
                return {
                    "success": result.get("status") == "success",
                    "data": result.get("data", {}),
                }

            print(
                "🔴 [VERIFY PAYMENT BY REFERENCE] HTTP Error: "
                f"{response.status_code} - {response.text}"
            )
            return {
                "success": False,
                "error": f"HTTP {response.status_code}",
                "data": {},
            }

        except Exception as e:
            print(f"🔴 [VERIFY PAYMENT BY REFERENCE] Exception: {str(e)}")
            return {"success": False, "error": str(e), "data": {}}

    # def verify_paystack_payment(self, reference):
    #     """Verify Paystack payment using merchant transaction reference."""
    #     try:
    #         if not self.paystack_secret_key:
    #             return {"success": False, "error": "Paystack secret key not configured", "data": {}}
    #
    #         headers = {
    #             "Authorization": f"Bearer {self.paystack_secret_key}",
    #             "Content-Type": "application/json",
    #         }
    #
    #         response = self._http_request(
    #             "GET",
    #             f"{self.paystack_base_url}/transaction/verify/{reference}",
    #             headers=headers,
    #             timeout=30,
    #         )
    #
    #         print(
    #             f"🟡 [VERIFY PAYSTACK PAYMENT] Response status: {response.status_code}"
    #         )
    #
    #         if response.status_code == 200:
    #             result = response.json()
    #             print(
    #                 f"🟡 [VERIFY PAYSTACK PAYMENT] Verification result: {result}"
    #             )
    #             return {
    #                 "success": result.get("status") is True or result.get("data", {}).get("status") == "success",
    #                 "data": result.get("data", {}),
    #             }
    #
    #         print(
    #             "🔴 [VERIFY PAYSTACK PAYMENT] HTTP Error: "
    #             f"{response.status_code} - {response.text}"
    #         )
    #         return {
    #             "success": False,
    #             "error": f"HTTP {response.status_code}",
    #             "data": {},
    #         }
    #
    #     except Exception as e:
    #         print(f"🔴 [VERIFY PAYSTACK PAYMENT] Exception: {str(e)}")
    #         return {"success": False, "error": str(e), "data": {}}

    def resolve_flutterwave_verification(self, tx_ref=None, transaction_id=None):
        """Resolve payment state from Flutterwave using transaction ID, tx_ref, or both."""
        verification_attempts = []

        if transaction_id:
            verification = self.verify_flutterwave_payment(transaction_id)
            verification_attempts.append(("transaction_id", verification))
            verified_status = (
                (verification.get("data", {}) or {}).get("status") or ""
            ).strip().lower()
            if verification.get("success") and verified_status:
                return {
                    "success": True,
                    "data": verification.get("data", {}) or {},
                    "verified_status": verified_status,
                    "source": "transaction_id",
                }

        if tx_ref:
            verification = self.verify_flutterwave_payment_by_reference(tx_ref)
            verification_attempts.append(("tx_ref", verification))
            verified_status = (
                (verification.get("data", {}) or {}).get("status") or ""
            ).strip().lower()
            if verification.get("success") and verified_status:
                return {
                    "success": True,
                    "data": verification.get("data", {}) or {},
                    "verified_status": verified_status,
                    "source": "tx_ref",
                }

        fallback_data = {}
        fallback_error = None
        for source, attempt in reversed(verification_attempts):
            if attempt.get("data"):
                fallback_data = attempt.get("data", {}) or {}
            if attempt.get("error"):
                fallback_error = attempt.get("error")

        return {
            "success": False,
            "data": fallback_data,
            "verified_status": ((fallback_data.get("status") or "").strip().lower()),
            "source": None,
            "error": fallback_error or "Payment verification failed",
        }

    # def resolve_paystack_verification(self, reference=None):
    #     """Resolve payment state from Paystack using merchant reference."""
    #     if reference:
    #         verification = self.verify_paystack_payment(reference)
    #         verified_status = (
    #             (verification.get("data", {}) or {}).get("status") or ""
    #         ).strip().lower()
    #         if verification.get("success") and verified_status:
    #             return {
    #                 "success": True,
    #                 "data": verification.get("data", {}) or {},
    #                 "verified_status": verified_status,
    #                 "source": "reference",
    #             }
    #         return {
    #             "success": False,
    #             "error": verification.get("error", "Failed to verify Paystack payment"),
    #             "data": verification.get("data", {}),
    #             "verified_status": verified_status or "failed",
    #         }
    #     return {
    #         "success": False,
    #         "error": "No reference provided for Paystack verification",
    #         "data": {},
    #         "verified_status": "failed",
    #     }

    def get_monnify_token(self):
        """Get access token for Monnify API."""
        import base64
        if not self.monnify_api_key or not self.monnify_secret_key:
            print("🔴 [MONNIFY AUTH] Missing API keys")
            return None
        
        auth_str = f"{self.monnify_api_key}:{self.monnify_secret_key}"
        b64_auth_str = base64.b64encode(auth_str.encode()).decode()
        
        headers = {
            "Authorization": f"Basic {b64_auth_str}"
        }
        try:
            response = self._http_request(
                "POST",
                f"{self.monnify_base_url}/auth/login",
                headers=headers,
                timeout=30
            )
            if response.status_code == 200:
                result = response.json()
                return result.get("responseBody", {}).get("accessToken")
            else:
                print(f"🔴 [MONNIFY AUTH] Error: {response.text}")
        except Exception as e:
            print(f"🔴 [MONNIFY AUTH] Exception: {str(e)}")
        return None

    def verify_monnify_payment(self, transaction_reference):
        """Verify Monnify payment using transaction reference."""
        token = self.get_monnify_token()
        if not token:
            return {"success": False, "error": "Could not authenticate with Monnify", "data": {}}
            
        headers = {
            "Authorization": f"Bearer {token}"
        }
        try:
            response = self._http_request(
                "GET",
                f"{self.monnify_base_url}/merchant/transactions/query?transactionReference={transaction_reference}",
                headers=headers,
                timeout=30
            )
            if response.status_code == 200:
                result = response.json()
                data = result.get("responseBody", {})
                status = data.get("paymentStatus")
                return {
                    "success": status == "PAID",
                    "data": data,
                    "verified_status": status.lower() if status else "failed"
                }
            return {"success": False, "error": f"HTTP {response.status_code}", "data": {}, "verified_status": "failed"}
        except Exception as e:
            return {"success": False, "error": str(e), "data": {}, "verified_status": "failed"}

    def resolve_monnify_verification(self, reference=None):
        """Resolve payment state from Monnify using merchant reference."""
        if reference:
            verification = self.verify_monnify_payment(reference)
            verified_status = verification.get("verified_status", "failed")
            if verification.get("success"):
                return {
                    "success": True,
                    "data": verification.get("data", {}) or {},
                    "verified_status": verified_status,
                    "source": "reference",
                }
            return {
                "success": False,
                "error": verification.get("error", "Failed to verify Monnify payment"),
                "data": verification.get("data", {}),
                "verified_status": verified_status,
            }
        return {
            "success": False,
            "error": "No reference provided for Monnify verification",
            "data": {},
            "verified_status": "failed",
        }

    def verify_stripe_payment(self, session_id):
        """Verify Stripe checkout session."""
        try:
            import stripe
            stripe.api_key = self.stripe_secret_key
            session = stripe.checkout.Session.retrieve(session_id)
            return {
                "success": session.payment_status == "paid",
                "data": session,
                "verified_status": session.payment_status
            }
        except Exception as e:
            return {"success": False, "error": str(e), "data": {}, "verified_status": "failed"}

    def resolve_stripe_verification(self, session_id=None):
        """Resolve payment state from Stripe using session ID."""
        if session_id:
            verification = self.verify_stripe_payment(session_id)
            verified_status = verification.get("verified_status", "failed")
            if verification.get("success"):
                return {
                    "success": True,
                    "data": verification.get("data", {}),
                    "verified_status": verified_status,
                    "source": "session_id",
                }
            return {
                "success": False,
                "error": verification.get("error", "Failed to verify Stripe payment"),
                "data": verification.get("data", {}),
                "verified_status": verified_status,
            }
        return {
            "success": False,
            "error": "No session ID provided for Stripe verification",
            "data": {},
            "verified_status": "failed",
        }

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
            f"[INFO] [KEY VALIDATION] Public Key: {'SET' if self.flutterwave_public_key else 'MISSING'}"
        )
        print(
            f"[INFO] [KEY VALIDATION] Secret Key: {'SET' if self.flutterwave_secret_key else 'MISSING'}"
        )

        if not self.flutterwave_secret_key:
            raise ValueError("Flutterwave secret key is not configured")

        # Test key format (Flutterwave keys typically start with specific prefixes)
        if self.flutterwave_secret_key and not self.flutterwave_secret_key.startswith(
            ("FLWSECK-", "FLWSECK_TEST-")
        ):
            print("[WARN] [KEY VALIDATION] Secret key format may be incorrect")

        if self.flutterwave_public_key and not self.flutterwave_public_key.startswith(
            ("FLWPUBK-", "FLWPUBK_TEST-")
        ):
            print("[WARN] [KEY VALIDATION] Public key format may be incorrect")

        print(f"[OK] [KEY VALIDATION] Keys validated successfully")

    def create_matchmaking_payment(
        self, user, matchmaking_request, package, currency="USD", amount=None, gateway="flutterwave"
    ):
        """Create payment for matchmaking request using Flutterwave or Paystack"""
        try:
            print(f"🟡 [MATCHMAKING PAYMENT] Starting payment process")
            print(
                f"🟡 [MATCHMAKING PAYMENT] User: {user.id}, Request: {matchmaking_request.id}, Package: {package.name}, Gateway: {gateway}"
            )

            # Use provided amount or fallback to package price
            currency = self.normalize_currency(currency)
            payment_amount = float(amount) if amount is not None else float(package.price)

            # Generate unique transaction reference
            tx_ref = f"KIMBELA_MATCH_{matchmaking_request.id}_{int(time.time())}"

            # if gateway == "paystack":
            #     payment_data = {
            #         "email": user.email,
            #         "amount": int(payment_amount * 100),  # Paystack uses kobo
            #         "currency": currency,
            #         "reference": tx_ref,
            #         "callback_url": url_for("match.payment_callback", _external=True),
            #         "metadata": {
            #             "user_id": user.id,
            #             "matchmaking_request_id": matchmaking_request.id,
            #             "package_id": package.id,
            #             "transaction_type": "matchmaking",
            #         }
            #     }
            #     
            #     headers = {
            #         "Authorization": f"Bearer {self.paystack_secret_key}",
            #         "Content-Type": "application/json",
            #     }
            #
            #     print(f"🟡 [MATCHMAKING PAYMENT] Sending request to Paystack...")
            #     
            #     response = self._http_request(
            #         "POST",
            #         f"{self.paystack_base_url}/transaction/initialize",
            #         headers=headers,
            #         json=payment_data,
            #         timeout=30,
            #     )
            #
            #     if response.status_code == 200:
            #         result = response.json()
            #         if result.get("status") is True:
            #             payment_url = result["data"]["authorization_url"]
            #             
            #             matchmaking_payment = MatchmakingPayments(
            #                 user_id=user.id,
            #                 matchmaking_request_id=matchmaking_request.id,
            #                 package_id=package.id,
            #                 amount=payment_amount,
            #                 currency=currency,
            #                 gateway="paystack",
            #                 gateway_reference=tx_ref,
            #                 gateway_status="initiated",
            #                 status="pending",
            #                 payment_status="pending",
            #                 description=f"Matchmaking Package: {package.name}",
            #             )
            #             db.session.add(matchmaking_payment)
            #             db.session.commit()
            #
            #             return {
            #                 "success": True,
            #                 "payment_url": payment_url,
            #                 "payment_id": matchmaking_payment.id,
            #                 "gateway_reference": tx_ref,
            #                 "message": "Matchmaking payment initiated successfully via Paystack",
            #             }
            #         else:
            #             return {"success": False, "error": f"Paystack error: {result.get('message')}"}
            #     else:
            #         return {"success": False, "error": f"Paystack returned error: {response.status_code}"}

#            if gateway == "monnify":
#                token = self.get_monnify_token()
#                if not token:
#                    return {"success": False, "error": "Monnify authentication failed"}

#                payment_data = {
#                    "amount": payment_amount,
#                    "customerName": user.full_name or user.first_name or user.email.split("@")[0],
#                    "customerEmail": user.email,
#                    "paymentReference": tx_ref,
#                    "paymentDescription": f"Matchmaking Package: {package.name}",
#                    "currencyCode": currency,
#                    "contractCode": self.monnify_contract_code,
#                    "redirectUrl": url_for("match.payment_callback", _external=True),
#                    "paymentMethods": ["CARD", "ACCOUNT_TRANSFER"]
#                }
                
#                headers = {
#                    "Authorization": f"Bearer {token}",
#                    "Content-Type": "application/json",
#                }

#                print(f"🟡 [MATCHMAKING PAYMENT] Sending request to Monnify...")
                
#                response = self._http_request(
#                    "POST",
#                    f"{self.monnify_base_url}/merchant/transactions/init-transaction",
#                    headers=headers,
#                    json=payment_data,
#                    timeout=30,
#                )

#                if response.status_code == 200:
#                    result = response.json()
#                    if result.get("requestSuccessful"):
#                        payment_url = result["responseBody"]["checkoutUrl"]
                        
#                        matchmaking_payment = MatchmakingPayments(
#                            user_id=user.id,
#                            matchmaking_request_id=matchmaking_request.id,
#                            package_id=package.id,
#                            amount=payment_amount,
#                            currency=currency,
#                            gateway="monnify",
#                            gateway_reference=tx_ref,
#                            gateway_status="initiated",
#                            status="pending",
#                            payment_status="pending",
#                            description=f"Matchmaking Package: {package.name}",
#                        )
#                        db.session.add(matchmaking_payment)
#                        db.session.commit()

#                        return {
#                            "success": True,
#                            "payment_url": payment_url,
#                            "payment_id": matchmaking_payment.id,
#                            "gateway_reference": tx_ref,
#                            "message": "Matchmaking payment initiated successfully via Monnify",
#                        }
#                    else:
#                        return {"success": False, "error": f"Monnify error: {result.get('responseMessage')}"}
#                else:
#                    return {"success": False, "error": f"Monnify returned error: {response.status_code}"}

#            if gateway == "stripe":
#                try:
#                    import stripe
#                    stripe.api_key = self.stripe_secret_key
                    
#                    callback_url = url_for("match.payment_callback", _external=True)
                    
#                    session = stripe.checkout.Session.create(
#                        payment_method_types=['card'],
#                        line_items=[{
#                            'price_data': {
#                                'currency': currency.lower(),
#                                'product_data': {
#                                    'name': f"Kimbela Matchmaking: {package.name}",
#                                },
#                                'unit_amount': int(payment_amount * 100), # Stripe uses cents
#                            },
#                            'quantity': 1,
#                        }],
#                        mode='payment',
#                        success_url=callback_url + f"?tx_ref={tx_ref}&status=successful",
#                        cancel_url=callback_url + f"?tx_ref={tx_ref}&status=cancelled",
#                        client_reference_id=tx_ref,
#                        metadata={
#                            "user_id": user.id,
#                            "matchmaking_request_id": matchmaking_request.id,
#                            "package_id": package.id,
#                            "transaction_type": "matchmaking"
#                        }
#                    )
                    
#                    matchmaking_payment = MatchmakingPayments(
#                        user_id=user.id,
#                        matchmaking_request_id=matchmaking_request.id,
#                        package_id=package.id,
#                        amount=payment_amount,
#                        currency=currency,
#                        gateway="stripe",
#                        gateway_reference=tx_ref,
#                        gateway_status="initiated",
#                        status="pending",
#                        payment_status="pending",
#                        description=f"Matchmaking Package: {package.name}",
#                    )
#                    db.session.add(matchmaking_payment)
#                    db.session.commit()

#                    return {
#                        "success": True,
#                        "payment_url": session.url,
#                        "payment_id": matchmaking_payment.id,
#                        "gateway_reference": tx_ref,
#                        "message": "Matchmaking payment initiated successfully via Stripe",
#                    }
#                except Exception as e:
#                    print(f"🔴 [MATCHMAKING PAYMENT] Stripe Exception: {str(e)}")
#                    return {"success": False, "error": f"Stripe error: {str(e)}"}

            # Convert USD to NGN for Flutterwave checkout — all payments in Naira
            checkout_currency = "NGN"
            checkout_amount = float(payment_amount)
            if currency.upper() == "USD":
                rate = float(self.get_ngn_rate())
                checkout_amount = round(checkout_amount * rate, 2)
                print(f"🟡 [MATCHMAKING PAYMENT] Converted USD {payment_amount} to NGN {checkout_amount} at rate {rate}")

            # Prepare payment data for matchmaking (Flutterwave)
            payment_data = {
                "tx_ref": tx_ref,
                "amount": str(checkout_amount),
                "currency": checkout_currency,
                "redirect_url": url_for("match.payment_callback", _external=True),
                "payment_options": "card,banktransfer,ussd",
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

            response = self._http_request(
                "POST",
                f"{self.flutterwave_base_url}/payments",
                headers=headers,
                json=payment_data,
                timeout=30,
            )

            print(f"🟡 [MATCHMAKING PAYMENT] Response status: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()

                if result.get("status") == "success":
                    payment_url = result["data"]["link"]

                    # Create matchmaking payment record
                    matchmaking_payment = MatchmakingPayments(
                        user_id=user.id,
                        matchmaking_request_id=matchmaking_request.id,
                        package_id=package.id,
                        amount=payment_amount,
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
                        "message": "Matchmaking payment initiated successfully via Flutterwave",
                    }
                else:
                    error_msg = result.get("message", "Unknown Flutterwave error")
                    return {
                        "success": False,
                        "error": f"Payment gateway error: {error_msg}",
                    }
            else:
                error_text = response.text

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
            gateway_status = flutterwave_data.get("status", "failed")
            if self.is_success_status(gateway_status) or self.is_pending_status(
                gateway_status
            ):
                matchmaking_payment.gateway_status = gateway_status
                matchmaking_payment.gateway_metadata = json.dumps(flutterwave_data)
                matchmaking_payment.updated_at = utcnow()
                db.session.commit()
                return True

            # Update matchmaking payment record
            matchmaking_payment.status = "failed"
            matchmaking_payment.payment_status = "failed"
            matchmaking_payment.gateway_status = gateway_status
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
            currency = self.normalize_currency(currency)
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

            # Convert USD to NGN for Flutterwave checkout — all payments in Naira
            checkout_currency = "NGN"
            checkout_amount = float(package.price)
            if currency.upper() == "USD":
                rate = float(self.get_ngn_rate())
                checkout_amount = round(checkout_amount * rate, 2)
                print(f"🟡 [MATCHMAKING RETRY] Converted USD {package.price} to NGN {checkout_amount} at rate {rate}")

            # Prepare payment data
            payment_data = {
                "tx_ref": tx_ref,
                "amount": str(checkout_amount),
                "currency": checkout_currency,
                "redirect_url": url_for("match.payment_callback", _external=True),
                "payment_options": "card,banktransfer,ussd",
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

    def resolve_flutterwave_verification(self, tx_ref=None, transaction_id=None):
        """Resolve Flutterwave verification using transaction ID or tx_ref."""
        return self.marketplace_service.resolve_flutterwave_verification(
            tx_ref=tx_ref, transaction_id=transaction_id
        )

    def handle_marketplace_payment_success(self, transaction_id, payment_data):
        """Handle successful marketplace payment"""
        marketplace_payment = MarketplacePayment.query.get(transaction_id)
        if not marketplace_payment:
            return False

        return self.marketplace_service.handle_marketplace_payment_success(
            marketplace_payment=marketplace_payment, flutterwave_data=payment_data
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

    def create_marketplace_payment(self, user, plan, currency="USD", gateway="flutterwave"):
        """Create Flutterwave or Paystack payment for marketplace subscription - FIXED VERSION"""
        try:
            from marketplace.market import get_marketplace_checkout_amount
            payment_amount = get_marketplace_checkout_amount(plan, currency)

            print(f"[INFO] [MARKETPLACE PAYMENT] Starting payment for plan: {plan.name}, Gateway: {gateway}")
            print(
                f"[INFO] [MARKETPLACE PAYMENT] User: {user.id}, Amount: {payment_amount} {currency}"
            )

            # Generate transaction reference
            import time

            tx_ref = f"KIMBELA_MARKET_{user.id}_{int(time.time())}"

            print(f"[INFO] [MARKETPLACE PAYMENT] TX Ref: {tx_ref}")
            print(f"[INFO] [MARKETPLACE PAYMENT] Amount: {payment_amount}")

            # if gateway == "paystack":
            #     return self.create_paystack_marketplace_payment(user, plan, currency)
            
#            if gateway == "monnify":
#                token = self.get_monnify_token()
#                if not token:
#                    return {"success": False, "error": "Monnify authentication failed"}

#                payment_data = {
#                    "amount": payment_amount,
#                    "customerName": user.full_name or user.first_name or user.email.split("@")[0],
#                    "customerEmail": user.email,
#                    "paymentReference": tx_ref,
#                    "paymentDescription": f"Marketplace Subscription: {plan.name}",
#                    "currencyCode": currency,
#                    "contractCode": self.monnify_contract_code,
#                    "redirectUrl": url_for("market.subscription_callback", _external=True),
#                    "paymentMethods": ["CARD", "ACCOUNT_TRANSFER"]
#                }
                
#                headers = {
#                    "Authorization": f"Bearer {token}",
#                    "Content-Type": "application/json",
#                }

#                response = self._http_request(
#                    "POST",
#                    f"{self.monnify_base_url}/merchant/transactions/init-transaction",
#                    headers=headers,
#                    json=payment_data,
#                    timeout=30,
#                )

#                if response.status_code == 200:
#                    result = response.json()
#                    if result.get("requestSuccessful"):
#                        payment_url = result["responseBody"]["checkoutUrl"]
                        
#                        marketplace_payment = MarketplacePayment(
#                            user_id=user.id,
#                            subscription_id=plan.id,
#                            amount=payment_amount,
#                            currency=currency,
#                            tokens_paid=int(payment_amount * 100),
#                            gateway="monnify",
#                            gateway_reference=tx_ref,
#                            gateway_status="initiated",
#                            status="pending",
#                            payment_method="card",
#                            description=f"Marketplace Subscription: {plan.name}",
#                            start_date=utcnow(),
#                            end_date=utcnow() + timedelta(days=getattr(plan, "duration_days", 30)),
#                        )
#                        db.session.add(marketplace_payment)
#                        db.session.commit()

#                        return {
#                            "success": True,
#                            "payment_url": payment_url,
#                            "payment_id": marketplace_payment.id,
#                            "gateway_reference": tx_ref,
#                            "message": "Marketplace subscription payment initiated successfully via Monnify",
#                        }
#                    else:
#                        return {"success": False, "error": f"Monnify error: {result.get('responseMessage')}"}
#                else:
#                    return {"success": False, "error": f"Monnify returned error: {response.status_code}"}

#            elif gateway == "stripe":
#                try:
#                    import stripe
#                    stripe.api_key = self.stripe_secret_key
                    
#                    callback_url = url_for("market.subscription_callback", _external=True)
                    
#                    session = stripe.checkout.Session.create(
#                        payment_method_types=['card'],
#                        line_items=[{
#                            'price_data': {
#                                'currency': currency.lower(),
#                                'product_data': {
#                                    'name': f"Kimbela Marketplace: {plan.name}",
#                                },
#                                'unit_amount': int(payment_amount * 100),
#                            },
#                            'quantity': 1,
#                        }],
#                        mode='payment',
#                        success_url=callback_url + f"?tx_ref={tx_ref}&status=successful",
#                        cancel_url=callback_url + f"?tx_ref={tx_ref}&status=cancelled",
#                        client_reference_id=tx_ref,
#                        metadata={
#                            "user_id": user.id,
#                            "plan_id": plan.id,
#                            "plan_name": plan.name,
#                            "transaction_type": "marketplace_subscription",
#                        }
#                    )
                    
#                    marketplace_payment = MarketplacePayment(
#                        user_id=user.id,
#                        subscription_id=plan.id,
#                        amount=payment_amount,
#                        currency=currency,
#                        tokens_paid=int(payment_amount * 100),
#                        gateway="stripe",
#                        gateway_reference=tx_ref,
#                        gateway_status="initiated",
#                        status="pending",
#                        payment_method="card",
#                        description=f"Marketplace Subscription: {plan.name}",
#                        start_date=utcnow(),
#                        end_date=utcnow() + timedelta(days=getattr(plan, "duration_days", 30)),
#                    )
#                    db.session.add(marketplace_payment)
#                    db.session.commit()

#                    return {
#                        "success": True,
#                        "payment_url": session.url,
#                        "payment_id": marketplace_payment.id,
#                        "gateway_reference": tx_ref,
#                        "message": "Marketplace payment initiated successfully via Stripe",
#                    }
#                except Exception as e:
#                    return {"success": False, "error": f"Stripe error: {str(e)}"}
            
#            else:
                # Convert USD to NGN for Flutterwave checkout — all payments in Naira
#                checkout_currency = "NGN"
#                checkout_amount = float(payment_amount)
#                if currency.upper() == "USD":
#                    rate = float(self.get_ngn_rate())
#                    checkout_amount = round(checkout_amount * rate, 2)
#                    print(f"🟡 [MARKETPLACE PAYMENT] Converted USD {payment_amount} to NGN {checkout_amount} at rate {rate}")

                # Prepare payment data for Flutterwave
#                payment_data = {
#                    "tx_ref": tx_ref,
#                    "amount": str(checkout_amount),
#                    "currency": checkout_currency,
#                    "redirect_url": url_for("market.subscription_callback", _external=True),
#                    "payment_options": "card",
#                    "customer": {
#                        "email": user.email,
#                        "name": user.full_name
#                        or user.first_name
#                        or user.email.split("@")[0],
#                    },
#                    "meta": {
#                        "user_id": user.id,
#                        "plan_id": plan.id,
#                        "plan_name": plan.name,
#                        "transaction_type": "marketplace_subscription",
#                    },
#                    "customizations": {
#                        "title": "Kimbela Marketplace",
#                        "description": f"Subscription Plan: {plan.name}",
#                    },
#                }

                # Add phone number if available
#                if hasattr(user, "phone_number") and user.phone_number:
#                    payment_data["customer"]["phone_number"] = user.phone_number

#                headers = {
#                    "Authorization": f"Bearer {self.flutterwave_secret_key}",
#                    "Content-Type": "application/json",
#                }

#                print(f"🟡 [MARKETPLACE PAYMENT] Sending request to Flutterwave...")
#                print(f"🟡 [MARKETPLACE PAYMENT] URL: {self.flutterwave_base_url}/payments")
#                print(f"🟡 [MARKETPLACE PAYMENT] Headers: {headers}")

                # Make the request
#                response = self._http_request(
#                    "POST",
#                    f"{self.flutterwave_base_url}/payments",
#                    headers=headers,
#                    json=payment_data,
#                    timeout=30,
#                )

#            print(f"🟡 [MARKETPLACE PAYMENT] Response status: {response.status_code}")
#            print(
#                f"🟡 [MARKETPLACE PAYMENT] Response headers: {dict(response.headers)}"
#            )

            # Parse response
#            response_text = response.text
#            print(f"🟡 [MARKETPLACE PAYMENT] Response text: {response_text[:500]}...")

#            if response.status_code == 200:
#                try:
#                    result = response.json()
#                    print(f"🟡 [MARKETPLACE PAYMENT] Parsed JSON: {result}")

#                    if result.get("status") == "success":
#                        payment_url = result["data"]["link"]
#                        print(
#                            f"✅ [MARKETPLACE PAYMENT] Payment URL generated: {payment_url}"
#                        )

                        # Create MarketplacePayment record
#                        marketplace_payment = MarketplacePayment(
#                            user_id=user.id,
#                            subscription_id=plan.id,
#                            amount=payment_amount,
#                            currency=currency,
#                            tokens_paid=int(payment_amount * 100),
#                            gateway="flutterwave",
#                            gateway_reference=tx_ref,
#                            gateway_payment_id=result["data"].get("id"),
#                            gateway_status="initiated",
#                            gateway_metadata=json.dumps(result.get("data", {})),
#                            status="pending",
#                            payment_method="card",
#                            description=f"Marketplace Subscription: {plan.name}",
#                            start_date=utcnow(),
#                            end_date=utcnow()
#                            + timedelta(days=getattr(plan, "duration_days", 30)),
#                        )

#                        db.session.add(marketplace_payment)
#                        db.session.commit()

#                        print(
#                            f"✅ [MARKETPLACE PAYMENT] Payment record created: {marketplace_payment.id}"
#                        )

#                        return {
#                            "success": True,
#                            "payment_url": payment_url,
#                            "payment_id": marketplace_payment.id,
#                            "gateway_reference": tx_ref,
#                            "message": "Marketplace subscription payment initiated successfully",
#                        }
#                    else:
#                        error_msg = result.get("message", "Unknown Flutterwave error")
#                        print(
#                            f"🔴 [MARKETPLACE PAYMENT] Flutterwave error: {error_msg}"
#                        )
#                        return {
#                            "success": False,
#                            "error": f"Payment gateway error: {error_msg}",
#                        }

#                except json.JSONDecodeError as e:
#                    print(f"🔴 [MARKETPLACE PAYMENT] Failed to parse JSON: {e}")
#                    print(f"🔴 [MARKETPLACE PAYMENT] Raw response: {response_text}")
#                    return {
#                        "success": False,
#                        "error": f"Invalid response from payment gateway: {response_text[:200]}",
#                    }
#            else:
#                error_text = (
#                    response.text[:500]
#                    if hasattr(response, "text")
#                    else "No response text"
#                )
#                print(
#                    f"🔴 [MARKETPLACE PAYMENT] HTTP error {response.status_code}: {error_text}"
#                )
#                return {
#                    "success": False,
#                    "error": f"Payment gateway returned error: {response.status_code} - {error_text}",
#                }

#        except Exception as e:
#            print(f"🔴 [MARKETPLACE PAYMENT] Exception: {str(e)}")
#            import traceback

#            print(f"🔴 [MARKETPLACE PAYMENT] Traceback:\n{traceback.format_exc()}")
#            if isinstance(e, UpstreamServiceError):
#                return {
#                    "success": False,
#                    "error": "Payment provider is temporarily unreachable. Please try again in a moment.",
#                    "error_type": "upstream_unavailable",
#                }
#            return {"success": False, "error": f"Payment processing error: {str(e)}"}

#    def create_paystack_marketplace_payment(self, user, plan, currency="USD"):
#        """Create Paystack payment for marketplace subscription"""
#        try:
#            from marketplace.market import get_marketplace_checkout_amount
#            payment_amount = get_marketplace_checkout_amount(plan, currency)

#            print(f"[INFO] [PAYSTACK SUBSCRIPTION] Starting payment for plan: {plan.name}")
#            print(f"[INFO] [PAYSTACK SUBSCRIPTION] User: {user.id}, Amount: {payment_amount} {currency}")

            # Import PaystackService dynamically
#            from utils.paystack import PaystackService
#            paystack_service = PaystackService()

            # Generate transaction reference
#            import time
#            tx_ref = f"KIMBELA_MARKET_{user.id}_{int(time.time())}"

#            print(f"[INFO] [PAYSTACK SUBSCRIPTION] TX Ref: {tx_ref}")

#            callback_url = url_for("market.subscription_callback", _external=True)

#            metadata = {
#                "user_id": user.id,
#                "plan_id": plan.id,
#                "plan_name": plan.name,
#                "transaction_type": "marketplace_subscription",
#                "custom_fields": [
#                    {
#                        "display_name": "Plan Name",
#                        "variable_name": "plan_name",
#                        "value": plan.name
#                    }
#                ]
#            }

            # Initialize Paystack payment
#            result = paystack_service.initialize_transaction(
#                email=user.email,
#                amount=float(payment_amount),
#                reference=tx_ref,
#                callback_url=callback_url,
#                metadata=metadata
#            )

#            print(f"[INFO] [PAYSTACK SUBSCRIPTION] Result: {result}")

#            if result.get("status"):
#                payment_url = result["data"]["authorization_url"]
                
                # Create MarketplacePayment record
#                marketplace_payment = MarketplacePayment(
#                    user_id=user.id,
#                    subscription_id=plan.id,
#                    amount=payment_amount,
#                    currency=currency,
#                    tokens_paid=int(payment_amount * 100),
#                    gateway="paystack",
#                    gateway_reference=tx_ref,
#                    gateway_payment_id=result["data"].get("reference"),
#                    gateway_status="initiated",
#                    gateway_metadata=json.dumps(result.get("data", {})),
#                    status="pending",
#                    payment_method="card",
#                    description=f"Marketplace Subscription: {plan.name}",
#                    start_date=utcnow(),
#                    end_date=utcnow() + timedelta(days=getattr(plan, "duration_days", 30)),
#                )

#                db.session.add(marketplace_payment)
#                db.session.commit()

#                print(f"[SUCCESS] [PAYSTACK SUBSCRIPTION] Payment record created: {marketplace_payment.id}")

#                return {
#                    "success": True,
#                    "payment_url": payment_url,
#                    "payment_id": marketplace_payment.id,
#                    "gateway_reference": tx_ref,
#                    "message": "Marketplace subscription payment initiated successfully",
#                }
#            else:
#                return {
#                    "success": False,
#                    "error": result.get("message", "Paystack initialization failed"),
#                }

#        except Exception as e:
#            print(f"[ERROR] [PAYSTACK SUBSCRIPTION] Exception: {str(e)}")
#            import traceback
#            print(f"[ERROR] [PAYSTACK SUBSCRIPTION] Traceback:\n{traceback.format_exc()}")
#            return {"success": False, "error": f"Payment processing error: {str(e)}"}

#    def handle_marketplace_payment_success(self, marketplace_payment, flutterwave_data):
#        """Handle successful marketplace payment"""
#        try:
#            print(
#                f"🟡 [PAYMENT SUCCESS] Starting to handle successful payment for payment ID: {marketplace_payment.id}"
#            )

            # Update marketplace payment record
#            marketplace_payment.status = "completed"
#            marketplace_payment.gateway_status = flutterwave_data.get(
#                "status", "successful"
#            )
#            marketplace_payment.gateway_payment_id = flutterwave_data.get("id")
#            marketplace_payment.gateway_metadata = json.dumps(flutterwave_data)
#            marketplace_payment.paid_at = utcnow()
#            marketplace_payment.updated_at = utcnow()

#            print(
#                f"🟡 [PAYMENT SUCCESS] Updated payment record: {marketplace_payment.id}"
#            )

            # Update user subscription
#            user = marketplace_payment.user
#            if user:
#                user.marketplace_subscription_id = marketplace_payment.subscription_id
#                user.marketplace_subscription_status = "active"
#                user.marketplace_subscription_expires = utcnow() + timedelta(
#                    days=30
#                )  # Adjust as needed

                # Set featured until date if plan includes featured status
                # You might need to check the subscription plan details

#                print(f"✅ [PAYMENT SUCCESS] User subscription updated: {user.id}")

#                waiting_services = MarketplaceService.query.filter_by(
#                    seller_id=user.id, status="awaiting_subscription"
#                ).all()
#                for service in waiting_services:
#                    service.status = "active"
#                    service.subscription_status = "active"
#                    if not service.published_at:
#                        service.published_at = utcnow()

#            db.session.commit()
#            print(f"✅ [PAYMENT SUCCESS] Database committed successfully")

            # Send success email
#            self.send_marketplace_payment_success_email(marketplace_payment)

#            return True

#        except Exception as e:
#            db.session.rollback()
#            print(f"🔴 [PAYMENT SUCCESS] Exception: {str(e)}")
#            import traceback

#            print(f"🔴 [PAYMENT SUCCESS] Traceback: {traceback.format_exc()}")
#            return False

#    def send_marketplace_payment_success_email(self, transaction):
#        """Send payment success email for marketplace subscription"""
#        try:
#            user = transaction.user
#            if not user:
#                return False

            # Parse plan info from meta
#            meta_data = (
#                json.loads(transaction.meta_data) if transaction.meta_data else {}
#            )
#            meta = meta_data.get("meta", {})
#            plan_name = meta.get("plan_name", "Marketplace Subscription")

#            subject = "🎉 Your Kimbela Marketplace Subscription is Active!"

#            html_body = f"""
#            <!DOCTYPE html>
#            <html>
#            <head>
#                <style>
#                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
#                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
#                    .header {{ background: linear-gradient(135deg, #D97706 0%, #FBBF24 100%); color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0; }}
#                    .content {{ background: #FFFBEB; padding: 20px; border-radius: 0 0 10px 10px; }}
#                    .details {{ background: white; padding: 15px; border-radius: 5px; margin: 10px 0; border-left: 4px solid #D97706; }}
#                    .footer {{ text-align: center; margin-top: 20px; color: #666; font-size: 12px; }}
#                </style>
#            </head>
#            <body>
#                <div class="container">
#                    <div class="header">
#                        <h1>🎉 Welcome to Kimbela Marketplace!</h1>
#                        <p>Your seller subscription is now active</p>
#                    </div>
#                    <div class="content">
#                        <p>Hello {user.full_name},</p>
#                        <p>Congratulations! Your Kimbela Marketplace subscription has been successfully activated. You can now start selling your services and digital products.</p>
                        
#                        <div class="details">
#                            <h3>📋 Subscription Details</h3>
#                            <p><strong>Plan:</strong> {plan_name}</p>
#                            <p><strong>Amount Paid:</strong> {transaction.amount:.2f} {transaction.currency}</p>
#                            <p><strong>Transaction ID:</strong> {transaction.gateway_reference}</p>
#                            <p><strong>Activation Date:</strong> {utcnow().strftime('%B %d, %Y %I:%M %p')}</p>
#                            <p><strong>Status:</strong> <span style="color: #10B981; font-weight: bold;">Active ✅</span></p>
#                        </div>
                        
#                        <div class="details">
#                            <h3>🚀 Next Steps</h3>
#                            <p>1. <a href="{current_app.config.get('BASE_URL', 'http://localhost:5000')}/market/create_service" style="color: #D97706; font-weight: bold;">Create your first service listing</a></p>
#                            <p>2. Complete your seller profile</p>
#                            <p>3. Add your contact information</p>
#                            <p>4. Start promoting your services</p>
#                        </div>
                        
#                        <div class="details">
#                            <h3>💡 Tips for Success</h3>
#                            <p>• Use high-quality images for your services</p>
#                            <p>• Write detailed descriptions</p>
#                            <p>• Set competitive prices</p>
#                            <p>• Respond quickly to inquiries</p>
#                            <p>• Ask satisfied clients for reviews</p>
#                        </div>
                        
#                        <p>Need help getting started? Visit our <a href="{current_app.config.get('BASE_URL', 'http://localhost:5000')}/help/marketplace" style="color: #D97706; font-weight: bold;">Marketplace Seller Guide</a> for tips and best practices.</p>
                        
#                        <p>Happy selling!<br>The Kimbela Marketplace Team</p>
#                    </div>
#                    <div class="footer">
#                        <p>© {utcnow().year} Kimbela Marketplace. Empowering African creators and professionals.</p>
#                    </div>
#                </div>
#            </body>
#            </html>
#            """

#            return self._send_email(subject, user.email, html_body)

#        except Exception as e:
#            print(f"❌ Failed to send marketplace success email: {str(e)}")
#            return False


#class MarketplacePaymentService(BasePaymentService):
#    """Payment service for marketplace subscriptions"""

#    def __init__(self):
#        super().__init__()
#        self.email_service = MarketplaceEmailService()  # Add email service

#    def _get_marketplace_payment_amount(self, plan, currency):
#        currency = self.normalize_currency(currency)
#        return float(plan.price_usd)

#    def create_marketplace_payment(self, user, plan, currency="USD", gateway="flutterwave"):
#        """Create payment for marketplace subscription"""
#        try:
#            currency = self.normalize_currency(currency)
#            print(f"[INFO] [MARKETPLACE PAYMENT] Starting payment for plan: {plan.name}")
#            print(
#                f"[INFO] [MARKETPLACE PAYMENT] User: {user.id}, Currency: {currency}, Gateway: {gateway}"
#            )

            # Generate transaction reference
#            import time

#            tx_ref = f"KIMBELA_MARKET_{user.id}_{int(time.time())}"
#            payment_amount = self._get_marketplace_payment_amount(plan, currency)

#            if gateway == "paystack":
#                payment_data = {
#                    "email": user.email,
#                    "amount": int(payment_amount * 100),  # Paystack uses kobo
#                    "currency": currency,
#                    "reference": tx_ref,
#                    "callback_url": url_for("market.subscription_callback", _external=True),
#                    "metadata": {
#                        "user_id": user.id,
#                        "plan_id": plan.id,
#                        "plan_name": plan.name,
#                        "transaction_type": "marketplace_subscription",
#                    }
#                }

#                headers = {
#                    "Authorization": f"Bearer {self.paystack_secret_key}",
#                    "Content-Type": "application/json",
#                }

#                print(f"[INFO] [MARKETPLACE PAYMENT] Sending request to Paystack...")

#                response = self._http_request(
#                    "POST",
#                    f"{self.paystack_base_url}/transaction/initialize",
#                    headers=headers,
#                    json=payment_data,
#                    timeout=30,
#                )

#                if response.status_code == 200:
#                    result = response.json()
#                    if result.get("status") is True:
#                        payment_url = result["data"]["authorization_url"]

#                        marketplace_payment = MarketplacePayment(
#                            user_id=user.id,
#                            subscription_id=plan.id,
#                            amount=payment_amount,
#                            currency=currency,
#                            tokens_paid=int(payment_amount * 100),
#                            gateway="paystack",
#                            gateway_reference=tx_ref,
#                            gateway_status="initiated",
#                            status="pending",
#                            payment_method="card",
#                        )
#                        db.session.add(marketplace_payment)
#                        db.session.commit()

#                        return {
#                            "success": True,
#                            "payment_url": payment_url,
#                            "gateway_reference": tx_ref,
#                            "message": "Marketplace payment initiated successfully via Paystack",
#                        }
#                    else:
#                        return {"success": False, "error": f"Paystack error: {result.get('message')}"}
#                else:
#                    return {"success": False, "error": f"Paystack returned error: {response.status_code}"}

            # Prepare payment data
            payment_data = {
                "tx_ref": tx_ref,
                "amount": str(float(payment_amount)),
                "currency": currency,
                "redirect_url": url_for("market.subscription_callback", _external=True),
                "payment_options": "card",
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

            print(f"[INFO] [MARKETPLACE PAYMENT] Sending request to Flutterwave...")

            response = self._http_request(
                "POST",
                f"{self.flutterwave_base_url}/payments",
                headers=headers,
                json=payment_data,
                timeout=30,
            )

            print(f"[INFO] [MARKETPLACE PAYMENT] Response status: {response.status_code}")

            if response.status_code == 200:
                result = response.json()
                print(
                    f"[INFO] [MARKETPLACE PAYMENT] Flutterwave response: {json.dumps(result, indent=2)}"
                )

                if result.get("status") == "success":
                    payment_url = result["data"]["link"]
                    print(
                        f"[SUCCESS] [MARKETPLACE PAYMENT] Payment URL generated: {payment_url}"
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
                    print(f"[ERROR] [MARKETPLACE PAYMENT] Flutterwave error: {error_msg}")
                    return {
                        "success": False,
                        "error": f"Payment gateway error: {error_msg}",
                    }
            else:
                print(
                    f"[ERROR] [MARKETPLACE PAYMENT] HTTP error {response.status_code}: {response.text}"
                )
                return {
                    "success": False,
                    "error": f"Payment gateway returned error: {response.status_code}",
                }

        except Exception as e:
            print(f"[ERROR] [MARKETPLACE PAYMENT] Exception: {str(e)}")
            import traceback

            print(f"[ERROR] [MARKETPLACE PAYMENT] Traceback:\n{traceback.format_exc()}")
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
            print(f"[INFO] [PAYMENT SUCCESS] Starting to handle successful payment")

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

                waiting_services = MarketplaceService.query.filter_by(
                    seller_id=user.id, status="awaiting_subscription"
                ).all()
                for service in waiting_services:
                    service.status = "active"
                    service.subscription_status = "active"
                    if not service.published_at:
                        service.published_at = utcnow()

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
            gateway_status = flutterwave_data.get("status", "failed")

            if self.is_success_status(gateway_status) or self.is_pending_status(
                gateway_status
            ):
                marketplace_payment.gateway_status = gateway_status
                marketplace_payment.gateway_metadata = json.dumps(flutterwave_data)
                marketplace_payment.updated_at = utcnow()
                db.session.commit()
                print(
                    f"⚠️ [PAYMENT FAILURE] Skipped failure email because provider status is {gateway_status}"
                )
                return True

            # Update payment record
            marketplace_payment.status = "failed"
            marketplace_payment.gateway_status = gateway_status
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
