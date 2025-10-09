"""
Authentication System Usage Examples

This file demonstrates how to use the authentication system in your application.
"""
from database import get_db_context
from auth import (
    register_user,
    login_user,
    logout_user,
    get_user_from_token,
    generate_password_reset_token,
    reset_password,
    change_password,
    create_admin_user,
    deactivate_user,
    activate_user,
    UserExistsError,
    InvalidCredentialsError,
    InvalidTokenError,
    InactiveUserError
)
from email_service import (
    send_welcome_email,
    send_password_reset_email,
    send_password_changed_email,
    test_smtp_connection
)


def example_user_registration():
    """Example: Register a new user"""
    print("\n--- User Registration Example ---")

    with get_db_context() as db:
        try:
            # Register new user
            user = register_user(
                db=db,
                username='johndoe',
                email='john@example.com',
                password='SecurePass123!',
                full_name='John Doe',
                ip_address='192.168.1.100',
                user_agent='Mozilla/5.0'
            )

            print(f"User registered successfully!")
            print(f"  ID: {user.id}")
            print(f"  Username: {user.username}")
            print(f"  Email: {user.email}")
            print(f"  Full Name: {user.full_name}")

            # Send welcome email (optional)
            try:
                send_welcome_email(
                    to_email=user.email,
                    username=user.username,
                    full_name=user.full_name
                )
                print(f"  Welcome email sent to {user.email}")
            except Exception as e:
                print(f"  Warning: Could not send welcome email: {e}")

        except UserExistsError as e:
            print(f"Registration failed: {e}")
        except ValueError as e:
            print(f"Validation failed: {e}")


def example_user_login():
    """Example: User login and JWT token generation"""
    print("\n--- User Login Example ---")

    with get_db_context() as db:
        try:
            # Login with username or email
            user, token = login_user(
                db=db,
                username_or_email='johndoe',  # Can also use email
                password='SecurePass123!',
                ip_address='192.168.1.100',
                user_agent='Mozilla/5.0'
            )

            print(f"Login successful!")
            print(f"  User: {user.username}")
            print(f"  Last Login: {user.last_login}")
            print(f"  JWT Token: {token[:50]}...")  # Show first 50 chars
            print(f"\nStore this token and send it with subsequent requests")

            return token

        except InvalidCredentialsError as e:
            print(f"Login failed: {e}")
        except InactiveUserError as e:
            print(f"Account inactive: {e}")


def example_validate_token(token: str):
    """Example: Validate JWT token and get user"""
    print("\n--- Token Validation Example ---")

    with get_db_context() as db:
        try:
            # Get user from token
            user = get_user_from_token(db, token)

            print(f"Token validated successfully!")
            print(f"  User ID: {user.id}")
            print(f"  Username: {user.username}")
            print(f"  Email: {user.email}")
            print(f"  Is Admin: {user.is_admin}")

            return user

        except InvalidTokenError as e:
            print(f"Token validation failed: {e}")
        except InactiveUserError as e:
            print(f"User account inactive: {e}")


def example_password_reset():
    """Example: Password reset flow"""
    print("\n--- Password Reset Example ---")

    with get_db_context() as db:
        try:
            # Step 1: User requests password reset
            user, reset_token = generate_password_reset_token(
                db=db,
                email='john@example.com',
                ip_address='192.168.1.100',
                user_agent='Mozilla/5.0'
            )

            print(f"Password reset requested for {user.email}")
            print(f"  Reset token: {reset_token[:20]}...")

            # Send password reset email
            try:
                send_password_reset_email(
                    to_email=user.email,
                    username=user.username,
                    reset_token=reset_token,
                    expires_hours=24
                )
                print(f"  Reset email sent to {user.email}")
            except Exception as e:
                print(f"  Warning: Could not send reset email: {e}")

            # Step 2: User uses reset token to set new password
            print("\n  User clicks link in email and enters new password...")

            user = reset_password(
                db=db,
                token=reset_token,
                new_password='NewSecurePass456!',
                ip_address='192.168.1.100',
                user_agent='Mozilla/5.0'
            )

            print(f"  Password reset successful for {user.username}")

            # Send confirmation email
            try:
                send_password_changed_email(
                    to_email=user.email,
                    username=user.username
                )
                print(f"  Confirmation email sent to {user.email}")
            except Exception as e:
                print(f"  Warning: Could not send confirmation email: {e}")

        except Exception as e:
            print(f"Password reset failed: {e}")


def example_change_password():
    """Example: Change password (requires current password)"""
    print("\n--- Change Password Example ---")

    with get_db_context() as db:
        try:
            # User must provide current password
            user = change_password(
                db=db,
                user_id=1,  # User's ID from session/token
                current_password='NewSecurePass456!',
                new_password='AnotherPass789!',
                ip_address='192.168.1.100',
                user_agent='Mozilla/5.0'
            )

            print(f"Password changed successfully for {user.username}")

            # Send notification email
            try:
                send_password_changed_email(
                    to_email=user.email,
                    username=user.username
                )
                print(f"  Notification email sent to {user.email}")
            except Exception as e:
                print(f"  Warning: Could not send notification email: {e}")

        except InvalidCredentialsError as e:
            print(f"Password change failed: {e}")
        except ValueError as e:
            print(f"Validation failed: {e}")


def example_user_logout(user_id: int):
    """Example: User logout"""
    print("\n--- User Logout Example ---")

    with get_db_context() as db:
        logout_user(
            db=db,
            user_id=user_id,
            ip_address='192.168.1.100',
            user_agent='Mozilla/5.0'
        )

        print(f"User logged out successfully")
        print(f"  Audit log entry created")
        print(f"  Client should delete the JWT token")


def example_admin_operations():
    """Example: Admin operations"""
    print("\n--- Admin Operations Example ---")

    with get_db_context() as db:
        # Create admin user if doesn't exist
        admin_user = create_admin_user(db)
        print(f"Admin user: {admin_user.username}")

        # Admin deactivates a user
        try:
            user = deactivate_user(
                db=db,
                user_id=2,  # Target user ID
                admin_user_id=admin_user.id,
                ip_address='192.168.1.1',
                user_agent='Admin Console'
            )
            print(f"  User {user.username} deactivated")
        except Exception as e:
            print(f"  Deactivation failed: {e}")

        # Admin reactivates a user
        try:
            user = activate_user(
                db=db,
                user_id=2,  # Target user ID
                admin_user_id=admin_user.id,
                ip_address='192.168.1.1',
                user_agent='Admin Console'
            )
            print(f"  User {user.username} activated")
        except Exception as e:
            print(f"  Activation failed: {e}")


def example_email_test():
    """Example: Test SMTP configuration"""
    print("\n--- Email Service Test ---")

    success, message = test_smtp_connection()
    if success:
        print(f"Email service configured correctly")
        print(f"  {message}")
    else:
        print(f"Email service configuration issue:")
        print(f"  {message}")
        print(f"\nPlease check your SMTP environment variables:")
        print(f"  SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD")


def run_all_examples():
    """Run all examples (for demonstration)"""
    print("\n" + "=" * 60)
    print("Authentication System Examples")
    print("=" * 60)

    # Test email configuration first
    example_email_test()

    # Run examples
    example_user_registration()

    token = example_user_login()

    if token:
        user = example_validate_token(token)

        if user:
            example_password_reset()
            example_change_password()
            example_user_logout(user.id)

    example_admin_operations()

    print("\n" + "=" * 60)
    print("Examples completed!")
    print("=" * 60)


if __name__ == '__main__':
    run_all_examples()
