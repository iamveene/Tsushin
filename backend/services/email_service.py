"""
Email Service
Phase 7.9: Email Notifications

Handles sending emails for invitations, password resets, and notifications.
Supports multiple providers (console logging for dev, SMTP, SendGrid, etc.)
"""

import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Dict, Any
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class EmailProvider(ABC):
    """Abstract base class for email providers."""

    @abstractmethod
    def send(
        self,
        to: str,
        subject: str,
        html_body: str,
        text_body: Optional[str] = None,
    ) -> bool:
        """Send an email. Returns True if successful."""
        pass


class ConsoleEmailProvider(EmailProvider):
    """Email provider that logs emails to console (for development)."""

    def send(
        self,
        to: str,
        subject: str,
        html_body: str,
        text_body: Optional[str] = None,
    ) -> bool:
        logger.info(f"\n{'='*50}")
        logger.info(f"EMAIL TO: {to}")
        logger.info(f"SUBJECT: {subject}")
        logger.info(f"{'='*50}")
        logger.info(text_body or html_body)
        logger.info(f"{'='*50}\n")
        print(f"\n[EMAIL] To: {to} | Subject: {subject}")
        return True


class SMTPEmailProvider(EmailProvider):
    """Email provider using SMTP."""

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        from_email: str,
        use_tls: bool = True,
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.from_email = from_email
        self.use_tls = use_tls

    def send(
        self,
        to: str,
        subject: str,
        html_body: str,
        text_body: Optional[str] = None,
    ) -> bool:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.from_email
            msg["To"] = to

            if text_body:
                msg.attach(MIMEText(text_body, "plain"))
            msg.attach(MIMEText(html_body, "html"))

            with smtplib.SMTP(self.host, self.port) as server:
                if self.use_tls:
                    server.starttls()
                server.login(self.username, self.password)
                server.sendmail(self.from_email, to, msg.as_string())

            logger.info(f"Email sent to {to}: {subject}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email to {to}: {e}")
            return False


class EmailService:
    """Main email service that uses configured provider."""

    def __init__(self, provider: Optional[EmailProvider] = None):
        """
        Initialize email service with a provider.

        If no provider is specified, uses ConsoleEmailProvider for development.
        In production, configure via environment variables.
        """
        if provider:
            self.provider = provider
        else:
            # Auto-configure based on environment
            smtp_host = os.getenv("SMTP_HOST")
            if smtp_host:
                self.provider = SMTPEmailProvider(
                    host=smtp_host,
                    port=int(os.getenv("SMTP_PORT", "587")),
                    username=os.getenv("SMTP_USERNAME", ""),
                    password=os.getenv("SMTP_PASSWORD", ""),
                    from_email=os.getenv("SMTP_FROM_EMAIL", "noreply@tsushin.io"),
                    use_tls=os.getenv("SMTP_USE_TLS", "true").lower() == "true",
                )
                logger.info("Email service configured with SMTP")
            else:
                self.provider = ConsoleEmailProvider()
                logger.info("Email service using console provider (development mode)")

        self.base_url = os.getenv("FRONTEND_URL", "http://localhost:3030")
        self.app_name = os.getenv("APP_NAME", "Tsushin")

    def send_invitation_email(
        self,
        to_email: str,
        inviter_name: str,
        tenant_name: str,
        role_name: str,
        invitation_token: str,
        personal_message: Optional[str] = None,
    ) -> bool:
        """Send an invitation email."""
        invitation_url = f"{self.base_url}/auth/invite/{invitation_token}"

        subject = f"{inviter_name} invited you to join {tenant_name} on {self.app_name}"

        html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ text-align: center; margin-bottom: 30px; }}
        .button {{
            display: inline-block;
            padding: 12px 24px;
            background-color: #2563eb;
            color: white;
            text-decoration: none;
            border-radius: 6px;
            margin: 20px 0;
        }}
        .footer {{ margin-top: 30px; font-size: 12px; color: #666; }}
        .message-box {{
            background-color: #f3f4f6;
            padding: 15px;
            border-radius: 6px;
            margin: 15px 0;
            font-style: italic;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{self.app_name}</h1>
        </div>

        <p>Hi there,</p>

        <p><strong>{inviter_name}</strong> has invited you to join
        <strong>{tenant_name}</strong> on {self.app_name} as a <strong>{role_name}</strong>.</p>

        {f'<div class="message-box">"{personal_message}"</div>' if personal_message else ''}

        <p>Click the button below to accept the invitation and create your account:</p>

        <p style="text-align: center;">
            <a href="{invitation_url}" class="button">Accept Invitation</a>
        </p>

        <p>Or copy and paste this link into your browser:</p>
        <p style="word-break: break-all;">{invitation_url}</p>

        <p>This invitation will expire in 7 days.</p>

        <div class="footer">
            <p>If you didn't expect this invitation, you can safely ignore this email.</p>
            <p>© {self.app_name}</p>
        </div>
    </div>
</body>
</html>
"""

        text_body = f"""
{inviter_name} invited you to join {tenant_name} on {self.app_name}

You've been invited to join {tenant_name} as a {role_name}.

{f'Personal message: "{personal_message}"' if personal_message else ''}

Accept the invitation here:
{invitation_url}

This invitation will expire in 7 days.

If you didn't expect this invitation, you can safely ignore this email.
"""

        return self.provider.send(to_email, subject, html_body, text_body)

    def send_password_reset_email(
        self,
        to_email: str,
        reset_token: str,
    ) -> bool:
        """Send a password reset email."""
        reset_url = f"{self.base_url}/auth/reset-password?token={reset_token}"

        subject = f"Reset your {self.app_name} password"

        html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ text-align: center; margin-bottom: 30px; }}
        .button {{
            display: inline-block;
            padding: 12px 24px;
            background-color: #2563eb;
            color: white;
            text-decoration: none;
            border-radius: 6px;
            margin: 20px 0;
        }}
        .footer {{ margin-top: 30px; font-size: 12px; color: #666; }}
        .warning {{ color: #dc2626; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{self.app_name}</h1>
        </div>

        <p>Hi,</p>

        <p>We received a request to reset your password for your {self.app_name} account.</p>

        <p>Click the button below to reset your password:</p>

        <p style="text-align: center;">
            <a href="{reset_url}" class="button">Reset Password</a>
        </p>

        <p>Or copy and paste this link into your browser:</p>
        <p style="word-break: break-all;">{reset_url}</p>

        <p class="warning">This link will expire in 24 hours.</p>

        <div class="footer">
            <p>If you didn't request a password reset, you can safely ignore this email.
            Your password will not be changed.</p>
            <p>© {self.app_name}</p>
        </div>
    </div>
</body>
</html>
"""

        text_body = f"""
Reset your {self.app_name} password

We received a request to reset your password for your {self.app_name} account.

Reset your password here:
{reset_url}

This link will expire in 24 hours.

If you didn't request a password reset, you can safely ignore this email.
Your password will not be changed.
"""

        return self.provider.send(to_email, subject, html_body, text_body)

    def send_welcome_email(
        self,
        to_email: str,
        full_name: str,
        tenant_name: str,
    ) -> bool:
        """Send a welcome email to new users."""
        subject = f"Welcome to {tenant_name} on {self.app_name}!"

        html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ text-align: center; margin-bottom: 30px; }}
        .button {{
            display: inline-block;
            padding: 12px 24px;
            background-color: #2563eb;
            color: white;
            text-decoration: none;
            border-radius: 6px;
            margin: 20px 0;
        }}
        .footer {{ margin-top: 30px; font-size: 12px; color: #666; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Welcome to {self.app_name}!</h1>
        </div>

        <p>Hi {full_name},</p>

        <p>Welcome to <strong>{tenant_name}</strong> on {self.app_name}!
        Your account has been created and you're ready to get started.</p>

        <p style="text-align: center;">
            <a href="{self.base_url}" class="button">Go to {self.app_name}</a>
        </p>

        <div class="footer">
            <p>© {self.app_name}</p>
        </div>
    </div>
</body>
</html>
"""

        text_body = f"""
Welcome to {self.app_name}!

Hi {full_name},

Welcome to {tenant_name} on {self.app_name}!
Your account has been created and you're ready to get started.

Visit {self.base_url} to get started.
"""

        return self.provider.send(to_email, subject, html_body, text_body)


# Singleton instance for easy access
_email_service: Optional[EmailService] = None


def get_email_service() -> EmailService:
    """Get the email service singleton."""
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service


def send_invitation(
    to_email: str,
    inviter_name: str,
    tenant_name: str,
    role_name: str,
    invitation_token: str,
    personal_message: Optional[str] = None,
) -> bool:
    """Convenience function to send invitation email."""
    return get_email_service().send_invitation_email(
        to_email, inviter_name, tenant_name, role_name, invitation_token, personal_message
    )


def send_password_reset(to_email: str, reset_token: str) -> bool:
    """Convenience function to send password reset email."""
    return get_email_service().send_password_reset_email(to_email, reset_token)
