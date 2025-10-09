#!/usr/bin/env python3
"""
Authentication system initialization script

This script:
1. Initializes the database
2. Creates the default admin user (user500)
3. Tests basic authentication functionality
"""
import sys
from database import init_db, get_db_context
from auth import create_admin_user, login_user, generate_jwt_token, validate_jwt_token


def main():
    """Initialize authentication system"""
    print("=" * 60)
    print("Ninox2Git Authentication System Initialization")
    print("=" * 60)
    print()

    # Initialize database
    print("1. Initializing database...")
    try:
        init_db()
    except Exception as e:
        print(f"   Error initializing database: {e}")
        return 1

    # Create admin user
    print("\n2. Creating default admin user...")
    try:
        with get_db_context() as db:
            admin_user = create_admin_user(db)
            print(f"   Username: {admin_user.username}")
            print(f"   Email: {admin_user.email}")
            print(f"   Is Admin: {admin_user.is_admin}")
            print(f"   Is Active: {admin_user.is_active}")
    except Exception as e:
        print(f"   Error creating admin user: {e}")
        return 1

    # Test authentication
    print("\n3. Testing authentication...")
    try:
        with get_db_context() as db:
            user, token = login_user(
                db=db,
                username_or_email='user500',
                password='Quaternion1234____',
                ip_address='127.0.0.1',
                user_agent='Init Script'
            )
            print(f"   Login successful for user: {user.username}")
            print(f"   JWT token generated (length: {len(token)} characters)")

            # Validate token
            payload = validate_jwt_token(token)
            print(f"   Token validated successfully")
            print(f"   Token payload: user_id={payload['user_id']}, is_admin={payload['is_admin']}")
    except Exception as e:
        print(f"   Error testing authentication: {e}")
        return 1

    print("\n" + "=" * 60)
    print("Authentication system initialized successfully!")
    print("=" * 60)
    print("\nDefault Admin Credentials:")
    print("  Username: user500")
    print("  Password: Quaternion1234____")
    print("\nIMPORTANT: Change the admin password after first login!")
    print("=" * 60)

    return 0


if __name__ == '__main__':
    sys.exit(main())
