from time_utils import utcnow
# email_service.py
from flask_mail import Message
from flask import render_template, current_app
from extensions import mail
from datetime import datetime, timedelta
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
                recipients=[user.email],
            )

            msg.html = render_template(
                "success_ad_purchase.html",
                user=user,
                transaction=transaction,
                campaign=campaign,
                package=package,
            )

            mail.send(msg)
            current_app.logger.info(
                f"✅ Success email sent to {user.email} for transaction {transaction.id}"
            )
            return True

        except Exception as e:
            current_app.logger.error(
                f"❌ Failed to send success email to {user.email}: {str(e)}"
            )
            return False

    @staticmethod
    def send_ad_purchase_failed(
        user, package, transaction=None, error_message="Payment failed", campaign=None
    ):
        """Send email for failed ad purchase"""
        try:
            msg = Message(
                subject="⚠️ Payment Issue with Your Kimbela Ad Purchase",
                sender=current_app.config["MAIL_DEFAULT_SENDER"],
                recipients=[user.email],
            )

            msg.html = render_template(
                "failed_ad_purchase.html",
                user=user,
                package=package,
                transaction=transaction,
                error_message=error_message,
                campaign=campaign,
                attempt_date=utcnow(),
            )

            mail.send(msg)
            current_app.logger.info(f"✅ Failed purchase email sent to {user.email}")
            return True

        except Exception as e:
            current_app.logger.error(
                f"❌ Failed to send failure email to {user.email}: {str(e)}"
            )
            return False

    # MATCHMAKING EMAIL METHODS
    @staticmethod
    def send_matchmaking_payment_success(
        user, transaction, matchmaking_request, package
    ):
        """Send email for successful matchmaking purchase"""
        try:
            expiry_date = (
                matchmaking_request.end_date.strftime("%B %d, %Y")
                if matchmaking_request.end_date
                else "Not set"
            )
            duration_days = package.duration_days if package else 30

            msg = Message(
                subject="💖 Your Kimbela Matchmaking Request is Active!",
                sender=current_app.config["MAIL_DEFAULT_SENDER"],
                recipients=[user.email],
            )

            # If you have a template, use it. Otherwise, use the HTML string.
            try:
                msg.html = render_template(
                    "success_matchmaking_purchase.html",
                    user=user,
                    transaction=transaction,
                    matchmaking_request=matchmaking_request,
                    package=package,
                    expiry_date=expiry_date,
                    duration_days=duration_days,
                )
            except:
                # Fallback to direct HTML if template doesn't exist
                msg.html = EmailService._get_matchmaking_success_html(
                    user,
                    transaction,
                    matchmaking_request,
                    package,
                    expiry_date,
                    duration_days,
                )

            mail.send(msg)
            current_app.logger.info(
                f"✅ Matchmaking success email sent to {user.email}"
            )
            return True

        except Exception as e:
            current_app.logger.error(
                f"❌ Failed to send matchmaking success email to {user.email}: {str(e)}"
            )
            return False

    @staticmethod
    def send_matchmaking_payment_failed(
        user,
        package,
        transaction=None,
        error_message="Payment failed",
        matchmaking_request=None,
    ):
        """Send email for failed matchmaking purchase"""
        try:
            msg = Message(
                subject="❌ Payment Failed - Kimbela Matchmaking Request",
                sender=current_app.config["MAIL_DEFAULT_SENDER"],
                recipients=[user.email],
            )

            # If you have a template, use it. Otherwise, use the HTML string.
            try:
                msg.html = render_template(
                    "failed_matchmaking_purchase.html",
                    user=user,
                    package=package,
                    transaction=transaction,
                    error_message=error_message,
                    matchmaking_request=matchmaking_request,
                    attempt_date=utcnow(),
                )
            except:
                # Fallback to direct HTML if template doesn't exist
                msg.html = EmailService._get_matchmaking_failed_html(
                    user, package, transaction, error_message, matchmaking_request
                )

            mail.send(msg)
            current_app.logger.info(
                f"✅ Matchmaking failure email sent to {user.email}"
            )
            return True

        except Exception as e:
            current_app.logger.error(
                f"❌ Failed to send matchmaking failure email to {user.email}: {str(e)}"
            )
            return False

    @staticmethod
    def send_matchmaking_expiry_reminder(user, matchmaking_request):
        """Send expiry reminder email for matchmaking requests"""
        try:
            days_remaining = (matchmaking_request.end_date - utcnow()).days
            package_name = (
                matchmaking_request.package.name
                if matchmaking_request.package
                else "your package"
            )

            msg = Message(
                subject=f"⏰ Your Matchmaking Request Expires in {days_remaining} Days",
                sender=current_app.config["MAIL_DEFAULT_SENDER"],
                recipients=[user.email],
            )

            msg.html = EmailService._get_matchmaking_expiry_html(
                user, matchmaking_request, days_remaining, package_name
            )

            mail.send(msg)
            current_app.logger.info(
                f"✅ Expiry reminder sent to {user.email} for request {matchmaking_request.id}"
            )
            return True

        except Exception as e:
            current_app.logger.error(
                f"❌ Failed to send expiry reminder to {user.email}: {str(e)}"
            )
            return False

    @staticmethod
    def check_and_send_expiry_reminders():
        """Check for expiring matchmaking requests and send reminders"""
        try:
            from models import MatchmakingRequest

            # Get requests expiring in 1, 3, and 7 days
            today = utcnow().date()
            reminder_days = [1, 3, 7]
            total_sent = 0

            for days in reminder_days:
                expiry_date = today + timedelta(days=days)
                expiring_requests = MatchmakingRequest.query.filter(
                    MatchmakingRequest.status == "active",
                    MatchmakingRequest.end_date >= today,
                    MatchmakingRequest.end_date <= expiry_date,
                    MatchmakingRequest.payment_status == "paid",
                ).all()

                for request in expiring_requests:
                    user = request.user
                    if user and user.email:
                        EmailService.send_matchmaking_expiry_reminder(user, request)
                        total_sent += 1

            current_app.logger.info(
                f"✅ Expiry reminder check completed. Sent {total_sent} reminders"
            )
            return True

        except Exception as e:
            current_app.logger.error(f"❌ Error checking expiry reminders: {str(e)}")
            return False

    # HTML TEMPLATE METHODS
    @staticmethod
    def _get_matchmaking_success_html(
        user, transaction, matchmaking_request, package, expiry_date, duration_days
    ):
        """Generate HTML for matchmaking success email"""
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #B76E79 0%, #DCAE96 100%); color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ background: #fdf6f0; padding: 20px; border-radius: 0 0 10px 10px; }}
                .details {{ background: white; padding: 15px; border-radius: 5px; margin: 10px 0; border-left: 4px solid #B76E79; }}
                .footer {{ text-align: center; margin-top: 20px; color: #666; font-size: 12px; }}
                .heart {{ color: #B76E79; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>💖 Matchmaking Request Activated!</h1>
                    <p>Your journey to find meaningful connections begins now</p>
                </div>
                <div class="content">
                    <p>Hello {user.full_name},</p>
                    <p>Wonderful news! Your matchmaking request has been successfully activated and is now visible to potential matches on Kimbela.</p>
                    
                    <div class="details">
                        <h3>📋 Request Details</h3>
                        <p><strong>Package:</strong> {package.name}</p>
                        <p><strong>Total Amount:</strong> {transaction.amount:.2f} {transaction.currency}</p>
                        <p><strong>Duration:</strong> {duration_days} days</p>
                        <p><strong>Start Date:</strong> {matchmaking_request.created_at.strftime('%B %d, %Y')}</p>
                        <p><strong>Expiry Date:</strong> {expiry_date}</p>
                    </div>
                    
                    <div class="details">
                        <h3>✨ What's Next?</h3>
                        <p><span class="heart">❤️</span> Your profile is now visible to compatible matches</p>
                        <p><span class="heart">❤️</span> Receive likes and messages from interested users</p>
                        <p><span class="heart">❤️</span> Browse through potential matches in your criteria</p>
                        <p><span class="heart">❤️</span> Build meaningful connections with like-minded people</p>
                    </div>
                    
                    <p>Ready to start connecting? <a href="{current_app.config.get('BASE_URL', 'http://localhost:5000')}/view_requests" style="color: #B76E79; font-weight: bold;">View your matches now</a></p>
                    
                    <p>Wishing you the best in your journey to find love,<br>The Kimbela Matchmaking Team</p>
                </div>
                <div class="footer">
                    <p>© 2024 Kimbela Matchmaking. Connecting hearts worldwide.</p>
                </div>
            </div>
        </body>
        </html>
        """

    @staticmethod
    def _get_matchmaking_failed_html(
        user, package, transaction, error_message, matchmaking_request
    ):
        """Generate HTML for matchmaking failed payment email"""
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: #dc3545; color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ background: #fdf6f0; padding: 20px; border-radius: 0 0 10px 10px; }}
                .footer {{ text-align: center; margin-top: 20px; color: #666; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>❌ Matchmaking Payment Failed</h1>
                    <p>We couldn't process your matchmaking request payment</p>
                </div>
                <div class="content">
                    <p>Hello {user.full_name},</p>
                    <p>We were unable to process the payment for your matchmaking request. Your request has been saved but will not be activated until payment is completed.</p>
                    
                    <p><strong>Package:</strong> {package.name if package else 'Standard'}</p>
                    <p><strong>Amount:</strong> {transaction.amount if transaction else package.price:.2f} {transaction.currency if transaction else 'USD'}</p>
                    <p><strong>Error:</strong> {error_message}</p>
                    
                    <div style="background: #fff3cd; padding: 15px; border-radius: 5px; margin: 15px 0; border-left: 4px solid #ffc107;">
                        <h4 style="margin-top: 0; color: #856404;">💡 Need Help?</h4>
                        <p style="margin-bottom: 0; color: #856404;">
                            If you're experiencing payment issues, please:
                            <br>• Check your payment method details
                            <br>• Ensure sufficient funds are available
                            <br>• Try a different payment method
                            <br>• Contact our support team for assistance
                        </p>
                    </div>
                    
                    <p>You can retry the payment from your <a href="{current_app.config.get('BASE_URL', 'http://localhost:5000')}/requests" style="color: #B76E79; font-weight: bold;">matchmaking dashboard</a>.</p>
                    
                    <p>Best regards,<br>The Kimbela Matchmaking Team</p>
                </div>
                <div class="footer">
                    <p>© 2024 Kimbela Matchmaking. Connecting hearts worldwide.</p>
                </div>
            </div>
        </body>
        </html>
        """

    @staticmethod
    def _get_matchmaking_expiry_html(
        user, matchmaking_request, days_remaining, package_name
    ):
        """Generate HTML for matchmaking expiry reminder email"""
        urgent_html = ""
        if days_remaining <= 3:
            urgent_html = """
            <div style="background: #fff3cd; padding: 15px; border-radius: 5px; margin: 15px 0; border-left: 4px solid #ffc107;">
                <h3 style="margin-top: 0; color: #856404;">🚨 Action Required</h3>
                <p style="margin-bottom: 0; color: #856404;">Your request expires soon! Consider extending your package to continue receiving matches.</p>
            </div>
            """

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #B76E79 0%, #DCAE96 100%); color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ background: #fdf6f0; padding: 20px; border-radius: 0 0 10px 10px; }}
                .details {{ background: white; padding: 15px; border-radius: 5px; margin: 10px 0; border-left: 4px solid #B76E79; }}
                .footer {{ text-align: center; margin-top: 20px; color: #666; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>⏰ Matchmaking Expiry Reminder</h1>
                    <p>Your request will expire in {days_remaining} days</p>
                </div>
                <div class="content">
                    <p>Hello {user.full_name},</p>
                    <p>This is a friendly reminder that your matchmaking request will expire soon.</p>
                    
                    <div class="details">
                        <h3>📋 Request Details</h3>
                        <p><strong>Package:</strong> {package_name}</p>
                        <p><strong>Expiry Date:</strong> {matchmaking_request.end_date.strftime('%B %d, %Y')}</p>
                        <p><strong>Days Remaining:</strong> {days_remaining} days</p>
                    </div>
                    
                    {urgent_html}
                    
                    <div class="details">
                        <h3>✨ Don't Miss Out!</h3>
                        <p>• Continue receiving matches from compatible partners</p>
                        <p>• Maintain your visibility in search results</p>
                        <p>• Keep your conversations active</p>
                        <p>• Extend your journey to find meaningful connections</p>
                    </div>
                    
                    <p>Ready to continue your journey? <a href="{current_app.config.get('BASE_URL', 'http://localhost:5000')}/requests" style="color: #B76E79; font-weight: bold;">Extend your package now</a></p>
                    
                    <p>Best regards,<br>The Kimbela Matchmaking Team</p>
                </div>
                <div class="footer">
                    <p>© 2024 Kimbela Matchmaking. Connecting hearts worldwide.</p>
                </div>
            </div>
        </body>
        </html>
        """

    @staticmethod
    def send_generic_notification(user, subject, template, **kwargs):
        """Send generic notification email"""
        try:
            msg = Message(
                subject=subject,
                sender=current_app.config["MAIL_DEFAULT_SENDER"],
                recipients=[user.email],
            )

            msg.html = render_template(f"{template}", user=user, **kwargs)
            mail.send(msg)
            current_app.logger.info(f"✅ Notification email sent to {user.email}")
            return True

        except Exception as e:
            current_app.logger.error(
                f"❌ Failed to send notification email to {user.email}: {str(e)}"
            )
            return False