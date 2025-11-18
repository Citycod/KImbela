# payment_service.py
import stripe
import requests
import json
from flask import current_app
from extensions import db
from models import PaymentTransaction, AdCampaign
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

class PaymentService:
    def __init__(self):
        self.stripe_secret_key = current_app.config.get('STRIPE_SECRET_KEY') or os.getenv('STRIPE_SECRET_KEY')
        self.paystack_secret_key = current_app.config.get('PAYSTACK_SECRET_KEY') or os.getenv('PAYSTACK_SECRET_KEY')
        
        if self.stripe_secret_key:
            stripe.api_key = self.stripe_secret_key

    def create_paystack_transaction(self, user, campaign, package, currency='NGN'):
        """Create Paystack transaction"""
        try:
            current_app.logger.info(f"Creating Paystack transaction for campaign {campaign.id}")
            
            # Convert to kobo for Paystack (NGN)
            amount_kobo = int(package.price * 100)
            
            # Prepare callback URL
            base_url = current_app.config.get('BASE_URL', 'http://localhost:5000')
            callback_url = f"{base_url}/paystack/callback"
            
            # Prepare request data
            data = {
                'email': user.email,
                'amount': amount_kobo,
                'currency': currency,
                'metadata': {
                    'user_id': user.id,
                    'campaign_id': campaign.id,
                    'package_id': package.id,
                    'type': 'ad_campaign'
                },
                'callback_url': callback_url
            }
            
            current_app.logger.info(f"Paystack request data: {data}")
            
            # Make request to Paystack
            headers = {
                'Authorization': f'Bearer {self.paystack_secret_key}',
                'Content-Type': 'application/json'
            }
            
            response = requests.post(
                'https://api.paystack.co/transaction/initialize',
                headers=headers,
                data=json.dumps(data),
                timeout=30
            )
            
            current_app.logger.info(f"Paystack response status: {response.status_code}")
            current_app.logger.info(f"Paystack response: {response.text}")
            
            if response.status_code == 200:
                result = response.json()
                if result['status']:
                    payment_data = result['data']
                    
                    # Create transaction record
                    transaction = PaymentTransaction(
                        user_id=user.id,
                        campaign_id=campaign.id,
                        amount=package.price,
                        currency=currency,
                        gateway='paystack',
                        gateway_payment_id=payment_data['reference'],
                        gateway_status='initialized',
                        description=f"Ad Campaign: {campaign.title}",
                        gateway_metadata=json.dumps(payment_data)
                    )
                    db.session.add(transaction)
                    
                    # Update campaign with payment info
                    campaign.payment_gateway = 'paystack'
                    campaign.payment_id = payment_data['reference']
                    campaign.currency = currency
                    
                    db.session.commit()
                    
                    current_app.logger.info(f"Paystack transaction created: {transaction.id}")
                    
                    return {
                        'success': True,
                        'authorization_url': payment_data['authorization_url'],
                        'reference': payment_data['reference'],
                        'transaction_id': transaction.id
                    }
                else:
                    error_msg = result.get('message', 'Paystack API error')
                    current_app.logger.error(f"Paystack API error: {error_msg}")
                    return {
                        'success': False, 
                        'error': error_msg
                    }
            
            error_msg = f'HTTP {response.status_code}: {response.text}'
            current_app.logger.error(f"Paystack HTTP error: {error_msg}")
            return {
                'success': False, 
                'error': error_msg
            }
            
        except Exception as e:
            current_app.logger.error(f"Paystack transaction creation failed: {str(e)}", exc_info=True)
            return {'success': False, 'error': str(e)}

    def create_payment_intent(self, user, campaign, package, currency='USD'):
        """Create Stripe Payment Intent"""
        try:
            # Convert to cents for Stripe
            amount_cents = int(package.price * 100)
            
            # Create PaymentIntent
            intent = stripe.PaymentIntent.create(
                amount=amount_cents,
                currency=currency.lower(),
                metadata={
                    'user_id': user.id,
                    'campaign_id': campaign.id,
                    'package_id': package.id,
                    'type': 'ad_campaign'
                },
                automatic_payment_methods={
                    'enabled': True,
                },
            )
            
            # Create transaction record
            transaction = PaymentTransaction(
                user_id=user.id,
                campaign_id=campaign.id,
                amount=package.price,
                currency=currency,
                gateway='stripe',
                gateway_payment_id=intent.id,
                gateway_status='requires_payment_method',
                description=f"Ad Campaign: {campaign.title}",
                gateway_metadata=json.dumps({
                    'client_secret': intent.client_secret,
                    'status': intent.status
                })
            )
            
            db.session.add(transaction)
            
            # Update campaign with payment info
            campaign.payment_gateway = 'stripe'
            campaign.payment_id = intent.id
            campaign.currency = currency
            
            db.session.commit()
            
            return {
                'success': True,
                'client_secret': intent.client_secret,
                'payment_intent_id': intent.id,
                'transaction_id': transaction.id
            }
            
        except Exception as e:
            current_app.logger.error(f"Stripe payment intent creation failed: {str(e)}", exc_info=True)
            return {'success': False, 'error': str(e)}

    def verify_paystack_payment(self, reference):
        """Verify Paystack payment"""
        try:
            current_app.logger.info(f"Verifying Paystack payment for reference: {reference}")
            
            headers = {
                'Authorization': f'Bearer {self.paystack_secret_key}',
                'Content-Type': 'application/json'
            }
            
            response = requests.get(
                f'https://api.paystack.co/transaction/verify/{reference}',
                headers=headers,
                timeout=30
            )
            
            current_app.logger.info(f"Paystack verification response: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                current_app.logger.info(f"Paystack verification result: {result}")
                
                return {
                    'success': result['status'],
                    'data': result.get('data', {})
                }
            
            current_app.logger.error(f"Paystack verification HTTP error: {response.status_code}")
            return {
                'success': False, 
                'error': f'HTTP {response.status_code}',
                'data': {}
            }
            
        except Exception as e:
            current_app.logger.error(f"Paystack verification failed: {str(e)}", exc_info=True)
            return {
                'success': False, 
                'error': str(e),
                'data': {}
            }

    def handle_successful_payment(self, transaction_id, payment_data=None):
        """Handle successful payment - UPDATED TO PROPERLY UPDATE STATUS"""
        try:
            transaction = PaymentTransaction.query.get(transaction_id)
            if not transaction:
                current_app.logger.error(f"Transaction not found: {transaction_id}")
                return False
            
            current_app.logger.info(f"Handling successful payment for transaction: {transaction_id}")
            
            # Update transaction status
            transaction.status = 'completed'
            transaction.gateway_status = 'success'
            transaction.gateway_metadata = json.dumps(payment_data) if payment_data else transaction.gateway_metadata
            transaction.updated_at = datetime.utcnow()
            
            # Update campaign status
            campaign = AdCampaign.query.get(transaction.campaign_id)
            if campaign:
                campaign.payment_status = 'paid'
                campaign.status = 'active'
                campaign.payment_gateway = transaction.gateway
                campaign.payment_id = transaction.gateway_payment_id
                campaign.updated_at = datetime.utcnow()
                
                current_app.logger.info(f"Updated campaign {campaign.id} to paid and active")
            else:
                current_app.logger.error(f"Campaign not found for transaction: {transaction_id}")
            
            db.session.commit()
            
            current_app.logger.info(f"Successfully processed payment for transaction: {transaction_id}")
            return True
            
        except Exception as e:
            current_app.logger.error(f"Payment handling failed: {str(e)}", exc_info=True)
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
            
            db.session.commit()
            return True
            
        except Exception as e:
            current_app.logger.error(f"Failed payment handling failed: {str(e)}")
            db.session.rollback()
            return False