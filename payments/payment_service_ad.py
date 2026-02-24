from time_utils import utcnow
# payment_service_ad.py
import json
from flask import url_for
from extensions import db
from models import PaymentTransaction, AdCampaign, User
import time
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class AdCampaignPaymentService:
    def __init__(self):
        # Lazy import to avoid circular imports
        from .payment_service import BasePaymentService

        self.base = BasePaymentService()

        # ✅ FIX: Access Flutterwave credentials through the base service
        self.FLW_SECRET_KEY = self.base.flutterwave_secret_key
        self.flutterwave_base_url = self.base.flutterwave_base_url

    def _http_request(self, method, url, **kwargs):
        """Delegate HTTP requests to base service"""
        return self.base._http_request(method, url, **kwargs)

    def _send_email(self, subject, recipient, html_body):
        """Delegate email sending to base service"""
        return self.base._send_email(subject, recipient, html_body)

    def create_ad_campaign_payment(self, user, campaign, currency="USD"):
        """Create Flutterwave payment for ad campaigns"""
        try:
            print(f"🟡 [AD PAYMENT] Starting payment for campaign: {campaign.id}")
            print(
                "🟡 [AD PAYMENT] Secret key present"
                if self.FLW_SECRET_KEY
                else "🔴 [AD PAYMENT] No secret key!"
            )

            # Generate unique transaction reference
            tx_ref = f"KIMBELA_AD_{campaign.id}_{int(time.time())}"

            # Prepare payment data
            payment_data = {
                "tx_ref": tx_ref,
                "amount": str(float(campaign.budget)),
                "currency": currency,
                "redirect_url": url_for("payments.payment_callback", _external=True),
                "customer": {
                    "email": user.email,
                    "name": user.first_name or user.email.split("@")[0],
                },
                "meta": {
                    "user_id": user.id,
                    "campaign_id": campaign.id,
                    "transaction_type": "ad_campaign",
                },
                "customizations": {
                    "title": "Kimbela Ads",
                    "description": f"Ad Campaign: {campaign.title}",
                    "logo": url_for(
                        "static", filename="images/logo.png", _external=True
                    ),
                },
            }

            headers = {
                "Authorization": f"Bearer {self.FLW_SECRET_KEY}",
                "Content-Type": "application/json",
            }

            print(f"🟡 [AD PAYMENT] Sending request to Flutterwave...")

            response = self._http_request(
                "POST",
                f"{self.flutterwave_base_url}/payments",
                headers=headers,
                json=payment_data,
                timeout=30,
            )

            print(f"🟡 [AD PAYMENT] Response status: {response.status_code}")

            if response.status_code == 200:
                result = response.json()
                print(
                    f"🟡 [AD PAYMENT] Flutterwave response: {json.dumps(result, indent=2)}"
                )

                if result.get("status") == "success":
                    payment_url = result["data"]["link"]
                    print(f"✅ [AD PAYMENT] Payment URL generated: {payment_url}")

                    # Create payment record
                    payment = PaymentTransaction(
                        user_id=user.id,
                        campaign_id=campaign.id,
                        amount=campaign.budget,
                        currency=currency,
                        gateway_payment_id=tx_ref,
                        gateway="flutterwave",
                        status="pending",
                        transaction_type="ad_campaign",
                    )
                    db.session.add(payment)
                    db.session.commit()

                    return {
                        "success": True,
                        "payment_url": payment_url,
                        "gateway_payment_id": tx_ref,
                        "message": "Ad campaign payment initiated successfully",
                    }
                else:
                    error_msg = result.get("message", "Unknown Flutterwave error")
                    print(f"🔴 [AD PAYMENT] Flutterwave error: {error_msg}")
                    return {
                        "success": False,
                        "error": f"Payment gateway error: {error_msg}",
                    }
            else:
                error_text = response.text
                print(
                    f"🔴 [AD PAYMENT] HTTP error {response.status_code}: {error_text}"
                )
                return {
                    "success": False,
                    "error": f"Payment gateway returned error: {response.status_code}",
                }

        except Exception as e:
            print(f"🔴 [AD PAYMENT] Exception: {str(e)}")
            import traceback

            print(f"🔴 [AD PAYMENT] Traceback: {traceback.format_exc()}")
            return {"success": False, "error": f"Payment processing error: {str(e)}"}

    def handle_ad_payment_success(self, transaction_id, payment_data=None):
        """Handle successful ad campaign payment"""
        try:
            transaction = PaymentTransaction.query.get(transaction_id)
            if not transaction:
                return False

            campaign = AdCampaign.query.get(transaction.campaign_id)
            if not campaign:
                return False

            # Update transaction
            transaction.status = "completed"
            transaction.gateway_status = "successful"
            if payment_data:
                transaction.gateway_metadata = json.dumps(payment_data)
            transaction.updated_at = utcnow()

            # Update campaign
            campaign.payment_status = "paid"
            campaign.status = "active"
            campaign.payment_gateway = "flutterwave"
            campaign.payment_id = transaction.gateway_payment_id
            campaign.start_date = utcnow()

            # Calculate end date
            duration_days = getattr(campaign, "duration_days", 30)
            campaign.end_date = utcnow() + timedelta(days=duration_days)
            campaign.updated_at = utcnow()

            db.session.commit()

            # Send success email
            self.send_ad_payment_success_email(
                transaction.user_id, campaign, transaction
            )

            return True

        except Exception as e:
            db.session.rollback()
            print(f"🔴 [AD PAYMENT SUCCESS] Exception: {str(e)}")
            return False

    def handle_ad_payment_failure(self, transaction_id, payment_data=None):
        """Handle failed ad campaign payment"""
        try:
            transaction = PaymentTransaction.query.get(transaction_id)
            if not transaction:
                return False

            # Update transaction status
            transaction.status = "failed"
            transaction.gateway_status = (
                payment_data.get("status", "failed") if payment_data else "failed"
            )
            transaction.gateway_metadata = (
                json.dumps(payment_data)
                if payment_data
                else transaction.gateway_metadata
            )
            transaction.updated_at = utcnow()

            campaign = AdCampaign.query.get(transaction.campaign_id)
            if campaign:
                campaign.payment_status = "failed"
                campaign.status = "pending"
                campaign.updated_at = utcnow()
                self.send_ad_payment_failed_email(
                    transaction.user_id, campaign, transaction
                )

            db.session.commit()
            return True

        except Exception as e:
            db.session.rollback()
            return False

    def send_ad_payment_success_email(self, user_id, campaign, transaction):
        """Send payment success email for ad campaigns"""
        try:
            user = User.query.get(user_id)
            if not user:
                return False

            expiry_date = campaign.end_date.strftime("%B %d, %Y")
            duration_days = getattr(campaign, "duration_days", 30)

            subject = "🎉 Your Kimbela Ad Campaign is Live!"

            html_body = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0; }}
                    .content {{ background: #f9f9f9; padding: 20px; border-radius: 0 0 10px 10px; }}
                    .details {{ background: white; padding: 15px; border-radius: 5px; margin: 10px 0; }}
                    .footer {{ text-align: center; margin-top: 20px; color: #666; font-size: 12px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>🎉 Ad Campaign Activated!</h1>
                        <p>Your Kimbela advertising campaign is now live</p>
                    </div>
                    <div class="content">
                        <p>Hello {user.full_name},</p>
                        <p>Great news! Your ad campaign has been successfully activated and is now running on Kimbela.</p>
                        
                        <div class="details">
                            <h3>📊 Campaign Details</h3>
                            <p><strong>Campaign Title:</strong> {campaign.title}</p>
                            <p><strong>Description:</strong> {campaign.description or 'N/A'}</p>
                            <p><strong>Total Amount:</strong> {transaction.amount:.2f} {transaction.currency}</p>
                            <p><strong>Duration:</strong> {duration_days} days</p>
                            <p><strong>Start Date:</strong> {campaign.start_date.strftime('%B %d, %Y')}</p>
                            <p><strong>Expiry Date:</strong> {expiry_date}</p>
                        </div>
                        
                        <div class="details">
                            <h3>📈 What's Next?</h3>
                            <p>• Your ad is now visible to our community</p>                           
                            <p>• Campaign will automatically end on {expiry_date}</p>
                        </div>
                        
                        <p>Need help? Contact our support team anytime.</p>
                        
                        <p>Best regards,<br>The Kimbela Team</p>
                    </div>
                    <div class="footer">
                        <p>© 2024 Kimbela. All rights reserved.</p>
                    </div>
                </div>
            </body>
            </html>
            """

            return self._send_email(subject, user.email, html_body)

        except Exception as e:
            print(f"❌ Failed to send ad success email: {str(e)}")
            return False

    def send_ad_payment_failed_email(self, user_id, campaign, transaction):
        """Send payment failure email for ad campaigns"""
        try:
            user = User.query.get(user_id)
            if not user:
                return False

            subject = "❌ Payment Failed - Kimbela Ad Campaign"

            html_body = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background: #dc3545; color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0; }}
                    .content {{ background: #f9f9f9; padding: 20px; border-radius: 0 0 10px 10px; }}
                    .footer {{ text-align: center; margin-top: 20px; color: #666; font-size: 12px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>❌ Payment Failed</h1>
                        <p>Your Kimbela ad campaign payment was not successful</p>
                    </div>
                    <div class="content">
                        <p>Hello {user.full_name},</p>
                        <p>We were unable to process the payment for your ad campaign. Your campaign has been saved as a draft and will not be activated until payment is completed.</p>
                        
                        <p><strong>Campaign:</strong> {campaign.title}</p>
                        <p><strong>Amount:</strong> ${transaction.amount:.2f} {transaction.currency}</p>
                        
                        <p>You can retry the payment from your dashboard or try a different payment method.</p>
                        
                        <p>If you believe this is an error, please contact our support team for assistance.</p>
                        
                        <p>Best regards,<br>The Kimbela Team</p>
                    </div>
                    <div class="footer">
                        <p>© 2024 Kimbela. All rights reserved.</p>
                    </div>
                </div>
            </body>
            </html>
            """

            return self._send_email(subject, user.email, html_body)

        except Exception as e:
            print(f"❌ Failed to send ad failure email: {str(e)}")
            return False