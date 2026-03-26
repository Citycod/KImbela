from time_utils import utcnow
# email_service.py
from flask import render_template, current_app
from extensions import mail
from resend_mail import Message
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class EmailService:
    @staticmethod
    def _logo_url():
        return f"{current_app.config.get('BASE_URL', 'http://localhost:5000')}/static/assets/img/kim.png"

    @staticmethod
    def _render_matchmaking_shell(eyebrow, title, subtitle, body_html, accent="linear-gradient(135deg, #17324d 0%, #3f2d64 55%, #b37b37 100%)"):
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
            <div class="wrap"><div class="card"><div class="hero">
            <img class="logo" src="{EmailService._logo_url()}" alt="Kimbela">
            <span class="eyebrow">{eyebrow}</span><h1>{title}</h1><p>{subtitle}</p>
            </div><div class="content">{body_html}</div>
            <div class="footer">This email was sent automatically by Kimbela Matchmaking.</div>
            </div></div>
        </body>
        </html>
        """
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
        body_html = f"""
        <p class="lead">Hello {user.full_name}, your matchmaking request is now active and visible to potential matches on Kimbela.</p>
        <div class="panel">
            <strong>Request details</strong><br>
            Package: {package.name}<br>
            Amount: {transaction.amount:.2f} {transaction.currency}<br>
            Duration: {duration_days} days<br>
            Start date: {matchmaking_request.created_at.strftime('%B %d, %Y')}<br>
            Expiry date: {expiry_date}
        </div>
        <p class="lead">You can now receive interest from compatible users, review potential matches, and start meaningful conversations.</p>
        <a href="{current_app.config.get('BASE_URL', 'http://localhost:5000')}/view_requests" class="button">View Matches</a>
        """
        return EmailService._render_matchmaking_shell(
            "Matchmaking",
            "Your request is active",
            "Your journey to meaningful connections begins now.",
            body_html,
            accent="linear-gradient(135deg, #7a3047 0%, #b76e79 55%, #d2a164 100%)",
        )

    @staticmethod
    def _get_matchmaking_failed_html(
        user, package, transaction, error_message, matchmaking_request
    ):
        """Generate HTML for matchmaking failed payment email"""
        amount = transaction.amount if transaction else package.price
        currency = transaction.currency if transaction else "USD"
        body_html = f"""
        <p class="lead">Hello {user.full_name}, we could not process the payment for your matchmaking request, so it has not been activated yet.</p>
        <div class="panel">
            <strong>Payment details</strong><br>
            Package: {package.name if package else 'Standard'}<br>
            Amount: {amount:.2f} {currency}<br>
            Error: {error_message}
        </div>
        <p class="lead">Please review your payment method, make sure funds are available, or try again from your matchmaking dashboard.</p>
        <a href="{current_app.config.get('BASE_URL', 'http://localhost:5000')}/requests" class="button">Retry Payment</a>
        """
        return EmailService._render_matchmaking_shell(
            "Matchmaking",
            "Payment was not completed",
            "Your matchmaking request is saved, but it is waiting for successful payment.",
            body_html,
            accent="linear-gradient(135deg, #5d2028 0%, #9a3d38 55%, #b37b37 100%)",
        )

    @staticmethod
    def _get_matchmaking_expiry_html(
        user, matchmaking_request, days_remaining, package_name
    ):
        """Generate HTML for matchmaking expiry reminder email"""
        urgent_html = (
            "<div class='panel'><strong>Action recommended</strong><br>Your request expires very soon. Extend it now if you want to keep receiving matches without interruption.</div>"
            if days_remaining <= 3
            else ""
        )

        body_html = f"""
        <p class="lead">Hello {user.full_name}, this is a reminder that your matchmaking request will expire soon.</p>
        <div class="panel">
            <strong>Request details</strong><br>
            Package: {package_name}<br>
            Expiry date: {matchmaking_request.end_date.strftime('%B %d, %Y')}<br>
            Days remaining: {days_remaining}
        </div>
        {urgent_html}
        <p class="lead">Extend your package to keep your visibility active, maintain conversations, and continue receiving compatible matches.</p>
        <a href="{current_app.config.get('BASE_URL', 'http://localhost:5000')}/requests" class="button">Extend Package</a>
        """
        return EmailService._render_matchmaking_shell(
            "Matchmaking",
            "Your request expires soon",
            f"You have {days_remaining} days remaining on your active matchmaking request.",
            body_html,
            accent="linear-gradient(135deg, #6b2f67 0%, #b24a76 55%, #d39b43 100%)",
        )

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
