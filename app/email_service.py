"""
Email service for sending authentication-related emails

This module provides email functionality for:
- Password reset emails
- Welcome emails for new users
- Email templates with customization
"""
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from datetime import datetime
from .database import get_db
from .models.smtp_config import SmtpConfig
from .utils.encryption import get_encryption_manager


# Application URL for email links
APP_URL = os.getenv('APP_URL', 'http://localhost:8000')


def get_active_smtp_config():
    """
    Get active SMTP configuration from database
    Falls back to environment variables if no active config in database

    Returns:
        Dictionary with SMTP configuration
    """
    db = get_db()
    try:
        # Try to get active SMTP config from database
        smtp_config = db.query(SmtpConfig).filter(SmtpConfig.is_active == True).first()

        if smtp_config:
            # Decrypt password
            encryption = get_encryption_manager()
            password = encryption.decrypt(smtp_config.password_encrypted)

            return {
                'host': smtp_config.host,
                'port': smtp_config.port,
                'username': smtp_config.username,
                'password': password,
                'use_tls': smtp_config.use_tls,
                'use_ssl': smtp_config.use_ssl,
                'from_email': smtp_config.from_email,
                'from_name': smtp_config.from_name
            }
    finally:
        db.close()

    # Fall back to environment variables if no active config
    return {
        'host': os.getenv('SMTP_HOST', 'localhost'),
        'port': int(os.getenv('SMTP_PORT', '587')),
        'username': os.getenv('SMTP_USER', os.getenv('SMTP_USERNAME', '')),
        'password': os.getenv('SMTP_PASSWORD', ''),
        'use_tls': os.getenv('SMTP_USE_TLS', 'true').lower() == 'true',
        'use_ssl': False,
        'from_email': os.getenv('SMTP_FROM', os.getenv('SMTP_FROM_EMAIL', 'noreply@nx2git.local')),
        'from_name': os.getenv('SMTP_FROM_NAME', 'Ninox2Git')
    }


class EmailError(Exception):
    """Base exception for email errors"""
    pass


class SMTPConfigError(EmailError):
    """Raised when SMTP configuration is invalid"""
    pass


def create_email_message(
    to_email: str,
    subject: str,
    html_body: str,
    text_body: Optional[str] = None,
    from_email: Optional[str] = None,
    from_name: Optional[str] = None
) -> MIMEMultipart:
    """
    Create email message with HTML and optional text body

    Args:
        to_email: Recipient email address
        subject: Email subject
        html_body: HTML email body
        text_body: Plain text email body (optional)
        from_email: Sender email (uses active SMTP config if not provided)
        from_name: Sender name (uses active SMTP config if not provided)

    Returns:
        MIMEMultipart email message
    """
    # Get active SMTP config for defaults
    smtp_config = get_active_smtp_config()

    message = MIMEMultipart('alternative')
    message['Subject'] = subject
    message['From'] = f'{from_name or smtp_config["from_name"]} <{from_email or smtp_config["from_email"]}>'
    message['To'] = to_email

    # Add text part if provided
    if text_body:
        text_part = MIMEText(text_body, 'plain')
        message.attach(text_part)

    # Add HTML part
    html_part = MIMEText(html_body, 'html')
    message.attach(html_part)

    return message


def send_email(
    to_email: str,
    subject: str,
    html_body: str,
    text_body: Optional[str] = None,
    from_email: Optional[str] = None,
    from_name: Optional[str] = None
) -> bool:
    """
    Send email via SMTP

    Args:
        to_email: Recipient email address
        subject: Email subject
        html_body: HTML email body
        text_body: Plain text email body (optional)
        from_email: Sender email (uses active SMTP config if not provided)
        from_name: Sender name (uses active SMTP config if not provided)

    Returns:
        True if email sent successfully, False otherwise

    Raises:
        EmailError: If email sending fails
        SMTPConfigError: If SMTP configuration is invalid
    """
    try:
        # Get active SMTP configuration
        smtp_config = get_active_smtp_config()

        # Create message
        message = create_email_message(
            to_email=to_email,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            from_email=from_email,
            from_name=from_name
        )

        # Connect to SMTP server
        if smtp_config['use_ssl']:
            server = smtplib.SMTP_SSL(smtp_config['host'], smtp_config['port'])
        else:
            server = smtplib.SMTP(smtp_config['host'], smtp_config['port'])
            if smtp_config['use_tls']:
                server.starttls()

        # Login if credentials provided
        if smtp_config['username'] and smtp_config['password']:
            server.login(smtp_config['username'], smtp_config['password'])

        # Send email
        server.send_message(message)
        server.quit()

        return True

    except smtplib.SMTPAuthenticationError as e:
        raise SMTPConfigError(f"SMTP authentication failed: {str(e)}")
    except smtplib.SMTPException as e:
        raise EmailError(f"Failed to send email: {str(e)}")
    except Exception as e:
        raise EmailError(f"Unexpected error sending email: {str(e)}")


def get_email_base_template(content: str, title: str = "Ninox2Git") -> str:
    """
    Get base HTML email template

    Args:
        content: HTML content to insert into template
        title: Email title

    Returns:
        Complete HTML email template
    """
    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            background-color: #f4f4f4;
            margin: 0;
            padding: 0;
        }}
        .container {{
            max-width: 600px;
            margin: 20px auto;
            background-color: #ffffff;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .header {{
            background-color: #2563eb;
            color: #ffffff;
            padding: 30px;
            text-align: center;
        }}
        .header h1 {{
            margin: 0;
            font-size: 24px;
            font-weight: 600;
        }}
        .content {{
            padding: 30px;
        }}
        .button {{
            display: inline-block;
            padding: 12px 24px;
            background-color: #2563eb;
            color: #ffffff;
            text-decoration: none;
            border-radius: 5px;
            font-weight: 500;
            margin: 20px 0;
        }}
        .button:hover {{
            background-color: #1d4ed8;
        }}
        .footer {{
            background-color: #f8f9fa;
            padding: 20px 30px;
            text-align: center;
            font-size: 14px;
            color: #6c757d;
            border-top: 1px solid #e9ecef;
        }}
        .alert {{
            background-color: #fef3c7;
            border-left: 4px solid #f59e0b;
            padding: 12px;
            margin: 20px 0;
        }}
        code {{
            background-color: #f1f5f9;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: 'Courier New', monospace;
            font-size: 14px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{title}</h1>
        </div>
        <div class="content">
            {content}
        </div>
        <div class="footer">
            <p>&copy; {datetime.utcnow().year} Ninox2Git. All rights reserved.</p>
            <p>This is an automated email. Please do not reply to this message.</p>
        </div>
    </div>
</body>
</html>
"""


def send_password_reset_email(
    to_email: str,
    username: str,
    reset_token: str,
    expires_hours: int = 24
) -> bool:
    """
    Send password reset email to user

    Args:
        to_email: User's email address
        username: User's username
        reset_token: Password reset token
        expires_hours: Token expiration time in hours

    Returns:
        True if email sent successfully, False otherwise

    Raises:
        EmailError: If email sending fails
    """
    # Create reset URL
    reset_url = f"{APP_URL}/reset-password?token={reset_token}"

    # HTML content
    html_content = f"""
        <h2>Password Reset Request</h2>
        <p>Hello <strong>{username}</strong>,</p>
        <p>We received a request to reset the password for your Ninox2Git account.</p>
        <p>Click the button below to reset your password:</p>
        <p style="text-align: center;">
            <a href="{reset_url}" class="button">Reset Password</a>
        </p>
        <p>Or copy and paste this link into your browser:</p>
        <p><code>{reset_url}</code></p>
        <div class="alert">
            <strong>Security Notice:</strong>
            <ul style="margin: 10px 0; padding-left: 20px;">
                <li>This link will expire in {expires_hours} hours</li>
                <li>If you didn't request this reset, please ignore this email</li>
                <li>Your password will not be changed until you complete the reset process</li>
            </ul>
        </div>
    """

    # Plain text content
    text_content = f"""
Password Reset Request

Hello {username},

We received a request to reset the password for your Ninox2Git account.

Click the link below to reset your password:
{reset_url}

Security Notice:
- This link will expire in {expires_hours} hours
- If you didn't request this reset, please ignore this email
- Your password will not be changed until you complete the reset process

---
© {datetime.utcnow().year} Ninox2Git. All rights reserved.
This is an automated email. Please do not reply to this message.
"""

    # Create complete HTML email
    html_body = get_email_base_template(html_content, "Password Reset - Ninox2Git")

    # Send email
    return send_email(
        to_email=to_email,
        subject="Reset Your Ninox2Git Password",
        html_body=html_body,
        text_body=text_content
    )


def send_welcome_email(
    to_email: str,
    username: str,
    full_name: Optional[str] = None
) -> bool:
    """
    Send welcome email to newly registered user

    Args:
        to_email: User's email address
        username: User's username
        full_name: User's full name (optional)

    Returns:
        True if email sent successfully, False otherwise

    Raises:
        EmailError: If email sending fails
    """
    # Use full name if available, otherwise username
    display_name = full_name or username

    # HTML content
    html_content = f"""
        <h2>Welcome to Ninox2Git!</h2>
        <p>Hello <strong>{display_name}</strong>,</p>
        <p>Thank you for registering with Ninox2Git! Your account has been successfully created.</p>

        <h3>Account Details:</h3>
        <ul>
            <li><strong>Username:</strong> {username}</li>
            <li><strong>Email:</strong> {to_email}</li>
        </ul>

        <h3>Getting Started:</h3>
        <p>Ninox2Git helps you synchronize your Ninox databases with Git repositories for version control and backup.</p>
        <ul>
            <li>Connect your Ninox servers</li>
            <li>Configure database synchronization</li>
            <li>Set up automated Git backups</li>
            <li>Track changes and collaborate with your team</li>
        </ul>

        <p style="text-align: center;">
            <a href="{APP_URL}/login" class="button">Login to Your Account</a>
        </p>

        <div class="alert">
            <strong>Security Tip:</strong> Keep your password secure and never share it with anyone.
        </div>

        <p>If you have any questions or need assistance, please don't hesitate to contact our support team.</p>
        <p>Happy syncing!</p>
    """

    # Plain text content
    text_content = f"""
Welcome to Ninox2Git!

Hello {display_name},

Thank you for registering with Ninox2Git! Your account has been successfully created.

Account Details:
- Username: {username}
- Email: {to_email}

Getting Started:
Ninox2Git helps you synchronize your Ninox databases with Git repositories for version control and backup.

- Connect your Ninox servers
- Configure database synchronization
- Set up automated Git backups
- Track changes and collaborate with your team

Login to your account: {APP_URL}/login

Security Tip: Keep your password secure and never share it with anyone.

If you have any questions or need assistance, please don't hesitate to contact our support team.

Happy syncing!

---
© {datetime.utcnow().year} Ninox2Git. All rights reserved.
This is an automated email. Please do not reply to this message.
"""

    # Create complete HTML email
    html_body = get_email_base_template(html_content, "Welcome to Ninox2Git!")

    # Send email
    return send_email(
        to_email=to_email,
        subject="Welcome to Ninox2Git!",
        html_body=html_body,
        text_body=text_content
    )


def send_password_changed_email(
    to_email: str,
    username: str
) -> bool:
    """
    Send notification email when password is changed

    Args:
        to_email: User's email address
        username: User's username

    Returns:
        True if email sent successfully, False otherwise

    Raises:
        EmailError: If email sending fails
    """
    # HTML content
    html_content = f"""
        <h2>Password Changed</h2>
        <p>Hello <strong>{username}</strong>,</p>
        <p>This email confirms that your Ninox2Git account password has been successfully changed.</p>

        <p><strong>Change Time:</strong> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}</p>

        <div class="alert">
            <strong>Didn't make this change?</strong><br>
            If you did not change your password, please contact support immediately and secure your account.
        </div>

        <p>For your security, here are some best practices:</p>
        <ul>
            <li>Use a strong, unique password</li>
            <li>Don't share your password with anyone</li>
            <li>Enable two-factor authentication if available</li>
            <li>Regularly update your password</li>
        </ul>
    """

    # Plain text content
    text_content = f"""
Password Changed

Hello {username},

This email confirms that your Ninox2Git account password has been successfully changed.

Change Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}

Didn't make this change?
If you did not change your password, please contact support immediately and secure your account.

For your security, here are some best practices:
- Use a strong, unique password
- Don't share your password with anyone
- Enable two-factor authentication if available
- Regularly update your password

---
© {datetime.utcnow().year} Ninox2Git. All rights reserved.
This is an automated email. Please do not reply to this message.
"""

    # Create complete HTML email
    html_body = get_email_base_template(html_content, "Password Changed - Ninox2Git")

    # Send email
    return send_email(
        to_email=to_email,
        subject="Your Ninox2Git Password Has Been Changed",
        html_body=html_body,
        text_body=text_content
    )


def send_account_deactivated_email(
    to_email: str,
    username: str,
    admin_username: str
) -> bool:
    """
    Send notification email when account is deactivated

    Args:
        to_email: User's email address
        username: User's username
        admin_username: Username of admin who deactivated the account

    Returns:
        True if email sent successfully, False otherwise

    Raises:
        EmailError: If email sending fails
    """
    # HTML content
    html_content = f"""
        <h2>Account Deactivated</h2>
        <p>Hello <strong>{username}</strong>,</p>
        <p>Your Ninox2Git account has been deactivated by an administrator.</p>

        <p><strong>Deactivated By:</strong> {admin_username}</p>
        <p><strong>Deactivation Time:</strong> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}</p>

        <div class="alert">
            <strong>What this means:</strong><br>
            You will no longer be able to log in to your account until it is reactivated by an administrator.
        </div>

        <p>If you believe this was done in error or have questions, please contact your system administrator.</p>
    """

    # Plain text content
    text_content = f"""
Account Deactivated

Hello {username},

Your Ninox2Git account has been deactivated by an administrator.

Deactivated By: {admin_username}
Deactivation Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}

What this means:
You will no longer be able to log in to your account until it is reactivated by an administrator.

If you believe this was done in error or have questions, please contact your system administrator.

---
© {datetime.utcnow().year} Ninox2Git. All rights reserved.
This is an automated email. Please do not reply to this message.
"""

    # Create complete HTML email
    html_body = get_email_base_template(html_content, "Account Deactivated - Ninox2Git")

    # Send email
    return send_email(
        to_email=to_email,
        subject="Your Ninox2Git Account Has Been Deactivated",
        html_body=html_body,
        text_body=text_content
    )


def test_smtp_connection() -> tuple[bool, str]:
    """
    Test SMTP connection and configuration

    Returns:
        Tuple of (success, message)
    """
    try:
        # Get active SMTP configuration
        smtp_config = get_active_smtp_config()

        # Connect to SMTP server
        if smtp_config['use_ssl']:
            server = smtplib.SMTP_SSL(smtp_config['host'], smtp_config['port'], timeout=10)
        else:
            server = smtplib.SMTP(smtp_config['host'], smtp_config['port'], timeout=10)
            if smtp_config['use_tls']:
                server.starttls()

        # Login if credentials provided
        if smtp_config['username'] and smtp_config['password']:
            server.login(smtp_config['username'], smtp_config['password'])
            server.quit()
            return True, f"SMTP connection successful (authenticated) - {smtp_config['host']}:{smtp_config['port']}"
        else:
            server.quit()
            return True, f"SMTP connection successful (no authentication) - {smtp_config['host']}:{smtp_config['port']}"

    except smtplib.SMTPAuthenticationError as e:
        return False, f"SMTP authentication failed: {str(e)}"
    except smtplib.SMTPException as e:
        return False, f"SMTP error: {str(e)}"
    except Exception as e:
        return False, f"Connection error: {str(e)}"
