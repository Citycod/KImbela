from flask import (
    Blueprint, request, jsonify, render_template, redirect, url_for, current_app, flash
)
from flask_login import login_required, current_user
from extensions import db
from models import User, AdCampaign, AdPackage, PaymentTransaction
from .payment_service import PaymentService
import cloudinary.uploader
import os, requests
from email_service import EmailService 
import json
from datetime import datetime, timedelta
import time
import time
payments = Blueprint("payments", __name__)





@payments.route('/ad-packages')
@login_required
def ad_packages():
    """Display available ad packages"""
    packages = AdPackage.query.filter_by(is_active=True).all()
    return render_template('packages.html', packages=packages)





# @payments.route('/create-campaign', methods=['POST'])
# @login_required
# def create_campaign():
#     """Create a new ad campaign"""
#     try:
#         data = request.get_json()
#         if not data:
#             return jsonify({'success': False, 'error': 'No data provided'}), 400

#         package_id = data.get('package_id')
#         ad_data = data.get('ad_data', {})
        
#         if not package_id:
#             return jsonify({'success': False, 'error': 'Package ID is required'}), 400

#         # Convert package_id to integer
#         try:
#             package_id = int(package_id)
#         except (ValueError, TypeError):
#             return jsonify({'success': False, 'error': 'Invalid package ID format'}), 400

#         # Check if package exists
#         package = AdPackage.query.get(package_id)
        
#         if not package:
#             return jsonify({'success': False, 'error': f'Package with ID {package_id} not found'})

#         # Validate required fields
#         if not ad_data.get('title'):
#             return jsonify({'success': False, 'error': 'Ad title is required'}), 400
            
#         if not ad_data.get('target_url'):
#             return jsonify({'success': False, 'error': 'Target URL is required'}), 400

#         # Parse targeting data
#         target_countries = ad_data.get('countries', [])
#         target_interests = ad_data.get('interests', [])
        
#         # Calculate end date based on package duration
#         start_date = datetime.utcnow()
#         end_date = start_date + timedelta(days=package.duration_days)
        
#         # Create campaign
#         campaign = AdCampaign(
#             user_id=current_user.id,
#             package_id=package_id,
#             title=ad_data.get('title', ''),
#             description=ad_data.get('description', ''),
#             image=ad_data.get('image', ''),
#             target_url=ad_data.get('target_url', ''),
#             call_to_action=ad_data.get('call_to_action', 'Learn More'),
#             target_audience=ad_data.get('audience', 'all'),
#             target_countries=json.dumps(target_countries) if target_countries else None,
#             target_interests=json.dumps(target_interests) if target_interests else None,
#             budget=package.price,
#             status='pending',
#             payment_status='pending',
#             start_date=start_date,
#             end_date=end_date
#         )
        
#         db.session.add(campaign)
#         db.session.commit()
        
#         current_app.logger.info(f"✅ Campaign created successfully for user {current_user.id}: {campaign.id}")
        
#         return jsonify({
#             'success': True,
#             'campaign_id': campaign.id,
#             'message': 'Campaign created successfully'
#         })
        
#     except Exception as e:
#         db.session.rollback()
#         current_app.logger.error(f"❌ Campaign creation failed: {str(e)}")
#         return jsonify({'success': False, 'error': str(e)}), 500
    
    
    
    
    

# @payments.route('/initiate-payment', methods=['POST'])
# @login_required
# def initiate_payment():
#     """Initiate payment for a campaign"""
#     try:
#         data = request.get_json()
#         if not data:
#             return jsonify({'success': False, 'error': 'No data provided'}), 400

#         campaign_id = data.get('campaign_id')
#         payment_method = data.get('payment_method')
#         currency = data.get('currency', 'USD').upper()

#         campaign = AdCampaign.query.get(campaign_id)
#         if not campaign:
#             return jsonify({'success': False, 'error': 'Campaign not found'}), 404
            
#         if campaign.user_id != current_user.id:
#             return jsonify({'success': False, 'error': 'Unauthorized'}), 403

#         package = AdPackage.query.get(campaign.package_id)
#         payment_service = PaymentService()

#         # Use the selected payment method
#         if payment_method == 'paystack':
#             result = payment_service.create_paystack_transaction(
#                 user=current_user,
#                 campaign=campaign,
#                 package=package,
#                 currency=currency or 'NGN'
#             )
#         else:  # stripe
#             result = payment_service.create_payment_intent(
#                 user=current_user,
#                 campaign=campaign,
#                 package=package,
#                 currency=currency or 'USD'
#             )

#         current_app.logger.info(f"✅ Payment initiated for campaign {campaign_id} by user {current_user.id}")

#         return jsonify(result)

#     except Exception as e:
#         current_app.logger.error(f"❌ Payment initiation failed: {str(e)}", exc_info=True)
#         return jsonify({'success': False, 'error': 'Payment initiation failed'}), 500
    
    
    
    
    

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
    
    




@payments.route('/flutterwave-callback')
def flutterwave_callbackk():
    """Handle Flutterwave payment callback - REDIRECTS TO USER_DASHBOARD"""
    try:
        print(f"🟡 [FLUTTERWAVE_CALLBACK] Received callback with args: {request.args}")
        
        # Get parameters from Flutterwave
        status = request.args.get('status')
        tx_ref = request.args.get('tx_ref')
        transaction_id = request.args.get('transaction_id')
        
        print(f"🟡 [FLUTTERWAVE_CALLBACK] status: {status}, tx_ref: {tx_ref}, transaction_id: {transaction_id}")
        
        # For this route, just redirect to the main callback handler
        # This ensures both callback URLs work the same way
        return redirect(url_for('payments.flutterwave_callbackk', 
                              status=status, 
                              tx_ref=tx_ref, 
                              transaction_id=transaction_id))
        
    except Exception as e:
        print(f"🔴 [FLUTTERWAVE_CALLBACK] Exception: {str(e)}")
        flash('An error occurred during payment processing.', 'error')
        return redirect(url_for('user_dashboard'))

 
 
 
 
   
    
    
    
@payments.route('/flutterwave/callback', methods=['GET'])
def flutterwave_callback():
    """Flutterwave payment callback - FIXED VERSION"""
    try:
        status = request.args.get('status')
        tx_ref = request.args.get('tx_ref')
        transaction_id = request.args.get('transaction_id')
        
        print(f"🟡 [FLUTTERWAVE/CALLBACK] Received - status: {status}, tx_ref: {tx_ref}, transaction_id: {transaction_id}")
        
        payment_service = PaymentService()
        
        # Find transaction by tx_ref (our reference)
        transaction = PaymentTransaction.query.filter_by(gateway_payment_id=tx_ref).first()
        
        if not transaction:
            print(f"🔴 [CALLBACK] No transaction found for tx_ref: {tx_ref}")
            flash('Transaction not found', 'error')
            return redirect(url_for('user_dashboard'))
        
        print(f"✅ [CALLBACK] Found transaction: {transaction.id}")
        
        # Verify payment with Flutterwave
        verification_result = payment_service.verify_flutterwave_payment(transaction_id)
        print(f"🟡 [CALLBACK] Verification result: {verification_result}")
        
        if verification_result['success']:
            payment_data = verification_result.get('data', {})
            actual_status = payment_data.get('status', 'failed')
            
            print(f"🟡 [CALLBACK] Payment status from Flutterwave: {actual_status}")
            
            if actual_status == 'successful':
                # Handle successful payment
                success = payment_service.handle_successful_payment(transaction.id, payment_data)
                if success:
                    print("✅ [CALLBACK] Payment handled successfully")
                    flash('Payment completed successfully! Your campaign is now active.', 'success')
                else:
                    print("🔴 [CALLBACK] Failed to handle successful payment")
                    flash('Payment verification failed. Please contact support.', 'error')
            else:
                # Handle failed payment
                payment_service.handle_failed_payment(transaction.id, payment_data)
                flash('Payment failed. Please try again.', 'error')
        else:
            print(f"🔴 [CALLBACK] Payment verification failed: {verification_result.get('error')}")
            flash('Payment verification failed. Please contact support.', 'error')
        
        return redirect(url_for('user.user_dashboard'))
        
    except Exception as e:
        print(f"🔴 [CALLBACK] Exception: {str(e)}")
        import traceback
        print(f"🔴 [CALLBACK] Traceback: {traceback.format_exc()}")
        flash('An error occurred during payment processing.', 'error')
        return redirect(url_for('user.user_dashboard'))
    
    
    
    
    

@payments.route('/payment-success/<int:transaction_id>')
@login_required
def payment_success(transaction_id):
    """Handle successful payment - REDIRECT TO DASHBOARD"""
    try:
        transaction = PaymentTransaction.query.get(transaction_id)
        
        if not transaction or transaction.user_id != current_user.id:
            flash('Transaction not found', 'error')
            return redirect(url_for('user_dashboard'))
        
        # Verify payment is actually completed
        if transaction.status != 'completed':
            payment_service = PaymentService()
            verification_result = payment_service.verify_flutterwave_payment(transaction.gateway_payment_id)
            
            if verification_result['success'] and verification_result['data'].get('status') == 'successful':
                payment_service.handle_successful_payment(transaction.id, verification_result['data'])
            else:
                flash('Payment verification failed', 'error')
                return redirect(url_for('user_dashboard'))
        
        campaign = AdCampaign.query.get(transaction.campaign_id) if transaction.campaign_id else None
        
        if campaign:
            print(f"✅ [PAYMENT SUCCESS] Final campaign status:")
            print(f"   - status: {campaign.status}")
            print(f"   - payment_status: {campaign.payment_status}")
            print(f"   - start_date: {campaign.start_date}")
            print(f"   - end_date: {campaign.end_date}")
        
        flash('Payment completed successfully! Your campaign is now active.', 'success')
        return redirect(url_for('user_dashboard'))
    
    except Exception as e:
        print(f"🔴 [PAYMENT SUCCESS] Error: {str(e)}")
        flash('An error occurred while processing your payment.', 'error')
        return redirect(url_for('user_dashboard'))
    
    
    
    

@payments.route('/payment-failed')
@login_required
def payment_failed():
    """Handle failed payment"""
    current_app.logger.info(f"⚠️ User {current_user.id} viewed payment failed page")
    return render_template('failed.html')





# @payments.route('/verify-payment', methods=['POST'])
# @login_required
# def verify_payment():
#     """Verify payment status (for AJAX calls)"""
#     try:
#         data = request.get_json()
#         reference = data.get('reference')
        
#         if not reference:
#             return jsonify({'success': False, 'error': 'No reference provided'})
        
#         payment_service = PaymentService()
#         result = payment_service.verify_paystack_payment(reference)
        
#         if result['success'] and result['data']['status'] == 'success':
#             # Find and update transaction
#             transaction = PaymentTransaction.query.filter_by(
#                 gateway_payment_id=reference,
#                 user_id=current_user.id
#             ).first()
            
#             if transaction:
#                 payment_service.handle_successful_payment(transaction.id, result['data'])
                
#                 # Send success email
#                 campaign = AdCampaign.query.get(transaction.campaign_id)
#                 package = AdPackage.query.get(campaign.package_id) if campaign else None
                
#                 if campaign and package:
#                     EmailService.send_ad_purchase_success(current_user, transaction, campaign, package)
                
#                 return jsonify({
#                     'success': True,
#                     'transaction_id': transaction.id,
#                     'status': 'completed'
#                 })
        
#         # Send failure email if payment failed
#         transaction = PaymentTransaction.query.filter_by(gateway_payment_id=reference).first()
#         if transaction:
#             campaign = AdCampaign.query.get(transaction.campaign_id)
#             package = AdPackage.query.get(campaign.package_id) if campaign else None
            
#             if package:
#                 EmailService.send_ad_purchase_failed(
#                     user=current_user,
#                     package=package,
#                     transaction=transaction,
#                     campaign=campaign,
#                     error_message="Payment verification failed"
#                 )
        
#         return jsonify({'success': False, 'error': 'Payment verification failed'})
        
#     except Exception as e:
#         current_app.logger.error(f"❌ Payment verification error: {str(e)}")
#         return jsonify({'success': False, 'error': str(e)})
    
    
    
    
    
    

    
    

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
    
    
    
    
@payments.route('/create-campaign', methods=['POST'])
@login_required
def create_campaign():
    """Create ad campaign with user-selected budget and targeting data"""
    try:
        data = request.get_json()
        print(f"🔵 [CREATE CAMPAIGN] Received data: {data}")
        
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400

        # Extract and validate data with correct field names
        daily_budget = data.get('daily_budget')
        duration_days = data.get('duration_days')
        title = data.get('title')
        description = data.get('description')
        target_url = data.get('target_url')
        call_to_action = data.get('call_to_action', 'Learn More')
        image = data.get('image', '')
        currency = data.get('currency', 'USD')
        
        # ✅ Extract targeting data
        targeting = data.get('targeting', {})
        target_gender = targeting.get('gender', 'all')
        target_age_min = targeting.get('age_min', 31)
        target_age_max = targeting.get('age_max', 65)
        target_locations = targeting.get('locations', [])
        target_interests = targeting.get('interests', [])
        target_language = targeting.get('language', 'all')
        target_relationship = targeting.get('relationship', 'all')
        target_education = targeting.get('education', 'all')
        target_occupation = targeting.get('occupation', 'all')
        
        
        print(f"🔵 [CREATE CAMPAIGN] Parsed: daily_budget={daily_budget}, duration_days={duration_days}, title={title}")
        print(f"🔵 [CREATE CAMPAIGN] Targeting: gender={target_gender}, age={target_age_min}-{target_age_max}, locations={len(target_locations)}, interests={len(target_interests)}")
        
        # Validate required fields
        validation_errors = []
        if not title:
            validation_errors.append('Ad title is required')
        if not target_url:
            validation_errors.append('Target URL is required')
        if not daily_budget:
            validation_errors.append('Daily budget is required')
        if not duration_days:
            validation_errors.append('Duration days is required')
            
        if validation_errors:
            print(f"🔴 [CREATE CAMPAIGN] Validation errors: {validation_errors}")
            return jsonify({'success': False, 'error': ', '.join(validation_errors)}), 400
        
        # Convert and validate numeric fields
        try:
            daily_budget = float(daily_budget)
            duration_days = int(duration_days)
            target_age_min = int(target_age_min)
            target_age_max = int(target_age_max)
        except (TypeError, ValueError) as e:
            print(f"🔴 [CREATE CAMPAIGN] Numeric conversion error: {e}")
            return jsonify({'success': False, 'error': 'Invalid budget, duration, or age format'}), 400
        
        if daily_budget < 2:
            return jsonify({'success': False, 'error': 'Minimum daily budget is $2'}), 400
        if duration_days < 3:
            return jsonify({'success': False, 'error': 'Minimum duration is 3 days'}), 400
        if target_age_min < 31 or target_age_max > 80 or target_age_min > target_age_max:
            return jsonify({'success': False, 'error': 'Invalid age range'}), 400
        
        # Calculate total budget
        total_budget = daily_budget * duration_days
        
        # ✅ Create campaign with ALL targeting data
        campaign = AdCampaign(
            user_id=current_user.id,
            title=title,
            description=description,
            image=image,
            target_url=target_url,
            call_to_action=call_to_action,
            budget=total_budget,
            daily_budget=daily_budget,
            duration_days=duration_days,
            currency=currency,  # ✅ Save currency
            status='pending',
            payment_status='pending',
            
            # ✅ Save all targeting data
            target_gender=json.dumps([target_gender]) if target_gender != 'all' else None,
            target_age_min=target_age_min,
            target_age_max=target_age_max,
            target_countries=json.dumps(target_locations) if target_locations else None,
            target_interests=json.dumps(target_interests) if target_interests else None,
            target_language=target_language if target_language != 'all' else None,
            
            # Set default values for other targeting fields
            target_education=json.dumps(target_education) if target_education else None,
            target_occupation=json.dumps(target_occupation) if target_occupation else None,
            target_relationship=json.dumps(target_relationship) if target_relationship else None,
            
        )
        
        db.session.add(campaign)
        db.session.commit()
        
        print(f"✅ [CREATE CAMPAIGN] Campaign created successfully: ID {campaign.id}")
        print(f"✅ [CREATE CAMPAIGN] Targeting saved: {campaign.get_targeting_data()}")
        
        return jsonify({
            'success': True,
            'campaign_id': campaign.id,
            'message': 'Campaign created successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"🔴 [CREATE CAMPAIGN] Campaign creation failed: {str(e)}")
        import traceback
        print(f"🔴 [CREATE CAMPAIGN] Traceback: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': str(e)}), 500
    


    
@payments.route('/initiate-payment', methods=['POST'])
@login_required
def initiate_payment():
    """Fixed payment initiation route"""
    try:
        data = request.get_json()
        print(f"🟡 [INITIATE PAYMENT] Request content type: {request.content_type}")
        print(f"🟡 [INITIATE PAYMENT] Raw data: {request.data}")

        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400

        campaign_id = data.get('campaign_id')
        amount = data.get('amount')
        currency = data.get('currency', 'USD').upper()

        print(f"🟡 [INITIATE PAYMENT] campaign_id: {campaign_id}, amount: {amount}, currency: {currency}")

        # Validate required fields
        if not campaign_id:
            return jsonify({'success': False, 'error': 'Campaign ID is required'}), 400
        
        if not amount:
            return jsonify({'success': False, 'error': 'Amount is required'}), 400

        # ✅ ADD CURRENCY VALIDATION
        supported_currencies = ['NGN', 'USD', 'GBP', 'EUR']  # Your supported currencies
        if currency not in supported_currencies:
            return jsonify({
                'success': False, 
                'error': f'Currency {currency} is not supported. Please use one of: {", ".join(supported_currencies)}'
            }), 400

        try:
            campaign_id = int(campaign_id)
            amount = float(amount)
        except (ValueError, TypeError):
            return jsonify({'success': False, 'error': 'Invalid campaign ID or amount format'}), 400

        # Rest of your existing code remains the same...
        campaign = AdCampaign.query.get(campaign_id)
        if not campaign:
            return jsonify({'success': False, 'error': 'Campaign not found'}), 404
            
        if campaign.user_id != current_user.id:
            return jsonify({'success': False, 'error': 'Unauthorized access to campaign'}), 403

        if campaign.payment_status == 'paid':
            return jsonify({'success': False, 'error': 'Campaign already paid'}), 400

        print(f"🟡 [INITIATE PAYMENT] Campaign found: {campaign.title}, User: {current_user.email}")

        payment_service = PaymentService()
        
        result = payment_service.create_flutterwave_transaction(
            user=current_user,
            campaign=campaign,
            amount=amount,
            currency=currency  # This now uses validated currency
        )

        print(f"🟡 [INITIATE PAYMENT] Payment service result: {result}")

        if result.get('success'):
            return jsonify(result)
        else:
            return jsonify({
                'success': False,
                'error': result.get('error', 'Payment initiation failed')
            }), 400

    except Exception as e:
        print(f"🔴 [INITIATE PAYMENT] Error: {str(e)}")
        import traceback
        print(f"🔴 [INITIATE PAYMENT] Traceback: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': 'Internal server error'}), 500
    
    
    
@payments.route('/debug-payment-service', methods=['GET'])
@login_required
def debug_payment_service():
    """Debug PaymentService configuration"""
    payment_service = PaymentService()
    
    # Test with a recent campaign
    campaign = AdCampaign.query.filter_by(user_id=current_user.id).order_by(AdCampaign.created_at.desc()).first()
    
    debug_info = {
        'service_initialized': True,
        'flutterwave_public_key': bool(payment_service.flutterwave_public_key),
        'flutterwave_secret_key': bool(payment_service.flutterwave_secret_key),
        'flutterwave_base_url': payment_service.flutterwave_base_url,
        'test_campaign_available': bool(campaign),
        'current_user': current_user.email
    }
    
    if campaign:
        debug_info['campaign_id'] = campaign.id
        debug_info['campaign_title'] = campaign.title
        
        # Test creating a transaction
        result = payment_service.create_flutterwave_transaction(current_user, campaign, 1.0, 'USD')
        debug_info['payment_test_result'] = result
    
    return jsonify(debug_info)
    
    
    
    
@payments.route('/test-payment-flow/<int:campaign_id>', methods=['GET'])
@login_required
def test_payment_flow(campaign_id):
    """Test payment flow for a specific campaign"""
    try:
        campaign = AdCampaign.query.get(campaign_id)
        if not campaign or campaign.user_id != current_user.id:
            return jsonify({'success': False, 'error': 'Campaign not found or unauthorized'})
        
        # Calculate amount based on daily budget and duration
        amount = campaign.daily_budget * campaign.duration_days
        
        payment_service = PaymentService()
        
        print(f"🧪 [TEST PAYMENT] Testing with campaign {campaign_id}, amount: {amount}")
        
        result = payment_service.create_flutterwave_transaction(
            current_user, campaign, amount, 'USD'
        )
        
        return jsonify({
            'success': True,
            'test_result': result,
            'campaign': {
                'id': campaign.id,
                'title': campaign.title,
                'daily_budget': campaign.daily_budget,
                'duration_days': campaign.duration_days,
                'calculated_amount': amount
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    
    

print('LEAVING PAYMENTSAASSSSSSS')
    
    
@payments.route('/test-flutterwave-direct', methods=['GET'])
@login_required
def test_flutterwave_direct():
    """Test Flutterwave API directly"""
    try:
        payment_service = PaymentService()
        
        # Simple test payload
        test_data = {
            'tx_ref': f"direct_test_{int(time.time())}",
            'amount': '10',  # Small test amount
            'currency': 'USD',
            'redirect_url': 'http://localhost:5000/user/dashboard',
            'payment_options': 'card',
            'customer': {
                'email': current_user.email,
                'name': current_user.full_name,
            },
            'customizations': {
                'title': 'Kimbela Test',
                'description': 'Direct Flutterwave Test',
            }
        }
        
        headers = {
            'Authorization': f'Bearer {payment_service.flutterwave_secret_key}',
            'Content-Type': 'application/json'
        }
        
        print(f"🧪 [DIRECT TEST] Sending to Flutterwave:")
        print(f"🧪 [DIRECT TEST] URL: https://api.flutterwave.com/v3/payments")
        print(f"🧪 [DIRECT TEST] Headers: {headers}")
        print(f"🧪 [DIRECT TEST] Data: {json.dumps(test_data, indent=2)}")
        
        response = requests.post(
            'https://api.flutterwave.com/v3/payments',
            headers=headers,
            json=test_data,
            timeout=30
        )
        
        result = {
            'status_code': response.status_code,
            'success': response.status_code == 200,
            'response': response.json() if response.status_code == 200 else response.text
        }
        
        print(f"🧪 [DIRECT TEST] Flutterwave response:")
        print(f"🧪 [DIRECT TEST] Status: {result['status_code']}")
        print(f"🧪 [DIRECT TEST] Response: {json.dumps(result, indent=2)}")
        
        return jsonify(result)
        
    except Exception as e:
        print(f"🔴 [DIRECT TEST] Error: {str(e)}")
        import traceback
        print(f"🔴 [DIRECT TEST] Traceback: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500





    
@payments.route('/diagnose-payment', methods=['GET'])
@login_required
def diagnose_payment():
    """Diagnose payment configuration"""
    try:
        payment_service = PaymentService()
        
        diagnostic_info = {
            'flutterwave_configured': bool(payment_service.flutterwave_secret_key),
            'base_url': current_app.config.get('BASE_URL'),
            'environment_variables': {
                'PUBLIC_KEY_loaded': bool(os.getenv('PUBLIC_KEY')),
                'SECRET_KEY_loaded': bool(os.getenv('SECRET_KEY')),
                'ENCRYPTION_KEY_loaded': bool(os.getenv('ENCRYPTION_KEY')),
            },
            'current_user': {
                'id': current_user.id,
                'email': current_user.email,
                'name': current_user.full_name
            }
        }
        
        print(f"🔍 [DIAGNOSTIC] Payment configuration: {json.dumps(diagnostic_info, indent=2)}")
        
        return jsonify(diagnostic_info)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
    

    

@payments.route('/verify-payment', methods=['POST'])
@login_required
def verify_payment():
    """Verify payment status"""
    try:
        data = request.get_json()
        reference = data.get('reference')
        
        payment_service = PaymentService()
        result = payment_service.verify_flutterwave_payment(reference)
        
        return jsonify(result)
        
    except Exception as e:
        current_app.logger.error(f"Payment verification failed: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500




@payments.route('/get-supported-currencies', methods=['GET'])
@login_required
def get_supported_currencies():
    """Get list of currencies supported by your Flutterwave account"""
    try:
        # For Nigerian Flutterwave accounts, these are typically supported
        supported_currencies = ['NGN', 'USD', 'GBP', 'EUR']
        
        # You could also fetch this dynamically from Flutterwave API
        # But for now, we'll use the common ones
        
        current_app.logger.info(f"✅ Supported currencies requested by user {current_user.id}")
        
        return jsonify({
            'success': True,
            'currencies': supported_currencies
        })
        
    except Exception as e:
        current_app.logger.error(f"❌ Error getting supported currencies: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'currencies': ['NGN', 'USD']  # Fallback
        }), 500
        
        
        
        
@payments.route('/debug-transaction/<tx_ref>', methods=['GET'])
@login_required
def debug_transaction(tx_ref):
    """Debug transaction status"""
    try:
        transaction = PaymentTransaction.query.filter_by(gateway_payment_id=tx_ref).first()
        if not transaction:
            return jsonify({'success': False, 'error': 'Transaction not found'})
        
        campaign = AdCampaign.query.get(transaction.campaign_id) if transaction.campaign_id else None
        
        debug_info = {
            'transaction': {
                'id': transaction.id,
                'status': transaction.status,
                'gateway_status': transaction.gateway_status,
                'gateway_payment_id': transaction.gateway_payment_id,
                'campaign_id': transaction.campaign_id,
                'amount': transaction.amount,
                'currency': transaction.currency,
                'created_at': transaction.created_at.isoformat() if transaction.created_at else None,
                'updated_at': transaction.updated_at.isoformat() if transaction.updated_at else None
            },
            'campaign': {
                'id': campaign.id if campaign else None,
                'title': campaign.title if campaign else None,
                'status': campaign.status if campaign else None,
                'payment_status': campaign.payment_status if campaign else None,
                'start_date': campaign.start_date.isoformat() if campaign and campaign.start_date else None,
                'end_date': campaign.end_date.isoformat() if campaign and campaign.end_date else None,
                'payment_gateway': campaign.payment_gateway if campaign else None,
                'payment_id': campaign.payment_id if campaign else None
            } if campaign else None
        }
        
        return jsonify(debug_info)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@payments.route('/fix-campaign-status/<int:campaign_id>', methods=['POST'])
@login_required
def fix_campaign_status(campaign_id):
    """Manually fix campaign status"""
    try:
        campaign = AdCampaign.query.get(campaign_id)
        if not campaign or campaign.user_id != current_user.id:
            return jsonify({'success': False, 'error': 'Campaign not found or unauthorized'})
        
        # Find the successful transaction for this campaign
        transaction = PaymentTransaction.query.filter_by(
            campaign_id=campaign_id,
            status='completed'
        ).first()
        
        if transaction:
            # Update campaign with transaction data
            campaign.payment_status = 'paid'
            campaign.status = 'active'
            campaign.payment_gateway = transaction.gateway
            campaign.payment_id = transaction.gateway_payment_id
            campaign.start_date = datetime.utcnow()
            campaign.end_date = datetime.utcnow() + timedelta(days=campaign.duration_days)
            campaign.updated_at = datetime.utcnow()
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'Campaign status fixed successfully',
                'campaign': {
                    'id': campaign.id,
                    'status': campaign.status,
                    'payment_status': campaign.payment_status,
                    'start_date': campaign.start_date.isoformat(),
                    'end_date': campaign.end_date.isoformat()
                }
            })
        else:
            return jsonify({'success': False, 'error': 'No completed transaction found for this campaign'})
            
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500