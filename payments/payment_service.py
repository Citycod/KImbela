import requests as http_requests
import json
from flask import current_app, url_for
from extensions import db
from models import PaymentTransaction, AdCampaign, User, MatchmakingRequest, MatchmakingPackage
import logging
import os, time
from datetime import datetime, timedelta
from flask_mail import Message
from extensions import mail
from models import PaymentTransaction, AdCampaign, User, MatchmakingRequest, MatchmakingPackage, MatchmakingPayments

logger = logging.getLogger(__name__)

class BasePaymentService:
    """Base payment service with common functionality"""
    def __init__(self):
        # Use the correct environment variable names that actually exist
        self.flutterwave_public_key = os.getenv('FLW_PUBLIC_KEY')
        self.flutterwave_secret_key = os.getenv('FLW_SECRET_KEY')
        self.flutterwave_base_url = "https://api.flutterwave.com/v3"
        
        print(f"🟡 [BASE PAYMENT INIT] Public Key configured: {self.flutterwave_public_key is not None}")
        print(f"🟡 [BASE PAYMENT INIT] Secret Key configured: {self.flutterwave_secret_key is not None}")
        
        if self.flutterwave_public_key:
            print(f"🟡 [BASE PAYMENT INIT] Public Key: {self.flutterwave_public_key[:20]}...")
        if self.flutterwave_secret_key:
            print(f"🟡 [BASE PAYMENT INIT] Secret Key: {self.flutterwave_secret_key[:20]}...")
            
    def _http_request(self, method, url, **kwargs):
        """Safe HTTP request method that re-imports requests"""
        import requests as http_requests
        method_func = getattr(http_requests, method.lower())
        return method_func(url, **kwargs)

    def verify_flutterwave_payment(self, transaction_id):
        """Verify Flutterwave payment using transaction ID"""
        try:
            headers = {
                'Authorization': f'Bearer {self.flutterwave_secret_key}',
                'Content-Type': 'application/json'
            }
            
            response = self._http_request(
                'GET',
                f'{self.flutterwave_base_url}/transactions/{transaction_id}/verify',
                headers=headers,
                timeout=30
            )
            
            print(f"🟡 [VERIFY PAYMENT] Response status: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                print(f"🟡 [VERIFY PAYMENT] Verification result: {result}")
                return {
                    'success': result.get('status') == 'success',
                    'data': result.get('data', {})
                }
            
            print(f"🔴 [VERIFY PAYMENT] HTTP Error: {response.status_code} - {response.text}")
            return {
                'success': False, 
                'error': f'HTTP {response.status_code}',
                'data': {}
            }
        
        except Exception as e:
            print(f"🔴 [VERIFY PAYMENT] Exception: {str(e)}")
            return {
                'success': False, 
                'error': str(e),
                'data': {}
            }

    def _send_email(self, subject, recipient, html_body):
        """Helper method to send emails"""
        try:
            msg = Message(
                subject=subject,
                recipients=[recipient],
                html=html_body,
                sender=current_app.config.get('MAIL_DEFAULT_SENDER')
            )
            mail.send(msg)
            print(f"✅ [EMAIL] Sent to {recipient}")
            return True
        except Exception as e:
            print(f"❌ [EMAIL] Failed to send: {str(e)}")
            return False


class AdCampaignPaymentService(BasePaymentService):
    """Payment service specifically for ad campaigns"""
    
    def create_ad_campaign_payment(self, user, campaign, currency='USD'):
        """Create Flutterwave payment for ad campaigns"""
        try:
            print(f"🟡 [AD PAYMENT] Starting payment for campaign: {campaign.id}")
            
            # Generate unique transaction reference
            tx_ref = f"KIMBELA_AD_{campaign.id}_{int(time.time())}"
            
            # Prepare payment data
            payment_data = {
                "tx_ref": tx_ref,
                "amount": str(float(campaign.budget)),
                "currency": currency,
                "redirect_url": url_for('payments.payment_callback', _external=True),
                "customer": {
                    "email": user.email,
                    "name": user.first_name or user.email.split('@')[0]
                },
                "meta": {
                    "user_id": user.id,
                    "campaign_id": campaign.id,
                    "transaction_type": "ad_campaign"
                },
                "customizations": {
                    "title": "Kimbela Ads",
                    "description": f"Ad Campaign: {campaign.title}",
                    "logo": url_for('static', filename='images/logo.png', _external=True)
                }
            }
            
            headers = {
                'Authorization': f'Bearer {self.flutterwave_secret_key}',
                'Content-Type': 'application/json'
            }
            
            response = self._http_request(
                'POST',
                f"{self.flutterwave_base_url}/payments",
                headers=headers,
                json=payment_data,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                
                if result.get('status') == 'success':
                    payment_url = result['data']['link']
                    
                    # Create payment record
                    payment = PaymentTransaction(
                        user_id=user.id,
                        campaign_id=campaign.id,
                        amount=campaign.budget,
                        currency=currency,
                        gateway_payment_id=tx_ref,
                        gateway='flutterwave',
                        status='pending',
                        transaction_type='ad_campaign'
                    )
                    db.session.add(payment)
                    db.session.commit()
                    
                    return {
                        'success': True,
                        'payment_url': payment_url,
                        'gateway_payment_id': tx_ref,
                        'message': 'Ad campaign payment initiated successfully'
                    }
                else:
                    error_msg = result.get('message', 'Unknown Flutterwave error')
                    return {
                        'success': False,
                        'error': f'Payment gateway error: {error_msg}'
                    }
            else:
                return {
                    'success': False,
                    'error': f'Payment gateway returned error: {response.status_code}'
                }
                
        except Exception as e:
            print(f"🔴 [AD PAYMENT] Exception: {str(e)}")
            return {
                'success': False,
                'error': f'Payment processing error: {str(e)}'
            }

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
            transaction.status = 'completed'
            transaction.gateway_status = 'successful'
            if payment_data:
                transaction.gateway_metadata = json.dumps(payment_data)
            transaction.updated_at = datetime.utcnow()
            
            # Update campaign
            campaign.payment_status = 'paid'
            campaign.status = 'active'
            campaign.payment_gateway = 'flutterwave'
            campaign.payment_id = transaction.gateway_payment_id
            campaign.start_date = datetime.utcnow()
            
            # Calculate end date
            duration_days = getattr(campaign, 'duration_days', 30)
            campaign.end_date = datetime.utcnow() + timedelta(days=duration_days)
            campaign.updated_at = datetime.utcnow()
            
            db.session.commit()
            
            # Send success email
            self.send_ad_payment_success_email(transaction.user_id, campaign, transaction)
            
            return True
            
        except Exception as e:
            db.session.rollback()
            return False

    def handle_ad_payment_failure(self, transaction_id, payment_data=None):
        """Handle failed ad campaign payment"""
        try:
            transaction = PaymentTransaction.query.get(transaction_id)
            if not transaction:
                return False
            
            # Update transaction status
            transaction.status = 'failed'
            transaction.gateway_status = payment_data.get('status', 'failed') if payment_data else 'failed'
            transaction.gateway_metadata = json.dumps(payment_data) if payment_data else transaction.gateway_metadata
            transaction.updated_at = datetime.utcnow()
            
            campaign = AdCampaign.query.get(transaction.campaign_id)
            if campaign:
                campaign.payment_status = 'failed'
                campaign.status = 'pending'
                campaign.updated_at = datetime.utcnow()
                self.send_ad_payment_failed_email(transaction.user_id, campaign, transaction)
            
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
            
            expiry_date = campaign.end_date.strftime('%B %d, %Y')
            duration_days = getattr(campaign, 'duration_days', 30)
            
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
                        
                        <p>You can retry the payment from your <a href="{current_app.config.get('BASE_URL', 'http://localhost:5000')}/user/dashboard">dashboard</a> or try a different payment method.</p>
                        
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


class MatchmakingPaymentService(BasePaymentService):
    """Payment service specifically for matchmaking requests"""
    
    def __init__(self):
        super().__init__()
        self._validate_keys()
    
    def _validate_keys(self):
        """Validate that Flutterwave keys are properly configured"""
        print(f"🔑 [KEY VALIDATION] Public Key: {'✅ SET' if self.flutterwave_public_key else '❌ MISSING'}")
        print(f"🔑 [KEY VALIDATION] Secret Key: {'✅ SET' if self.flutterwave_secret_key else '❌ MISSING'}")
        
        if not self.flutterwave_secret_key:
            raise ValueError("Flutterwave secret key is not configured")
        
        # Test key format (Flutterwave keys typically start with specific prefixes)
        if self.flutterwave_secret_key and not self.flutterwave_secret_key.startswith(('FLWSECK-', 'FLWSECK_TEST-')):
            print("⚠️ [KEY VALIDATION] Secret key format may be incorrect")
        
        if self.flutterwave_public_key and not self.flutterwave_public_key.startswith(('FLWPUBK-', 'FLWPUBK_TEST-')):
            print("⚠️ [KEY VALIDATION] Public key format may be incorrect")
        
        print(f"✅ [KEY VALIDATION] Keys validated successfully")

    def create_matchmaking_payment(self, user, matchmaking_request, package, currency='USD', amount=None):
        """Create Flutterwave payment for matchmaking request"""
        try:
            print(f"🟡 [MATCHMAKING PAYMENT] Starting payment process")
            print(f"🟡 [MATCHMAKING PAYMENT] User: {user.id}, Request: {matchmaking_request.id}, Package: {package.name}")
            
            # Use provided amount or fallback to package price
            payment_amount = amount if amount is not None else package.price
            
            # Generate unique transaction reference
            tx_ref = f"KIMBELA_MATCH_{matchmaking_request.id}_{int(time.time())}"
            
            # Prepare payment data for matchmaking
            payment_data = {
                "tx_ref": tx_ref,
                "amount": str(float(payment_amount)),
                "currency": currency,
                "redirect_url": url_for('match.payment_callback', _external=True),
                "customer": {
                    "email": user.email,
                    "name": user.full_name or user.first_name or user.email.split('@')[0],
                },
                "meta": {
                    "user_id": user.id,
                    "matchmaking_request_id": matchmaking_request.id,
                    "package_id": package.id,
                    "transaction_type": "matchmaking"
                },
                "customizations": {
                    "title": "Kimbela Matchmaking",
                    "description": f"Matchmaking Package: {package.name}",
                }
            }
            
            # Add phone number if available
            if hasattr(user, 'phone_number') and user.phone_number:
                payment_data["customer"]["phone_number"] = user.phone_number
            
            headers = {
                'Authorization': f'Bearer {self.flutterwave_secret_key}',
                'Content-Type': 'application/json'
            }
            
            print(f"🟡 [MATCHMAKING PAYMENT] Sending request to Flutterwave...")
            print(f"🟡 [MATCHMAKING PAYMENT] Using Secret Key: {self.flutterwave_secret_key[:20]}...")
            print(f"🟡 [MATCHMAKING PAYMENT] Request data: {json.dumps(payment_data, indent=2)}")
            
            response = self._http_request(
                'POST',
                f"{self.flutterwave_base_url}/payments",
                headers=headers,
                json=payment_data,
                timeout=30
            )
            
            print(f"🟡 [MATCHMAKING PAYMENT] Response status: {response.status_code}")
            print(f"🟡 [MATCHMAKING PAYMENT] Response headers: {dict(response.headers)}")
            
            if response.status_code == 200:
                result = response.json()
                print(f"🟡 [MATCHMAKING PAYMENT] Flutterwave response: {json.dumps(result, indent=2)}")
                
                if result.get('status') == 'success':
                    payment_url = result['data']['link']
                    print(f"✅ [MATCHMAKING PAYMENT] Payment URL generated: {payment_url}")
                    
                    # Create matchmaking payment record
                    matchmaking_payment = MatchmakingPayments(
                        user_id=user.id,
                        matchmaking_request_id=matchmaking_request.id,
                        package_id=package.id,
                        amount=package.price,
                        currency=currency,
                        gateway='flutterwave',
                        gateway_reference=tx_ref,
                        gateway_payment_id=result['data'].get('id'),
                        gateway_status='initiated',
                        status='pending',
                        payment_status='pending',
                        description=f"Matchmaking Package: {package.name}"
                    )
                    db.session.add(matchmaking_payment)
                    db.session.commit()
                    
                    return {
                        'success': True,
                        'payment_url': payment_url,
                        'payment_id': matchmaking_payment.id,
                        'gateway_reference': tx_ref,
                        'message': 'Matchmaking payment initiated successfully'
                    }
                else:
                    error_msg = result.get('message', 'Unknown Flutterwave error')
                    print(f"🔴 [MATCHMAKING PAYMENT] Flutterwave error: {error_msg}")
                    return {
                        'success': False,
                        'error': f'Payment gateway error: {error_msg}'
                    }
            else:
                error_text = response.text
                print(f"🔴 [MATCHMAKING PAYMENT] HTTP error {response.status_code}: {error_text}")
                
                # More specific error handling
                if response.status_code == 401:
                    return {
                        'success': False,
                        'error': 'Invalid Flutterwave API keys. Please check your environment variables.'
                    }
                elif response.status_code == 400:
                    try:
                        error_data = response.json()
                        return {
                            'success': False,
                            'error': f'Bad request: {error_data.get("message", "Unknown error")}'
                        }
                    except:
                        return {
                            'success': False,
                            'error': f'Bad request: {error_text}'
                        }
                else:
                    return {
                        'success': False,
                        'error': f'Payment gateway returned error: {response.status_code}'
                    }
                
        except Exception as e:
            print(f"🔴 [MATCHMAKING PAYMENT] Exception: {str(e)}")
            import traceback
            print(f"🔴 [MATCHMAKING PAYMENT] Traceback: {traceback.format_exc()}")
            return {
                'success': False,
                'error': f'Payment processing error: {str(e)}'
            }

    def handle_matchmaking_payment_success(self, matchmaking_payment, flutterwave_data):
        """Handle successful matchmaking payment"""
        try:
            print(f"🟡 [PAYMENT SUCCESS] Starting to handle successful payment for payment ID: {matchmaking_payment.id}")
            
            # Update matchmaking payment record
            matchmaking_payment.status = 'completed'
            matchmaking_payment.payment_status = 'paid'
            matchmaking_payment.gateway_status = flutterwave_data.get('status', 'successful')
            matchmaking_payment.gateway_payment_id = flutterwave_data.get('id')
            matchmaking_payment.gateway_metadata = json.dumps(flutterwave_data)
            matchmaking_payment.paid_at = datetime.utcnow()
            matchmaking_payment.updated_at = datetime.utcnow()
            
            print(f"🟡 [PAYMENT SUCCESS] Updated payment record: {matchmaking_payment.to_dict()}")
            
            # Get matchmaking request
            matchmaking_request = matchmaking_payment.matchmaking_request
            if not matchmaking_request:
                print(f"🔴 [PAYMENT SUCCESS] No matchmaking request found for payment {matchmaking_payment.id}")
                return False
            
            print(f"🟡 [PAYMENT SUCCESS] Found matchmaking request: {matchmaking_request.id}")
            
            # Update matchmaking request
            matchmaking_request.payment_status = 'completed'
            matchmaking_request.status = 'active'
            matchmaking_request.payment_gateway = 'flutterwave'
            
            # Calculate end date based on package duration
            if matchmaking_request.package:
                duration_days = matchmaking_request.package.duration_days
                matchmaking_request.end_date = datetime.utcnow() + timedelta(days=duration_days)
                print(f"🟡 [PAYMENT SUCCESS] Set end date to: {matchmaking_request.end_date}")
            
            matchmaking_request.updated_at = datetime.utcnow()
            
            db.session.commit()
            print(f"✅ [PAYMENT SUCCESS] Database committed successfully")
            
            # Send success email
            email_sent = self.send_matchmaking_payment_success_email(
                matchmaking_payment.user_id, 
                matchmaking_request, 
                matchmaking_payment
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
            matchmaking_payment.status = 'failed'
            matchmaking_payment.payment_status = 'failed'
            matchmaking_payment.gateway_status = flutterwave_data.get('status', 'failed')
            matchmaking_payment.gateway_metadata = json.dumps(flutterwave_data)
            matchmaking_payment.updated_at = datetime.utcnow()
            
            # Update matchmaking request
            matchmaking_request = matchmaking_payment.matchmaking_request
            if matchmaking_request:
                matchmaking_request.payment_status = 'failed'
                matchmaking_request.status = 'pending'
                matchmaking_request.updated_at = datetime.utcnow()
            
            db.session.commit()
            
            # Send failure email
            self.send_matchmaking_payment_failed_email(
                matchmaking_payment.user_id, 
                matchmaking_request, 
                matchmaking_payment
            )
            
            return True
            
        except Exception as e:
            db.session.rollback()
            return False

    def get_payment_by_reference(self, gateway_reference):
        """Get matchmaking payment by gateway reference"""
        return MatchmakingPayments.query.filter_by(gateway_reference=gateway_reference).first()

    def get_payment_by_id(self, payment_id):
        """Get matchmaking payment by ID"""
        return MatchmakingPayments.query.get(payment_id)

    def get_user_payments(self, user_id):
        """Get all matchmaking payments for a user"""
        return MatchmakingPayments.query.filter_by(user_id=user_id).order_by(MatchmakingPayments.created_at.desc()).all()

    def get_payment_by_gateway_id(self, gateway_payment_id):
        """Get matchmaking payment by gateway payment ID"""
        return MatchmakingPayments.query.filter_by(gateway_payment_id=gateway_payment_id).first()

    def send_matchmaking_payment_success_email(self, user_id, matchmaking_request, payment):
        """Send payment success email for matchmaking"""
        try:
            user = User.query.get(user_id)
            if not user:
                return False
            
            expiry_date = matchmaking_request.end_date.strftime('%B %d, %Y') if matchmaking_request.end_date else 'Not set'
            package_name = matchmaking_request.package.name if matchmaking_request.package else 'Standard'
            duration_days = matchmaking_request.package.duration_days if matchmaking_request.package else 30
            
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

    def send_matchmaking_payment_failed_email(self, user_id, matchmaking_request, payment):
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

    def retry_payment(self, payment_id, currency='USD'):
        """Retry a failed matchmaking payment"""
        try:
            matchmaking_payment = self.get_payment_by_id(payment_id)
            if not matchmaking_payment:
                return {
                    'success': False,
                    'error': 'Payment not found'
                }
            
            # Get related objects
            user = User.query.get(matchmaking_payment.user_id)
            matchmaking_request = MatchmakingRequest.query.get(matchmaking_payment.matchmaking_request_id)
            package = MatchmakingPackage.query.get(matchmaking_payment.package_id)
            
            if not all([user, matchmaking_request, package]):
                return {
                    'success': False,
                    'error': 'Missing payment details'
                }
            
            # Generate new transaction reference
            tx_ref = f"KIMBELA_MATCH_RETRY_{matchmaking_request.id}_{int(time.time())}"
            
            # Prepare payment data
            payment_data = {
                "tx_ref": tx_ref,
                "amount": str(float(package.price)),
                "currency": currency,
                "redirect_url": url_for('match.payment_callback', _external=True),
                "customer": {
                    "email": user.email,
                    "name": user.full_name or user.first_name or user.email.split('@')[0],
                },
                "meta": {
                    "user_id": user.id,
                    "matchmaking_request_id": matchmaking_request.id,
                    "package_id": package.id,
                    "transaction_type": "matchmaking_retry"
                },
                "customizations": {
                    "title": "Kimbela Matchmaking",
                    "description": f"Matchmaking Package: {package.name} (Retry)",
                }
            }
            
            headers = {
                'Authorization': f'Bearer {self.flutterwave_secret_key}',
                'Content-Type': 'application/json'
            }
            
            response = self._http_request(
                'POST',
                f"{self.flutterwave_base_url}/payments",
                headers=headers,
                json=payment_data,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                
                if result.get('status') == 'success':
                    payment_url = result['data']['link']
                    
                    # Update the existing payment record for retry
                    matchmaking_payment.gateway_reference = tx_ref
                    matchmaking_payment.gateway_payment_id = result['data'].get('id')
                    matchmaking_payment.gateway_status = 'retry_initiated'
                    matchmaking_payment.status = 'pending'
                    matchmaking_payment.payment_status = 'pending'
                    matchmaking_payment.updated_at = datetime.utcnow()
                    
                    db.session.commit()
                    
                    return {
                        'success': True,
                        'payment_url': payment_url,
                        'payment_id': matchmaking_payment.id,
                        'gateway_reference': tx_ref,
                        'message': 'Payment retry initiated successfully'
                    }
                else:
                    error_msg = result.get('message', 'Unknown Flutterwave error')
                    return {
                        'success': False,
                        'error': f'Payment gateway error: {error_msg}'
                    }
            else:
                return {
                    'success': False,
                    'error': f'Payment gateway returned error: {response.status_code}'
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': f'Payment retry error: {str(e)}'
            }


class PaymentService:
    """Legacy payment service for backward compatibility"""
    def __init__(self):
        self.ad_service = AdCampaignPaymentService()
        self.matchmaking_service = MatchmakingPaymentService()

    def create_flutterwave_transaction(self, user, campaign=None, amount=0, currency='USD', request_id=None):
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
                    amount=amount
                )
        else:
            # This is an ad campaign payment
            if campaign:
                return self.ad_service.create_ad_campaign_payment(
                    user=user,
                    campaign=campaign,
                    currency=currency
                )
        
        return {
            'success': False,
            'error': 'Invalid payment request'
        }

    def handle_successful_payment(self, transaction_id, payment_data=None):
        """Legacy method - redirect to appropriate service"""
        transaction = PaymentTransaction.query.get(transaction_id)
        if not transaction:
            return False
        
        if transaction.transaction_type == 'ad_campaign':
            return self.ad_service.handle_ad_payment_success(transaction_id, payment_data)
        elif transaction.transaction_type == 'matchmaking':
            return self.matchmaking_service.handle_matchmaking_payment_success(
                self.matchmaking_service.get_payment_by_gateway_id(transaction.gateway_payment_id),
                payment_data
            )
        return False

    def handle_failed_payment(self, transaction_id, payment_data=None):
        """Legacy method - redirect to appropriate service"""
        transaction = PaymentTransaction.query.get(transaction_id)
        if not transaction:
            return False
        
        if transaction.transaction_type == 'ad_campaign':
            return self.ad_service.handle_ad_payment_failure(transaction_id, payment_data)
        elif transaction.transaction_type == 'matchmaking':
            return self.matchmaking_service.handle_matchmaking_payment_failure(
                self.matchmaking_service.get_payment_by_gateway_id(transaction.gateway_payment_id),
                payment_data
            )
        return False