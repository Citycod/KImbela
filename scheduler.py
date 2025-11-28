from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from campaign_service import CampaignService
from email_service import EmailService  # Add this import
from extensions import db
from models import AdCampaign, MatchmakingRequest  # Add MatchmakingRequest
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

def init_scheduler(app):
    """Initialize the background scheduler"""
    scheduler = BackgroundScheduler()
    campaign_service = CampaignService()
    
    @scheduler.scheduled_job('interval', hours=1)
    def check_expired_campaigns():
        """Check for expired campaigns every hour"""
        with app.app_context():
            try:
                expired_count = campaign_service.check_campaign_expiry()
                if expired_count > 0:
                    logger.info(f"Expired {expired_count} campaigns")
                
                # Also check for campaigns expiring soon (3 days)
                expiring_soon = campaign_service.get_expiring_soon_campaigns(days=3)
                for campaign in expiring_soon:
                    if not campaign.expiry_notification_sent:
                        campaign_service.send_expiry_reminder(campaign)
                        campaign.expiry_notification_sent = True
                        db.session.commit()
                        
            except Exception as e:
                logger.error(f"Error in scheduled task: {str(e)}")
    
    @scheduler.scheduled_job('cron', hour=0, minute=0)
    def daily_maintenance():
        """Daily maintenance tasks"""
        with app.app_context():
            try:
                # Update click-through rates
                campaigns = AdCampaign.query.filter(
                    AdCampaign.impressions > 0
                ).all()
                
                for campaign in campaigns:
                    if campaign.impressions > 0:
                        campaign.click_through_rate = (campaign.clicks / campaign.impressions) * 100
                
                db.session.commit()
                logger.info("Updated campaign CTRs")
                
            except Exception as e:
                logger.error(f"Error in daily maintenance: {str(e)}")
                db.session.rollback()
    
    # NEW: Matchmaking expiry reminders
    @scheduler.scheduled_job('cron', hour=9, minute=0)  # Daily at 9 AM
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
    
    # NEW: Check for expired matchmaking requests hourly
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
    
    # NEW: Weekly performance report (optional)
    @scheduler.scheduled_job('cron', day_of_week='mon', hour=8, minute=0)  # Monday at 8 AM
    def weekly_performance_report():
        """Send weekly performance reports"""
        with app.app_context():
            try:
                logger.info("Generating weekly performance reports...")
                
                # You can add weekly reporting logic here
                # For example:
                # - Send performance reports to advertisers
                # - Send matchmaking activity reports
                # - System health reports
                
                logger.info("Weekly performance reports completed")
                
            except Exception as e:
                logger.error(f"Error in weekly performance report: {str(e)}")
    
    scheduler.start()
    logger.info("Scheduler started successfully with matchmaking support")
    return scheduler

# Manual trigger functions for testing
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