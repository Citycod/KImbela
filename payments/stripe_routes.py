from flask import Blueprint, request, jsonify, url_for, current_app
from extensions import db
from models import PaymentTransaction, MatchmakingPayments, MarketplacePayment
from time_utils import utcnow
import logging
import stripe
import os
from .payment_service import PaymentService

logger = logging.getLogger(__name__)

stripe_bp = Blueprint('stripe', __name__, url_prefix='/stripe')
payment_service = PaymentService()

@stripe_bp.route('/initialize', methods=['POST'])
def initialize():
    # Typically called from the frontend or service layer
    return jsonify({"message": "Use the payment_service to initialize Stripe"}), 200

@stripe_bp.route('/callback', methods=['GET'])
def callback():
    # Handle stripe return URL
    tx_ref = request.args.get('tx_ref')
    status = request.args.get('status')
    return jsonify({"message": "Stripe callback received", "reference": tx_ref, "status": status}), 200

@stripe_bp.route('/webhook', methods=['POST'])
def webhook():
    stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
    endpoint_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    
    payload = request.data
    sig_header = request.headers.get('STRIPE_SIGNATURE')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except ValueError as e:
        # Invalid payload
        return jsonify({"status": "error", "message": "Invalid payload"}), 400
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        return jsonify({"status": "error", "message": "Invalid signature"}), 400

    # Handle the event
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        tx_ref = session.get('client_reference_id')
        
        # Determine the transaction type by looking up the reference
        # Check Matchmaking
        match_payment = MatchmakingPayments.query.filter_by(gateway_reference=tx_ref).first()
        if match_payment and match_payment.status != 'completed':
            payment_service.matchmaking_service.handle_matchmaking_payment_success(
                match_payment, session
            )
            return jsonify({"status": "success"}), 200
            
        # Check Ad Campaigns
        ad_payment = PaymentTransaction.query.filter_by(gateway_reference=tx_ref, transaction_type='ad_campaign').first()
        if ad_payment and ad_payment.status != 'completed':
            payment_service.ad_service.handle_ad_payment_success(ad_payment.id, session)
            return jsonify({"status": "success"}), 200
            
        # Check Marketplace
        market_payment = MarketplacePayment.query.filter_by(gateway_reference=tx_ref).first()
        if market_payment and market_payment.status != 'completed':
            payment_service.marketplace_service.handle_marketplace_payment_success(
                market_payment, session
            )
            return jsonify({"status": "success"}), 200

    return jsonify({"status": "success"}), 200
