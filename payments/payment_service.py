import requests
import json
from flask import current_app, url_for
from extensions import db
from models import PaymentTransaction, AdCampaign, User
import logging
import os, time
from datetime import datetime, timedelta  # ✅ ADDED timedelta import
from flask_mail import Message
from extensions import mail

logger = logging.getLogger(__name__)

class PaymentService:
    def __init__(self):
        self.flutterwave_public_key = current_app.config.get('FLUTTERWAVE_PUBLIC_KEY') or os.getenv('PUBLIC_KEY')
        self.flutterwave_secret_key = current_app.config.get('FLUTTERWAVE_SECRET_KEY') or os.getenv('SECRET_KEY')
        self.flutterwave_encryption_key = current_app.config.get('FLUTTERWAVE_ENCRYPTION_KEY') or os.getenv('ENCRYPTION_KEY')
        self.flutterwave_base_url = "https://api.flutterwave.com/v3" 
    
    def create_flutterwave_transaction(self, user, campaign, amount, currency='USD'):
        """Create a Flutterwave payment transaction - UPDATED CALLBACK URL"""
        try:
            print(f"🟡 [FLUTTERWAVE] Starting transaction creation")
            
            # Generate unique transaction reference
            tx_ref = f"KIMBELA_AD_{campaign.id}_{int(time.time())}"
            print(f"🟡 [FLUTTERWAVE] Generated tx_ref: {tx_ref}")
            
            # ✅ IMPORTANT: Use Flutterwave callback URL, not Paystack
            redirect_url = url_for('payments.flutterwave_callback', _external=True)
            print(f"🟡 [FLUTTERWAVE] Callback URL: {redirect_url}")
            
            # Prepare payment data
            payment_data = {
                "tx_ref": tx_ref,
                "amount": str(float(amount)),  # Flutterwave expects string amount
                "currency": currency,
                "redirect_url": redirect_url,  # ✅ Use Flutterwave callback
                "customer": {
                    "email": user.email,
                    "name": user.first_name or user.email.split('@')[0]
                },
                "meta": {
                    "user_id": user.id,
                    "campaign_id": campaign.id
                },
                "customizations": {
                    "title": "Kimbela Ads",
                    "description": f"Ad Campaign: {campaign.title}",
                    "logo": url_for('static', filename='images/logo.png', _external=True)
                }
            }
            
            # Rest of your existing code remains the same...
            print(f"🟡 [FLUTTERWAVE] Payment data prepared: {payment_data}")
            
            headers = {
                'Authorization': f'Bearer {self.flutterwave_secret_key}',
                'Content-Type': 'application/json'
            }
            
            print(f"🟡 [FLUTTERWAVE] Making request to Flutterwave API...")
            response = requests.post(
                f"{self.flutterwave_base_url}/payments",
                headers=headers,
                json=payment_data
            )
            
            print(f"🟡 [FLUTTERWAVE] Response status: {response.status_code}")
            print(f"🟡 [FLUTTERWAVE] Response headers: {dict(response.headers)}")
            print(f"🟡 [FLUTTERWAVE] Response text: {response.text}")
            
            if response.status_code == 200:
                result = response.json()
                print(f"🟡 [FLUTTERWAVE] Flutterwave API response: {result}")
                
                if result.get('status') == 'success':
                    payment_url = result['data']['link']
                    print(f"✅ [FLUTTERWAVE] Payment URL generated: {payment_url}")
                    
                    # Create payment record
                    payment = PaymentTransaction(
                        user_id=user.id,
                        campaign_id=campaign.id,
                        amount=amount,
                        currency=currency,
                        gateway_payment_id=tx_ref,
                        gateway='flutterwave',
                        status='pending'
                    )
                    db.session.add(payment)
                    db.session.commit()
                    print(f"✅ [FLUTTERWAVE] Payment record created: {payment.id}")
                    
                    return {
                        'success': True,
                        'payment_url': payment_url,
                        'gateway_payment_id': tx_ref,
                        'message': 'Payment initiated successfully'
                    }
                else:
                    error_msg = result.get('message', 'Unknown Flutterwave error')
                    print(f"🔴 [FLUTTERWAVE] Flutterwave API error: {error_msg}")
                    return {
                        'success': False,
                        'error': f'Flutterwave error: {error_msg}'
                    }
            else:
                print(f"🔴 [FLUTTERWAVE] HTTP error: {response.status_code}")
                try:
                    error_data = response.json()
                    print(f"🔴 [FLUTTERWAVE] Error response: {error_data}")
                    return {
                        'success': False,
                        'error': f'Payment gateway error: {error_data.get("message", "Unknown error")}'
                    }
                except:
                    return {
                        'success': False,
                        'error': f'Payment gateway HTTP error: {response.status_code}'
                    }
                    
        except Exception as e:
            print(f"🔴 [FLUTTERWAVE] Exception in create_flutterwave_transaction: {str(e)}")
            import traceback
            print(f"🔴 [FLUTTERWAVE] Traceback: {traceback.format_exc()}")
            return {
                'success': False,
                'error': f'Payment processing error: {str(e)}'
            }
            

    def verify_flutterwave_payment(self, transaction_id):
        """Verify Flutterwave payment"""
        try:
            current_app.logger.info(f"Verifying Flutterwave payment for transaction: {transaction_id}")
            
            headers = {
                'Authorization': f'Bearer {self.flutterwave_secret_key}',
                'Content-Type': 'application/json'
            }
            
            response = requests.get(
                f'https://api.flutterwave.com/v3/transactions/{transaction_id}/verify',
                headers=headers,
                timeout=30
            )
            
            current_app.logger.info(f"Flutterwave verification response: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                current_app.logger.info(f"Flutterwave verification result: {result}")
                
                return {
                    'success': result['status'] == 'success',
                    'data': result.get('data', {})
                }
            
            current_app.logger.error(f"Flutterwave verification HTTP error: {response.status_code}")
            return {
                'success': False, 
                'error': f'HTTP {response.status_code}',
                'data': {}
            }
            
        except Exception as e:
            current_app.logger.error(f"Flutterwave verification failed: {str(e)}", exc_info=True)
            return {
                'success': False, 
                'error': str(e),
                'data': {}
            }

    def handle_successful_payment(self, transaction_id, payment_data=None):
        """Handle successful payment - COMPLETELY FIXED VERSION"""
        try:
            print(f"🔄 [HANDLE PAYMENT] Starting for transaction: {transaction_id}")
            
            # Find transaction
            transaction = PaymentTransaction.query.get(transaction_id)
            if not transaction:
                print(f"🔴 [HANDLE PAYMENT] Transaction not found: {transaction_id}")
                return False
            
            print(f"✅ [HANDLE PAYMENT] Found transaction: {transaction.id}")
            print(f"✅ [HANDLE PAYMENT] Campaign ID: {transaction.campaign_id}")
            
            # Find campaign
            campaign = AdCampaign.query.get(transaction.campaign_id)
            if not campaign:
                print(f"🔴 [HANDLE PAYMENT] Campaign not found: {transaction.campaign_id}")
                return False
            
            print(f"✅ [HANDLE PAYMENT] Found campaign: {campaign.id}")
            
            # Log current state before update
            print(f"📊 [BEFORE UPDATE] Campaign state:")
            print(f"   - status: {campaign.status}")
            print(f"   - payment_status: {campaign.payment_status}")
            print(f"   - start_date: {campaign.start_date}")
            print(f"   - end_date: {campaign.end_date}")
            print(f"   - payment_gateway: {campaign.payment_gateway}")
            print(f"   - payment_id: {campaign.payment_id}")
            
            # ✅ UPDATE TRANSACTION FIELDS
            transaction.status = 'completed'
            transaction.gateway_status = 'successful'
            if payment_data:
                transaction.gateway_metadata = json.dumps(payment_data)
            transaction.updated_at = datetime.utcnow()
            
            print(f"✅ [HANDLE PAYMENT] Updated transaction fields")
            
            # ✅ UPDATE ALL CAMPAIGN FIELDS
            campaign.payment_status = 'paid'
            campaign.status = 'active'  # This changes from 'pending' to 'active'
            campaign.payment_gateway = 'flutterwave'  # Explicitly set gateway
            campaign.payment_id = transaction.gateway_payment_id  # Use tx_ref as payment_id
            campaign.start_date = datetime.utcnow()
            
            # Calculate end date based on duration_days
            duration_days = getattr(campaign, 'duration_days', 30)
            campaign.end_date = datetime.utcnow() + timedelta(days=duration_days)
            campaign.updated_at = datetime.utcnow()
            
            print(f"✅ [HANDLE PAYMENT] Updated campaign fields:")
            print(f"   - payment_status: {campaign.payment_status}")
            print(f"   - status: {campaign.status}")
            print(f"   - payment_gateway: {campaign.payment_gateway}")
            print(f"   - payment_id: {campaign.payment_id}")
            print(f"   - start_date: {campaign.start_date}")
            print(f"   - end_date: {campaign.end_date}")
            print(f"   - duration_days: {duration_days}")
            
            # Commit changes to database
            db.session.commit()
            print(f"✅ [HANDLE PAYMENT] Database changes committed")
            
            # Refresh and verify the changes
            db.session.refresh(transaction)
            db.session.refresh(campaign)
            
            print(f"✅ [AFTER COMMIT] Verification:")
            print(f"   - Campaign status: {campaign.status}")
            print(f"   - Campaign payment_status: {campaign.payment_status}")
            print(f"   - Campaign start_date: {campaign.start_date}")
            print(f"   - Campaign end_date: {campaign.end_date}")
            print(f"   - Transaction status: {transaction.status}")
            
            # Send success email
            try:
                self.send_payment_success_email(transaction.user_id, campaign, transaction)
                print(f"✅ [HANDLE PAYMENT] Success email sent")
            except Exception as email_error:
                print(f"⚠️ [HANDLE PAYMENT] Email sending failed: {email_error}")
            
            print(f"✅ [HANDLE PAYMENT] Payment handling completed successfully")
            return True
            
        except Exception as e:
            print(f"🔴 [HANDLE PAYMENT] Error: {str(e)}")
            import traceback
            print(f"🔴 [HANDLE PAYMENT] Traceback: {traceback.format_exc()}")
            db.session.rollback()
            return False
    
    
    def handle_failed_payment(self, transaction_id, payment_data=None):
        """Handle failed payment"""
        try:
            transaction = PaymentTransaction.query.get(transaction_id)
            if not transaction:
                return False
            
            # Update transaction status
            transaction.status = 'failed'
            transaction.gateway_status = payment_data.get('status', 'failed') if payment_data else 'failed'
            transaction.gateway_metadata = json.dumps(payment_data) if payment_data else transaction.gateway_metadata
            transaction.updated_at = datetime.utcnow()
            
            # Update campaign status
            campaign = AdCampaign.query.get(transaction.campaign_id)
            if campaign:
                campaign.payment_status = 'failed'
                campaign.status = 'pending'
                campaign.updated_at = datetime.utcnow()
                
                # Send failure email using our internal method
                self.send_payment_failed_email(transaction.user_id, campaign, transaction)
            
            db.session.commit()
            return True
            
        except Exception as e:
            current_app.logger.error(f"Failed payment handling failed: {str(e)}")
            db.session.rollback()
            return False

    def send_payment_success_email(self, user_id, campaign, transaction):
        """Send payment success email with campaign details"""
        try:
            user = User.query.get(user_id)
            if not user:
                return False
            
            # Calculate expiry date
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
            
            msg = Message(
                subject=subject,
                recipients=[user.email],
                html=html_body,
                sender=current_app.config.get('MAIL_DEFAULT_SENDER')
            )
            
            mail.send(msg)
            current_app.logger.info(f"✅ Success email sent to {user.email}")
            return True
            
        except Exception as e:
            current_app.logger.error(f"❌ Failed to send success email: {str(e)}")
            return False

    def send_payment_failed_email(self, user_id, campaign, transaction):
        """Send payment failure email"""
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
            
            msg = Message(
                subject=subject,
                recipients=[user.email],
                html=html_body,
                sender=current_app.config.get('MAIL_DEFAULT_SENDER')
            )
            
            mail.send(msg)
            current_app.logger.info(f"✅ Failure email sent to {user.email}")
            return True
            
        except Exception as e:
            current_app.logger.error(f"❌ Failed to send failure email: {str(e)}")
            return False