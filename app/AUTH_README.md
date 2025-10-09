# Ninox2Git Authentication System

Complete JWT-based authentication system with email notifications, password management, and audit logging.

## Features

### Core Authentication
- **Password Hashing**: Secure bcrypt-based password hashing
- **JWT Tokens**: Stateless authentication with configurable expiration
- **User Registration**: Email validation and secure password requirements
- **Login/Logout**: Session management with audit logging
- **Password Reset**: Secure token-based password recovery
- **Password Change**: Authenticated password updates

### Security Features
- **Bcrypt Password Hashing**: Industry-standard password security
- **JWT Token Validation**: Secure token generation and verification
- **Audit Logging**: Complete tracking of all authentication events
- **Email Validation**: RFC-compliant email address validation
- **Password Strength Requirements**: Enforced secure password policies
- **Account Activation/Deactivation**: Admin-controlled user access

### Email Notifications
- **Welcome Emails**: Sent on successful registration
- **Password Reset Emails**: Secure reset links with expiration
- **Password Changed Notifications**: Security alerts for password changes
- **Account Deactivation Notices**: Admin action notifications

## Files

### `/home/nx2git-go/webapp/app/auth.py`
Complete authentication module with:
- Password hashing and verification (bcrypt)
- JWT token generation and validation
- User registration with validation
- Login/logout functionality
- Password reset token generation
- Password management (reset/change)
- Audit logging for all actions
- Admin user creation and management

### `/home/nx2git-go/webapp/app/email_service.py`
Email service module with:
- SMTP configuration from environment
- HTML email templates
- Password reset emails
- Welcome emails
- Password changed notifications
- Account status notifications
- SMTP connection testing

### `/home/nx2git-go/webapp/app/init_auth.py`
Initialization script that:
- Creates database tables
- Creates default admin user
- Tests authentication functionality

### `/home/nx2git-go/webapp/app/auth_examples.py`
Comprehensive usage examples demonstrating:
- User registration
- Login/logout flows
- Token validation
- Password reset process
- Password change
- Admin operations

## Environment Variables

### JWT Configuration
```bash
JWT_SECRET_KEY=your-secret-key-change-in-production
JWT_ALGORITHM=HS256
JWT_EXPIRATION_HOURS=24
```

### SMTP Configuration
```bash
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_USE_TLS=true
SMTP_FROM_EMAIL=noreply@nx2git.local
SMTP_FROM_NAME=Ninox2Git
```

### Application Configuration
```bash
APP_URL=http://localhost:8000
DATABASE_URL=postgresql://nx2git:changeme@postgres:5432/nx2git
```

## Default Admin User

The system includes a default admin user for initial setup:

- **Username**: `user500`
- **Password**: `Quaternion1234____`
- **Email**: `admin@nx2git.local`
- **Role**: Administrator

**IMPORTANT**: Change this password immediately after first login!

## Installation & Setup

### 1. Install Dependencies
All required dependencies are already in `/home/nx2git-go/webapp/requirements.txt`:
```bash
cd /home/nx2git-go/webapp
pip install -r requirements.txt
```

Key dependencies:
- `PyJWT>=2.8.0` - JWT token handling
- `bcrypt>=4.1.0` - Password hashing
- `sqlalchemy>=2.0.0` - Database ORM
- `email-validator>=2.1.0` - Email validation

### 2. Configure Environment
Create a `.env` file in `/home/nx2git-go/webapp/`:
```bash
# JWT Settings
JWT_SECRET_KEY=generate-a-secure-random-key-here
JWT_ALGORITHM=HS256
JWT_EXPIRATION_HOURS=24

# SMTP Settings
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_USE_TLS=true
SMTP_FROM_EMAIL=noreply@yourdomain.com
SMTP_FROM_NAME=Ninox2Git

# Application
APP_URL=https://yourdomain.com
DATABASE_URL=postgresql://user:password@host:5432/database
```

### 3. Initialize Database
```bash
cd /home/nx2git-go/webapp/app
python init_auth.py
```

This will:
- Create all database tables
- Create the default admin user
- Test authentication functionality

### 4. Test Email Service
```python
from email_service import test_smtp_connection

success, message = test_smtp_connection()
print(f"SMTP Test: {message}")
```

## Usage Examples

### User Registration
```python
from database import get_db_context
from auth import register_user
from email_service import send_welcome_email

with get_db_context() as db:
    user = register_user(
        db=db,
        username='johndoe',
        email='john@example.com',
        password='SecurePass123!',
        full_name='John Doe',
        ip_address='192.168.1.100',
        user_agent='Mozilla/5.0'
    )

    # Send welcome email
    send_welcome_email(
        to_email=user.email,
        username=user.username,
        full_name=user.full_name
    )
```

### User Login
```python
from database import get_db_context
from auth import login_user

with get_db_context() as db:
    user, token = login_user(
        db=db,
        username_or_email='johndoe',
        password='SecurePass123!',
        ip_address='192.168.1.100',
        user_agent='Mozilla/5.0'
    )

    # Store token in session/cookie
    print(f"JWT Token: {token}")
```

### Validate Token & Get User
```python
from database import get_db_context
from auth import get_user_from_token

with get_db_context() as db:
    user = get_user_from_token(db, token)
    print(f"Authenticated as: {user.username}")
```

### Password Reset Flow
```python
from database import get_db_context
from auth import generate_password_reset_token, reset_password
from email_service import send_password_reset_email

# Step 1: User requests password reset
with get_db_context() as db:
    user, reset_token = generate_password_reset_token(
        db=db,
        email='john@example.com'
    )

    # Send reset email
    send_password_reset_email(
        to_email=user.email,
        username=user.username,
        reset_token=reset_token
    )

# Step 2: User uses token to reset password
with get_db_context() as db:
    user = reset_password(
        db=db,
        token=reset_token,
        new_password='NewSecurePass456!'
    )
```

### Change Password
```python
from database import get_db_context
from auth import change_password

with get_db_context() as db:
    user = change_password(
        db=db,
        user_id=user.id,
        current_password='OldPassword123!',
        new_password='NewPassword456!',
        ip_address='192.168.1.100'
    )
```

### Logout
```python
from database import get_db_context
from auth import logout_user

with get_db_context() as db:
    logout_user(
        db=db,
        user_id=user.id,
        ip_address='192.168.1.100'
    )
    # Client should delete JWT token
```

### Admin Operations
```python
from database import get_db_context
from auth import deactivate_user, activate_user

with get_db_context() as db:
    # Deactivate user
    user = deactivate_user(
        db=db,
        user_id=target_user_id,
        admin_user_id=admin_id
    )

    # Reactivate user
    user = activate_user(
        db=db,
        user_id=target_user_id,
        admin_user_id=admin_id
    )
```

## Password Requirements

Passwords must meet the following criteria:
- Minimum 8 characters
- At least one uppercase letter
- At least one lowercase letter
- At least one digit
- At least one special character (!@#$%^&*()_+-=[]{}; etc.)

## Username Requirements

Usernames must meet the following criteria:
- 3-50 characters
- Only alphanumeric, underscore, or hyphen
- Must start with alphanumeric character

## Email Validation

- RFC-compliant email validation using `email-validator` library
- Normalizes email addresses
- Checks for valid format and deliverability

## Audit Logging

All authentication events are logged in the `audit_logs` table:
- User registration
- Login attempts (successful and failed)
- Logout
- Password reset requests
- Password changes
- Account activation/deactivation
- Admin actions

Each audit log entry includes:
- User ID
- Action type
- Resource type and ID
- IP address
- User agent
- Timestamp
- Additional details

## Security Best Practices

### JWT Token Security
1. **Keep JWT_SECRET_KEY secure**: Never commit to version control
2. **Use environment variables**: Store secrets in environment, not code
3. **Set appropriate expiration**: Balance security and usability
4. **Use HTTPS**: Always transmit tokens over secure connections
5. **Store tokens securely**: Use httpOnly cookies or secure storage

### Password Security
1. **Enforce strong passwords**: System validates password strength
2. **Use bcrypt**: Industry-standard password hashing
3. **Never log passwords**: Passwords never appear in logs
4. **Rate limit login attempts**: Implement in your application layer
5. **Notify on password changes**: Automated email notifications

### SMTP Security
1. **Use TLS**: Always enable SMTP_USE_TLS=true
2. **App passwords**: Use app-specific passwords, not account passwords
3. **Secure credentials**: Store SMTP credentials in environment
4. **Test configuration**: Use test_smtp_connection() to verify setup

## Error Handling

The authentication system uses custom exceptions:

- `AuthError`: Base authentication error
- `InvalidCredentialsError`: Login failed
- `UserNotFoundError`: User doesn't exist
- `UserExistsError`: Registration failed (duplicate)
- `InvalidTokenError`: JWT or reset token invalid
- `InactiveUserError`: Account is deactivated

Example:
```python
from auth import login_user, InvalidCredentialsError, InactiveUserError

try:
    user, token = login_user(db, username, password)
except InvalidCredentialsError:
    # Handle wrong password
    pass
except InactiveUserError:
    # Handle deactivated account
    pass
```

## Testing

Run the examples to test all functionality:
```bash
cd /home/nx2git-go/webapp/app
python auth_examples.py
```

This will test:
- User registration
- Login/logout
- Token validation
- Password reset
- Password change
- Admin operations
- Email service

## Integration with NiceGUI

Example integration with NiceGUI web framework:

```python
from nicegui import ui, app
from database import get_db_context
from auth import login_user, get_user_from_token

@ui.page('/login')
def login_page():
    def handle_login():
        with get_db_context() as db:
            try:
                user, token = login_user(
                    db=db,
                    username_or_email=username.value,
                    password=password.value,
                    ip_address=app.storage.request.client.host
                )
                app.storage.user['token'] = token
                ui.navigate.to('/')
            except Exception as e:
                ui.notify(str(e), type='negative')

    with ui.card():
        username = ui.input('Username or Email')
        password = ui.input('Password', password=True)
        ui.button('Login', on_click=handle_login)

@ui.page('/')
def index():
    token = app.storage.user.get('token')
    if not token:
        ui.navigate.to('/login')
        return

    with get_db_context() as db:
        try:
            user = get_user_from_token(db, token)
            ui.label(f'Welcome, {user.username}!')
        except Exception:
            ui.navigate.to('/login')
```

## Database Schema

The authentication system uses these models:

### User Table (`users`)
- id (primary key)
- username (unique, indexed)
- email (unique, indexed)
- password_hash
- full_name
- is_active
- is_admin
- last_login
- created_at
- updated_at

### AuditLog Table (`audit_logs`)
- id (primary key)
- user_id (foreign key)
- action
- resource_type
- resource_id
- details
- ip_address
- user_agent
- created_at

### PasswordReset Table (`password_resets`)
- id (primary key)
- user_id (foreign key)
- token (unique, indexed)
- is_used
- created_at
- expires_at
- used_at

## Troubleshooting

### Email Not Sending
1. Check SMTP configuration in environment variables
2. Run `test_smtp_connection()` to diagnose issues
3. For Gmail: Enable "Less secure app access" or use App Passwords
4. Check firewall/network settings for SMTP port

### JWT Token Invalid
1. Verify JWT_SECRET_KEY is consistent across restarts
2. Check token expiration time
3. Ensure token is being transmitted correctly
4. Verify token format (should be three base64 segments separated by dots)

### Password Reset Not Working
1. Check token hasn't expired (24 hours default)
2. Verify token hasn't been used already
3. Check email delivery for reset link
4. Ensure APP_URL is correctly configured

## License

Part of the Ninox2Git project.
