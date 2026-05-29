from time_utils import utcnow
# payments/email_service.py
from flask import current_app
from extensions import mail
from resend_mail import Message
from datetime import datetime, timedelta
import logging
import time

from requests.exceptions import ConnectionError as RequestsConnectionError, Timeout

logger = logging.getLogger(__name__)


class MarketplaceEmailService:
    """Robust email service for marketplace notifications"""

    def __init__(self):
        # Don't access current_app in __init__
        self.base_url = None  # Will be set when needed
        self._initialized = False

    def _ensure_initialized(self):
        """Lazy initialization to avoid circular imports"""
        if not self._initialized:
            self.base_url = (
                current_app.config.get("BASE_URL") or "http://localhost:5000"
            ).rstrip("/")
            self._initialized = True

    @staticmethod
    def _format_money(amount, currency):
        currency = (currency or "USD").upper()
        symbols = {"USD": "$", "EUR": "€", "GBP": "£"}
        symbol = symbols.get(currency, "$")
        return f"{symbol}{float(amount):,.2f} {currency}".strip()

    def _send_email(self, subject, recipient, html_body, text_body=None):
        """Robust email sending with error handling"""
        # Ensure we have current_app context
        self._ensure_initialized()

        max_attempts = 2

        for attempt in range(1, max_attempts + 1):
            try:
                msg = Message(
                    subject=subject,
                    recipients=[recipient],
                    html=html_body,
                    body=text_body,
                    sender=current_app.config.get(
                        "MAIL_DEFAULT_SENDER", "noreply@kimbela.com"
                    ),
                    charset="utf-8",
                )

                # Add important headers
                msg.extra_headers = {
                    "X-Priority": "1",
                    "X-Mailer": "Kimbela Marketplace",
                    "Precedence": "bulk",
                }

                mail.send(msg)
                logger.info(f"✅ Email sent to {recipient}: {subject}")
                return True

            except (RequestsConnectionError, Timeout) as e:
                logger.warning(
                    "Transient email delivery error to %s (attempt %s/%s): %s",
                    recipient,
                    attempt,
                    max_attempts,
                    e,
                )
                if attempt == max_attempts:
                    logger.error(f"❌ Failed to send email to {recipient}: {str(e)}")
                    return False
                time.sleep(0.5 * attempt)
            except Exception as e:
                logger.error(f"❌ Failed to send email to {recipient}: {str(e)}")
                # Log but don't crash the app
                return False

    def _logo_url(self):
        self._ensure_initialized()
        return f"{self.base_url}/static/assets/img/kim.png"

    def _render_shell(self, eyebrow, title, subtitle, body_html, accent):
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
                <img class="logo" src="{self._logo_url()}" alt="Kimbela">
                <span class="eyebrow">{eyebrow}</span>
                <h1>{title}</h1>
                <p>{subtitle}</p>
            </div><div class="content">{body_html}</div>
            <div class="footer">This email was sent automatically by Kimbela Marketplace.</div>
            </div></div>
        </body>
        </html>
        """

    def send_payment_success_email(self, user, marketplace_payment, plan):
        """Send payment success email"""
        try:
            subject = f"🎉 Your Kimbela Marketplace Subscription is Active! - Order #{marketplace_payment.gateway_reference}"

            # Calculate expiration
            expires_at = marketplace_payment.end_date or utcnow() + timedelta(
                days=30
            )

            html_body = self._render_shell(
                "Marketplace",
                "Your seller subscription is active",
                "You are ready to start selling on Kimbela Marketplace.",
                f"""
                <p class="lead">Hello {user.full_name or user.first_name}, your marketplace subscription has been activated successfully.</p>
                <div class="panel">
                    <strong>Order summary</strong><br>
                    Plan: {plan.name}<br>
                    Amount paid: {self._format_money(marketplace_payment.amount, marketplace_payment.currency)}<br>
                    Order ID: {marketplace_payment.gateway_reference}<br>
                    Payment date: {utcnow().strftime('%B %d, %Y')}<br>
                    Expires on: {expires_at.strftime('%B %d, %Y')}
                </div>
                <p class="lead">Next, complete your profile, create your first service, and make sure your listing is ready for buyers.</p>
                <a href="{self.base_url}/market/create_service" class="button">Create Your First Service</a>
                """,
                "linear-gradient(135deg, #8a5a12 0%, #d97706 55%, #f0b44c 100%)",
            )

            # Plain text version for email clients that don't support HTML
            text_body = f"""
            WELCOME TO KIMBELA MARKETPLACE!
            
            Hello {user.full_name or user.first_name},
            
            Thank you for choosing Kimbela Marketplace! Your subscription has been successfully activated.
            
            ORDER SUMMARY:
            --------------
            Plan: {plan.name}
            Amount Paid: {self._format_money(marketplace_payment.amount, marketplace_payment.currency)}
            Order ID: {marketplace_payment.gateway_reference}
            Payment Date: {utcnow().strftime('%B %d, %Y')}
            Expires On: {expires_at.strftime('%B %d, %Y')}
            Status: ACTIVE
            
            NEXT STEPS:
            -----------
            1. Complete Your Profile: Add your photo, bio, and contact information
            2. Create Your First Service: List your service with clear descriptions
            3. Set Your Availability: Let buyers know when you're available
            4. Promote Your Services: Share your Kimbela profile link
            
            GET STARTED:
            ------------
            Create your first service: {self.base_url}/market/create_service
            
            NEED HELP?
            ----------
            Visit our Seller Help Center: {self.base_url}/help/marketplace
            Email support: support@kimbela.com
            
            © {utcnow().year} Kimbela Marketplace
            This is an automated message. Please do not reply to this email.
            """

            return self._send_email(subject, user.email, html_body, text_body)

        except Exception as e:
            logger.error(f"Failed to create success email: {str(e)}")
            return False

    def send_payment_failed_email(
        self, user, marketplace_payment, plan, error_reason=None
    ):
        """Send payment failure email"""
        try:
            subject = f"❌ Payment Failed - Kimbela Marketplace Order #{marketplace_payment.gateway_reference}"

            error_html = f"<br>Error details: {error_reason}" if error_reason else ""
            html_body = self._render_shell(
                "Marketplace",
                "Payment was not completed",
                "We could not process your marketplace subscription payment.",
                f"""
                <p class="lead">Hello {user.full_name or user.first_name}, your payment for the <strong>{plan.name}</strong> subscription did not go through.</p>
                <div class="panel">
                    <strong>Payment details</strong><br>
                    Plan: {plan.name}<br>
                    Amount: {self._format_money(marketplace_payment.amount, marketplace_payment.currency)}<br>
                    Reference: {marketplace_payment.gateway_reference}<br>
                    Status: Failed{error_html}
                </div>
                <p class="lead">Please review your payment method, confirm available funds, or try again using a different payment option.</p>
                <a href="{self.base_url}/subscribe" class="button">Retry Payment</a>
                """,
                "linear-gradient(135deg, #5d2028 0%, #9a3d38 55%, #b37b37 100%)",
            )

            text_body = f"""
            PAYMENT FAILED - KIMBELA MARKETPLACE
            
            Hello {user.full_name or user.first_name},
            
            We attempted to process your payment for the {plan.name} subscription, but the transaction was not successful.
            
            PAYMENT DETAILS:
            ----------------
            Plan: {plan.name}
            Amount: {self._format_money(marketplace_payment.amount, marketplace_payment.currency)}
            Reference: {marketplace_payment.gateway_reference}
            Status: FAILED
            
            {f'Error Reason: {error_reason}' if error_reason else ''}
            
            RETRY YOUR PAYMENT:
            -------------------
            You can retry your payment here: {self.base_url}/subscribe
            
            TROUBLESHOOTING:
            ----------------
            1. Check your payment method details
            2. Ensure you have sufficient funds
            3. Try a different payment method
            4. Contact your bank if international transactions are blocked
            
            NEED HELP?
            ----------
            Email our support team: support@kimbela.com
            
            We're here to help you succeed on Kimbela Marketplace!
            
            © {utcnow().year} Kimbela Marketplace
            This is an automated message.
            """

            return self._send_email(subject, user.email, html_body, text_body)

        except Exception as e:
            logger.error(f"Failed to create failure email: {str(e)}")
            return False
