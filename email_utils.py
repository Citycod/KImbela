# email_utils.py
import os
from flask import render_template_string, url_for
import resend
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Initialize Resend
resend.api_key = os.getenv("RESEND_API_KEY", "")


class EmailService:
    """Service for sending emails via Resend"""

    @staticmethod
    def send_email(to_email, subject, html_content, text_content=None, from_email=None):
        """
        Send email using Resend
        """
        try:
            if not resend.api_key:
                logger.warning("Resend API key not configured. Email not sent.")
                return False

            from_address = from_email or os.getenv(
                "MAIL_DEFAULT_SENDER", "noreply@resend.dev"
            )

            # Ensure from_email has proper format
            if "@" not in from_address:
                from_address = f"{from_address} <noreply@resend.dev>"
            elif "<" not in from_address:
                # If it's just an email, add a default name
                from_address = f"Kimbela <{from_address}>"

            # Ensure to_email is a list
            if isinstance(to_email, str):
                to_email = [to_email]

            params = {
                "from": from_address,
                "to": to_email,
                "subject": subject,
                "html": html_content,
            }

            if text_content:
                params["text"] = text_content

            response = resend.Emails.send(params)
            logger.info(
                f"Email sent successfully to {to_email}: {response.get('id', 'No ID')}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {str(e)}")
            return False

    @staticmethod
    def send_welcome_email(user, otp=None):
        """Send welcome/verification email"""
        if otp:
            subject = "Welcome to Kimbela - Verify Your Email"
            html = render_template_string(
                """
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
                    .container { max-width: 600px; margin: 0 auto; padding: 20px; }
                    .header { background-color: #4F46E5; color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }
                    .content { padding: 30px; background-color: #f9f9f9; border-radius: 0 0 10px 10px; }
                    .otp-code { 
                        font-size: 32px; 
                        font-weight: bold; 
                        color: #4F46E5; 
                        letter-spacing: 10px;
                        text-align: center;
                        margin: 20px 0;
                        padding: 15px;
                        background: #f0f0f0;
                        border-radius: 5px;
                    }
                    .button {
                        display: inline-block;
                        background-color: #4F46E5;
                        color: white;
                        padding: 12px 30px;
                        text-decoration: none;
                        border-radius: 5px;
                        font-weight: bold;
                        margin: 20px 0;
                    }
                    .footer { 
                        margin-top: 30px; 
                        padding-top: 20px; 
                        border-top: 1px solid #ddd; 
                        color: #666; 
                        font-size: 12px; 
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>Welcome to Kimbela! 🎉</h1>
                        <p>Your journey to meaningful connections starts here</p>
                    </div>
                    <div class="content">
                        <h2>Hello {{ user.first_name }},</h2>
                        <p>Thank you for joining Kimbela! We're excited to have you as part of our community.</p>

                        <p>To complete your registration, please use the verification code below:</p>

                        <div class="otp-code">{{ otp }}</div>

                        <p>This code will expire in 1 hour.</p>

                        <p>If you didn't create an account with Kimbela, please ignore this email.</p>

                        <p>Best regards,<br>
                        <strong>The Kimbela Team</strong></p>
                    </div>
                    <div class="footer">
                        <p>© 2024 Kimbela. All rights reserved.</p>
                        <p>This email was sent to {{ user.email }} because you registered on Kimbela.</p>
                    </div>
                </div>
            </body>
            </html>
            """,
                user=user,
                otp=otp,
            )

            text_content = f"""
            Welcome to Kimbela, {user.first_name}!

            Thank you for joining Kimbela! We're excited to have you as part of our community.

            Your verification code is: {otp}

            This code will expire in 1 hour.

            If you didn't create an account with Kimbela, please ignore this email.

            Best regards,
            The Kimbela Team
            """
        else:
            subject = "Welcome to Kimbela!"
            html = render_template_string(
                """
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
                    .container { max-width: 600px; margin: 0 auto; padding: 20px; }
                    .header { background-color: #4F46E5; color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }
                    .content { padding: 30px; background-color: #f9f9f9; border-radius: 0 0 10px 10px; }
                    .button {
                        display: inline-block;
                        background-color: #4F46E5;
                        color: white;
                        padding: 12px 30px;
                        text-decoration: none;
                        border-radius: 5px;
                        font-weight: bold;
                        margin: 20px 0;
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>Welcome to Kimbela! 🎉</h1>
                    </div>
                    <div class="content">
                        <h2>Hello {{ user.first_name }},</h2>
                        <p>Your email has been successfully verified! Welcome to the Kimbela community.</p>

                        <p>Get started by:</p>
                        <ul>
                            <li>Completing your profile</li>
                            <li>Exploring potential matches</li>
                            <li>Joining interesting groups</li>
                            <li>Connecting with like-minded people</li>
                        </ul>

                        <a href="https://yourdomain.com/dashboard" class="button">Go to Dashboard</a>

                        <p>If you have any questions, feel free to reach out to our support team.</p>

                        <p>Best regards,<br>
                        <strong>The Kimbela Team</strong></p>
                    </div>
                </div>
            </body>
            </html>
            """,
                user=user,
            )

            text_content = f"""
            Welcome to Kimbela, {user.first_name}!

            Your email has been successfully verified! Welcome to the Kimbela community.

            Get started by:
            - Completing your profile
            - Exploring potential matches
            - Joining interesting groups
            - Connecting with like-minded people

            Login: https://yourdomain.com/login

            Best regards,
            The Kimbela Team
            """

        return EmailService.send_email(
            to_email=user.email,
            subject=subject,
            html_content=html,
            text_content=text_content,
        )

    @staticmethod
    def send_password_reset_email(user, reset_token, reset_url):
        """Send password reset email"""
        subject = "Reset Your Kimbela Password"
        html = render_template_string(
            """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
                .container { max-width: 600px; margin: 0 auto; padding: 20px; }
                .header { background-color: #4F46E5; color: white; padding: 20px; text-align: center; }
                .content { padding: 30px; background-color: #f9f9f9; }
                .button {
                    display: inline-block;
                    background-color: #4F46E5;
                    color: white;
                    padding: 12px 30px;
                    text-decoration: none;
                    border-radius: 5px;
                    font-weight: bold;
                }
                .warning {
                    color: #ff6b6b;
                    font-weight: bold;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>Password Reset Request</h2>
                </div>
                <div class="content">
                    <h3>Hello {{ user.first_name }},</h3>

                    <p>We received a request to reset your password for your Kimbela account.</p>

                    <p>Click the button below to reset your password:</p>

                    <p>
                        <a href="{{ reset_url }}" class="button">Reset Password</a>
                    </p>

                    <p>Or copy and paste this link in your browser:<br>
                    <small>{{ reset_url }}</small></p>

                    <p class="warning">This link will expire in 1 hour.</p>

                    <p>If you didn't request a password reset, please ignore this email.</p>

                    <p>Best regards,<br>
                    <strong>The Kimbela Team</strong></p>
                </div>
            </div>
        </body>
        </html>
        """,
            user=user,
            reset_url=reset_url,
        )

        text_content = f"""
        Password Reset Request

        Hello {user.first_name},

        We received a request to reset your password for your Kimbela account.

        Reset your password by visiting: {reset_url}

        This link will expire in 1 hour.

        If you didn't request a password reset, please ignore this email.

        Best regards,
        The Kimbela Team
        """

        return EmailService.send_email(
            to_email=user.email,
            subject=subject,
            html_content=html,
            text_content=text_content,
        )

    @staticmethod
    def send_password_reset_success_email(user):
        """Send password reset confirmation email"""
        subject = "Your Kimbela Password Has Been Reset"
        html = render_template_string(
            """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
                .container { max-width: 600px; margin: 0 auto; padding: 20px; }
                .header { background-color: #28a745; color: white; padding: 20px; text-align: center; }
                .content { padding: 30px; background-color: #f9f9f9; }
                .info-box {
                    background-color: #e7f3ff;
                    border-left: 4px solid #4F46E5;
                    padding: 15px;
                    margin: 20px 0;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>✅ Password Reset Successful</h2>
                </div>
                <div class="content">
                    <h3>Hello {{ user.first_name }},</h3>

                    <p>Your Kimbela password has been successfully reset.</p>

                    <div class="info-box">
                        <p><strong>Security Notice:</strong> If you did not initiate this password reset, 
                        please contact our support team immediately.</p>
                    </div>

                    <p>You can now login with your new password:</p>
                    <p><a href="https://yourdomain.com/login">Login to Kimbela</a></p>

                    <p>For security reasons, we recommend that you:</p>
                    <ul>
                        <li>Use a strong, unique password</li>
                        <li>Enable two-factor authentication if available</li>
                        <li>Avoid using the same password on multiple sites</li>
                    </ul>

                    <p>Best regards,<br>
                    <strong>The Kimbela Team</strong></p>
                </div>
            </div>
        </body>
        </html>
        """,
            user=user,
        )

        text_content = f"""
        Password Reset Successful

        Hello {user.first_name},

        Your Kimbela password has been successfully reset.

        Security Notice: If you did not initiate this password reset, please contact our support team immediately.

        You can now login with your new password: https://yourdomain.com/login

        For security reasons, we recommend that you:
        - Use a strong, unique password
        - Enable two-factor authentication if available
        - Avoid using the same password on multiple sites

        Best regards,
        The Kimbela Team
        """

        return EmailService.send_email(
            to_email=user.email,
            subject=subject,
            html_content=html,
            text_content=text_content,
        )

    @staticmethod
    def send_test_email(test_email):
        """Send test email"""
        subject = "🎉 Kimbela Email Test - Resend Service"

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .success {{ color: #28a745; font-weight: bold; }}
                .info {{ background: #f8f9fa; padding: 15px; border-radius: 5px; }}
            </style>
        </head>
        <body>
            <h1 class="success">✅ Kimbela Email Test - RESEND SERVICE</h1>
            <p>Hello!</p>
            <p>This is a test email from your Kimbela application using <strong>Resend</strong> service.</p>

            <div class="info">
                <p><strong>Resend Email Service Active</strong></p>
                <p>This email was sent via Resend's email delivery API.</p>
                <p>Timestamp: {datetime.utcnow()}</p>
                <p>Recipient: {test_email}</p>
            </div>

            <p>Your email functionality with Resend is working correctly!</p>

            <hr>
            <p><small>Kimbela Team</small></p>
        </body>
        </html>
        """

        text_content = f"""
        Kimbela Email Test - RESEND SERVICE

        Hello!

        This is a test email from your Kimbela application using Resend service.

        Resend Email Service Active
        This email was sent via Resend's email delivery API.
        Timestamp: {datetime.utcnow()}
        Recipient: {test_email}

        Your email functionality with Resend is working correctly!

        Kimbela Team
        """

        return EmailService.send_email(
            to_email=test_email,
            subject=subject,
            html_content=html,
            text_content=text_content,
        )
