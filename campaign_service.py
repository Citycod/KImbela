from flask import current_app

from extensions import db, mail
from models import AdCampaign, User
from resend_mail import Message
from datetime import datetime, timedelta
import logging
from sqlalchemy import and_

from time_utils import utcnow
logger = logging.getLogger(__name__)


class CampaignService:
    def _logo_url(self):
        return f"{current_app.config.get('BASE_URL', 'http://localhost:5000')}/static/assets/img/kim.png"

    def _render_email_shell(self, eyebrow, title, subtitle, body_html, accent="linear-gradient(135deg, #17324d 0%, #244f68 55%, #b37b37 100%)"):
        return f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body {{ margin: 0; padding: 0; background: #f4efe6; color: #1f2937; font-family: "Segoe UI", Arial, sans-serif; line-height: 1.55; font-size: 14px; }}
                .wrap {{ width: 100%; padding: 24px 12px; box-sizing: border-box; }}
                .card {{ max-width: 660px; margin: 0 auto; background: #fffdfa; border: 1px solid #e9ddca; border-radius: 24px; overflow: hidden; box-shadow: 0 18px 50px rgba(55, 42, 18, 0.08); }}
                .hero {{ padding: 28px 28px 24px; background: {accent}; color: #fffdf8; text-align: center; }}
                .logo {{ width: auto; max-width: 160px; max-height: 88px; display: block; margin: 0 auto 18px; }}
                .eyebrow {{ display: inline-block; padding: 7px 12px; border-radius: 999px; background: rgba(255,255,255,0.12); border: 1px solid rgba(255,255,255,0.16); text-transform: uppercase; letter-spacing: 0.08em; font-size: 11px; }}
                .hero h1 {{ margin: 16px 0 8px; font-size: 28px; line-height: 1.15; font-weight: 700; }}
                .hero p {{ margin: 0; font-size: 14px; color: rgba(255,253,248,0.9); }}
                .content {{ padding: 28px; }}
                .lead {{ margin: 0 0 16px; font-size: 15px; color: #334155; }}
                .panel {{ margin: 22px 0; padding: 20px; border-radius: 18px; background: #f7f2e8; border: 1px solid #eadfce; }}
                .button {{ display: inline-block; margin-top: 10px; padding: 13px 22px; border-radius: 999px; background: #17324d; color: #fffdfa !important; text-decoration: none; font-size: 14px; font-weight: 700; }}
                .footer {{ padding: 22px 28px 28px; border-top: 1px solid #ece1d2; color: #6b7280; font-size: 12px; line-height: 1.65; }}
                @media only screen and (max-width: 640px) {{
                    .wrap {{ padding: 12px 8px; }}
                    .hero, .content, .footer {{ padding-left: 20px; padding-right: 20px; }}
                    .hero h1 {{ font-size: 23px; }}
                    .lead, .panel {{ font-size: 13px; }}
                    .button {{ width: 100%; box-sizing: border-box; text-align: center; }}
                    .logo {{ max-height: 72px; max-width: 140px; }}
                }}
            </style>
        </head>
        <body>
            <div class="wrap">
                <div class="card">
                    <div class="hero">
                        <img class="logo" src="{self._logo_url()}" alt="Kimbela">
                        <span class="eyebrow">{eyebrow}</span>
                        <h1>{title}</h1>
                        <p>{subtitle}</p>
                    </div>
                    <div class="content">{body_html}</div>
                    <div class="footer">This email was sent automatically by Kimbela regarding your ad campaign.</div>
                </div>
            </div>
        </body>
        </html>
        """

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

            cpc = ((campaign.budget * campaign.duration_days) / campaign.clicks) if campaign.clicks > 0 else 0
            body_html = f"""
            <p class="lead">Hello {user.full_name}, your ad campaign <strong>{campaign.title}</strong> has ended as scheduled.</p>
            <div class="panel">
                <strong>Performance summary</strong><br>
                Duration: {campaign.duration_days} days<br>
                Impressions: {campaign.impressions:,}<br>
                Clicks: {campaign.clicks:,}<br>
                Click-through rate: {campaign.click_through_rate:.2f}%<br>
                Total budget: ${campaign.budget * campaign.duration_days:.2f}<br>
                Cost per click: ${cpc:.2f}
            </div>
            <p class="lead">Your campaign data is preserved for reference, and you can launch a new campaign whenever you are ready.</p>
            <a href="{current_app.config.get('BASE_URL', 'http://localhost:5000')}/create-campaign" class="button">Create New Campaign</a>
            """
            html_body = self._render_email_shell(
                "Advertising",
                "Campaign completed",
                "Your ad campaign has ended and your results are ready to review.",
                body_html,
                accent="linear-gradient(135deg, #5d2028 0%, #9a3d38 55%, #b37b37 100%)",
            )

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

            body_html = f"""
            <p class="lead">Hello {user.full_name}, your campaign <strong>{campaign.title}</strong> will end on <strong>{campaign.end_date.strftime('%B %d, %Y')}</strong>.</p>
            <div class="panel">
                <strong>Current performance</strong><br>
                Impressions: {campaign.impressions:,}<br>
                Clicks: {campaign.clicks:,}<br>
                Click-through rate: {campaign.click_through_rate:.2f}%<br>
                Days remaining: {days_remaining}
            </div>
            <p class="lead">If you want to keep reaching your audience, now is a good time to renew or launch a new campaign.</p>
            <a href="{current_app.config.get('BASE_URL', 'http://localhost:5000')}/user/dashboard" class="button">Manage Campaigns</a>
            """
            html_body = self._render_email_shell(
                "Advertising",
                "Campaign ending soon",
                f"Your ad campaign has {days_remaining} days remaining.",
                body_html,
                accent="linear-gradient(135deg, #6b2f67 0%, #b24a76 55%, #d39b43 100%)",
            )

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
