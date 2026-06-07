from flask import Blueprint, request, jsonify, url_for, current_app
from extensions import db
from models import PaymentTransaction, MatchmakingPayments, MarketplacePayment
from time_utils import utcnow
import logging
import hashlib
import hmac
import os
import json
from .payment_service import PaymentService

logger = logging.getLogger(__name__)

monnify_bp = Blueprint('monnify', __name__, url_prefix='/monnify')
payment_service = PaymentService()

@monnify_bp.route('/initialize', methods=['POST'])
def initialize():
    # Typically called from the frontend or service layer
    return jsonify({"message": "Use the payment_service to initialize Monnify"}), 200

@monnify_bp.route('/callback', methods=['GET'])
def callback():
    # Handle monnify redirect callback
    tx_ref = request.args.get('paymentReference')
    status = request.args.get('paymentStatus')
    # Can redirect user back to their dashboard or success page
    return jsonify({"message": "Monnify callback received", "reference": tx_ref, "status": status}), 200

def compute_monnify_hash(payload_str, secret_key):
    return hmac.new(
        secret_key.encode('utf-8'),
        payload_str.encode('utf-8'),
        hashlib.sha512
    ).hexdigest()

@monnify_bp.route('/webhook', methods=['POST'])
def webhook():
    monnify_signature = request.headers.get('monnify-signature')
    if not monnify_signature:
        return jsonify({"status": "error", "message": "Missing signature"}), 400

    payload_str = request.get_data(as_text=True)
    secret_key = os.getenv("MONNIFY_SECRET_KEY", "")
    
    computed_hash = compute_monnify_hash(payload_str, secret_key)
    if computed_hash != monnify_signature:
        return jsonify({"status": "error", "message": "Invalid signature"}), 401

    data = request.get_json() or {}
    event_type = data.get('eventType')
    event_data = data.get('eventData', {})
    
    if event_type == 'SUCCESSFUL_TRANSACTION':
        tx_ref = event_data.get('paymentReference')
        amount_paid = event_data.get('amountPaid')
        
        # Determine the transaction type by looking up the reference in various tables
        # or relying on metadata if available. Monnify allows metaData in init-transaction.
        # Check Matchmaking
        match_payment = MatchmakingPayments.query.filter_by(gateway_reference=tx_ref).first()
        if match_payment and match_payment.status != 'completed':
            payment_service.matchmaking_service.handle_matchmaking_payment_success(
                match_payment, event_data
            )
            return jsonify({"status": "success"}), 200
            
        # Check Ad Campaigns
        ad_payment = PaymentTransaction.query.filter_by(gateway_reference=tx_ref, transaction_type='ad_campaign').first()
        if ad_payment and ad_payment.status != 'completed':
            payment_service.ad_service.handle_ad_payment_success(ad_payment.id, event_data)
            return jsonify({"status": "success"}), 200
            
        # Check Marketplace
        market_payment = MarketplacePayment.query.filter_by(gateway_reference=tx_ref).first()
        if market_payment and market_payment.status != 'completed':
            payment_service.marketplace_service.handle_marketplace_payment_success(
                market_payment, event_data
            )
            return jsonify({"status": "success"}), 200
            
    elif event_type == 'REFUND_COMPLETED':
        pass # Refund completion
    elif event_type == 'DISBURSEMENT':
        pass # Disbursement
    elif event_type == 'SETTLEMENT':
        pass # Settlement
    elif event_type == 'MANDATE':
        pass # Mandate
    elif event_type == 'WALLET_ACTIVITY':
        pass # Wallet Activity Notification
    elif event_type == 'LOW_BALANCE':
        pass # Low Balance Notification
        
    return jsonify({"status": "success"}), 200
