from extensions import db, mail
from models import AdCampaign, User
from flask_mail import Message
from datetime import datetime, timedelta
import logging
from sqlalchemy import and_

from time_utils import utcnow
logger = logging.getLogger(__name__)


class CampaignService:

    def check_campaign_expiry(self):
        """Check and expire campaigns that have reached their end date"""
        try:
            now = utcnow()
            expired_campaigns = AdCampaign.query.filter(
                and_(AdCampaign.end_date <= now, AdCampaign.status == "active")
            ).all()

            for campaign in expired_campaigns:
                self.expire_campaign(campaign)

            return len(expired_campaigns)

        except Exception as e:
            logger.error(f"Error checking campaign expiry: {str(e)}")
            return 0

    def expire_campaign(self, campaign):
        """Expire a single campaign and send notification"""
        try:
            # Update campaign status
            campaign.status = "expired"
            campaign.updated_at = utcnow()

            # Send expiry notification
            self.send_campaign_expired_email(campaign)

            db.session.commit()
            logger.info(f"Campaign {campaign.id} expired successfully")

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error expiring campaign {campaign.id}: {str(e)}")

    def send_campaign_expired_email(self, campaign):
        """Send email notification when campaign expires"""
        try:
            user = User.query.get(campaign.user_id)
            if not user:
                return False

            subject = "📅 Your Kimbela Ad Campaign Has Ended"

            html_body = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background: linear-gradient(135deg, #ff6b6b 0%, #ee5a24 100%); color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0; }}
                    .content {{ background: #f9f9f9; padding: 20px; border-radius: 0 0 10px 10px; }}
                    .stats {{ background: white; padding: 15px; border-radius: 5px; margin: 10px 0; }}
                    .footer {{ text-align: center; margin-top: 20px; color: #666; font-size: 12px; }}
                    .button {{ background: #667eea; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; display: inline-block; margin: 10px 0; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>📅 Campaign Completed</h1>
                        <p>Your ad campaign has ended - View your results</p>
                    </div>
                    <div class="content">
                        <p>Hello {user.full_name},</p>
                        <p>Your Kimbela ad campaign <strong>"{campaign.title}"</strong> has ended as scheduled.</p>
                        
                        <div class="stats">
                            <h3>📊 Campaign Performance Summary</h3>
                            <p><strong>Campaign Duration:</strong> {campaign.duration_days} days</p>
                            <p><strong>Total Impressions:</strong> {campaign.impressions:,}</p>
                            <p><strong>Total Clicks:</strong> {campaign.clicks:,}</p>
                            <p><strong>Click-Through Rate:</strong> {campaign.click_through_rate:.2f}%</p>
                            <p><strong>Total Budget:</strong> ${campaign.budget * campaign.duration_days:.2f}</p>
                            <p><strong>Cost Per Click:</strong> ${(campaign.budget * campaign.duration_days) / campaign.clicks:.2f if campaign.clicks > 0 else 0}</p>
                        </div>
                        
                        <div class="stats">
                            <h3>🎯 What's Next?</h3>
                            <p>• Your campaign data is preserved for future reference</p>
                            <p>• Create a new campaign to continue reaching your audience</p>
                            <p>• Analyze performance to optimize future campaigns</p>
                            <p>• Consider A/B testing for better results</p>
                        </div>
                        
                        <p>Ready to launch your next campaign?</p>
                        <a href="{current_app.config.get('BASE_URL', 'http://localhost:5000')}/create-campaign" class="button">Create New Campaign</a>
                        
                        <p>Thank you for advertising with Kimbela!</p>
                        
                        <p>Best regards,<br>The Kimbela Team</p>
                    </div>
                    <div class="footer">
                        <p>© 2024 Kimbela. All rights reserved.</p>
                    </div>
                </div>
            </body>
            </html>
            """

            msg = Message(
                subject=subject,
                recipients=[user.email],
                html=html_body,
                sender=current_app.config.get("MAIL_DEFAULT_SENDER"),
            )

            mail.send(msg)
            logger.info(f"Campaign expiry email sent to {user.email}")
            return True

        except Exception as e:
            logger.error(f"Failed to send campaign expiry email: {str(e)}")
            return False

    def get_active_campaigns_count(self, user_id=None):
        """Get count of active campaigns"""
        query = AdCampaign.query.filter_by(status="active")
        if user_id:
            query = query.filter_by(user_id=user_id)
        return query.count()

    def get_expiring_soon_campaigns(self, days=3):
        """Get campaigns expiring in the next few days"""
        target_date = utcnow() + timedelta(days=days)
        return AdCampaign.query.filter(
            and_(
                AdCampaign.end_date <= target_date,
                AdCampaign.end_date > utcnow(),
                AdCampaign.status == "active",
            )
        ).all()

    def send_expiry_reminder(self, campaign):
        """Send reminder email before campaign expires"""
        try:
            user = User.query.get(campaign.user_id)
            days_remaining = (campaign.end_date - utcnow()).days

            subject = f"⏰ Your Ad Campaign Expires in {days_remaining} Days"

            html_body = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0; }}
                    .content {{ background: #f9f9f9; padding: 20px; border-radius: 0 0 10px 10px; }}
                    .button {{ background: #667eea; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; display: inline-block; margin: 10px 0; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>⏰ Campaign Ending Soon</h1>
                        <p>Your ad campaign has {days_remaining} days remaining</p>
                    </div>
                    <div class="content">
                        <p>Hello {user.full_name},</p>
                        <p>Your Kimbela ad campaign <strong>"{campaign.title}"</strong> will end on <strong>{campaign.end_date.strftime('%B %d, %Y')}</strong>.</p>
                        
                        <p><strong>Current Performance:</strong></p>
                        <ul>
                            <li>Impressions: {campaign.impressions:,}</li>
                            <li>Clicks: {campaign.clicks:,}</li>
                            <li>Click-Through Rate: {campaign.click_through_rate:.2f}%</li>
                        </ul>
                        
                        <p>To continue reaching your audience, consider renewing your campaign or creating a new one.</p>
                        
                        <a href="{current_app.config.get('BASE_URL', 'http://localhost:5000')}/user/dashboard" class="button">Manage Campaigns</a>
                        
                        <p>Best regards,<br>The Kimbela Team</p>
                    </div>
                </div>
            </body>
            </html>
            """

            msg = Message(
                subject=subject,
                recipients=[user.email],
                html=html_body,
                sender=current_app.config.get("MAIL_DEFAULT_SENDER"),
            )

            mail.send(msg)
            logger.info(f"Expiry reminder sent to {user.email}")
            return True

        except Exception as e:
            logger.error(f"Failed to send expiry reminder: {str(e)}")
            return False