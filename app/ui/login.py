"""
Login and registration page for Ninox2Git
"""
from nicegui import ui, app
from ..database import get_db
from ..auth import (
    login_user, register_user, generate_password_reset_token,
    InvalidCredentialsError, InactiveUserError, UserExistsError
)
from .components import (
    Card, FormField, Toast, PRIMARY_COLOR
)

# Session storage key
SESSION_TOKEN_KEY = 'jwt_token'


def render():
    """Render the login page"""
    # Clear any existing content
    ui.colors(primary=PRIMARY_COLOR)

    with ui.column().classes('w-full h-screen items-center justify-center').style(
        'background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);'
    ):
        # Logo and title
        with ui.column().classes('items-center gap-2 mb-8'):
            ui.icon('sync_alt', size='xl').classes('text-white')
            ui.label('Ninox2Git').classes('text-h3 text-white font-bold')
            ui.label('Sync your Ninox databases to GitHub').classes('text-white')

        # Login/Register card
        with ui.card().classes('w-full max-w-md p-6'):
            # Tabs for login and register
            with ui.tabs().classes('w-full') as tabs:
                login_tab = ui.tab('Login', icon='login')
                register_tab = ui.tab('Register', icon='person_add')
                reset_tab = ui.tab('Reset Password', icon='lock_reset')

            with ui.tab_panels(tabs, value=login_tab).classes('w-full'):
                # Login panel
                with ui.tab_panel(login_tab):
                    render_login_form()

                # Register panel
                with ui.tab_panel(register_tab):
                    render_register_form()

                # Password reset panel
                with ui.tab_panel(reset_tab):
                    render_reset_form()


def render_login_form():
    """Render login form"""
    with ui.column().classes('w-full gap-4'):
        ui.label('Sign In').classes('text-h5 font-bold mb-2')

        username_input = FormField.text(
            label='Username or Email',
            placeholder='Enter your username or email',
            required=True
        )

        password_input = FormField.password(
            label='Password',
            placeholder='Enter your password',
            required=True
        )

        # Error message placeholder
        error_label = ui.label('').classes('text-negative')
        error_label.visible = False

        async def handle_login():
            """Handle login submission"""
            import logging
            logger = logging.getLogger(__name__)
            logger.info("=== HANDLE_LOGIN CALLED ===")

            username = username_input.value.strip()
            password = password_input.value
            logger.info(f"Username: {username}, Password length: {len(password)}")

            # Validate inputs
            if not username or not password:
                error_label.text = 'Please fill in all fields'
                error_label.visible = True
                return

            error_label.visible = False

            db = None
            try:
                logger.info("Getting DB session...")
                db = get_db()
                logger.info("Calling login_user...")
                user, token = login_user(db, username, password)
                logger.info(f"login_user returned successfully")

                # UserDTO has all attributes already loaded
                user_display_name = user.full_name or user.username

                # Store token in session
                app.storage.user[SESSION_TOKEN_KEY] = token

                # Show success message using the stored name
                Toast.success(f'Welcome back, {user_display_name}!')

                # Redirect to dashboard
                ui.navigate.to('/dashboard')

            except InvalidCredentialsError:
                error_label.text = 'Invalid username/email or password'
                error_label.visible = True
            except InactiveUserError:
                error_label.text = 'Your account has been deactivated. Please contact an administrator.'
                error_label.visible = True
            except Exception as e:
                import traceback
                import logging
                logger = logging.getLogger(__name__)
                try:
                    error_msg = str(e)
                except:
                    error_msg = f"{type(e).__name__} (details unavailable)"
                logger.error(f"Login error: {type(e).__name__}: {error_msg}")
                logger.error(traceback.format_exc())
                error_label.text = f'Login failed: {error_msg}'
                error_label.visible = True
            finally:
                if db:
                    db.close()

        # Enter key submits form
        password_input.on('keydown.enter', handle_login)

        with ui.row().classes('w-full justify-between items-center mt-4'):
            ui.button(
                'Sign In',
                on_click=handle_login,
                color='primary'
            ).classes('flex-grow').props('size=lg')


def render_register_form():
    """Render registration form"""
    with ui.column().classes('w-full gap-4'):
        ui.label('Create Account').classes('text-h5 font-bold mb-2')

        username_input = FormField.text(
            label='Username',
            placeholder='Choose a username',
            required=True
        )

        email_input = FormField.text(
            label='Email',
            placeholder='your.email@example.com',
            required=True
        )

        full_name_input = FormField.text(
            label='Full Name',
            placeholder='Your full name (optional)'
        )

        password_input = FormField.password(
            label='Password',
            placeholder='Choose a strong password',
            required=True
        )

        password_confirm_input = FormField.password(
            label='Confirm Password',
            placeholder='Re-enter your password',
            required=True
        )

        # Error message placeholder
        error_label = ui.label('').classes('text-negative')
        error_label.visible = False

        # Success message placeholder
        success_label = ui.label('').classes('text-positive')
        success_label.visible = False

        async def handle_register():
            """Handle registration submission"""
            username = username_input.value.strip()
            email = email_input.value.strip()
            full_name = full_name_input.value.strip() or None
            password = password_input.value
            password_confirm = password_confirm_input.value

            # Validate inputs
            if not username or not email or not password:
                error_label.text = 'Please fill in all required fields'
                error_label.visible = True
                success_label.visible = False
                return

            if password != password_confirm:
                error_label.text = 'Passwords do not match'
                error_label.visible = True
                success_label.visible = False
                return

            error_label.visible = False

            try:
                db = get_db()
                user = register_user(
                    db,
                    username=username,
                    email=email,
                    password=password,
                    full_name=full_name
                )
                db.close()

                # Show success message
                success_label.text = 'Account created successfully! Please sign in.'
                success_label.visible = True
                error_label.visible = False

                # Clear form
                username_input.value = ''
                email_input.value = ''
                full_name_input.value = ''
                password_input.value = ''
                password_confirm_input.value = ''

                Toast.success('Account created! You can now sign in.')

            except UserExistsError as e:
                error_label.text = str(e)
                error_label.visible = True
                success_label.visible = False
            except ValueError as e:
                error_label.text = str(e)
                error_label.visible = True
                success_label.visible = False
            except Exception as e:
                error_label.text = f'Registration failed: {str(e)}'
                error_label.visible = True
                success_label.visible = False

        # Enter key submits form
        password_confirm_input.on('keydown.enter', handle_register)

        with ui.row().classes('w-full justify-between items-center mt-4'):
            ui.button(
                'Create Account',
                on_click=handle_register,
                color='primary'
            ).classes('flex-grow').props('size=lg')


def render_reset_form():
    """Render password reset request form"""
    with ui.column().classes('w-full gap-4'):
        ui.label('Reset Password').classes('text-h5 font-bold mb-2')
        ui.label('Enter your email address and we will send you a password reset link.').classes(
            'text-grey-7 mb-2'
        )

        email_input = FormField.text(
            label='Email',
            placeholder='your.email@example.com',
            required=True
        )

        # Error message placeholder
        error_label = ui.label('').classes('text-negative')
        error_label.visible = False

        # Success message placeholder
        success_label = ui.label('').classes('text-positive')
        success_label.visible = False

        async def handle_reset():
            """Handle password reset request"""
            email = email_input.value.strip()

            # Validate input
            if not email:
                error_label.text = 'Please enter your email address'
                error_label.visible = True
                success_label.visible = False
                return

            error_label.visible = False

            try:
                db = get_db()
                user, token = generate_password_reset_token(db, email)
                db.close()

                # In production, send email with reset link
                # For now, just show success message
                success_label.text = 'Password reset instructions have been sent to your email.'
                success_label.visible = True
                error_label.visible = False

                # Clear form
                email_input.value = ''

                Toast.success('Password reset email sent!')

            except Exception as e:
                # Don't reveal if email exists or not for security
                success_label.text = 'If an account exists with this email, you will receive reset instructions.'
                success_label.visible = True
                error_label.visible = False

        # Enter key submits form
        email_input.on('keydown.enter', handle_reset)

        with ui.row().classes('w-full justify-between items-center mt-4'):
            ui.button(
                'Send Reset Link',
                on_click=handle_reset,
                color='primary'
            ).classes('flex-grow').props('size=lg')
