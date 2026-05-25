from flask import Blueprint, request, jsonify, url_for
from extensions import db
from models import PaymentTransaction
from utils.paystack import PaystackService
from time_utils import utcnow
import logging
import uuid

logger = logging.getLogger(__name__)

paystack_bp = Blueprint('paystack', __name__, url_prefix='/paystack')

@paystack_bp.route('/initialize', methods=['POST'])
def initialize():
    """
    Initialize a Paystack payment.
    Expected JSON payload:
    {
        "email": "user@example.com",
        "amount": 5000,
        "category": "Marketplace Subscriptions",
        "user_id": 1
    }
    """
    data = request.get_json() or {}
    email = data.get('email')
    amount = data.get('amount')
    category = data.get('category')
    user_id = data.get('user_id')
    
    if not all([email, amount, category, user_id]):
        return jsonify({"error": "Missing required fields (email, amount, category, user_id)"}), 400
        
    paystack_service = PaystackService()
    
    # Generate an internal reference for idempotency and tracking
    reference = f"tx_{uuid.uuid4().hex}"
    
    metadata = {
        "category": category,
        "user_id": user_id,
        "custom_fields": [
            {
                "display_name": "Payment Category",
                "variable_name": "category",
                "value": category
            }
        ]
    }
    
    callback_url = url_for('paystack.callback', _external=True)
    
    response = paystack_service.initialize_transaction(
        email=email,
        amount=amount,
        reference=reference,
        callback_url=callback_url,
        metadata=metadata
    )
    
    if response.get('status'):
        # Create a pending PaymentTransaction record
        transaction = PaymentTransaction(
            gateway_reference=reference,
            user_id=user_id,
            amount=amount,
            transaction_type=category,
            status='pending',
            gateway='paystack',
            description=f"Paystack payment for {category}"
        )
        db.session.add(transaction)
        db.session.commit()
        
        return jsonify({
            "authorization_url": response['data']['authorization_url'],
            "reference": reference
        }), 200
        
    return jsonify({"error": "Payment initialization failed", "details": response.get('message')}), 400

@paystack_bp.route('/callback', methods=['GET'])
def callback():
    """
    Handle user redirect after payment completion.
    """
    reference = request.args.get('reference')
    if not reference:
        return jsonify({"error": "No reference provided"}), 400
        
    paystack_service = PaystackService()
    response = paystack_service.verify_transaction(reference)
    
    if response.get('status') and response.get('data', {}).get('status') == 'success':
        _process_successful_transaction(reference, response['data'])
        return jsonify({"message": "Payment successful", "reference": reference}), 200
    else:
        _process_failed_transaction(reference)
        return jsonify({"message": "Payment failed or could not be verified"}), 400

@paystack_bp.route('/webhook', methods=['POST'])
def webhook():
    """
    Secure webhook endpoint to handle asynchronous notifications from Paystack.
    """
    paystack_signature = request.headers.get('x-paystack-signature')
    if not paystack_signature:
        return jsonify({"error": "Missing signature"}), 400
        
    paystack_service = PaystackService()
    
    # Verify signature to ensure the request is from Paystack
    payload = request.get_data()
    if not paystack_service.verify_webhook_signature(payload, paystack_signature):
        return jsonify({"error": "Invalid signature"}), 400
        
    event = request.get_json()
    event_name = event.get('event')
    data = event.get('data', {})
    reference = data.get('reference')
    
    if not reference:
        return jsonify({"status": "ignored", "message": "No reference in data"}), 200
        
    if event_name == 'charge.success':
        _process_successful_transaction(reference, data)
    elif event_name in ['charge.failed', 'charge.reversed']:
        status = event_name.split('.')[1]
        _process_failed_transaction(reference, status=status)
        
    return jsonify({"status": "success"}), 200

def _process_successful_transaction(reference: str, data: dict):
    """
    Idempotent function to process successful transactions.
    """
    transaction = PaymentTransaction.query.filter_by(gateway_reference=reference).first()
    
    if not transaction:
        logger.error(f"Transaction {reference} not found in database.")
        return
        
    # Idempotency check: Don't process if already successful
    if transaction.status == 'completed':
        return
        
    transaction.status = 'completed'
    transaction.updated_at = utcnow()
    transaction.gateway_response = str(data)
    
    # Process logic based on category
    category = transaction.transaction_type
    # if category == 'Marketplace Subscriptions':
    #     ... handle subscription logic
    # elif category == 'Matchmaking Packages':
    #     ... handle matchmaking logic
    # elif category == 'Ad Campaigns':
    #     ... handle ad logic
    
    db.session.commit()
    logger.info(f"Transaction {reference} successfully processed.")

def _process_failed_transaction(reference: str, status: str = 'failed'):
    """
    Idempotent function to process failed or reversed transactions.
    """
    transaction = PaymentTransaction.query.filter_by(gateway_reference=reference).first()
    
    if not transaction:
        logger.error(f"Transaction {reference} not found in database.")
        return
        
    # Idempotency check
    if transaction.status in ['completed', 'failed', 'reversed']:
        return
        
    transaction.status = status
    transaction.updated_at = utcnow()
    db.session.commit()
    logger.info(f"Transaction {reference} marked as {status}.")
