from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from campaign_service import CampaignService
from extensions import db
from models import AdCampaign
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
    
    scheduler.start()
    logger.info("Scheduler started successfully")
    return scheduler