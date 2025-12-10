"""
Ninox2Git Web Application
Main NiceGUI application entry point with authentication and routing
"""
import os
import logging
import asyncio
from typing import Optional
from nicegui import app, ui
from contextlib import asynccontextmanager

from .database import init_db, get_db
from .auth import create_admin_user, get_user_from_token, InvalidTokenError
from .ui import login, dashboard, servers, teams, sync, admin, profile, cronjobs, json_viewer, code_viewer, yaml_code_viewer, changes
from .services.cronjob_scheduler import get_scheduler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Application configuration
APP_TITLE = "Ninox2Git"
APP_PORT = int(os.getenv('APP_PORT', '8765'))
APP_HOST = os.getenv('APP_HOST', '0.0.0.0')

# Session storage key for JWT token
SESSION_TOKEN_KEY = 'jwt_token'


def get_current_user():
    """
    Get current authenticated user from session token

    Returns:
        User object if authenticated, None otherwise
    """
    token = app.storage.user.get(SESSION_TOKEN_KEY)
    if not token:
        return None

    try:
        db = get_db()
        user = get_user_from_token(db, token)
        db.close()
        return user
    except (InvalidTokenError, Exception) as e:
        logger.warning(f"Invalid token in session: {e}")
        app.storage.user.pop(SESSION_TOKEN_KEY, None)
        return None


def require_auth():
    """
    Middleware to require authentication
    Redirects to login if not authenticated

    Returns:
        User object if authenticated, None if not authenticated
    """
    user = get_current_user()
    if not user:
        ui.navigate.to('/login')
        return None
    return user


def require_admin():
    """
    Middleware to require admin privileges
    Redirects to dashboard if not admin

    Returns:
        User object if authenticated and admin
    """
    user = require_auth()
    if user and not user.is_admin:
        ui.notify('Admin privileges required', type='negative')
        ui.navigate.to('/dashboard')
        return None
    return user


@ui.page('/')
def index():
    """Root page - redirect to sync or login"""
    user = get_current_user()
    if user:
        ui.navigate.to('/sync')
    else:
        ui.navigate.to('/login')
    return None


@ui.page('/login')
def login_page():
    """Login and registration page"""
    user = get_current_user()
    if user:
        ui.navigate.to('/dashboard')
        return None

    login.render()
    return None


@ui.page('/dashboard')
def dashboard_page():
    """Main dashboard page"""
    # Check authentication BEFORE rendering anything
    token = app.storage.user.get(SESSION_TOKEN_KEY)
    logger.debug(f"Dashboard access - token present: {bool(token)}, length: {len(token) if token else 0}")
    
    if not token:
        logger.warning("Dashboard access denied: no token in session - redirecting to login")
        ui.navigate.to('/login')
        return None

    try:
        db = get_db()
        user = get_user_from_token(db, token)
        db.close()
        logger.debug(f"Dashboard access granted for user: {user.username if user else 'None'}")
    except Exception as e:
        logger.error(f"Auth error on dashboard: {e}")
        app.storage.user.pop(SESSION_TOKEN_KEY, None)
        ui.navigate.to('/login')
        return None

    # Only render if we have a valid user
    dashboard.render(user)
    return None


@ui.page('/servers')
def servers_page():
    """Server management page"""
    # Check authentication BEFORE rendering anything
    token = app.storage.user.get(SESSION_TOKEN_KEY)
    if not token:
        ui.navigate.to('/login')
        return None

    try:
        db = get_db()
        user = get_user_from_token(db, token)
        db.close()
    except Exception as e:
        logger.error(f"Auth error: {e}")
        app.storage.user.pop(SESSION_TOKEN_KEY, None)
        ui.navigate.to('/login')
        return None

    servers.render(user)
    return None


@ui.page('/teams')
def teams_page():
    """Team management page"""
    token = app.storage.user.get(SESSION_TOKEN_KEY)
    if not token:
        ui.navigate.to('/login')
        return None

    try:
        db = get_db()
        user = get_user_from_token(db, token)
        db.close()
    except Exception as e:
        logger.error(f"Auth error: {e}")
        app.storage.user.pop(SESSION_TOKEN_KEY, None)
        ui.navigate.to('/login')
        return None

    teams.render(user)
    return None


@ui.page('/sync')
def sync_page(server: int = None, team: int = None):
    """Synchronization page with optional server and team parameters"""
    token = app.storage.user.get(SESSION_TOKEN_KEY)
    if not token:
        ui.navigate.to('/login')
        return None

    try:
        db = get_db()
        user = get_user_from_token(db, token)
        db.close()
    except Exception as e:
        logger.error(f"Auth error: {e}")
        app.storage.user.pop(SESSION_TOKEN_KEY, None)
        ui.navigate.to('/login')
        return None

    # Pass server and team parameters to render function
    sync.render(user, server_id_param=server, team_id_param=team)
    return None


@ui.page('/admin')
def admin_page():
    """Admin panel page - admin only"""
    token = app.storage.user.get(SESSION_TOKEN_KEY)
    if not token:
        ui.navigate.to('/login')
        return None

    try:
        db = get_db()
        user = get_user_from_token(db, token)
        db.close()

        # Additional admin check
        if not user.is_admin:
            ui.notify('Admin privileges required', type='negative')
            ui.navigate.to('/dashboard')
            return None
    except Exception as e:
        logger.error(f"Auth error: {e}")
        app.storage.user.pop(SESSION_TOKEN_KEY, None)
        ui.navigate.to('/login')
        return None

    admin.render(user)
    return None


@ui.page('/profile')
def profile_page():
    """User profile page"""
    token = app.storage.user.get(SESSION_TOKEN_KEY)
    if not token:
        ui.navigate.to('/login')
        return None

    try:
        db = get_db()
        user = get_user_from_token(db, token)
        db.close()
    except Exception as e:
        logger.error(f"Auth error: {e}")
        app.storage.user.pop(SESSION_TOKEN_KEY, None)
        ui.navigate.to('/login')
        return None

    profile.render(user)
    return None


@ui.page('/cronjobs')
def cronjobs_page():
    """Cronjob management page"""
    token = app.storage.user.get(SESSION_TOKEN_KEY)
    if not token:
        ui.navigate.to('/login')
        return None

    try:
        db = get_db()
        user = get_user_from_token(db, token)
        db.close()
    except Exception as e:
        logger.error(f"Auth error: {e}")
        app.storage.user.pop(SESSION_TOKEN_KEY, None)
        ui.navigate.to('/login')
        return None

    cronjobs.render(user)
    return None


@ui.page('/json-viewer')
def json_viewer_page():
    """JSON Viewer page"""
    token = app.storage.user.get(SESSION_TOKEN_KEY)
    if not token:
        ui.navigate.to('/login')
        return None

    try:
        db = get_db()
        user = get_user_from_token(db, token)
        db.close()
    except Exception as e:
        logger.error(f"Auth error: {e}")
        app.storage.user.pop(SESSION_TOKEN_KEY, None)
        ui.navigate.to('/login')
        return None

    json_viewer.render(user)
    return None


@ui.page('/code-viewer')
def code_viewer_page():
    """Ninox Code Viewer page"""
    token = app.storage.user.get(SESSION_TOKEN_KEY)
    if not token:
        ui.navigate.to('/login')
        return None

    try:
        db = get_db()
        user = get_user_from_token(db, token)
        db.close()
    except Exception as e:
        logger.error(f"Auth error: {e}")
        app.storage.user.pop(SESSION_TOKEN_KEY, None)
        ui.navigate.to('/login')
        return None

    code_viewer.render(user)
    return None


@ui.page('/changes')
def changes_page():
    """Changes/Changelog page"""
    token = app.storage.user.get(SESSION_TOKEN_KEY)
    if not token:
        ui.navigate.to('/login')
        return None

    try:
        db = get_db()
        user = get_user_from_token(db, token)
        db.close()
    except Exception as e:
        logger.error(f"Auth error: {e}")
        app.storage.user.pop(SESSION_TOKEN_KEY, None)
        ui.navigate.to('/login')
        return None

    changes.render(user)
    return None


@ui.page('/yaml-code-viewer')
def yaml_code_viewer_page():
    """YAML Code Viewer page for ninox-dev-cli files"""
    token = app.storage.user.get(SESSION_TOKEN_KEY)
    if not token:
        ui.navigate.to('/login')
        return None

    try:
        db = get_db()
        user = get_user_from_token(db, token)
        db.close()
    except Exception as e:
        logger.error(f"Auth error: {e}")
        app.storage.user.pop(SESSION_TOKEN_KEY, None)
        ui.navigate.to('/login')
        return None

    yaml_code_viewer.render(user)
    return None


# ============================================================================
# OAuth Routes
# ============================================================================

@ui.page('/auth/google')
def google_auth_start():
    """Start Google OAuth flow - redirects to Google"""
    from .services.oauth_service import get_oauth_service
    # Google Drive removed - no longer used
    from starlette.responses import RedirectResponse
    
    oauth_service = get_oauth_service()
    if not oauth_service:
        ui.notify('Google OAuth ist nicht konfiguriert', type='negative')
        ui.navigate.to('/login')
        return None

    # Google Drive removed - no longer request Drive scopes
    include_drive = False

    # Generate auth URL and redirect
    auth_url, state = oauth_service.generate_auth_url(include_drive=include_drive)
    
    # Store state in session for validation
    app.storage.user['oauth_state'] = state
    
    # Show loading message and redirect via meta refresh
    with ui.column().classes('w-full h-screen items-center justify-center'):
        ui.spinner(size='xl')
        ui.label('Weiterleitung zu Google...').classes('text-h6 mt-4')
        # Use HTML meta refresh as fallback
        ui.html(f'<meta http-equiv="refresh" content="0;url={auth_url}">', sanitize=False)
    return None


@ui.page('/auth/google/callback')
def google_auth_callback():
    """Handle Google OAuth callback - shows processing page"""
    # Show a processing page that will handle the OAuth callback via JavaScript
    with ui.column().classes('w-full h-screen items-center justify-center'):
        ui.spinner(size='xl')
        ui.label('Anmeldung wird verarbeitet...').classes('text-h6 mt-4')
        
        # Process OAuth callback
        async def process_oauth():
            from .services.oauth_service import get_oauth_service, OAuthError
            from .auth import login_or_create_oauth_user, OAuthDomainNotAllowedError, InactiveUserError
            
            try:
                # Get query params via JavaScript
                result = await ui.run_javascript('''
                    const params = new URLSearchParams(window.location.search);
                    return {
                        code: params.get('code'),
                        state: params.get('state'),
                        error: params.get('error')
                    };
                ''', timeout=5.0)
                
                code = result.get('code') if result else None
                state = result.get('state') if result else None
                error = result.get('error') if result else None
                
                logger.info(f"OAuth callback - code: {'yes' if code else 'no'}, state: {state[:8] if state else 'none'}...")
                
                if error:
                    logger.error(f"OAuth error from Google: {error}")
                    ui.notify(f'Google Anmeldung fehlgeschlagen: {error}', type='negative')
                    ui.navigate.to('/login')
                    return None
                
                if not code:
                    logger.error("No authorization code in callback")
                    ui.notify('Keine Autorisierung erhalten', type='negative')
                    ui.navigate.to('/login')
                    return None
                
                oauth_service = get_oauth_service()
                if not oauth_service:
                    ui.notify('Google OAuth ist nicht konfiguriert', type='negative')
                    ui.navigate.to('/login')
                    return None
                
                # Validate state
                stored_state = app.storage.user.get('oauth_state')
                if state and stored_state and state != stored_state:
                    if not oauth_service.validate_state(state):
                        logger.error("OAuth state mismatch")
                        ui.notify('Sicherheitsfehler. Bitte erneut versuchen.', type='negative')
                        ui.navigate.to('/login')
                        return None
                
                app.storage.user.pop('oauth_state', None)
                
                # Exchange code for user info
                user_info = await oauth_service.authenticate(code)
                
                # Login or create user
                db = get_db()
                try:
                    user_dto, token = login_or_create_oauth_user(
                        db=db,
                        google_id=user_info.google_id,
                        email=user_info.email,
                        full_name=user_info.name,
                        avatar_url=user_info.picture,
                        refresh_token=user_info.refresh_token,
                    )
                    
                    app.storage.user[SESSION_TOKEN_KEY] = token
                    logger.info(f"OAuth login successful for {user_dto.email}")
                    
                    ui.notify(f'Willkommen, {user_dto.full_name or user_dto.username}!', type='positive')
                    ui.navigate.to('/dashboard')
                    
                finally:
                    db.close()
                    
            except OAuthDomainNotAllowedError as e:
                logger.warning(f"OAuth domain not allowed: {e}")
                ui.notify(str(e), type='negative')
                ui.navigate.to('/login')
            except InactiveUserError as e:
                logger.warning(f"OAuth inactive user: {e}")
                ui.notify(str(e), type='negative')
                ui.navigate.to('/login')
            except OAuthError as e:
                logger.error(f"OAuth error: {e}")
                ui.notify(f'Anmeldung fehlgeschlagen: {str(e)}', type='negative')
                ui.navigate.to('/login')
            except Exception as e:
                logger.error(f"Unexpected OAuth error: {e}")
                ui.notify('Ein unerwarteter Fehler ist aufgetreten', type='negative')
                ui.navigate.to('/login')
        
        # Start processing after page is connected
        ui.timer(0.1, process_oauth, once=True)
    return None


@ui.page('/logout')
def logout_page():
    """Logout and redirect to login"""
    from .auth import logout_user

    # Get user before clearing token
    user = get_current_user()

    # Clear session token
    app.storage.user.pop(SESSION_TOKEN_KEY, None)

    # Log the logout
    if user:
        try:
            db = get_db()
            logout_user(db, user.id)
            db.close()
        except Exception as e:
            logger.error(f"Error logging logout: {e}")

    ui.notify('Logged out successfully', type='positive')
    ui.navigate.to('/login')
    return None


def init_app():
    """Initialize the application"""
    try:
        # Initialize database
        logger.info("Initializing database...")
        init_db()

        # Create admin user if not exists
        logger.info("Checking for admin user...")
        db = get_db()
        create_admin_user(db)
        db.close()
        
        # Register VS Code Server API router
        try:
            from .api.vscode_proxy import router as vscode_router
            app.add_api_route("/api/vscode/open", vscode_router.routes[0].endpoint, methods=["GET"])
            app.add_api_route("/api/vscode/status", vscode_router.routes[1].endpoint, methods=["GET"])
            logger.info("VS Code Server API routes registered")
        except Exception as e:
            logger.warning(f"Could not register VS Code API routes: {e}")

        logger.info("Application initialized successfully")

    except Exception as e:
        logger.error(f"Error initializing application: {e}")
        raise


async def startup_scheduler():
    """Start the cronjob scheduler on app startup"""
    logger.info("🚀 Starting cronjob scheduler...")
    scheduler = get_scheduler()
    import asyncio
    asyncio.create_task(scheduler.start())
    logger.info("✓ Cronjob scheduler task created")


def main():
    """Main application entry point"""
    try:
        # Initialize application
        init_app()

        # Register startup handler for scheduler
        app.on_startup(startup_scheduler)

        # Configure NiceGUI
        ui.run(
            title=APP_TITLE,
            host=APP_HOST,
            port=APP_PORT,
            reload=False,  # Disabled to prevent connection loss during operations
            show=False,
            storage_secret=os.getenv('SESSION_SECRET', 'change-this-secret-in-production')
        )

    except KeyboardInterrupt:
        logger.info("Application stopped by user")
    except Exception as e:
        logger.error(f"Application error: {e}")
        raise


if __name__ in {"__main__", "__mp_main__"}:
    main()
