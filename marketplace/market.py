# routes/market.py
from flask import Blueprint, request, jsonify, render_template, redirect, url_for, current_app, flash, session
from flask_login import login_required, current_user
from extensions import db
from models import (
    User, MarketplaceService, MarketplaceCategory, MarketplaceSubscription, 
    MarketplaceReview, MarketplacePayment, MarketplaceClick, PaymentTransaction
)
import cloudinary.uploader
import os, requests, json, uuid
from datetime import datetime, timedelta
from sqlalchemy import or_, desc, func
from werkzeug.utils import secure_filename
import time

market = Blueprint("market", __name__)

# ==================== HELPER FUNCTIONS ====================

def allowed_file(filename):
    """Check if file extension is allowed"""
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf', 'doc', 'docx'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def upload_to_cloudinary(file, folder="marketplace"):
    """Upload file to Cloudinary"""
    try:
        upload_result = cloudinary.uploader.upload(
            file,
            folder=f"kimbela/{folder}",
            resource_type="auto"
        )
        return upload_result.get('secure_url')
    except Exception as e:
        print(f"Cloudinary upload error: {e}")
        return None

def format_price(price):
    """Format price with commas"""
    return f"{price:,}"

def log_click(service_id, click_type, user_id=None):
    """Log a click on a service"""
    click = MarketplaceClick(
        service_id=service_id,
        user_id=user_id,
        click_type=click_type,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string
    )
    db.session.add(click)
    db.session.commit()

def get_featured_sellers(limit=6):
    """Get random featured sellers based on performance"""
    # Get sellers with featured services
    featured_services = MarketplaceService.query.filter_by(
        is_featured=True,
        status="active"
    ).all()
    
    seller_ids = list(set([service.seller_id for service in featured_services]))
    
    if len(seller_ids) == 0:
        # Fallback to sellers with highest ratings
        sellers = User.query.join(MarketplaceService).filter(
            MarketplaceService.status == "active"
        ).order_by(func.random()).limit(limit).all()
        return sellers
    
    # Get random sellers from featured list
    import random
    random.shuffle(seller_ids)
    selected_ids = seller_ids[:min(limit, len(seller_ids))]
    
    sellers = User.query.filter(User.id.in_(selected_ids)).all()
    
    # Add random sellers if not enough
    if len(sellers) < limit:
        additional = limit - len(sellers)
        extra_sellers = User.query.filter(
            User.id.notin_(seller_ids),
            User.id != current_user.id if current_user.is_authenticated else True
        ).order_by(func.random()).limit(additional).all()
        sellers.extend(extra_sellers)
    
    return sellers

# ==================== MAIN MARKETPLACE ROUTES ====================

@market.route("/main_market", methods=["GET"])
def main_market():
    """Marketplace homepage"""
    # Get all active services with pagination
    page = request.args.get('page', 1, type=int)
    per_page = 12
    
    services_query = MarketplaceService.query.filter_by(status="active")
    
    # Filter by category
    category_slug = request.args.get('category')
    if category_slug:
        category = MarketplaceCategory.query.filter_by(slug=category_slug).first()
        if category:
            services_query = services_query.filter_by(category_id=category.id)
    
    # Filter by search
    search_query = request.args.get('q')
    if search_query:
        services_query = services_query.filter(
            or_(
                MarketplaceService.title.ilike(f'%{search_query}%'),
                MarketplaceService.description.ilike(f'%{search_query}%'),
                MarketplaceService.short_description.ilike(f'%{search_query}%')
            )
        )
    
    # Filter by price
    min_price = request.args.get('min_price', type=int)
    max_price = request.args.get('max_price', type=int)
    if min_price is not None:
        services_query = services_query.filter(MarketplaceService.price_tokens >= min_price)
    if max_price is not None:
        services_query = services_query.filter(MarketplaceService.price_tokens <= max_price)
    
    # Filter by service type
    service_type = request.args.get('type')
    if service_type:
        services_query = services_query.filter_by(service_type=service_type)
    
    # Filter by featured
    featured_only = request.args.get('featured') == 'true'
    if featured_only:
        services_query = services_query.filter_by(is_featured=True)
    
    # Sort
    sort_by = request.args.get('sort', 'newest')
    if sort_by == 'popular':
        services_query = services_query.order_by(desc(MarketplaceService.views))
    elif sort_by == 'rating':
        services_query = services_query.order_by(desc(MarketplaceService.average_rating))
    elif sort_by == 'price_low':
        services_query = services_query.order_by(MarketplaceService.price_tokens)
    elif sort_by == 'price_high':
        services_query = services_query.order_by(desc(MarketplaceService.price_tokens))
    else:  # newest
        services_query = services_query.order_by(desc(MarketplaceService.created_at))
    
    # Paginate
    services = services_query.paginate(page=page, per_page=per_page, error_out=False)
    
    # Get categories
    categories = MarketplaceCategory.query.filter_by(is_active=True).order_by('sort_order').all()
    
    # Get featured sellers (random)
    featured_sellers = get_featured_sellers(6)
    
    # Get featured services
    featured_services = MarketplaceService.query.filter_by(
        is_featured=True,
        status="active"
    ).order_by(func.random()).limit(6).all()
    
    return render_template(
        "main_market.html",
        services=services,
        categories=categories,
        featured_sellers=featured_sellers,
        featured_services=featured_services,
        search_query=search_query,
        category_slug=category_slug,
        sort_by=sort_by,
        min_price=min_price,
        max_price=max_price,
        service_type=service_type,
        featured_only=featured_only,
        format_price=format_price
    )


@market.route("/marketplace/service/<slug>", methods=["GET"])
def service_detail(slug):
    """View service details"""
    service = MarketplaceService.query.filter_by(slug=slug).first_or_404()
    
    # Check if service is active
    if not service.is_active and (not current_user.is_authenticated or current_user.id != service.seller_id):
        flash("This service is no longer available", "warning")
        return redirect(url_for('market.main_market'))
    
    # Increment views
    service.views += 1
    db.session.commit()
    
    # Log view
    user_id = current_user.id if current_user.is_authenticated else None
    log_click(service.id, "view", user_id)
    
    # Get related services
    related_services = MarketplaceService.query.filter(
        MarketplaceService.category_id == service.category_id,
        MarketplaceService.id != service.id,
        MarketplaceService.status == "active"
    ).order_by(func.random()).limit(4).all()
    
    # Get reviews
    reviews = MarketplaceReview.query.filter_by(
        service_id=service.id,
        status="approved"
    ).order_by(desc(MarketplaceReview.created_at)).limit(10).all()
    
    # Get seller's other services
    seller_services = MarketplaceService.query.filter_by(
        seller_id=service.seller_id,
        status="active"
    ).filter(MarketplaceService.id != service.id).limit(4).all()
    
    # Parse JSON fields
    contact_methods = service.contact_methods_list
    gallery_images = service.gallery_images_list
    features = service.features_list
    
    return render_template(
        "marketplace/service_detail.html",
        service=service,
        related_services=related_services,
        reviews=reviews,
        seller_services=seller_services,
        contact_methods=contact_methods,
        gallery_images=gallery_images,
        features=features,
        format_price=format_price
    )


# @market.route("/seller/<int:seller_id>", methods=["GET"])
# def seller_profile(seller_id):
#     """View seller profile"""
#     seller = User.query.get_or_404(seller_id)
    
#     # Get seller's services
#     page = request.args.get('page', 1, type=int)
#     per_page = 12
    
#     services_query = MarketplaceService.query.filter_by(
#         seller_id=seller_id,
#         status="active"
#     ).order_by(desc(MarketplaceService.created_at))
    
#     services = services_query.paginate(page=page, per_page=per_page, error_out=False)
    
#     # Get seller stats
#     total_services = services_query.count()
#     total_reviews = MarketplaceReview.query.join(MarketplaceService).filter(
#         MarketplaceService.seller_id == seller_id
#     ).count()
    
#     # Calculate average rating
#     avg_rating = db.session.query(
#         func.avg(MarketplaceReview.rating)
#     ).join(MarketplaceService).filter(
#         MarketplaceService.seller_id == seller_id
#     ).scalar() or 0
    
#     return render_template(
#         "marketplace/seller_profile.html",
#         seller=seller,
#         services=services,
#         total_services=total_services,
#         total_reviews=total_reviews,
#         avg_rating=round(avg_rating, 1),
#         format_price=format_price
#     )


@market.route("/marketplace/category/<slug>", methods=["GET"])
def category_detail(slug):
    """View category details"""
    category = MarketplaceCategory.query.filter_by(slug=slug).first_or_404()
    
    # Get services in this category
    page = request.args.get('page', 1, type=int)
    per_page = 12
    
    services_query = MarketplaceService.query.filter_by(
        category_id=category.id,
        status="active"
    ).order_by(desc(MarketplaceService.created_at))
    
    services = services_query.paginate(page=page, per_page=per_page, error_out=False)
    
    # Get subcategories
    subcategories = MarketplaceCategory.query.filter_by(
        parent_id=category.id,
        is_active=True
    ).order_by('sort_order').all()
    
    return render_template(
        "marketplace/category_detail.html",
        category=category,
        services=services,
        subcategories=subcategories,
        format_price=format_price
    )


# ==================== SELLER DASHBOARD ROUTES ====================
@market.route("/seller_dashboard", methods=["GET"])
@login_required
def seller_dashboard():
    """Seller dashboard"""
    # Get seller's services
    services = MarketplaceService.query.filter_by(
        seller_id=current_user.id
    ).order_by(desc(MarketplaceService.created_at)).all()
    
    # Get stats
    total_services = len(services)
    active_services = len([s for s in services if s.is_active])
    total_views = sum(s.views for s in services)
    total_clicks = sum(s.clicks for s in services)
    
    # Calculate total earnings - handle None values
    total_earnings = sum((s.earnings or 0) for s in services)
    
    # Calculate average rating
    if total_services > 0:
        total_rating = sum((s.average_rating or 0) for s in services)
        average_rating = total_rating / total_services
    else:
        average_rating = 0.0
    
    # Calculate total reviews
    total_reviews = sum((s.review_count or 0) for s in services)
    
    # Get recent clicks
    recent_clicks = MarketplaceClick.query.join(MarketplaceService).filter(
        MarketplaceService.seller_id == current_user.id
    ).order_by(desc(MarketplaceClick.created_at)).limit(10).all()
    
    # Get current subscription
    current_sub = None
    for service in services:
        if service.subscription:
            current_sub = service.subscription
            break
    
    return render_template(
        "seller_dashboard.html",
        services=services,
        total_services=total_services,
        active_services=active_services,
        total_views=total_views,
        total_clicks=total_clicks,
        recent_clicks=recent_clicks,
        current_sub=current_sub,
        total_earnings=total_earnings,
        average_rating=average_rating,
        total_reviews=total_reviews,
        format_price=format_price
    )
    

@market.route("/create_service", methods=["GET", "POST"])
@login_required
def create_service():
    """Create a new service"""
    if request.method == "GET":
        # Get categories
        categories = MarketplaceCategory.query.filter_by(is_active=True).order_by('name').all()
        
        # Get subscription plans
        subscriptions = MarketplaceSubscription.query.filter_by(is_active=True).order_by('sort_order').all()
        
        return render_template(
            "create_service.html",
            categories=categories,
            subscriptions=subscriptions
        )
    
    # POST: Create service
    try:
        # Validate required fields
        title = request.form.get('title')
        category_id = request.form.get('category_id')
        description = request.form.get('description')
        price_tokens = request.form.get('price_tokens', 0, type=int)
        service_type = request.form.get('service_type', 'service')
        subscription_id = request.form.get('subscription_id')
        
        if not all([title, category_id, description]):
            flash("Please fill in all required fields", "danger")
            return redirect(url_for('market.create_service'))
        
        # Create slug from title
        slug = title.lower().replace(' ', '-') + '-' + str(int(time.time()))
        
        # Get subscription
        subscription = None
        if subscription_id:
            subscription = MarketplaceSubscription.query.get(subscription_id)
            if not subscription:
                flash("Invalid subscription plan", "danger")
                return redirect(url_for('market.create_service'))
        
        # Create service
        service = MarketplaceService(
            seller_id=current_user.id,
            category_id=category_id,
            title=title,
            slug=slug,
            description=description,
            short_description=request.form.get('short_description', '')[:500],
            service_type=service_type,
            price_tokens=price_tokens,
            is_free=price_tokens == 0,
            phone_number=request.form.get('phone_number'),
            whatsapp_number=request.form.get('whatsapp_number'),
            email=request.form.get('email'),
            duration=request.form.get('duration'),
            availability=request.form.get('availability'),
            subscription_id=subscription_id,
            subscription_status="pending" if subscription else "active",
            subscription_expires=datetime.utcnow() + timedelta(days=30) if subscription else None,
            status="pending" if subscription else "active"
        )
        
        # Handle contact methods
        contact_methods = []
        if request.form.get('contact_whatsapp'):
            contact_methods.append('whatsapp')
        if request.form.get('contact_phone'):
            contact_methods.append('phone')
        if request.form.get('contact_messenger'):
            contact_methods.append('messenger')
        if request.form.get('contact_email'):
            contact_methods.append('email')
        service.contact_methods = json.dumps(contact_methods)
        
        # Handle features
        features = []
        feature_count = int(request.form.get('feature_count', 0))
        for i in range(1, feature_count + 1):
            feature = request.form.get(f'feature_{i}')
            if feature:
                features.append(feature)
        service.features = json.dumps(features)
        
        # Handle cover image upload
        if 'cover_image' in request.files:
            file = request.files['cover_image']
            if file and allowed_file(file.filename):
                image_url = upload_to_cloudinary(file, "services/cover")
                if image_url:
                    service.cover_image = image_url
        
        # Handle gallery images
        gallery_images = []
        for i in range(1, 6):
            file_key = f'gallery_image_{i}'
            if file_key in request.files:
                file = request.files[file_key]
                if file and allowed_file(file.filename):
                    image_url = upload_to_cloudinary(file, "services/gallery")
                    if image_url:
                        gallery_images.append(image_url)
        if gallery_images:
            service.gallery_images = json.dumps(gallery_images)
        
        # Handle digital file upload
        if service_type == 'digital' and 'digital_file' in request.files:
            file = request.files['digital_file']
            if file and allowed_file(file.filename):
                file_url = upload_to_cloudinary(file, "services/digital")
                if file_url:
                    service.digital_file = file_url
                    service.file_type = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        
        db.session.add(service)
        db.session.commit()
        
        # Redirect to payment if subscription required
        if subscription:
            return redirect(url_for('market.payment', service_id=service.id))
        
        flash("Service created successfully! It will be reviewed before publishing.", "success")
        return redirect(url_for('market.seller_dashboard'))
    
    except Exception as e:
        db.session.rollback()
        print(f"Error creating service: {e}")
        flash("An error occurred while creating the service. Please try again.", "danger")
        return redirect(url_for('market.create_service'))


@market.route("/edit/<int:service_id>", methods=["GET", "POST"])
@login_required
def edit_service(service_id):
    """Edit a service"""
    service = MarketplaceService.query.get_or_404(service_id)
    
    # Check ownership
    if service.seller_id != current_user.id:
        flash("You don't have permission to edit this service", "danger")
        return redirect(url_for('market.seller_dashboard'))
    
    if request.method == "GET":
        categories = MarketplaceCategory.query.filter_by(is_active=True).order_by('name').all()
        subscriptions = MarketplaceSubscription.query.filter_by(is_active=True).order_by('sort_order').all()
        
        return render_template(
            "marketplace/edit_service.html",
            service=service,
            categories=categories,
            subscriptions=subscriptions
        )
    
    # POST: Update service
    try:
        service.title = request.form.get('title', service.title)
        service.category_id = request.form.get('category_id', service.category_id)
        service.description = request.form.get('description', service.description)
        service.short_description = request.form.get('short_description', service.short_description)[:500]
        service.price_tokens = request.form.get('price_tokens', service.price_tokens, type=int)
        service.is_free = service.price_tokens == 0
        service.phone_number = request.form.get('phone_number')
        service.whatsapp_number = request.form.get('whatsapp_number')
        service.email = request.form.get('email')
        service.duration = request.form.get('duration')
        service.availability = request.form.get('availability')
        
        # Update contact methods
        contact_methods = []
        if request.form.get('contact_whatsapp'):
            contact_methods.append('whatsapp')
        if request.form.get('contact_phone'):
            contact_methods.append('phone')
        if request.form.get('contact_messenger'):
            contact_methods.append('messenger')
        if request.form.get('contact_email'):
            contact_methods.append('email')
        service.contact_methods = json.dumps(contact_methods)
        
        # Update features
        features = []
        feature_count = int(request.form.get('feature_count', 0))
        for i in range(1, feature_count + 1):
            feature = request.form.get(f'feature_{i}')
            if feature:
                features.append(feature)
        service.features = json.dumps(features)
        
        # Update cover image
        if 'cover_image' in request.files:
            file = request.files['cover_image']
            if file and allowed_file(file.filename):
                image_url = upload_to_cloudinary(file, "services/cover")
                if image_url:
                    service.cover_image = image_url
        
        # Update gallery images
        gallery_images = service.gallery_images_list
        for i in range(1, 6):
            file_key = f'gallery_image_{i}'
            if file_key in request.files:
                file = request.files[file_key]
                if file and allowed_file(file.filename):
                    image_url = upload_to_cloudinary(file, "services/gallery")
                    if image_url and image_url not in gallery_images:
                        gallery_images.append(image_url)
        
        # Handle remove gallery images
        remove_images = request.form.getlist('remove_gallery')
        gallery_images = [img for img in gallery_images if img not in remove_images]
        
        if gallery_images:
            service.gallery_images = json.dumps(gallery_images)
        else:
            service.gallery_images = None
        
        db.session.commit()
        
        flash("Service updated successfully!", "success")
        return redirect(url_for('market.seller_dashboard'))
    
    except Exception as e:
        db.session.rollback()
        print(f"Error updating service: {e}")
        flash("An error occurred while updating the service. Please try again.", "danger")
        return redirect(url_for('market.edit_service', service_id=service_id))


@market.route("/marketplace/delete/<int:service_id>", methods=["POST"])
@login_required
def delete_service(service_id):
    """Delete a service"""
    service = MarketplaceService.query.get_or_404(service_id)
    
    # Check ownership
    if service.seller_id != current_user.id:
        return jsonify({"success": False, "error": "Permission denied"}), 403
    
    try:
        db.session.delete(service)
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting service: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@market.route("/marketplace/toggle-status/<int:service_id>", methods=["POST"])
@login_required
def toggle_service_status(service_id):
    """Toggle service active status"""
    service = MarketplaceService.query.get_or_404(service_id)
    
    # Check ownership
    if service.seller_id != current_user.id:
        return jsonify({"success": False, "error": "Permission denied"}), 403
    
    try:
        if service.status == "active":
            service.status = "paused"
        elif service.status == "paused":
            service.status = "active"
        
        db.session.commit()
        return jsonify({
            "success": True,
            "status": service.status
        })
    except Exception as e:
        db.session.rollback()
        print(f"Error toggling service status: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ==================== PAYMENT ROUTES ====================

@market.route("/marketplace/payment/<int:service_id>", methods=["GET"])
@login_required
def payment(service_id):
    """Payment page for service subscription"""
    service = MarketplaceService.query.get_or_404(service_id)
    
    # Check ownership
    if service.seller_id != current_user.id:
        flash("Permission denied", "danger")
        return redirect(url_for('market.seller_dashboard'))
    
    # Check if already paid
    if service.subscription_status == "active":
        flash("Service subscription is already active", "info")
        return redirect(url_for('market.seller_dashboard'))
    
    subscription = service.subscription
    if not subscription:
        flash("No subscription required for this service", "info")
        return redirect(url_for('market.seller_dashboard'))
    
    return render_template(
        "marketplace/payment.html",
        service=service,
        subscription=subscription,
        format_price=format_price
    )


@market.route("/marketplace/initiate-payment", methods=["POST"])
@login_required
def initiate_payment():
    """Initiate Flutterwave payment"""
    try:
        service_id = request.form.get('service_id')
        subscription_id = request.form.get('subscription_id')
        
        service = MarketplaceService.query.get_or_404(service_id)
        subscription = MarketplaceSubscription.query.get_or_404(subscription_id)
        
        # Check ownership
        if service.seller_id != current_user.id:
            return jsonify({
                "success": False,
                "error": "Permission denied"
            }), 403
        
        # Generate unique transaction reference
        tx_ref = f"KIMBELA-MP-{int(time.time())}-{service_id}"
        
        # Create payment record
        payment = MarketplacePayment(
            user_id=current_user.id,
            service_id=service_id,
            subscription_id=subscription_id,
            amount=subscription.price_usd,
            tokens_paid=subscription.price_tokens,
            gateway="flutterwave",
            gateway_reference=tx_ref,
            status="pending",
            description=f"Marketplace subscription: {subscription.name} for service: {service.title}"
        )
        db.session.add(payment)
        db.session.commit()
        
        # Prepare Flutterwave payment data
        payment_data = {
            "tx_ref": tx_ref,
            "amount": str(subscription.price_usd),
            "currency": "USD",
            "redirect_url": url_for('market.payment_callback', _external=True),
            "customer": {
                "email": current_user.email,
                "name": current_user.full_name,
                "phone_number": current_user.phone_number
            },
            "customizations": {
                "title": "Kimbela Marketplace",
                "description": f"Subscription: {subscription.name}",
                "logo": url_for('static', filename='assets/img/kim.png', _external=True)
            },
            "meta": {
                "service_id": service_id,
                "subscription_id": subscription_id,
                "payment_id": payment.id,
                "user_id": current_user.id
            }
        }
        
        return jsonify({
            "success": True,
            "payment_data": payment_data,
            "flutterwave_public_key": current_app.config.get('FLUTTERWAVE_PUBLIC_KEY')
        })
    
    except Exception as e:
        db.session.rollback()
        print(f"Error initiating payment: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@market.route("/marketplace/payment-callback", methods=["GET"])
@login_required
def payment_callback():
    """Handle Flutterwave payment callback"""
    try:
        tx_ref = request.args.get('tx_ref')
        transaction_id = request.args.get('transaction_id')
        status = request.args.get('status')
        
        # Verify payment with Flutterwave
        payment = MarketplacePayment.query.filter_by(gateway_reference=tx_ref).first_or_404()
        
        if payment.user_id != current_user.id:
            flash("Unauthorized access", "danger")
            return redirect(url_for('market.seller_dashboard'))
        
        if status == "successful":
            # Update payment record
            payment.gateway_payment_id = transaction_id
            payment.gateway_status = "successful"
            payment.status = "completed"
            payment.paid_at = datetime.utcnow()
            
            # Update service subscription
            service = payment.service
            service.subscription_status = "active"
            service.subscription_expires = datetime.utcnow() + timedelta(days=30)
            service.status = "pending"  # Will be reviewed by admin
            
            # Create payment transaction record
            transaction = PaymentTransaction(
                user_id=current_user.id,
                amount=payment.amount,
                currency=payment.currency,
                gateway="flutterwave",
                gateway_reference=tx_ref,
                gateway_payment_id=transaction_id,
                gateway_status="successful",
                status="completed",
                description=f"Marketplace subscription payment for {service.title}",
                transaction_type="marketplace_subscription"
            )
            db.session.add(transaction)
            db.session.commit()
            
            flash("Payment successful! Your service is now pending review.", "success")
            
            # TODO: Send email confirmation
            
        else:
            payment.status = "failed"
            payment.gateway_status = status
            db.session.commit()
            flash("Payment failed. Please try again.", "danger")
        
        return redirect(url_for('market.seller_dashboard'))
    
    except Exception as e:
        print(f"Payment callback error: {e}")
        flash("An error occurred processing your payment", "danger")
        return redirect(url_for('market.seller_dashboard'))


# ==================== API ROUTES ====================

@market.route("/api/marketplace/services", methods=["GET"])
def api_services():
    """API endpoint for services (for AJAX loading)"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 12
        
        # Build query
        query = MarketplaceService.query.filter_by(status="active")
        
        # Apply filters
        category_id = request.args.get('category_id')
        if category_id:
            query = query.filter_by(category_id=category_id)
        
        search = request.args.get('search')
        if search:
            query = query.filter(
                or_(
                    MarketplaceService.title.ilike(f'%{search}%'),
                    MarketplaceService.description.ilike(f'%{search}%')
                )
            )
        
        min_price = request.args.get('min_price', type=int)
        max_price = request.args.get('max_price', type=int)
        if min_price is not None:
            query = query.filter(MarketplaceService.price_tokens >= min_price)
        if max_price is not None:
            query = query.filter(MarketplaceService.price_tokens <= max_price)
        
        service_type = request.args.get('service_type')
        if service_type:
            query = query.filter_by(service_type=service_type)
        
        featured_only = request.args.get('featured') == 'true'
        if featured_only:
            query = query.filter_by(is_featured=True)
        
        # Sort
        sort_by = request.args.get('sort', 'newest')
        if sort_by == 'popular':
            query = query.order_by(desc(MarketplaceService.views))
        elif sort_by == 'rating':
            query = query.order_by(desc(MarketplaceService.average_rating))
        elif sort_by == 'price_low':
            query = query.order_by(MarketplaceService.price_tokens)
        elif sort_by == 'price_high':
            query = query.order_by(desc(MarketplaceService.price_tokens))
        else:  # newest
            query = query.order_by(desc(MarketplaceService.created_at))
        
        # Paginate
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        
        # Prepare response
        services = []
        for service in pagination.items:
            seller = service.seller
            services.append({
                'id': service.id,
                'title': service.title,
                'slug': service.slug,
                'short_description': service.short_description,
                'price_tokens': service.price_tokens,
                'formatted_price': format_price(service.price_tokens),
                'is_free': service.is_free,
                'is_featured': service.is_featured,
                'cover_image': service.cover_image or url_for('static', filename='assets/img/default-service.jpg'),
                'service_type': service.service_type,
                'duration': service.duration,
                'average_rating': service.average_rating,
                'review_count': service.review_count,
                'views': service.views,
                'created_at': service.created_at.isoformat(),
                'seller': {
                    'id': seller.id,
                    'name': seller.full_name,
                    'avatar': seller.profile_pic or url_for('static', filename='assets/img/default-avatar.png'),
                    'rating': seller.avg_rating if hasattr(seller, 'avg_rating') else 0
                },
                'category': service.category.name if service.category else 'Uncategorized'
            })
        
        return jsonify({
            'success': True,
            'services': services,
            'has_next': pagination.has_next,
            'has_prev': pagination.has_prev,
            'page': pagination.page,
            'pages': pagination.pages,
            'total': pagination.total
        })
    
    except Exception as e:
        print(f"API services error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@market.route("/api/marketplace/log-click/<int:service_id>", methods=["POST"])
def log_service_click(service_id):
    """Log a click on a service"""
    try:
        click_type = request.json.get('type', 'view')
        user_id = current_user.id if current_user.is_authenticated else None
        
        # Update service click count
        service = MarketplaceService.query.get(service_id)
        if service:
            if click_type == 'contact':
                service.clicks += 1
            elif click_type == 'whatsapp':
                service.clicks += 1
            db.session.commit()
        
        # Log click
        log_click(service_id, click_type, user_id)
        
        return jsonify({'success': True})
    
    except Exception as e:
        print(f"Log click error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@market.route("/api/marketplace/seller/<int:seller_id>/stats", methods=["GET"])
@login_required
def seller_stats(seller_id):
    """Get seller statistics"""
    if current_user.id != seller_id:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    
    try:
        # Get total services
        total_services = MarketplaceService.query.filter_by(seller_id=seller_id).count()
        
        # Get active services
        active_services = MarketplaceService.query.filter_by(
            seller_id=seller_id,
            status='active'
        ).count()
        
        # Get total views
        total_views = db.session.query(
            func.sum(MarketplaceService.views)
        ).filter_by(seller_id=seller_id).scalar() or 0
        
        # Get total clicks
        total_clicks = db.session.query(
            func.sum(MarketplaceService.clicks)
        ).filter_by(seller_id=seller_id).scalar() or 0
        
        # Get revenue (in tokens)
        total_revenue = db.session.query(
            func.sum(MarketplaceService.price_tokens)
        ).filter_by(seller_id=seller_id).scalar() or 0
        
        # Get monthly stats
        now = datetime.utcnow()
        month_start = datetime(now.year, now.month, 1)
        
        monthly_views = db.session.query(
            func.sum(MarketplaceService.views)
        ).filter(
            MarketplaceService.seller_id == seller_id,
            MarketplaceService.updated_at >= month_start
        ).scalar() or 0
        
        monthly_clicks = db.session.query(
            func.sum(MarketplaceService.clicks)
        ).filter(
            MarketplaceService.seller_id == seller_id,
            MarketplaceService.updated_at >= month_start
        ).scalar() or 0
        
        return jsonify({
            'success': True,
            'stats': {
                'total_services': total_services,
                'active_services': active_services,
                'total_views': total_views,
                'total_clicks': total_clicks,
                'total_revenue': total_revenue,
                'monthly_views': monthly_views,
                'monthly_clicks': monthly_clicks
            }
        })
    
    except Exception as e:
        print(f"Seller stats error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== ADMIN ROUTES ====================

@market.route("/admin/marketplace/services", methods=["GET"])
@login_required
def admin_services():
    """Admin view of all services"""
    if not current_user.is_admin:
        flash("Admin access required", "danger")
        return redirect(url_for('market.main_market'))
    
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    status = request.args.get('status', 'pending')
    
    query = MarketplaceService.query
    if status != 'all':
        query = query.filter_by(status=status)
    
    services = query.order_by(desc(MarketplaceService.created_at)).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return render_template(
        "marketplace/admin/services.html",
        services=services,
        status=status,
        format_price=format_price
    )


@market.route("/admin/marketplace/service/<int:service_id>/approve", methods=["POST"])
@login_required
def approve_service(service_id):
    """Approve a service"""
    if not current_user.is_admin:
        return jsonify({'success': False, 'error': 'Admin access required'}), 403
    
    service = MarketplaceService.query.get_or_404(service_id)
    
    try:
        service.status = 'active'
        service.published_at = datetime.utcnow()
        db.session.commit()
        
        # TODO: Send email notification to seller
        
        return jsonify({'success': True})
    
    except Exception as e:
        db.session.rollback()
        print(f"Approve service error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@market.route("/admin/marketplace/service/<int:service_id>/reject", methods=["POST"])
@login_required
def reject_service(service_id):
    """Reject a service"""
    if not current_user.is_admin:
        return jsonify({'success': False, 'error': 'Admin access required'}), 403
    
    service = MarketplaceService.query.get_or_404(service_id)
    reason = request.json.get('reason', '')
    
    try:
        service.status = 'rejected'
        service.rejection_reason = reason
        db.session.commit()
        
        # TODO: Send email notification to seller
        
        return jsonify({'success': True})
    
    except Exception as e:
        db.session.rollback()
        print(f"Reject service error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@market.route("/admin/marketplace/featured", methods=["GET", "POST"])
@login_required
def manage_featured():
    """Manage featured services"""
    if not current_user.is_admin:
        flash("Admin access required", "danger")
        return redirect(url_for('market.main_market'))
    
    if request.method == "POST":
        service_id = request.form.get('service_id')
        action = request.form.get('action')
        
        service = MarketplaceService.query.get_or_404(service_id)
        
        if action == 'feature':
            service.is_featured = True
            message = "Service featured successfully"
        else:
            service.is_featured = False
            message = "Service unfeatured successfully"
        
        db.session.commit()
        flash(message, "success")
        return redirect(url_for('market.manage_featured'))
    
    # GET: Show featured services
    featured_services = MarketplaceService.query.filter_by(is_featured=True).all()
    non_featured_services = MarketplaceService.query.filter_by(
        status='active',
        is_featured=False
    ).order_by(desc(MarketplaceService.created_at)).limit(50).all()
    
    return render_template(
        "marketplace/admin/featured.html",
        featured_services=featured_services,
        non_featured_services=non_featured_services,
        format_price=format_price
    )


# ==================== DATA INITIALIZATION ====================

@market.route("/marketplace/init-data", methods=["GET"])
def init_marketplace_data():
    """Initialize marketplace data (run once)"""
    if not current_user or not current_user.is_super_admin:
        return "Admin access required", 403
    
    try:
        # Create categories
        categories = [
            {"name": "Mentoring & Coaching", "slug": "mentoring-coaching", "icon": "bi-people-fill"},
            {"name": "Counseling Services", "slug": "counseling-services", "icon": "bi-heart-fill"},
            {"name": "Digital Products", "slug": "digital-products", "icon": "bi-laptop-fill"},
            {"name": "Legal Services", "slug": "legal-services", "icon": "bi-shield-check"},
            {"name": "Wedding Services", "slug": "wedding-services", "icon": "bi-rose"},
            {"name": "Relationship Coaching", "slug": "relationship-coaching", "icon": "bi-chat-heart-fill"},
            {"name": "Career Development", "slug": "career-development", "icon": "bi-briefcase-fill"},
            {"name": "Personal Growth", "slug": "personal-growth", "icon": "bi-person-badge-fill"},
            {"name": "Faith & Spirituality", "slug": "faith-spirituality", "icon": "bi-star-fill"},
            {"name": "Health & Wellness", "slug": "health-wellness", "icon": "bi-heart-pulse-fill"},
        ]
        
        for cat_data in categories:
            if not MarketplaceCategory.query.filter_by(slug=cat_data['slug']).first():
                category = MarketplaceCategory(
                    name=cat_data['name'],
                    slug=cat_data['slug'],
                    icon=cat_data['icon'],
                    description=f"{cat_data['name']} services on Kimbela Marketplace"
                )
                db.session.add(category)
        
        # Create subscription plans
        subscriptions = [
            {
                "name": "Free",
                "slug": "free",
                "description": "Basic listing for new sellers",
                "price_tokens": 0,
                "price_usd": 0,
                "max_services": 1,
                "max_images": 3,
                "is_featured": False,
                "badge_color": "gray",
                "sort_order": 1
            },
            {
                "name": "Basic",
                "slug": "basic",
                "description": "Perfect for individual sellers",
                "price_tokens": 50,
                "price_usd": 5,
                "max_services": 3,
                "max_images": 5,
                "is_featured": False,
                "badge_color": "blue",
                "sort_order": 2
            },
            {
                "name": "Professional",
                "slug": "professional",
                "description": "Best for serious sellers",
                "price_tokens": 150,
                "price_usd": 15,
                "max_services": 10,
                "max_images": 10,
                "is_featured": True,
                "badge_color": "purple",
                "is_popular": True,
                "sort_order": 3
            },
            {
                "name": "Enterprise",
                "slug": "enterprise",
                "description": "For professional service providers",
                "price_tokens": 500,
                "price_usd": 50,
                "max_services": 50,
                "max_images": 20,
                "is_featured": True,
                "badge_color": "gold",
                "sort_order": 4
            }
        ]
        
        for sub_data in subscriptions:
            if not MarketplaceSubscription.query.filter_by(slug=sub_data['slug']).first():
                subscription = MarketplaceSubscription(**sub_data)
                db.session.add(subscription)
        
        db.session.commit()
        return "Marketplace data initialized successfully!"
    
    except Exception as e:
        db.session.rollback()
        print(f"Init data error: {e}")
        return f"Error: {e}", 500
    
    
    
    
# Add these to your marketplace routes

@market.route("/api/marketplace/categories", methods=["GET"])
def api_categories():
    """Get all marketplace categories"""
    try:
        categories = MarketplaceCategory.query.filter_by(is_active=True).order_by('sort_order').all()
        
        result = []
        for category in categories:
            service_count = MarketplaceService.query.filter_by(
                category_id=category.id,
                status='active'
            ).count()
            
            result.append({
                'id': category.id,
                'name': category.name,
                'slug': category.slug,
                'icon': category.icon,
                'description': category.description,
                'service_count': service_count
            })
        
        return jsonify({
            'success': True,
            'categories': result,
            'total': len(result)
        })
    
    except Exception as e:
        print(f"API categories error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@market.route("/api/marketplace/featured-sellers", methods=["GET"])
def api_featured_sellers():
    """Get featured sellers"""
    try:
        # Get sellers with featured services
        featured_sellers = get_featured_sellers(6)
        
        result = []
        for seller in featured_sellers:
            # Get seller stats
            total_services = MarketplaceService.query.filter_by(
                seller_id=seller.id,
                status='active'
            ).count()
            
            total_reviews = db.session.query(
                func.count(MarketplaceReview.id)
            ).join(MarketplaceService).filter(
                MarketplaceService.seller_id == seller.id
            ).scalar() or 0
            
            avg_rating = db.session.query(
                func.avg(MarketplaceReview.rating)
            ).join(MarketplaceService).filter(
                MarketplaceService.seller_id == seller.id
            ).scalar() or 0
            
            result.append({
                'id': seller.id,
                'name': seller.full_name,
                'first_name': seller.first_name,
                'avatar': seller.profile_pic or url_for('static', filename='assets/img/default-avatar.png'),
                'title': seller.occupation or 'Professional Seller',
                'rating': float(avg_rating),
                'review_count': total_reviews,
                'total_services': total_services,
                'is_online': seller.is_online,
                'bio': seller.bio[:100] + '...' if seller.bio and len(seller.bio) > 100 else seller.bio
            })
        
        return jsonify({
            'success': True,
            'sellers': result
        })
    
    except Exception as e:
        print(f"API featured sellers error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@market.route("/api/marketplace/service/<slug>", methods=["GET"])
def api_service_detail(slug):
    """Get service details by slug"""
    try:
        service = MarketplaceService.query.filter_by(slug=slug).first_or_404()
        
        # Check if service is active
        if not service.is_active and (not current_user.is_authenticated or current_user.id != service.seller_id):
            return jsonify({'success': False, 'error': 'Service not available'}), 404
        
        # Increment views
        service.views += 1
        db.session.commit()
        
        # Get seller info
        seller = service.seller
        
        # Format data
        result = {
            'id': service.id,
            'title': service.title,
            'slug': service.slug,
            'description': service.description,
            'short_description': service.short_description,
            'price_tokens': service.price_tokens,
            'formatted_price': format_price(service.price_tokens),
            'is_free': service.is_free,
            'is_featured': service.is_featured,
            'cover_image': service.cover_image or url_for('static', filename='assets/img/default-service.jpg'),
            'service_type': service.service_type,
            'duration': service.duration,
            'availability': service.availability,
            'average_rating': float(service.average_rating),
            'review_count': service.review_count,
            'views': service.views,
            'clicks': service.clicks,
            'created_at': service.created_at.isoformat(),
            'created_at_formatted': service.created_at.strftime('%b %d, %Y'),
            'contact_methods': service.contact_methods_list,
            'gallery_images': service.gallery_images_list,
            'features': service.features_list,
            'whatsapp_number': service.whatsapp_number,
            'whatsapp_link': service.whatsapp_link,
            'phone_number': service.phone_number,
            'email': service.email,
            'category': service.category.name if service.category else 'Uncategorized',
            'seller': {
                'id': seller.id,
                'name': seller.full_name,
                'first_name': seller.first_name,
                'avatar': seller.profile_pic or url_for('static', filename='assets/img/default-avatar.png'),
                'description': seller.bio or f'Professional seller on Kimbela Marketplace',
                'rating': float(seller.avg_rating) if hasattr(seller, 'avg_rating') else 4.5,
                'service_count': MarketplaceService.query.filter_by(
                    seller_id=seller.id,
                    status='active'
                ).count(),
                'phone': seller.phone_number
            }
        }
        
        return jsonify({'success': True, 'service': result})
    
    except Exception as e:
        print(f"API service detail error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@market.route("/api/marketplace/seller/<int:seller_id>", methods=["GET"])
def api_seller_detail(seller_id):
    """Get seller details"""
    try:
        seller = User.query.get_or_404(seller_id)
        
        # Get seller stats
        total_services = MarketplaceService.query.filter_by(
            seller_id=seller_id,
            status='active'
        ).count()
        
        total_reviews = db.session.query(
            func.count(MarketplaceReview.id)
        ).join(MarketplaceService).filter(
            MarketplaceService.seller_id == seller_id
        ).scalar() or 0
        
        avg_rating = db.session.query(
            func.avg(MarketplaceReview.rating)
        ).join(MarketplaceService).filter(
            MarketplaceService.seller_id == seller_id
        ).scalar() or 0
        
        total_views = db.session.query(
            func.sum(MarketplaceService.views)
        ).filter_by(seller_id=seller_id).scalar() or 0
        
        # Get seller's other services
        other_services = MarketplaceService.query.filter_by(
            seller_id=seller_id,
            status='active'
        ).order_by(desc(MarketplaceService.created_at)).limit(4).all()
        
        services_data = []
        for service in other_services:
            services_data.append({
                'id': service.id,
                'title': service.title,
                'slug': service.slug,
                'cover_image': service.cover_image or url_for('static', filename='assets/img/default-service.jpg'),
                'average_rating': float(service.average_rating),
                'review_count': service.review_count,
                'price_tokens': service.price_tokens,
                'formatted_price': format_price(service.price_tokens),
                'is_free': service.is_free
            })
        
        result = {
            'id': seller.id,
            'name': seller.full_name,
            'first_name': seller.first_name,
            'avatar': seller.profile_pic or url_for('static', filename='assets/img/default-avatar.png'),
            'title': seller.occupation or 'Professional Seller',
            'bio': seller.bio,
            'rating': float(avg_rating),
            'review_count': total_reviews,
            'total_services': total_services,
            'total_views': total_views,
            'member_since': seller.created_at.strftime('%b %Y'),
            'phone': seller.phone_number,
            'email': seller.email,
            'services': services_data
        }
        
        return jsonify({'success': True, 'seller': result})
    
    except Exception as e:
        print(f"API seller detail error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    
    
    
    
# ==================== SELLER SETTINGS ROUTES ====================

@market.route("/marketplace/settings", methods=["GET", "POST"])
@login_required
def seller_settings():
    """Seller settings dashboard"""
    if request.method == "GET":
        # Get subscription plans
        subscription_plans = MarketplaceSubscription.query.filter_by(is_active=True).order_by('sort_order').all()
        
        # Get current subscription
        current_subscription = None
        subscription_expires = None
        for service in current_user.marketplace_services:
            if service.subscription:
                current_subscription = service.subscription
                subscription_expires = service.subscription_expires
                break
        
        # Get payment history (last 10 payments)
        payment_history = MarketplacePayment.query.filter_by(
            user_id=current_user.id
        ).order_by(desc(MarketplacePayment.created_at)).limit(10).all()
        
        # Get API keys
        api_keys = current_user.api_keys
        
        # Get login history (last 20 logins)
        login_history = LoginHistory.query.filter_by(
            user_id=current_user.id
        ).order_by(desc(LoginHistory.created_at)).limit(20).all()
        
        # Get active sessions
        active_sessions = current_user.active_sessions
        
        return render_template(
            "marketplace/seller_settings.html",
            current_subscription=current_subscription,
            subscription_expires=subscription_expires,
            subscription_plans=subscription_plans,
            payment_history=payment_history,
            api_keys=api_keys,
            login_history=login_history,
            active_sessions=active_sessions,
            now=datetime.utcnow()
        )
    
    # POST: Handle settings updates
    # (Implement based on which form was submitted)

@market.route("/marketplace/update-profile", methods=["POST"])
@login_required
def update_profile():
    """Update seller profile"""
    try:
        current_user.first_name = request.form.get('first_name', current_user.first_name)
        current_user.last_name = request.form.get('last_name', current_user.last_name)
        current_user.phone_number = request.form.get('phone_number')
        current_user.occupation = request.form.get('occupation')
        current_user.location = request.form.get('location')
        current_user.bio = request.form.get('bio')
        current_user.website = request.form.get('website')
        current_user.linkedin_url = request.form.get('linkedin')
        current_user.twitter_url = request.form.get('twitter')
        current_user.facebook_url = request.form.get('facebook')
        current_user.availability = request.form.get('availability')
        current_user.response_time = request.form.get('response_time')
        
        # Handle profile picture upload
        if 'profile_pic' in request.files:
            file = request.files['profile_pic']
            if file and allowed_file(file.filename):
                image_url = upload_to_cloudinary(file, "profiles")
                if image_url:
                    current_user.profile_pic = image_url
        
        db.session.commit()
        flash("Profile updated successfully!", "success")
        
    except Exception as e:
        db.session.rollback()
        print(f"Update profile error: {e}")
        flash("Error updating profile", "danger")
    
    return redirect(url_for('market.seller_settings') + '#profile')

@market.route("/marketplace/change-password", methods=["POST"])
@login_required
def change_password():
    """Change password"""
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')
    
    if not current_user.check_password(current_password):
        flash("Current password is incorrect", "danger")
    elif new_password != confirm_password:
        flash("New passwords do not match", "danger")
    elif len(new_password) < 8:
        flash("Password must be at least 8 characters", "danger")
    else:
        current_user.set_password(new_password)
        db.session.commit()
        flash("Password changed successfully", "success")
    
    return redirect(url_for('market.seller_settings') + '#security')

@market.route("/api/marketplace/generate-api-key", methods=["POST"])
@login_required
def generate_api_key():
    """Generate new API key"""
    try:
        name = request.json.get('name', 'API Key')
        
        # Generate random API key
        import secrets
        api_key = f"kimbela_sk_{secrets.token_urlsafe(32)}"
        
        # Save to database
        key = ApiKey(
            user_id=current_user.id,
            name=name,
            key=api_key
        )
        db.session.add(key)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'key': api_key,
            'id': key.id
        })
    
    except Exception as e:
        db.session.rollback()
        print(f"Generate API key error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    
    
@market.route("/edit-profile", methods=["GET", "POST"])
@login_required
def edit_seller_profile():
    """Edit seller profile"""
    if request.method == "POST":
        # Handle profile update
        current_user.bio = request.form.get('bio')
        current_user.occupation = request.form.get('occupation')
        current_user.location = request.form.get('location')
        current_user.website = request.form.get('website')
        
        # Handle profile picture upload
        if 'profile_pic' in request.files:
            file = request.files['profile_pic']
            if file and allowed_file(file.filename):
                image_url = upload_to_cloudinary(file, "profiles")
                if image_url:
                    current_user.profile_pic = image_url
        
        db.session.commit()
        flash("Profile updated successfully!", "success")
        return redirect(url_for('market.seller_profile', seller_id=current_user.id))
    
    return render_template("edit_seller_profile.html", now=datetime.utcnow())



@market.route("/marketplace/seller/<int:seller_id>", methods=["GET"])
def seller_profile(seller_id):
    """View seller profile"""
    seller = User.query.get_or_404(seller_id)
    
    # Get seller's services with pagination
    page = request.args.get('page', 1, type=int)
    per_page = 12
    
    services_query = MarketplaceService.query.filter_by(
        seller_id=seller_id,
        status="active"
    ).order_by(desc(MarketplaceService.created_at))
    
    services = services_query.paginate(page=page, per_page=per_page, error_out=False)
    
    # Get seller stats
    total_services = services_query.count()
    total_reviews = MarketplaceReview.query.join(MarketplaceService).filter(
        MarketplaceService.seller_id == seller_id
    ).count()
    
    # Calculate average rating
    avg_rating = db.session.query(
        func.avg(MarketplaceReview.rating)
    ).join(MarketplaceService).filter(
        MarketplaceService.seller_id == seller_id
    ).scalar() or 0
    
    # Get total views
    total_views = db.session.query(
        func.sum(MarketplaceService.views)
    ).filter_by(seller_id=seller_id).scalar() or 0
    
    # Get recent reviews
    reviews = MarketplaceReview.query.join(MarketplaceService).filter(
        MarketplaceService.seller_id == seller_id
    ).order_by(desc(MarketplaceReview.created_at)).limit(10).all()
    
    return render_template(
        "seller_profile.html",
        seller=seller,
        services=services,
        total_services=total_services,
        total_reviews=total_reviews,
        avg_rating=round(avg_rating, 1),
        total_views=total_views,
        reviews=reviews,
        format_price=format_price,
        now=datetime.utcnow()  # For copyright year
    )
    
    
# @market.route("/update-profile", methods=["POST"])
# @login_required
# def update_profile():
#     """Update seller profile"""
#     try:
#         current_user.first_name = request.form.get('first_name', current_user.first_name)
#         current_user.last_name = request.form.get('last_name', current_user.last_name)
#         current_user.phone_number = request.form.get('phone_number')
#         current_user.occupation = request.form.get('occupation')
#         current_user.location = request.form.get('location')
#         current_user.bio = request.form.get('bio')
#         current_user.website = request.form.get('website')
#         current_user.linkedin_url = request.form.get('linkedin_url')
#         current_user.twitter_url = request.form.get('twitter_url')
#         current_user.facebook_url = request.form.get('facebook_url')
#         current_user.instagram_url = request.form.get('instagram_url')
#         current_user.availability = request.form.get('availability')
#         current_user.response_time = request.form.get('response_time')
#         current_user.languages = request.form.get('languages')
#         current_user.skills = request.form.get('skills')
#         current_user.experience_years = request.form.get('experience_years')
#         current_user.certifications = request.form.get('certifications')
        
#         # Handle profile picture upload
#         if 'profile_pic' in request.files:
#             file = request.files['profile_pic']
#             if file and allowed_file(file.filename):
#                 image_url = upload_to_cloudinary(file, "profiles")
#                 if image_url:
#                     current_user.profile_pic = image_url
        
#         db.session.commit()
#         flash("Profile updated successfully!", "success")
        
#     except Exception as e:
#         db.session.rollback()
#         print(f"Update profile error: {e}")
#         flash("Error updating profile", "danger")
    
#     return redirect(url_for('market.seller_profile', seller_id=current_user.id))

@market.route("/remove-profile-picture", methods=["POST"])
@login_required
def remove_profile_picture():
    """Remove profile picture"""
    try:
        current_user.profile_pic = None
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500