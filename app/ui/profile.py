"""
User profile page for Ninox2Git
"""
from nicegui import ui
from ..database import get_db
from ..models.user import User
from ..auth import create_audit_log
from ..utils.encryption import get_encryption_manager
from .components import (
    NavHeader, Card, FormField, Toast, PRIMARY_COLOR
)


def render(user):
    """
    Render the user profile page

    Args:
        user: Current user object
    """
    ui.colors(primary=PRIMARY_COLOR)

    # Navigation header
    NavHeader(user, 'profile').render()

    # Main content
    with ui.column().classes('w-full p-6 gap-6').style('max-width: 1200px; margin: 0 auto;'):
        ui.label('User Profile').classes('text-h4 font-bold mb-4')

        with ui.tabs() as tabs:
            account_tab = ui.tab('Account')
            github_tab = ui.tab('GitHub')

        with ui.tab_panels(tabs, value=account_tab).classes('w-full'):
            # Account settings tab
            with ui.tab_panel(account_tab):
                render_account_settings(user)

            # GitHub configuration tab
            with ui.tab_panel(github_tab):
                render_github_settings(user)


def render_account_settings(user):
    """Render account settings section"""
    with Card('Account Information', 'account_circle'):
        # Read-only user info
        with ui.column().classes('gap-4'):
            with ui.row().classes('gap-4'):
                ui.label('Username:').classes('font-bold')
                ui.label(user.username)

            with ui.row().classes('gap-4'):
                ui.label('Email:').classes('font-bold')
                ui.label(user.email)

            with ui.row().classes('gap-4'):
                ui.label('Full Name:').classes('font-bold')
                ui.label(user.full_name or 'Not set')

            if user.last_login:
                with ui.row().classes('gap-4'):
                    ui.label('Last Login:').classes('font-bold')
                    ui.label(user.last_login.strftime('%Y-%m-%d %H:%M UTC'))

            if user.is_admin:
                ui.badge('Administrator', color='orange').classes('mt-2')


def render_github_settings(user):
    """Render GitHub configuration section"""
    # Get current GitHub configuration
    db = get_db()
    db_user = db.query(User).filter(User.id == user.id).first()

    # Decrypt GitHub token if exists
    encryption = get_encryption_manager()
    github_token = ''
    if db_user.github_token_encrypted:
        try:
            github_token = encryption.decrypt(db_user.github_token_encrypted)
        except:
            github_token = ''

    github_org = db_user.github_organization or ''
    github_repo = db_user.github_default_repo or ''
    db.close()

    with Card('GitHub Configuration', 'github'):
        ui.label(
            'Configure your GitHub integration for automatic synchronization of Ninox databases.'
        ).classes('text-grey-7 mb-4')

        with ui.column().classes('gap-4'):
            # GitHub Token input
            github_token_input = FormField.password(
                label='GitHub Personal Access Token',
                placeholder='ghp_xxxxxxxxxxxxxxxxxxxx'
            )
            if github_token:
                github_token_input.value = github_token

            ui.label(
                'Required scopes: repo (full control of private repositories)'
            ).classes('text-caption text-grey-6 -mt-2')

            # GitHub Organization input
            github_org_input = FormField.text(
                label='GitHub Organization',
                placeholder='your-organization',
                value=github_org
            )

            ui.label(
                'The GitHub organization or username where repositories will be created'
            ).classes('text-caption text-grey-6 -mt-2')

            # Default Repository Name input
            github_repo_input = FormField.text(
                label='Default Repository Name',
                placeholder='ninox-backup',
                value=github_repo
            )

            ui.label(
                'Default repository name for new Ninox database backups (can be overridden per team)'
            ).classes('text-caption text-grey-6 -mt-2')

            # Test connection button
            ui.button(
                'Test GitHub Connection',
                icon='cell_tower',
                on_click=lambda: test_github_connection(
                    github_token_input.value,
                    github_org_input.value
                )
            ).props('outline').classes('mt-2')

            # Error/success message
            message_label = ui.label('').classes('mt-2')
            message_label.visible = False

            # Save button
            async def save_github_config():
                """Save GitHub configuration"""
                token = github_token_input.value.strip()
                org = github_org_input.value.strip()
                repo = github_repo_input.value.strip()

                try:
                    db = get_db()
                    db_user = db.query(User).filter(User.id == user.id).first()

                    # Encrypt token if provided
                    if token:
                        encryption = get_encryption_manager()
                        db_user.github_token_encrypted = encryption.encrypt(token)
                    else:
                        db_user.github_token_encrypted = None

                    db_user.github_organization = org or None
                    db_user.github_default_repo = repo or None

                    db.commit()

                    # Create audit log
                    create_audit_log(
                        db=db,
                        user_id=user.id,
                        action='github_config_updated',
                        resource_type='user',
                        resource_id=user.id,
                        details='Updated GitHub configuration',
                        auto_commit=True
                    )

                    db.close()

                    Toast.success('GitHub configuration saved successfully!')

                    # Update message
                    message_label.text = 'Configuration saved successfully!'
                    message_label.classes('text-positive')
                    message_label.visible = True

                except Exception as e:
                    Toast.error(f'Error saving configuration: {str(e)}')
                    message_label.text = f'Error: {str(e)}'
                    message_label.classes('text-negative')
                    message_label.visible = True

            # Save button
            ui.button(
                'Save GitHub Configuration',
                icon='save',
                on_click=save_github_config
            ).props('color=primary').classes('mt-4')

        # Instructions section
        with ui.expansion('Setup Instructions', icon='info').classes('mt-4'):
            with ui.column().classes('gap-2 p-4'):
                ui.label('To set up GitHub integration:').classes('font-bold')
                ui.label('1. Create a GitHub Personal Access Token:')
                ui.label('   - Go to GitHub Settings > Developer settings > Personal access tokens')
                ui.label('   - Click "Generate new token (classic)"')
                ui.label('   - Select the "repo" scope for full repository access')
                ui.label('   - Copy the generated token')
                ui.label('2. Enter your GitHub organization or username')
                ui.label('3. Optionally set a default repository name')
                ui.label('4. Test the connection to verify everything works')
                ui.label('5. Save your configuration')


def test_github_connection(token: str, org: str):
    """Test GitHub connection with provided credentials"""
    if not token:
        Toast.warning('Please enter a GitHub token to test')
        return

    if not org:
        Toast.warning('Please enter a GitHub organization to test')
        return

    try:
        import requests

        # Test GitHub API with token
        headers = {
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github.v3+json'
        }

        # Check if we can access the org/user
        response = requests.get(
            f'https://api.github.com/users/{org}',
            headers=headers,
            timeout=10
        )

        if response.status_code == 200:
            # Also check if we have repo creation permissions
            user_response = requests.get(
                'https://api.github.com/user',
                headers=headers,
                timeout=10
            )

            if user_response.status_code == 200:
                user_data = user_response.json()
                Toast.success(f'GitHub connection successful! Authenticated as {user_data.get("login", "unknown")}')
            else:
                Toast.warning('GitHub token is valid but may have limited permissions')
        elif response.status_code == 404:
            Toast.error(f'GitHub organization/user "{org}" not found')
        elif response.status_code == 401:
            Toast.error('Invalid GitHub token')
        else:
            Toast.error(f'GitHub API error: {response.status_code}')

    except requests.exceptions.Timeout:
        Toast.error('GitHub connection timeout')
    except requests.exceptions.ConnectionError:
        Toast.error('Could not connect to GitHub')
    except Exception as e:
        Toast.error(f'Error testing connection: {str(e)}')