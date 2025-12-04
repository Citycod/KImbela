# payments/email_service.py
from flask import current_app
from flask_mail import Message
from extensions import mail
from datetime import datetime
import logging

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
            self.base_url = current_app.config.get("BASE_URL", "http://localhost:5000")
            self._initialized = True

    def _send_email(self, subject, recipient, html_body, text_body=None):
        """Robust email sending with error handling"""
        try:
            # Ensure we have current_app context
            self._ensure_initialized()

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

        except Exception as e:
            logger.error(f"❌ Failed to send email to {recipient}: {str(e)}")
            # Log but don't crash the app
            return False

    def send_payment_success_email(self, user, marketplace_payment, plan):
        """Send payment success email"""
        try:
            subject = f"🎉 Your Kimbela Marketplace Subscription is Active! - Order #{marketplace_payment.gateway_reference}"

            # Calculate expiration
            expires_at = marketplace_payment.end_date or datetime.utcnow() + timedelta(
                days=30
            )

            # Create beautiful HTML email
            html_body = f"""
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Subscription Activated</title>
                <style>
                    /* Base Styles */
                    * {{
                        margin: 0;
                        padding: 0;
                        box-sizing: border-box;
                    }}
                    
                    body {{
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                        line-height: 1.6;
                        color: #333;
                        background-color: #f8f9fa;
                        padding: 20px;
                    }}
                    
                    .email-container {{
                        max-width: 600px;
                        margin: 0 auto;
                        background: #ffffff;
                        border-radius: 12px;
                        overflow: hidden;
                        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
                    }}
                    
                    /* Header */
                    .email-header {{
                        background: linear-gradient(135deg, #D97706 0%, #FBBF24 100%);
                        padding: 40px 30px;
                        text-align: center;
                        color: white;
                    }}
                    
                    .email-header h1 {{
                        font-size: 28px;
                        font-weight: 700;
                        margin-bottom: 10px;
                    }}
                    
                    .email-header p {{
                        font-size: 16px;
                        opacity: 0.9;
                        margin-bottom: 0;
                    }}
                    
                    .success-icon {{
                        font-size: 48px;
                        margin-bottom: 20px;
                        display: inline-block;
                    }}
                    
                    /* Content */
                    .email-content {{
                        padding: 40px 30px;
                    }}
                    
                    .greeting {{
                        font-size: 18px;
                        margin-bottom: 25px;
                        color: #4b5563;
                    }}
                    
                    .greeting strong {{
                        color: #1f2937;
                    }}
                    
                    /* Order Summary */
                    .order-summary {{
                        background: linear-gradient(135deg, #fef3c7 0%, #fef9c3 100%);
                        border-radius: 10px;
                        padding: 25px;
                        margin-bottom: 30px;
                        border-left: 4px solid #D97706;
                    }}
                    
                    .order-summary h2 {{
                        color: #92400E;
                        font-size: 20px;
                        margin-bottom: 15px;
                        display: flex;
                        align-items: center;
                        gap: 10px;
                    }}
                    
                    .order-summary h2 i {{
                        font-size: 24px;
                    }}
                    
                    .order-details {{
                        display: grid;
                        grid-template-columns: 1fr 1fr;
                        gap: 15px;
                    }}
                    
                    .detail-item {{
                        margin-bottom: 10px;
                    }}
                    
                    .detail-label {{
                        font-weight: 600;
                        color: #6b7280;
                        font-size: 14px;
                        display: block;
                        margin-bottom: 4px;
                    }}
                    
                    .detail-value {{
                        font-weight: 700;
                        color: #1f2937;
                        font-size: 15px;
                    }}
                    
                    .status-badge {{
                        display: inline-block;
                        padding: 5px 12px;
                        background: #10b981;
                        color: white;
                        border-radius: 20px;
                        font-size: 12px;
                        font-weight: 600;
                    }}
                    
                    /* Next Steps */
                    .next-steps {{
                        background: #eff6ff;
                        border-radius: 10px;
                        padding: 25px;
                        margin-bottom: 30px;
                    }}
                    
                    .next-steps h2 {{
                        color: #1e40af;
                        font-size: 20px;
                        margin-bottom: 20px;
                    }}
                    
                    .steps-list {{
                        list-style: none;
                        padding: 0;
                    }}
                    
                    .step-item {{
                        display: flex;
                        align-items: flex-start;
                        margin-bottom: 15px;
                        padding-bottom: 15px;
                        border-bottom: 1px solid #dbeafe;
                    }}
                    
                    .step-item:last-child {{
                        border-bottom: none;
                        margin-bottom: 0;
                        padding-bottom: 0;
                    }}
                    
                    .step-number {{
                        background: #3b82f6;
                        color: white;
                        width: 28px;
                        height: 28px;
                        border-radius: 50%;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        font-weight: 700;
                        font-size: 14px;
                        flex-shrink: 0;
                        margin-right: 15px;
                    }}
                    
                    .step-content h3 {{
                        color: #1e40af;
                        font-size: 16px;
                        margin-bottom: 5px;
                    }}
                    
                    .step-content p {{
                        color: #4b5563;
                        font-size: 14px;
                        line-height: 1.5;
                    }}
                    
                    /* CTA Button */
                    .cta-container {{
                        text-align: center;
                        margin: 30px 0;
                    }}
                    
                    .cta-button {{
                        display: inline-block;
                        background: linear-gradient(135deg, #D97706 0%, #FBBF24 100%);
                        color: white;
                        text-decoration: none;
                        padding: 16px 40px;
                        border-radius: 8px;
                        font-weight: 700;
                        font-size: 16px;
                        transition: all 0.3s ease;
                        box-shadow: 0 4px 15px rgba(217, 119, 6, 0.3);
                    }}
                    
                    .cta-button:hover {{
                        transform: translateY(-2px);
                        box-shadow: 0 6px 20px rgba(217, 119, 6, 0.4);
                    }}
                    
                    /* Tips Section */
                    .tips-section {{
                        background: #f0fdf4;
                        border-radius: 10px;
                        padding: 25px;
                        margin-top: 30px;
                    }}
                    
                    .tips-section h2 {{
                        color: #065f46;
                        font-size: 20px;
                        margin-bottom: 20px;
                    }}
                    
                    .tips-grid {{
                        display: grid;
                        grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                        gap: 20px;
                    }}
                    
                    .tip-card {{
                        background: white;
                        padding: 20px;
                        border-radius: 8px;
                        border: 1px solid #d1fae5;
                    }}
                    
                    .tip-card h3 {{
                        color: #065f46;
                        font-size: 16px;
                        margin-bottom: 10px;
                        display: flex;
                        align-items: center;
                        gap: 8px;
                    }}
                    
                    .tip-card p {{
                        color: #4b5563;
                        font-size: 14px;
                        line-height: 1.5;
                    }}
                    
                    /* Footer */
                    .email-footer {{
                        background: #1f2937;
                        color: #9ca3af;
                        padding: 30px;
                        text-align: center;
                        font-size: 12px;
                    }}
                    
                    .footer-links {{
                        margin-bottom: 20px;
                    }}
                    
                    .footer-links a {{
                        color: #d1d5db;
                        text-decoration: none;
                        margin: 0 10px;
                        transition: color 0.3s ease;
                    }}
                    
                    .footer-links a:hover {{
                        color: white;
                    }}
                    
                    .copyright {{
                        opacity: 0.7;
                    }}
                    
                    /* Responsive */
                    @media (max-width: 640px) {{
                        .order-details {{
                            grid-template-columns: 1fr;
                        }}
                        
                        .tips-grid {{
                            grid-template-columns: 1fr;
                        }}
                        
                        .email-header h1 {{
                            font-size: 24px;
                        }}
                        
                        .email-content {{
                            padding: 20px;
                        }}
                    }}
                </style>
            </head>
            <body>
                <div class="email-container">
                    <!-- Header -->
                    <div class="email-header">
                        <div class="success-icon">🎉</div>
                        <h1>Welcome to Kimbela Marketplace!</h1>
                        <p>Your seller subscription is now active</p>
                    </div>
                    
                    <!-- Content -->
                    <div class="email-content">
                        <div class="greeting">
                            Hello <strong>{user.full_name or user.first_name}</strong>,
                        </div>
                        
                        <p style="font-size: 16px; color: #4b5563; margin-bottom: 25px; line-height: 1.6;">
                            Thank you for choosing Kimbela Marketplace! Your subscription has been successfully 
                            activated. You're now ready to start selling your services and connecting with buyers.
                        </p>
                        
                        <!-- Order Summary -->
                        <div class="order-summary">
                            <h2><i>📋</i> Order Summary</h2>
                            <div class="order-details">
                                <div class="detail-item">
                                    <span class="detail-label">Plan</span>
                                    <span class="detail-value">{plan.name}</span>
                                </div>
                                <div class="detail-item">
                                    <span class="detail-label">Amount Paid</span>
                                    <span class="detail-value">${marketplace_payment.amount:.2f} {marketplace_payment.currency}</span>
                                </div>
                                <div class="detail-item">
                                    <span class="detail-label">Order ID</span>
                                    <span class="detail-value">{marketplace_payment.gateway_reference}</span>
                                </div>
                                <div class="detail-item">
                                    <span class="detail-label">Payment Date</span>
                                    <span class="detail-value">{datetime.utcnow().strftime('%B %d, %Y')}</span>
                                </div>
                                <div class="detail-item">
                                    <span class="detail-label">Expires On</span>
                                    <span class="detail-value">{expires_at.strftime('%B %d, %Y')}</span>
                                </div>
                                <div class="detail-item">
                                    <span class="detail-label">Status</span>
                                    <span class="status-badge">ACTIVE</span>
                                </div>
                            </div>
                        </div>
                        
                        <!-- Next Steps -->
                        <div class="next-steps">
                            <h2>🚀 Your Next Steps</h2>
                            <ul class="steps-list">
                                <li class="step-item">
                                    <div class="step-number">1</div>
                                    <div class="step-content">
                                        <h3>Complete Your Profile</h3>
                                        <p>Add your photo, bio, and contact information to build trust with buyers.</p>
                                    </div>
                                </li>
                                <li class="step-item">
                                    <div class="step-number">2</div>
                                    <div class="step-content">
                                        <h3>Create Your First Service</h3>
                                        <p>List your service with clear descriptions, pricing, and high-quality images.</p>
                                    </div>
                                </li>
                                <li class="step-item">
                                    <div class="step-number">3</div>
                                    <div class="step-content">
                                        <h3>Set Your Availability</h3>
                                        <p>Let buyers know when you're available for consultations or service delivery.</p>
                                    </div>
                                </li>
                                <li class="step-item">
                                    <div class="step-number">4</div>
                                    <div class="step-content">
                                        <h3>Promote Your Services</h3>
                                        <p>Share your Kimbela profile link on social media and with your network.</p>
                                    </div>
                                </li>
                            </ul>
                        </div>
                        
                        <!-- CTA Button -->
                        <div class="cta-container">
                            <a href="{self.base_url}/market/create_service" class="cta-button">
                                🛍️ Create Your First Service
                            </a>
                        </div>
                        
                        <!-- Tips Section -->
                        <div class="tips-section">
                            <h2>💡 Pro Tips for Success</h2>
                            <div class="tips-grid">
                                <div class="tip-card">
                                    <h3>✨ Quality Images</h3>
                                    <p>Use clear, well-lit photos that showcase your work or service quality.</p>
                                </div>
                                <div class="tip-card">
                                    <h3>📝 Detailed Descriptions</h3>
                                    <p>Be specific about what buyers get, timelines, and any requirements.</p>
                                </div>
                                <div class="tip-card">
                                    <h3>💬 Quick Responses</h3>
                                    <p>Reply to inquiries within 24 hours to build trust and close sales faster.</p>
                                </div>
                                <div class="tip-card">
                                    <h3>⭐ Collect Reviews</h3>
                                    <p>Ask satisfied customers to leave reviews to boost your credibility.</p>
                                </div>
                            </div>
                        </div>
                        
                        <!-- Support Note -->
                        <div style="margin-top: 30px; padding: 20px; background: #f3f4f6; border-radius: 8px; text-align: center;">
                            <p style="color: #4b5563; font-size: 14px; margin-bottom: 10px;">
                                Need help? Visit our <a href="{self.base_url}/help/marketplace" style="color: #D97706; font-weight: 600; text-decoration: none;">Seller Help Center</a> 
                                or email <a href="mailto:support@kimbela.com" style="color: #D97706; font-weight: 600; text-decoration: none;">support@kimbela.com</a>
                            </p>
                        </div>
                    </div>
                    
                    <!-- Footer -->
                    <div class="email-footer">
                        <div class="footer-links">
                            <a href="{self.base_url}/privacy">Privacy Policy</a> | 
                            <a href="{self.base_url}/terms">Terms of Service</a> | 
                            <a href="{self.base_url}/contact">Contact Us</a> | 
                            <a href="{self.base_url}/unsubscribe">Unsubscribe</a>
                        </div>
                        <div class="copyright">
                            © {datetime.utcnow().year} Kimbela Marketplace. Connecting African professionals worldwide.
                            <br>This is an automated message. Please do not reply to this email.
                        </div>
                    </div>
                </div>
            </body>
            </html>
            """

            # Plain text version for email clients that don't support HTML
            text_body = f"""
            WELCOME TO KIMBELA MARKETPLACE!
            
            Hello {user.full_name or user.first_name},
            
            Thank you for choosing Kimbela Marketplace! Your subscription has been successfully activated.
            
            ORDER SUMMARY:
            --------------
            Plan: {plan.name}
            Amount Paid: ${marketplace_payment.amount:.2f} {marketplace_payment.currency}
            Order ID: {marketplace_payment.gateway_reference}
            Payment Date: {datetime.utcnow().strftime('%B %d, %Y')}
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
            
            © {datetime.utcnow().year} Kimbela Marketplace
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

            html_body = f"""
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Payment Failed</title>
                <style>
                    /* Reuse similar styles as success email but with red theme */
                    body {{
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                        line-height: 1.6;
                        color: #333;
                        background-color: #f8f9fa;
                        padding: 20px;
                    }}
                    
                    .email-container {{
                        max-width: 600px;
                        margin: 0 auto;
                        background: #ffffff;
                        border-radius: 12px;
                        overflow: hidden;
                        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
                    }}
                    
                    .email-header {{
                        background: linear-gradient(135deg, #dc2626 0%, #ef4444 100%);
                        padding: 40px 30px;
                        text-align: center;
                        color: white;
                    }}
                    
                    .email-header h1 {{
                        font-size: 28px;
                        font-weight: 700;
                        margin-bottom: 10px;
                    }}
                    
                    .warning-icon {{
                        font-size: 48px;
                        margin-bottom: 20px;
                    }}
                    
                    .email-content {{
                        padding: 40px 30px;
                    }}
                    
                    .status-badge-failed {{
                        display: inline-block;
                        padding: 5px 12px;
                        background: #dc2626;
                        color: white;
                        border-radius: 20px;
                        font-size: 12px;
                        font-weight: 600;
                    }}
                    
                    .retry-section {{
                        background: linear-gradient(135deg, #fef3c7 0%, #fef9c3 100%);
                        border-radius: 10px;
                        padding: 25px;
                        margin: 30px 0;
                        border-left: 4px solid #f59e0b;
                    }}
                    
                    .help-section {{
                        background: #fef2f2;
                        border-radius: 10px;
                        padding: 25px;
                        margin-top: 30px;
                    }}
                    
                    .cta-button-retry {{
                        display: inline-block;
                        background: linear-gradient(135deg, #dc2626 0%, #ef4444 100%);
                        color: white;
                        text-decoration: none;
                        padding: 16px 40px;
                        border-radius: 8px;
                        font-weight: 700;
                        font-size: 16px;
                        transition: all 0.3s ease;
                        box-shadow: 0 4px 15px rgba(220, 38, 38, 0.3);
                    }}
                    
                    .cta-button-retry:hover {{
                        transform: translateY(-2px);
                        box-shadow: 0 6px 20px rgba(220, 38, 38, 0.4);
                    }}
                </style>
            </head>
            <body>
                <div class="email-container">
                    <div class="email-header">
                        <div class="warning-icon">❌</div>
                        <h1>Payment Failed</h1>
                        <p>We couldn't process your subscription payment</p>
                    </div>
                    
                    <div class="email-content">
                        <div style="font-size: 18px; margin-bottom: 25px; color: #4b5563;">
                            Hello <strong>{user.full_name or user.first_name}</strong>,
                        </div>
                        
                        <p style="font-size: 16px; color: #4b5563; margin-bottom: 25px; line-height: 1.6;">
                            We attempted to process your payment for the <strong>{plan.name}</strong> subscription, 
                            but the transaction was not successful.
                        </p>
                        
                        <div style="background: #f3f4f6; border-radius: 10px; padding: 25px; margin-bottom: 30px;">
                            <h2 style="color: #1f2937; font-size: 20px; margin-bottom: 15px;">Payment Details</h2>
                            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px;">
                                <div>
                                    <span style="display: block; font-weight: 600; color: #6b7280; font-size: 14px; margin-bottom: 4px;">Plan</span>
                                    <span style="font-weight: 700; color: #1f2937;">{plan.name}</span>
                                </div>
                                <div>
                                    <span style="display: block; font-weight: 600; color: #6b7280; font-size: 14px; margin-bottom: 4px;">Amount</span>
                                    <span style="font-weight: 700; color: #1f2937;">${marketplace_payment.amount:.2f} {marketplace_payment.currency}</span>
                                </div>
                                <div>
                                    <span style="display: block; font-weight: 600; color: #6b7280; font-size: 14px; margin-bottom: 4px;">Reference</span>
                                    <span style="font-weight: 700; color: #1f2937;">{marketplace_payment.gateway_reference}</span>
                                </div>
                                <div>
                                    <span style="display: block; font-weight: 600; color: #6b7280; font-size: 14px; margin-bottom: 4px;">Status</span>
                                    <span class="status-badge-failed">FAILED</span>
                                </div>
                            </div>
                        </div>
                        
                        <div class="retry-section">
                            <h2 style="color: #92400E; font-size: 20px; margin-bottom: 15px;">🔄 Retry Your Payment</h2>
                            <p style="color: #92400E; margin-bottom: 20px; line-height: 1.6;">
                                You can easily retry your payment using the same or a different payment method.
                            </p>
                            <div style="text-align: center; margin-top: 25px;">
                                <a href="{self.base_url}/become-seller" class="cta-button-retry">
                                    🔄 Retry Payment
                                </a>
                            </div>
                        </div>
                        
                        <div class="help-section">
                            <h2 style="color: #991b1b; font-size: 20px; margin-bottom: 15px;">💡 Need Help?</h2>
                            
                            {f'<p style="color: #991b1b; margin-bottom: 15px; padding: 10px; background: #fecaca; border-radius: 5px; border-left: 4px solid #dc2626;"><strong>Error Details:</strong> {error_reason}</p>' if error_reason else ''}
                            
                            <p style="color: #4b5563; margin-bottom: 15px; line-height: 1.6;">
                                If you're experiencing payment issues:
                            </p>
                            
                            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 20px;">
                                <div style="background: white; padding: 15px; border-radius: 8px; border: 1px solid #fca5a5;">
                                    <h3 style="color: #dc2626; font-size: 16px; margin-bottom: 10px;">💰 Check Payment Method</h3>
                                    <p style="color: #6b7280; font-size: 14px;">
                                        Ensure your card details are correct and you have sufficient funds.
                                    </p>
                                </div>
                                <div style="background: white; padding: 15px; border-radius: 8px; border: 1px solid #fca5a5;">
                                    <h3 style="color: #dc2626; font-size: 16px; margin-bottom: 10px;">🔄 Try Different Method</h3>
                                    <p style="color: #6b7280; font-size: 14px;">
                                        Try a different credit/debit card or payment method.
                                    </p>
                                </div>
                                <div style="background: white; padding: 15px; border-radius: 8px; border: 1px solid #fca5a5;">
                                    <h3 style="color: #dc2626; font-size: 16px; margin-bottom: 10px;">🔒 Contact Your Bank</h3>
                                    <p style="color: #6b7280; font-size: 14px;">
                                        Some banks block international transactions. Contact them to approve.
                                    </p>
                                </div>
                                <div style="background: white; padding: 15px; border-radius: 8px; border: 1px solid #fca5a5;">
                                    <h3 style="color: #dc2626; font-size: 16px; margin-bottom: 10px;">📞 Contact Support</h3>
                                    <p style="color: #6b7280; font-size: 14px;">
                                        We're here to help! Email us at support@kimbela.com
                                    </p>
                                </div>
                            </div>
                        </div>
                        
                        <div style="margin-top: 30px; text-align: center;">
                            <p style="color: #6b7280; font-size: 14px;">
                                Don't let this stop your journey to becoming a seller. We're here to help you succeed!
                            </p>
                        </div>
                    </div>
                    
                    <div style="background: #1f2937; color: #9ca3af; padding: 30px; text-align: center; font-size: 12px;">
                        <div style="margin-bottom: 20px;">
                            <a href="{self.base_url}/privacy" style="color: #d1d5db; text-decoration: none; margin: 0 10px;">Privacy Policy</a> | 
                            <a href="{self.base_url}/terms" style="color: #d1d5db; text-decoration: none; margin: 0 10px;">Terms</a> | 
                            <a href="{self.base_url}/contact" style="color: #d1d5db; text-decoration: none; margin: 0 10px;">Contact</a>
                        </div>
                        <div style="opacity: 0.7;">
                            © {datetime.utcnow().year} Kimbela Marketplace
                            <br>This is an automated message. Please do not reply.
                        </div>
                    </div>
                </div>
            </body>
            </html>
            """

            text_body = f"""
            PAYMENT FAILED - KIMBELA MARKETPLACE
            
            Hello {user.full_name or user.first_name},
            
            We attempted to process your payment for the {plan.name} subscription, but the transaction was not successful.
            
            PAYMENT DETAILS:
            ----------------
            Plan: {plan.name}
            Amount: ${marketplace_payment.amount:.2f} {marketplace_payment.currency}
            Reference: {marketplace_payment.gateway_reference}
            Status: FAILED
            
            {f'Error Reason: {error_reason}' if error_reason else ''}
            
            RETRY YOUR PAYMENT:
            -------------------
            You can retry your payment here: {self.base_url}/become-seller
            
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
            
            © {datetime.utcnow().year} Kimbela Marketplace
            This is an automated message.
            """

            return self._send_email(subject, user.email, html_body, text_body)

        except Exception as e:
            logger.error(f"Failed to create failure email: {str(e)}")
            return False
