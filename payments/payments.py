from flask import (
    Blueprint, request, jsonify, render_template, redirect, url_for, current_app
)
from flask_login import login_required, current_user
from extensions import db
from models import User, AdCampaign, AdPackage, PaymentTransaction
from .payment_service import PaymentService
import cloudinary.uploader
import os
from email_service import EmailService 
import json
from datetime import datetime, timedelta

payments = Blueprint("payments", __name__)





@payments.route('/ad-packages')
@login_required
def ad_packages():
    """Display available ad packages"""
    packages = AdPackage.query.filter_by(is_active=True).all()
    return render_template('packages.html', packages=packages)





@payments.route('/create-campaign', methods=['POST'])
@login_required
def create_campaign():
    """Create a new ad campaign"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400

        package_id = data.get('package_id')
        ad_data = data.get('ad_data', {})
        
        if not package_id:
            return jsonify({'success': False, 'error': 'Package ID is required'}), 400

        # Convert package_id to integer
        try:
            package_id = int(package_id)
        except (ValueError, TypeError):
            return jsonify({'success': False, 'error': 'Invalid package ID format'}), 400

        # Check if package exists
        package = AdPackage.query.get(package_id)
        
        if not package:
            return jsonify({'success': False, 'error': f'Package with ID {package_id} not found'})

        # Validate required fields
        if not ad_data.get('title'):
            return jsonify({'success': False, 'error': 'Ad title is required'}), 400
            
        if not ad_data.get('target_url'):
            return jsonify({'success': False, 'error': 'Target URL is required'}), 400

        # Parse targeting data
        target_countries = ad_data.get('countries', [])
        target_interests = ad_data.get('interests', [])
        
        # Calculate end date based on package duration
        start_date = datetime.utcnow()
        end_date = start_date + timedelta(days=package.duration_days)
        
        # Create campaign
        campaign = AdCampaign(
            user_id=current_user.id,
            package_id=package_id,
            title=ad_data.get('title', ''),
            description=ad_data.get('description', ''),
            image=ad_data.get('image', ''),
            target_url=ad_data.get('target_url', ''),
            call_to_action=ad_data.get('call_to_action', 'Learn More'),
            target_audience=ad_data.get('audience', 'all'),
            target_countries=json.dumps(target_countries) if target_countries else None,
            target_interests=json.dumps(target_interests) if target_interests else None,
            budget=package.price,
            status='pending',
            payment_status='pending',
            start_date=start_date,
            end_date=end_date
        )
        
        db.session.add(campaign)
        db.session.commit()
        
        current_app.logger.info(f"✅ Campaign created successfully for user {current_user.id}: {campaign.id}")
        
        return jsonify({
            'success': True,
            'campaign_id': campaign.id,
            'message': 'Campaign created successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"❌ Campaign creation failed: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
    
    
    
    
    

@payments.route('/initiate-payment', methods=['POST'])
@login_required
def initiate_payment():
    """Initiate payment for a campaign"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400

        campaign_id = data.get('campaign_id')
        payment_method = data.get('payment_method')
        currency = data.get('currency', 'USD').upper()

        campaign = AdCampaign.query.get(campaign_id)
        if not campaign:
            return jsonify({'success': False, 'error': 'Campaign not found'}), 404
            
        if campaign.user_id != current_user.id:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403

        package = AdPackage.query.get(campaign.package_id)
        payment_service = PaymentService()

        # Use the selected payment method
        if payment_method == 'paystack':
            result = payment_service.create_paystack_transaction(
                user=current_user,
                campaign=campaign,
                package=package,
                currency=currency or 'NGN'
            )
        else:  # stripe
            result = payment_service.create_payment_intent(
                user=current_user,
                campaign=campaign,
                package=package,
                currency=currency or 'USD'
            )

        current_app.logger.info(f"✅ Payment initiated for campaign {campaign_id} by user {current_user.id}")

        return jsonify(result)

    except Exception as e:
        current_app.logger.error(f"❌ Payment initiation failed: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': 'Payment initiation failed'}), 500
    
    
    
    
    

@payments.route('/upload-image', methods=['POST'])
@login_required
def upload_image():
    """Upload ad image to Cloudinary"""
    try:
        if 'image' not in request.files:
            return jsonify({'success': False, 'error': 'No image provided'})
        
        image_file = request.files['image']
        if image_file.filename == '':
            return jsonify({'success': False, 'error': 'No image selected'})
        
        # Upload to Cloudinary
        upload_result = cloudinary.uploader.upload(
            image_file,
            folder="kimbela/ads",
            width=1200,
            height=630,
            crop="fill",
            quality="auto"
        )
        
        current_app.logger.info(f"✅ Image uploaded successfully for user {current_user.id}")
        
        return jsonify({
            'success': True,
            'image_url': upload_result['secure_url'],
            'public_id': upload_result['public_id']
        })
        
    except Exception as e:
        current_app.logger.error(f"❌ Image upload failed: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
    
    
    
    
    
    

@payments.route('/paystack/callback')
def paystack_callback():
    """Paystack payment callback - this can be accessed without login"""
    try:
        reference = request.args.get('reference')
        trxref = request.args.get('trxref')
        
        # Use reference or trxref (Paystack uses both)
        payment_reference = reference or trxref
        
        if not payment_reference:
            current_app.logger.error("❌ Paystack callback: No reference provided")
            return redirect(url_for('payments.payment_failed'))
        
        current_app.logger.info(f"🔄 Paystack callback received for reference: {payment_reference}")
        
        payment_service = PaymentService()
        
        # Verify payment with Paystack
        verification_result = payment_service.verify_paystack_payment(payment_reference)
        
        if verification_result['success'] and verification_result['data']['status'] == 'success':
            # Find transaction
            transaction = PaymentTransaction.query.filter_by(
                gateway_payment_id=payment_reference
            ).first()
            
            if transaction:
                # Get the payment data from verification
                payment_data = verification_result['data']
                
                # Handle successful payment
                if payment_service.handle_successful_payment(transaction.id, payment_data):
                    current_app.logger.info(f"✅ Payment successful for transaction: {transaction.id}")
                    
                    # Send success email via Gmail
                    user = User.query.get(transaction.user_id)
                    campaign = AdCampaign.query.get(transaction.campaign_id)
                    package = AdPackage.query.get(campaign.package_id) if campaign else None
                    
                    if user and campaign and package:
                        EmailService.send_ad_purchase_success(user, transaction, campaign, package)
                        current_app.logger.info(f"📧 Success email queued for {user.email}")
                    else:
                        current_app.logger.warning(f"⚠️ Could not find user, campaign, or package for transaction {transaction.id}")
                    
                    # Redirect to success page with transaction ID
                    return redirect(url_for('payments.payment_success', transaction_id=transaction.id))
                else:
                    current_app.logger.error(f"❌ Failed to handle successful payment for transaction: {transaction.id}")
            else:
                current_app.logger.error(f"❌ No transaction found for reference: {payment_reference}")
        
        # If payment failed, send failure email
        transaction = PaymentTransaction.query.filter_by(gateway_payment_id=payment_reference).first()
        if transaction:
            user = User.query.get(transaction.user_id)
            campaign = AdCampaign.query.get(transaction.campaign_id)
            package = AdPackage.query.get(campaign.package_id) if campaign else None
            
            if user and package:
                EmailService.send_ad_purchase_failed(
                    user=user,
                    package=package,
                    transaction=transaction,
                    campaign=campaign,
                    error_message="Payment verification failed or was declined"
                )
                current_app.logger.info(f"📧 Failure email queued for {user.email}")
        
        current_app.logger.error(f"❌ Payment verification failed for reference: {payment_reference}")
        return redirect(url_for('payments.payment_failed'))
        
    except Exception as e:
        current_app.logger.error(f"❌ Paystack callback error: {str(e)}", exc_info=True)
        return redirect(url_for('payments.payment_failed'))
    
    
    
    
    
    

@payments.route('/payment-success/<int:transaction_id>')
@login_required
def payment_success(transaction_id):
    """Handle successful payment"""
    try:
        transaction = PaymentTransaction.query.get(transaction_id)
        
        # Verify the transaction belongs to the current user
        if not transaction or transaction.user_id != current_user.id:
            current_app.logger.warning(f"⚠️ Unauthorized access to transaction {transaction_id} by user {current_user.id}")
            return redirect(url_for('payments.payment_failed'))
        
        # Double-check that payment was actually successful
        if transaction.status != 'completed':
            # If not completed, verify with payment gateway
            payment_service = PaymentService()
            if transaction.gateway == 'paystack':
                verification_result = payment_service.verify_paystack_payment(transaction.gateway_payment_id)
                if verification_result['success'] and verification_result['data']['status'] == 'success':
                    payment_service.handle_successful_payment(transaction.id, verification_result['data'])
                    
                    # Send success email if not already sent
                    campaign = AdCampaign.query.get(transaction.campaign_id)
                    package = AdPackage.query.get(campaign.package_id) if campaign else None
                    
                    if campaign and package:
                        EmailService.send_ad_purchase_success(current_user, transaction, campaign, package)
                        current_app.logger.info(f"📧 Success email sent to {current_user.email}")
                else:
                    current_app.logger.error(f"❌ Payment verification failed for transaction {transaction_id}")
                    return redirect(url_for('payments.payment_failed'))
        
        campaign = AdCampaign.query.get(transaction.campaign_id) if transaction.campaign_id else None
        
        current_app.logger.info(f"✅ User {current_user.id} viewed success page for transaction {transaction_id}")
        
        return render_template('success.html', 
                             transaction=transaction, 
                             campaign=campaign)
    
    except Exception as e:
        current_app.logger.error(f"❌ Payment success page error: {str(e)}")
        return redirect(url_for('payments.payment_failed'))
    
    
    
    

@payments.route('/payment-failed')
@login_required
def payment_failed():
    """Handle failed payment"""
    current_app.logger.info(f"⚠️ User {current_user.id} viewed payment failed page")
    return render_template('failed.html')





@payments.route('/verify-payment', methods=['POST'])
@login_required
def verify_payment():
    """Verify payment status (for AJAX calls)"""
    try:
        data = request.get_json()
        reference = data.get('reference')
        
        if not reference:
            return jsonify({'success': False, 'error': 'No reference provided'})
        
        payment_service = PaymentService()
        result = payment_service.verify_paystack_payment(reference)
        
        if result['success'] and result['data']['status'] == 'success':
            # Find and update transaction
            transaction = PaymentTransaction.query.filter_by(
                gateway_payment_id=reference,
                user_id=current_user.id
            ).first()
            
            if transaction:
                payment_service.handle_successful_payment(transaction.id, result['data'])
                
                # Send success email
                campaign = AdCampaign.query.get(transaction.campaign_id)
                package = AdPackage.query.get(campaign.package_id) if campaign else None
                
                if campaign and package:
                    EmailService.send_ad_purchase_success(current_user, transaction, campaign, package)
                
                return jsonify({
                    'success': True,
                    'transaction_id': transaction.id,
                    'status': 'completed'
                })
        
        # Send failure email if payment failed
        transaction = PaymentTransaction.query.filter_by(gateway_payment_id=reference).first()
        if transaction:
            campaign = AdCampaign.query.get(transaction.campaign_id)
            package = AdPackage.query.get(campaign.package_id) if campaign else None
            
            if package:
                EmailService.send_ad_purchase_failed(
                    user=current_user,
                    package=package,
                    transaction=transaction,
                    campaign=campaign,
                    error_message="Payment verification failed"
                )
        
        return jsonify({'success': False, 'error': 'Payment verification failed'})
        
    except Exception as e:
        current_app.logger.error(f"❌ Payment verification error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})
    
    
    
    
    
    

    
    

@payments.route('/update-payment-status', methods=['POST'])
@login_required
def update_payment_status():
    """Update payment status (for manual updates)"""
    try:
        data = request.get_json()
        transaction_id = data.get('transaction_id')
        status = data.get('status')
        
        if not transaction_id or not status:
            return jsonify({'success': False, 'error': 'Transaction ID and status are required'})
        
        transaction = PaymentTransaction.query.get(transaction_id)
        
        if not transaction or transaction.user_id != current_user.id:
            return jsonify({'success': False, 'error': 'Transaction not found'})
        
        payment_service = PaymentService()
        
        if status == 'completed':
            # Verify with payment gateway first
            if transaction.gateway == 'paystack':
                verification_result = payment_service.verify_paystack_payment(transaction.gateway_payment_id)
                if verification_result['success'] and verification_result['data']['status'] == 'success':
                    payment_service.handle_successful_payment(transaction.id, verification_result['data'])
                else:
                    return jsonify({'success': False, 'error': 'Payment verification failed'})
        
        return jsonify({'success': True, 'message': 'Payment status updated'})
        
    except Exception as e:
        current_app.logger.error(f"Payment status update error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})
    
    
    
    
 

@payments.route('/ads/active')
def get_active_ads():
    """Get active ads for display"""
    try:
        active_ads = AdCampaign.query.filter_by(
            status='active'
        ).filter(
            AdCampaign.budget > 0
        ).filter(
            AdCampaign.start_date <= datetime.utcnow(),
            AdCampaign.end_date >= datetime.utcnow()
        ).all()
        
        ads_data = []
        for ad in active_ads:
            ads_data.append({
                'id': ad.id,
                'title': ad.title,
                'description': ad.description,
                'image': ad.image,
                'target_url': ad.target_url,
                'call_to_action': ad.call_to_action,
                'budget': ad.budget,
                'status': 'active'
            })
        
        return jsonify(ads_data)
    except Exception as e:
        print(f"Error loading ads: {e}")
        return jsonify([])

@payments.route('/ads/track/impression/<int:ad_id>', methods=['POST'])
def track_ad_impression(ad_id):
    """Track ad impression"""
    try:
        ad = AdCampaign.query.get_or_404(ad_id)
        ad.impressions += 1
        db.session.commit()
        return jsonify({'success': True})
    except:
        return jsonify({'success': False})

@payments.route('/ads/track/click/<int:ad_id>', methods=['POST'])
def track_ad_click(ad_id):
    """Track ad click"""
    try:
        ad = AdCampaign.query.get_or_404(ad_id)
        ad.clicks += 1
        # Update CTR
        if ad.impressions > 0:
            ad.click_through_rate = (ad.clicks / ad.impressions) * 100
        db.session.commit()
        return jsonify({'success': True})
    except:
        return jsonify({'success': False})