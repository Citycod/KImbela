from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from campaign_service import CampaignService
from email_service import EmailService
from extensions import db, mail
from models import AdCampaign, MatchmakingRequest, User, MarketplaceService
import logging
from datetime import datetime, timedelta
from flask import current_app, render_template_string
from flask_mail import Message

logger = logging.getLogger(__name__)

def init_scheduler(app):
    """Initialize the background scheduler"""
    scheduler = BackgroundScheduler()
    campaign_service = CampaignService()
    
    # Campaign expiry check - every hour
    @scheduler.scheduled_job('interval', hours=1)
    def check_expired_campaigns():
        """Check for expired campaigns every hour"""
        with app.app_context():
            try:
                expired_count = campaign_service.check_campaign_expiry()
                if expired_count > 0:
                    logger.info(f"Expired {expired_count} campaigns")
                
                # Check for campaigns expiring soon (3 days)
                expiring_soon = campaign_service.get_expiring_soon_campaigns(days=3)
                for campaign in expiring_soon:
                    if not campaign.expiry_notification_sent:
                        campaign_service.send_expiry_reminder(campaign)
                        campaign.expiry_notification_sent = True
                        db.session.commit()
                        
            except Exception as e:
                logger.error(f"Error in campaign expiry check: {str(e)}")
    
    # Daily maintenance - midnight
    @scheduler.scheduled_job('cron', hour=0, minute=0)
    def daily_maintenance():
        """Daily maintenance tasks"""
        with app.app_context():
            try:
                # Update campaign click-through rates
                campaigns = AdCampaign.query.filter(
                    AdCampaign.impressions > 0
                ).all()
                
                for campaign in campaigns:
                    if campaign.impressions > 0:
                        campaign.click_through_rate = (campaign.clicks / campaign.impressions) * 100
                
                # Update marketplace service statistics
                update_marketplace_stats()
                
                db.session.commit()
                logger.info("Daily maintenance completed")
                
            except Exception as e:
                logger.error(f"Error in daily maintenance: {str(e)}")
                db.session.rollback()
    
    # Marketplace subscription reminders - daily at 9 AM
    @scheduler.scheduled_job('cron', hour=9, minute=0)
    def check_marketplace_subscriptions():
        """Check for expiring marketplace subscriptions daily at 9 AM"""
        with app.app_context():
            try:
                logger.info("Starting marketplace subscription check...")
                
                # Check expiring subscriptions (3 days before expiry)
                check_expiring_subscriptions()
                
                # Check expired subscriptions
                check_expired_subscriptions()
                
                # Check new subscribers for welcome emails
                check_new_subscribers()
                
                logger.info("Marketplace subscription check completed")
                
            except Exception as e:
                logger.error(f"Error in marketplace subscription check: {str(e)}")
    
    # Matchmaking expiry reminders - daily at 9 AM
    @scheduler.scheduled_job('cron', hour=9, minute=0)
    def check_matchmaking_expiry():
        """Check for expiring matchmaking requests daily at 9 AM"""
        with app.app_context():
            try:
                logger.info("Starting matchmaking expiry reminder check...")
                
                # Check and send expiry reminders
                success = EmailService.check_and_send_expiry_reminders()
                
                if success:
                    logger.info("Matchmaking expiry reminders sent successfully")
                else:
                    logger.warning("Matchmaking expiry reminders check completed with issues")
                    
            except Exception as e:
                logger.error(f"Error in matchmaking expiry check: {str(e)}")
    
    # Check for expired matchmaking requests - hourly
    @scheduler.scheduled_job('interval', hours=1)
    def check_expired_matchmaking_requests():
        """Check for expired matchmaking requests every hour"""
        with app.app_context():
            try:
                expired_count = 0
                now = datetime.utcnow()
                
                # Find active matchmaking requests that have expired
                expired_requests = MatchmakingRequest.query.filter(
                    MatchmakingRequest.status == 'active',
                    MatchmakingRequest.end_date <= now,
                    MatchmakingRequest.payment_status == 'paid'
                ).all()
                
                for request in expired_requests:
                    # Mark as expired
                    request.status = 'expired'
                    request.updated_at = now
                    expired_count += 1
                    
                    logger.info(f"Marked matchmaking request {request.id} as expired")
                
                if expired_count > 0:
                    db.session.commit()
                    logger.info(f"Marked {expired_count} matchmaking requests as expired")
                
            except Exception as e:
                logger.error(f"Error checking expired matchmaking requests: {str(e)}")
                db.session.rollback()
    
    # Check for inactive marketplace sellers - daily at 8 AM
    @scheduler.scheduled_job('cron', hour=8, minute=0)
    def check_inactive_sellers():
        """Check for sellers who need subscription reminders"""
        with app.app_context():
            try:
                logger.info("Checking for inactive sellers...")
                
                # Find sellers with services but no active subscription
                sellers_with_services = db.session.query(User).join(
                    MarketplaceService, MarketplaceService.seller_id == User.id
                ).filter(
                    MarketplaceService.status == 'active'
                ).distinct().all()
                
                for seller in sellers_with_services:
                    # Check if seller has active subscription
                    has_active_sub = False
                    for service in seller.marketplace_services:
                        if service.subscription_status == 'active' and \
                           service.subscription_expires and \
                           service.subscription_expires > datetime.utcnow():
                            has_active_sub = True
                            break
                    
                    if not has_active_sub:
                        # Send promotion email about subscription benefits
                        send_subscription_promotion(seller)
                
                logger.info(f"Checked {len(sellers_with_services)} sellers")
                
            except Exception as e:
                logger.error(f"Error checking inactive sellers: {str(e)}")
    
    # Weekly performance report - Monday at 8 AM
    @scheduler.scheduled_job('cron', day_of_week='mon', hour=8, minute=0)
    def weekly_performance_report():
        """Send weekly performance reports"""
        with app.app_context():
            try:
                logger.info("Generating weekly performance reports...")
                
                # Generate marketplace performance report
                generate_marketplace_report()
                
                logger.info("Weekly performance reports completed")
                
            except Exception as e:
                logger.error(f"Error in weekly performance report: {str(e)}")
    
    scheduler.start()
    logger.info("Scheduler started successfully with marketplace subscription support")
    return scheduler

# Marketplace subscription functions
def check_expiring_subscriptions():
    """Check for expiring marketplace subscriptions"""
    try:
        three_days_from_now = datetime.utcnow() + timedelta(days=3)
        now = datetime.utcnow()
        
        # Find users with subscriptions expiring in 3 days
        expiring_users = []
        
        # Get all sellers with active services
        sellers = User.query.filter(
            User.marketplace_services.any(MarketplaceService.status == 'active')
        ).all()
        
        for seller in sellers:
            for service in seller.marketplace_services:
                if (service.subscription_status == 'active' and 
                    service.subscription_expires and
                    service.subscription_expires <= three_days_from_now and
                    service.subscription_expires > now):
                    
                    # Check if we already sent reminder for this service
                    if not hasattr(service, 'expiry_reminder_sent') or not service.expiry_reminder_sent:
                        send_subscription_reminder(seller, 'expiring_soon', service)
                        service.expiry_reminder_sent = True
                        expiring_users.append(seller.email)
                        break  # Only send one email per seller
        
        if expiring_users:
            logger.info(f"Sent expiring soon reminders to {len(expiring_users)} sellers")
            db.session.commit()
            
    except Exception as e:
        logger.error(f"Error checking expiring subscriptions: {str(e)}")
        db.session.rollback()

def check_expired_subscriptions():
    """Check for expired marketplace subscriptions"""
    try:
        now = datetime.utcnow()
        
        # Find services with expired subscriptions
        expired_services = MarketplaceService.query.filter(
            MarketplaceService.subscription_status == 'active',
            MarketplaceService.subscription_expires <= now,
            MarketplaceService.status == 'active'
        ).all()
        
        for service in expired_services:
            # Mark subscription as expired
            service.subscription_status = 'expired'
            
            # Send expired notification to seller
            send_subscription_reminder(service.seller, 'expired', service)
            
            # Update seller's visibility
            update_seller_visibility(service.seller)
        
        if expired_services:
            logger.info(f"Processed {len(expired_services)} expired subscriptions")
            db.session.commit()
            
    except Exception as e:
        logger.error(f"Error checking expired subscriptions: {str(e)}")
        db.session.rollback()

def check_new_subscribers():
    """Send welcome emails to new subscribers"""
    try:
        yesterday = datetime.utcnow() - timedelta(days=1)
        
        # Find services with newly activated subscriptions
        new_subscriptions = MarketplaceService.query.filter(
            MarketplaceService.subscription_status == 'active',
            MarketplaceService.subscription_expires > datetime.utcnow(),
            MarketplaceService.created_at >= yesterday,
            MarketplaceService.status == 'active'
        ).all()
        
        for service in new_subscriptions:
            # Check if welcome email already sent
            if not hasattr(service, 'welcome_email_sent') or not service.welcome_email_sent:
                send_subscription_reminder(service.seller, 'welcome', service)
                service.welcome_email_sent = True
        
        if new_subscriptions:
            logger.info(f"Sent welcome emails to {len(new_subscriptions)} new subscribers")
            db.session.commit()
            
    except Exception as e:
        logger.error(f"Error checking new subscribers: {str(e)}")
        db.session.rollback()

def send_subscription_reminder(user, reminder_type, service=None):
    """Send subscription reminder email"""
    try:
        if reminder_type == 'expiring_soon':
            subject = f"⏰ Your Kimbela Subscription Expires Soon!"
            message = f"Your subscription for '{service.title}' expires on {service.subscription_expires.strftime('%B %d, %Y')}. Renew now to continue getting premium visibility."
            action_text = "Renew Subscription"
            action_url = f"/become-seller?plan={service.subscription_id}"
            
        elif reminder_type == 'expired':
            subject = f"📉 Your Kimbela Subscription Has Expired"
            message = f"Your subscription for '{service.title}' has expired. Your service is now less visible in search results. Renew now to regain premium visibility."
            action_text = "Renew Now"
            action_url = f"/become-seller?plan={service.subscription_id}"
            
        elif reminder_type == 'welcome':
            subject = f"🎉 Welcome to Kimbela Marketplace!"
            message = f"Thank you for subscribing to Kimbela Marketplace! Your service '{service.title}' now has premium visibility and will reach more customers."
            action_text = "View Dashboard"
            action_url = "/seller_dashboard"
            
        elif reminder_type == 'promotion':
            subject = f"🚀 Boost Your Service Visibility!"
            message = "Your services are active but not getting maximum visibility. Subscribe now to appear higher in search results and get 5x more views."
            action_text = "View Plans"
            action_url = "/become-seller"
            
        else:
            return
        
        # Create email content
        email_content = render_template_string('''
        <!DOCTYPE html>
        <html>
        <body>
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; font-family: Arial, sans-serif;">
                <div style="text-align: center; margin-bottom: 30px;">
                    <img src="{{ url_for('static', filename='assets/img/kim.png', _external=True) }}" 
                         alt="Kimbela Marketplace" style="height: 50px;">
                </div>
                
                <div style="background: #f8f9fa; padding: 30px; border-radius: 10px;">
                    <h2 style="color: #333; margin-bottom: 20px;">{{ subject }}</h2>
                    
                    <p style="color: #666; line-height: 1.6; margin-bottom: 20px;">
                        Hi {{ user.first_name }},
                    </p>
                    
                    <p style="color: #666; line-height: 1.6; margin-bottom: 20px;">
                        {{ message }}
                    </p>
                    
                    <div style="background: white; padding: 20px; border-radius: 8px; margin: 20px 0;">
                        <h3 style="color: #333; margin-bottom: 15px;">Benefits of subscribing:</h3>
                        <ul style="color: #666; line-height: 1.6; padding-left: 20px;">
                            <li>Higher ranking in search results</li>
                            <li>Featured placement on homepage</li>
                            <li>5x more customer views</li>
                            <li>Priority customer support</li>
                            <li>Detailed analytics dashboard</li>
                        </ul>
                    </div>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{{ url_for('market.become_seller', _external=True) }}{{ action_url_param }}" 
                           style="background: linear-gradient(135deg, #5a4500 0%, #b88900 100%); 
                                  color: white; 
                                  padding: 12px 30px; 
                                  text-decoration: none; 
                                  border-radius: 8px; 
                                  font-weight: bold;
                                  display: inline-block;">
                            {{ action_text }}
                        </a>
                    </div>
                    
                    <p style="color: #999; font-size: 12px; line-height: 1.6; margin-top: 30px;">
                        You're receiving this email because you have services listed on Kimbela Marketplace.<br>
                        <a href="{{ unsubscribe_url }}" style="color: #999;">Unsubscribe from these emails</a>
                    </p>
                </div>
            </div>
        </body>
        </html>
        ''', 
        subject=subject, 
        message=message, 
        user=user,
        action_text=action_text,
        action_url_param=action_url if reminder_type != 'promotion' else '',
        unsubscribe_url=f"/unsubscribe/{user.id}/{user.get_unsubscribe_token()}"
        )
        
        # Create and send email
        msg = Message(
            subject=subject,
            recipients=[user.email],
            html=email_content,
            sender=current_app.config['MAIL_DEFAULT_SENDER']
        )
        
        mail.send(msg)
        logger.info(f"Sent {reminder_type} email to {user.email}")
        
    except Exception as e:
        logger.error(f"Error sending {reminder_type} email to {user.email}: {str(e)}")

def send_subscription_promotion(user):
    """Send subscription promotion email to inactive sellers"""
    try:
        subject = "🚀 Boost Your Service Visibility on Kimbela!"
        message = f"Hi {user.first_name}, your services are active but not getting maximum visibility. Subscribe now to reach more customers and grow your business."
        
        email_content = render_template_string('''
        <!DOCTYPE html>
        <html>
        <body>
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; font-family: Arial, sans-serif;">
                <div style="text-align: center; margin-bottom: 30px;">
                    <img src="{{ url_for('static', filename='assets/img/kim.png', _external=True) }}" 
                         alt="Kimbela Marketplace" style="height: 50px;">
                </div>
                
                <div style="background: #f8f9fa; padding: 30px; border-radius: 10px;">
                    <h2 style="color: #333; margin-bottom: 20px;">{{ subject }}</h2>
                    
                    <p style="color: #666; line-height: 1.6; margin-bottom: 20px;">
                        {{ message }}
                    </p>
                    
                    <div style="background: white; padding: 20px; border-radius: 8px; margin: 20px 0;">
                        <h3 style="color: #333; margin-bottom: 15px;">What subscribers get:</h3>
                        <ul style="color: #666; line-height: 1.6; padding-left: 20px;">
                            <li><strong>5x More Views:</strong> Appear at the top of search results</li>
                            <li><strong>Featured Placement:</strong> Get highlighted on the homepage</li>
                            <li><strong>Priority Support:</strong> Get help when you need it</li>
                            <li><strong>Analytics Dashboard:</strong> Track performance in real-time</li>
                            <li><strong>Verified Badge:</strong> Build trust with customers</li>
                        </ul>
                    </div>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{{ url_for('market.become_seller', _external=True) }}" 
                           style="background: linear-gradient(135deg, #5a4500 0%, #b88900 100%); 
                                  color: white; 
                                  padding: 12px 30px; 
                                  text-decoration: none; 
                                  border-radius: 8px; 
                                  font-weight: bold;
                                  display: inline-block;">
                            View Subscription Plans
                        </a>
                    </div>
                    
                    <div style="background: #e8f5e9; border: 1px solid #c8e6c9; padding: 15px; border-radius: 8px; margin: 20px 0;">
                        <h4 style="color: #2e7d32; margin: 0 0 10px 0;">Success Story:</h4>
                        <p style="color: #555; font-style: italic; margin: 0;">
                            "After subscribing, my coaching service got 300% more inquiries in the first month!"<br>
                            <strong>- Sarah J., Relationship Coach</strong>
                        </p>
                    </div>
                    
                    <p style="color: #999; font-size: 12px; line-height: 1.6; margin-top: 30px;">
                        Plans start at just $5/month. Cancel anytime.<br>
                        <a href="{{ unsubscribe_url }}" style="color: #999;">Unsubscribe from these emails</a>
                    </p>
                </div>
            </div>
        </body>
        </html>
        ''', 
        subject=subject, 
        message=message,
        unsubscribe_url=f"/unsubscribe/{user.id}/{user.get_unsubscribe_token()}"
        )
        
        msg = Message(
            subject=subject,
            recipients=[user.email],
            html=email_content,
            sender=current_app.config['MAIL_DEFAULT_SENDER']
        )
        
        mail.send(msg)
        logger.info(f"Sent subscription promotion to {user.email}")
        
    except Exception as e:
        logger.error(f"Error sending promotion email to {user.email}: {str(e)}")

def update_marketplace_stats():
    """Update marketplace statistics"""
    try:
        # Update service rankings based on subscription status
        services = MarketplaceService.query.filter_by(status='active').all()
        
        for service in services:
            # Calculate ranking score
            base_score = service.views * 0.1 + service.clicks * 0.5 + (service.average_rating or 0) * 20
            
            # Boost score for subscribed services
            if (service.subscription_status == 'active' and 
                service.subscription_expires and 
                service.subscription_expires > datetime.utcnow()):
                base_score *= 3  # 3x boost for subscribed services
            
            # Store ranking score (you can add this field to the model)
            if hasattr(service, 'ranking_score'):
                service.ranking_score = base_score
        
        logger.info(f"Updated rankings for {len(services)} services")
        
    except Exception as e:
        logger.error(f"Error updating marketplace stats: {str(e)}")

def update_seller_visibility(seller):
    """Update seller visibility based on subscription status"""
    try:
        # Check if seller has any active subscriptions
        has_active_sub = False
        for service in seller.marketplace_services:
            if (service.subscription_status == 'active' and 
                service.subscription_expires and 
                service.subscription_expires > datetime.utcnow()):
                has_active_sub = True
                break
        
        # Update seller's featured status
        if hasattr(seller, 'is_featured_seller'):
            seller.is_featured_seller = has_active_sub
        
        logger.info(f"Updated visibility for seller {seller.email}: Active subscription = {has_active_sub}")
        
    except Exception as e:
        logger.error(f"Error updating seller visibility: {str(e)}")

def generate_marketplace_report():
    """Generate weekly marketplace performance report"""
    try:
        # Get weekly stats
        week_ago = datetime.utcnow() - timedelta(days=7)
        
        total_services = MarketplaceService.query.filter(
            MarketplaceService.status == 'active'
        ).count()
        
        new_services = MarketplaceService.query.filter(
            MarketplaceService.status == 'active',
            MarketplaceService.created_at >= week_ago
        ).count()
        
        subscribed_services = MarketplaceService.query.filter(
            MarketplaceService.status == 'active',
            MarketplaceService.subscription_status == 'active',
            MarketplaceService.subscription_expires > datetime.utcnow()
        ).count()
        
        total_views = db.session.query(db.func.sum(MarketplaceService.views)).filter(
            MarketplaceService.status == 'active'
        ).scalar() or 0
        
        # Log report
        logger.info(f"""
        Weekly Marketplace Report:
        - Total Active Services: {total_services}
        - New Services (7 days): {new_services}
        - Subscribed Services: {subscribed_services}
        - Total Views: {total_views}
        - Subscription Rate: {(subscribed_services/total_services*100 if total_services > 0 else 0):.1f}%
        """)
        
    except Exception as e:
        logger.error(f"Error generating marketplace report: {str(e)}")

# Manual trigger functions for testing
def manual_trigger_subscription_check():
    """Manually trigger subscription check (for testing)"""
    try:
        from flask import current_app
        with current_app.app_context():
            check_expiring_subscriptions()
            check_expired_subscriptions()
            check_new_subscribers()
            logger.info("Manual subscription check completed")
            return True
    except Exception as e:
        logger.error(f"Error in manual subscription check: {str(e)}")
        return False

def manual_trigger_seller_promotion():
    """Manually trigger seller promotion emails (for testing)"""
    try:
        from flask import current_app
        with current_app.app_context():
            check_inactive_sellers()
            logger.info("Manual seller promotion check completed")
            return True
    except Exception as e:
        logger.error(f"Error in manual seller promotion: {str(e)}")
        return False

def manual_trigger_matchmaking_expiry_check():
    """Manually trigger matchmaking expiry check (for testing)"""
    try:
        from flask import current_app
        with current_app.app_context():
            success = EmailService.check_and_send_expiry_reminders()
            logger.info(f"Manual matchmaking expiry check: {'Success' if success else 'Failed'}")
            return success
    except Exception as e:
        logger.error(f"Error in manual matchmaking expiry check: {str(e)}")
        return False

def manual_trigger_expired_matchmaking_check():
    """Manually trigger expired matchmaking check (for testing)"""
    try:
        from flask import current_app
        with current_app.app_context():
            now = datetime.utcnow()
            expired_requests = MatchmakingRequest.query.filter(
                MatchmakingRequest.status == 'active',
                MatchmakingRequest.end_date <= now,
                MatchmakingRequest.payment_status == 'paid'
            ).all()
            
            for request in expired_requests:
                request.status = 'expired'
                request.updated_at = now
            
            db.session.commit()
            logger.info(f"Manually expired {len(expired_requests)} matchmaking requests")
            return len(expired_requests)
    except Exception as e:
        logger.error(f"Error in manual expired matchmaking check: {str(e)}")
        return 0