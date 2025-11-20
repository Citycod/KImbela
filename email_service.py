# email_service.py
from flask_mail import Message
from flask import render_template, current_app
from extensions import mail
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class EmailService:
    @staticmethod
    def send_ad_purchase_success(user, transaction, campaign, package):
        """Send email for successful ad purchase"""
        try:
            msg = Message(
                subject="🎉 Your Kimbela Ad is Live! - Purchase Confirmed",
                sender=current_app.config["MAIL_DEFAULT_SENDER"],
                recipients=[user.email]
            )
            
            msg.html = render_template(
                "success_ad_purchase.html",
                user=user,
                transaction=transaction,
                campaign=campaign,
                package=package
            )
            
            mail.send(msg)
            current_app.logger.info(f"✅ Success email sent to {user.email} for transaction {transaction.id}")
            return True
            
        except Exception as e:
            current_app.logger.error(f"❌ Failed to send success email to {user.email}: {str(e)}")
            return False

    @staticmethod
    def send_ad_purchase_failed(user, package, transaction=None, error_message="Payment failed", campaign=None):
        """Send email for failed ad purchase"""
        try:
            msg = Message(
                subject="⚠️ Payment Issue with Your Kimbela Ad Purchase",
                sender=current_app.config["MAIL_DEFAULT_SENDER"],
                recipients=[user.email]
            )
            
            msg.html = render_template(
                "failed_ad_purchase.html",
                user=user,
                package=package,
                transaction=transaction,
                error_message=error_message,
                campaign=campaign,
                attempt_date=datetime.utcnow()
            )
            
            mail.send(msg)
            current_app.logger.info(f"✅ Failed purchase email sent to {user.email}")
            return True
            
        except Exception as e:
            current_app.logger.error(f"❌ Failed to send failure email to {user.email}: {str(e)}")
            return False

    @staticmethod
    def send_generic_notification(user, subject, template, **kwargs):
        """Send generic notification email"""
        try:
            msg = Message(
                subject=subject,
                sender=current_app.config["MAIL_DEFAULT_SENDER"],
                recipients=[user.email]
            )
            
            msg.html = render_template(f"{template}", user=user, **kwargs)
            mail.send(msg)
            current_app.logger.info(f"✅ Notification email sent to {user.email}")
            return True
            
        except Exception as e:
            current_app.logger.error(f"❌ Failed to send notification email to {user.email}: {str(e)}")
            return False