"""
Admin panel for Ninox2Git
"""
from nicegui import ui
from datetime import datetime
from ..database import get_db
from ..models.user import User
from ..models.server import Server
from ..models.team import Team
from ..models.database import Database
from ..models.audit_log import AuditLog
from ..models.ai_config import AIConfig, AIProvider, AVAILABLE_MODELS, DEFAULT_MODELS
from ..auth import (
    register_user, activate_user, deactivate_user, create_audit_log,
    UserExistsError
)
from ..utils.encryption import get_encryption_manager
from .components import (
    NavHeader, Card, FormField, Toast, ConfirmDialog,
    DataTable, StatusBadge, format_datetime, PRIMARY_COLOR,
    WARNING_COLOR, ERROR_COLOR, SUCCESS_COLOR
)


def render(user):
    """
    Render the admin panel page

    Args:
        user: Current user object (must be admin)
    """
    ui.colors(primary=PRIMARY_COLOR)

    # Navigation header
    NavHeader(user, 'admin').render()

    # Main content
    with ui.column().classes('w-full p-6 gap-6').style('max-width: 1400px; margin: 0 auto;'):
        ui.label('Admin Panel').classes('text-h4 font-bold mb-4')

        # Admin tabs
        with ui.tabs().classes('w-full') as tabs:
            overview_tab = ui.tab('Overview', icon='dashboard')
            users_tab = ui.tab('Users', icon='people')
            oauth_tab = ui.tab('OAuth', icon='login')
            ai_tab = ui.tab('KI-Konfiguration', icon='psychology')
            smtp_tab = ui.tab('SMTP Config', icon='email')
            audit_tab = ui.tab('Audit Logs', icon='receipt_long')
            stats_tab = ui.tab('Statistics', icon='analytics')

        with ui.tab_panels(tabs, value=overview_tab).classes('w-full'):
            # Overview panel
            with ui.tab_panel(overview_tab):
                render_overview(user)

            # Users panel
            with ui.tab_panel(users_tab):
                render_users_management(user)

            # OAuth Configuration panel
            with ui.tab_panel(oauth_tab):
                render_oauth_config(user)

            # AI Configuration panel
            with ui.tab_panel(ai_tab):
                render_ai_config(user)

            # SMTP Configuration panel
            with ui.tab_panel(smtp_tab):
                render_smtp_config(user)

            # Audit logs panel
            with ui.tab_panel(audit_tab):
                render_audit_logs(user)

            # Statistics panel
            with ui.tab_panel(stats_tab):
                render_statistics(user)


def render_oauth_config(user):
    """Render OAuth configuration panel"""
    from ..models.oauth_config import OAuthConfig
    
    encryption = get_encryption_manager()
    
    with ui.column().classes('w-full gap-4'):
        ui.label('OAuth Konfiguration').classes('text-h5 font-bold')
        ui.label(
            'Konfigurieren Sie Google Workspace OAuth für Single Sign-On. '
            'Benutzer können sich dann mit ihrem Google-Konto anmelden.'
        ).classes('text-grey-7 mb-4')
        
        # Instructions card
        with ui.card().classes('w-full p-4 bg-blue-50'):
            ui.label('Einrichtung in Google Cloud Console:').classes('font-bold mb-2')
            with ui.column().classes('gap-1 text-sm'):
                ui.label('1. Gehen Sie zu console.cloud.google.com')
                ui.label('2. Erstellen Sie ein neues Projekt oder wählen Sie ein bestehendes')
                ui.label('3. Aktivieren Sie "Google+ API" unter APIs & Services')
                ui.label('4. Erstellen Sie OAuth 2.0 Credentials unter "Credentials"')
                ui.label('5. Fügen Sie die Redirect URI hinzu (siehe unten)')
        
        # Config form
        config_container = ui.column().classes('w-full gap-4 mt-4')
        
        def load_config():
            """Load OAuth config"""
            config_container.clear()
            
            db = get_db()
            try:
                config = db.query(OAuthConfig).filter(OAuthConfig.provider == 'google').first()
                
                if not config:
                    # Create default config
                    config = OAuthConfig(
                        provider='google',
                        is_enabled=False,
                        auto_create_users=True,
                    )
                    db.add(config)
                    db.commit()
                
                # Decrypt client secret if exists
                client_secret_decrypted = ''
                if config.client_secret_encrypted:
                    try:
                        client_secret_decrypted = encryption.decrypt(config.client_secret_encrypted) or ''
                    except:
                        pass
                
                with config_container:
                    with ui.card().classes('w-full p-4'):
                        ui.label('Google OAuth').classes('text-h6 font-bold mb-4')
                        
                        # Enabled toggle
                        enabled_switch = ui.switch(
                            'OAuth aktiviert',
                            value=config.is_enabled
                        ).classes('mb-4')
                        
                        # Client ID
                        client_id_input = ui.input(
                            label='Client ID',
                            value=config.client_id or '',
                            placeholder='xxx.apps.googleusercontent.com'
                        ).classes('w-full mb-2')
                        
                        # Client Secret
                        client_secret_input = ui.input(
                            label='Client Secret',
                            value=client_secret_decrypted,
                            password=True,
                            password_toggle_button=True,
                            placeholder='Client Secret von Google'
                        ).classes('w-full mb-2')
                        
                        # Redirect URI (read-only)
                        import os
                        app_url = os.getenv('APP_URL', 'http://localhost:8765')
                        redirect_uri = f"{app_url}/auth/google/callback"
                        
                        ui.input(
                            label='Redirect URI (in Google Console eintragen)',
                            value=redirect_uri,
                        ).classes('w-full mb-2').props('readonly')
                        
                        # Allowed domains
                        allowed_domains_input = ui.input(
                            label='Erlaubte Domains (kommagetrennt, leer = alle erlaubt)',
                            value=config.allowed_domains or '',
                            placeholder='beispiel.de, firma.com'
                        ).classes('w-full mb-2')
                        
                        # Auto-create users
                        auto_create_switch = ui.switch(
                            'Neue Benutzer automatisch anlegen',
                            value=config.auto_create_users
                        ).classes('mb-4')
                        
                        ui.label(
                            'Wenn aktiviert, werden neue Benutzer automatisch angelegt, '
                            'wenn sie sich zum ersten Mal mit Google anmelden und ihre Domain erlaubt ist.'
                        ).classes('text-sm text-grey-6 mb-4')
                        
                        # Save button
                        async def save_config():
                            db = get_db()
                            try:
                                config = db.query(OAuthConfig).filter(OAuthConfig.provider == 'google').first()
                                
                                config.is_enabled = enabled_switch.value
                                config.client_id = client_id_input.value.strip() or None
                                
                                # Encrypt client secret if changed
                                new_secret = client_secret_input.value.strip()
                                if new_secret:
                                    config.client_secret_encrypted = encryption.encrypt(new_secret)
                                elif not client_secret_input.value:
                                    config.client_secret_encrypted = None
                                
                                config.allowed_domains = allowed_domains_input.value.strip() or None
                                config.auto_create_users = auto_create_switch.value
                                config.redirect_uri = redirect_uri
                                
                                db.commit()
                                
                                Toast.success('OAuth Konfiguration gespeichert!')
                                
                            except Exception as e:
                                Toast.error(f'Fehler beim Speichern: {str(e)}')
                            finally:
                                db.close()
                        
                        ui.button(
                            'Speichern',
                            on_click=save_config,
                            color='primary',
                            icon='save'
                        )
                
            finally:
                db.close()
        
        load_config()


def render_ai_config(user):
    """Render AI provider configuration"""
    encryption = get_encryption_manager()
    
    with ui.column().classes('w-full gap-4'):
        ui.label('KI-Konfiguration').classes('text-h5 font-bold')
        ui.label(
            'Konfigurieren Sie die KI-Provider für die automatische Änderungsanalyse. '
            'Die Beschreibungen werden auf Deutsch generiert.'
        ).classes('text-grey-7 mb-4')
        
        # Container for provider cards
        providers_container = ui.column().classes('w-full gap-4')
        
        def load_providers():
            """Load and display all provider configurations"""
            providers_container.clear()
            
            db = get_db()
            try:
                # Get or create default configurations
                configs = db.query(AIConfig).all()
                
                # Create missing provider configs
                existing_providers = {c.provider for c in configs}
                for provider in AIProvider:
                    if provider.value not in existing_providers:
                        new_config = AIConfig(
                            provider=provider.value,
                            model=DEFAULT_MODELS.get(provider, ''),
                            is_default=(provider == AIProvider.CLAUDE and not configs),
                            is_active=True,
                            max_tokens=1000,
                            temperature=0.3,
                        )
                        db.add(new_config)
                        configs.append(new_config)
                
                db.commit()
                
                # Refresh to get IDs
                configs = db.query(AIConfig).order_by(AIConfig.provider).all()
                
                with providers_container:
                    for config in configs:
                        render_provider_card(config, user, providers_container, load_providers)
                        
            finally:
                db.close()
        
        load_providers()


def render_provider_card(config: AIConfig, user, container, reload_callback):
    """Render a single provider configuration card"""
    encryption = get_encryption_manager()
    
    # Provider display info
    provider_info = {
        'claude': {'name': 'Claude (Anthropic)', 'icon': 'smart_toy', 'color': '#8B5CF6'},
        'openai': {'name': 'OpenAI', 'icon': 'auto_awesome', 'color': '#10A37F'},
        'gemini': {'name': 'Google Gemini', 'icon': 'stars', 'color': '#4285F4'},
    }
    
    info = provider_info.get(config.provider, {'name': config.provider, 'icon': 'psychology', 'color': PRIMARY_COLOR})
    
    border_style = f'border-left: 4px solid {info["color"]};'
    if config.is_default:
        border_style = f'border: 2px solid {info["color"]};'
    
    with ui.card().classes('w-full p-4').style(border_style):
        with ui.row().classes('w-full items-center justify-between'):
            # Provider info
            with ui.row().classes('items-center gap-3'):
                ui.icon(info['icon'], size='lg').style(f'color: {info["color"]};')
                with ui.column().classes('gap-1'):
                    with ui.row().classes('items-center gap-2'):
                        ui.label(info['name']).classes('text-h6 font-bold')
                        if config.is_default:
                            ui.badge('Standard', color='primary')
                        if not config.is_active:
                            ui.badge('Inaktiv', color='grey')
                    
                    # Status line
                    if config.is_configured:
                        if config.last_test_success is True:
                            ui.label('Verbunden').classes('text-positive text-sm')
                        elif config.last_test_success is False:
                            ui.label('Verbindungsfehler').classes('text-negative text-sm')
                        else:
                            ui.label('Konfiguriert (nicht getestet)').classes('text-warning text-sm')
                    else:
                        ui.label('Nicht konfiguriert').classes('text-grey-6 text-sm')
            
            # Actions
            with ui.row().classes('gap-2'):
                ui.button(
                    'Konfigurieren',
                    icon='settings',
                    on_click=lambda c=config: show_provider_config_dialog(c, user, reload_callback)
                ).props('flat dense')
                
                if config.is_configured:
                    ui.button(
                        'Testen',
                        icon='play_arrow',
                        on_click=lambda c=config: test_provider_connection(c, reload_callback)
                    ).props('flat dense color=primary')
                
                if not config.is_default and config.is_configured:
                    ui.button(
                        'Als Standard',
                        icon='star',
                        on_click=lambda c=config: set_default_provider(c, reload_callback)
                    ).props('flat dense color=warning')


def show_provider_config_dialog(config: AIConfig, user, reload_callback):
    """Show dialog to configure a provider"""
    encryption = get_encryption_manager()
    
    # Decrypt existing API key for display (masked)
    existing_key = ""
    if config.api_key_encrypted:
        try:
            existing_key = encryption.decrypt(config.api_key_encrypted)
        except Exception:
            existing_key = ""
    
    with ui.dialog() as dialog, ui.card().classes('w-full p-6').style('min-width: 500px;'):
        ui.label(f'{config.display_name} konfigurieren').classes('text-h5 font-bold mb-4')
        
        # API Key input
        api_key_input = ui.input(
            label='API-Key',
            placeholder='sk-...' if config.provider == 'openai' else 'API-Key eingeben',
            password=True,
            password_toggle_button=True,
            value=existing_key
        ).classes('w-full mb-2')
        
        if config.provider == 'claude':
            ui.label('Anthropic API-Key von console.anthropic.com').classes('text-caption text-grey-7 mb-4')
        elif config.provider == 'openai':
            ui.label('OpenAI API-Key von platform.openai.com').classes('text-caption text-grey-7 mb-4')
        elif config.provider == 'gemini':
            ui.label('Google AI API-Key von aistudio.google.com').classes('text-caption text-grey-7 mb-4')
        
        # Model selection
        model_options = AVAILABLE_MODELS.get(AIProvider(config.provider), [])
        model_select = ui.select(
            label='Modell',
            options=model_options,
            value=config.model if config.model in model_options else (model_options[0] if model_options else '')
        ).classes('w-full mb-4')
        
        # Advanced settings
        with ui.expansion('Erweiterte Einstellungen', icon='tune').classes('w-full mb-4'):
            with ui.column().classes('w-full gap-2 p-2'):
                max_tokens_input = ui.number(
                    label='Max Tokens',
                    value=config.max_tokens,
                    min=100,
                    max=4000,
                    step=100
                ).classes('w-full')
                
                temperature_input = ui.number(
                    label='Temperature',
                    value=config.temperature,
                    min=0.0,
                    max=1.0,
                    step=0.1,
                    format='%.1f'
                ).classes('w-full')
                
                is_active_switch = ui.switch(
                    'Provider aktiv',
                    value=config.is_active
                )
        
        error_label = ui.label('').classes('text-negative')
        error_label.visible = False
        
        async def save_config():
            """Save the provider configuration"""
            api_key = api_key_input.value.strip()
            model = model_select.value
            max_tokens = int(max_tokens_input.value) if max_tokens_input.value else 1000
            temperature = float(temperature_input.value) if temperature_input.value else 0.3
            is_active = is_active_switch.value
            
            if not api_key:
                error_label.text = 'Bitte geben Sie einen API-Key ein'
                error_label.visible = True
                return
            
            if not model:
                error_label.text = 'Bitte wählen Sie ein Modell aus'
                error_label.visible = True
                return
            
            db = get_db()
            try:
                # Reload config to avoid stale data
                db_config = db.query(AIConfig).filter(AIConfig.id == config.id).first()
                if not db_config:
                    error_label.text = 'Konfiguration nicht gefunden'
                    error_label.visible = True
                    return
                
                # Encrypt and save API key
                db_config.api_key_encrypted = encryption.encrypt(api_key)
                db_config.model = model
                db_config.max_tokens = max_tokens
                db_config.temperature = temperature
                db_config.is_active = is_active
                db_config.last_test_success = None  # Reset test status
                db_config.last_test_at = None
                
                db.commit()
                
                Toast.success(f'{config.display_name} wurde konfiguriert')
                dialog.close()
                reload_callback()
                
            except Exception as e:
                error_label.text = f'Fehler beim Speichern: {str(e)}'
                error_label.visible = True
            finally:
                db.close()
        
        with ui.row().classes('w-full justify-end gap-2 mt-4'):
            ui.button('Abbrechen', on_click=dialog.close).props('flat')
            ui.button('Speichern', on_click=save_config, color='primary')
    
    dialog.open()


def test_provider_connection(config: AIConfig, reload_callback):
    """Show dialog to test provider connection with optional question"""
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    from ..services.ai_changelog import get_ai_changelog_service
    
    encryption = get_encryption_manager()
    
    # Decrypt API key
    try:
        api_key = encryption.decrypt(config.api_key_encrypted)
    except Exception:
        Toast.error('API-Key konnte nicht entschlüsselt werden')
        return
    
    # Provider info for display
    provider_info = {
        'claude': {'name': 'Claude (Anthropic)', 'icon': 'smart_toy', 'color': '#8B5CF6'},
        'openai': {'name': 'OpenAI', 'icon': 'auto_awesome', 'color': '#10A37F'},
        'gemini': {'name': 'Google Gemini', 'icon': 'stars', 'color': '#4285F4'},
    }
    info = provider_info.get(config.provider, {'name': config.provider, 'icon': 'psychology', 'color': PRIMARY_COLOR})
    
    with ui.dialog() as dialog, ui.card().classes('w-full p-6').style('min-width: 600px; max-width: 800px;'):
        with ui.row().classes('w-full items-center gap-3 mb-4'):
            ui.icon(info['icon'], size='lg').style(f'color: {info["color"]};')
            ui.label(f'{info["name"]} testen').classes('text-h5 font-bold')
        
        ui.label(f'Modell: {config.model}').classes('text-grey-7 mb-4')
        
        # Status container
        status_container = ui.column().classes('w-full gap-2 mb-4')
        
        # Question input
        ui.label('Testfrage (optional):').classes('font-bold')
        question_input = ui.textarea(
            placeholder='Stelle eine Frage an die KI, z.B. "Was ist 2+2?" oder "Erkläre mir kurz was Python ist."',
            value='Was ist die Hauptstadt von Deutschland?'
        ).classes('w-full').props('outlined rows=2')
        
        # Answer container (initially hidden)
        answer_container = ui.column().classes('w-full gap-2 mt-4')
        answer_container.visible = False
        
        # Button reference for disabling during test
        test_button = None
        
        def do_api_call(service, provider, key, model, question):
            """Blocking API call to run in thread pool"""
            if question:
                return service.ask_question(
                    provider_name=provider,
                    api_key=key,
                    model=model,
                    question=question,
                    max_tokens=500,
                    temperature=0.7
                )
            else:
                result = service.test_provider(provider, key, model)
                result['answer'] = ''
                return result
        
        async def run_test():
            """Run the connection test in background thread"""
            nonlocal test_button
            
            status_container.clear()
            answer_container.clear()
            answer_container.visible = False
            
            # Disable button during test
            if test_button:
                test_button.disable()
            
            with status_container:
                with ui.row().classes('items-center gap-2'):
                    ui.spinner(size='sm')
                    ui.label('Verbindung wird getestet... (kann einige Sekunden dauern)').classes('text-grey-7')
            
            service = get_ai_changelog_service()
            question = question_input.value.strip()
            
            # Run blocking API call in thread pool to not block the event loop
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor() as executor:
                result = await loop.run_in_executor(
                    executor,
                    do_api_call,
                    service,
                    config.provider,
                    api_key,
                    config.model,
                    question
                )
            
            # Update test status in database
            db = get_db()
            try:
                db_config = db.query(AIConfig).filter(AIConfig.id == config.id).first()
                if db_config:
                    db_config.last_test_at = datetime.utcnow()
                    db_config.last_test_success = result['success']
                    db_config.last_test_error = result.get('error')
                    db.commit()
            finally:
                db.close()
            
            # Show result
            status_container.clear()
            with status_container:
                if result['success']:
                    with ui.row().classes('items-center gap-2'):
                        ui.icon('check_circle', color='positive', size='sm')
                        ui.label('Verbindung erfolgreich!').classes('text-positive font-bold')
                else:
                    with ui.column().classes('gap-1'):
                        with ui.row().classes('items-center gap-2'):
                            ui.icon('error', color='negative', size='sm')
                            ui.label('Verbindungsfehler').classes('text-negative font-bold')
                        ui.label(result.get('error', 'Unbekannter Fehler')).classes('text-negative text-sm')
            
            # Show answer if available
            if result.get('answer'):
                answer_container.visible = True
                with answer_container:
                    ui.separator()
                    ui.label('Antwort der KI:').classes('font-bold text-grey-8')
                    with ui.card().classes('w-full p-4 mt-2').style('background-color: #f5f5f5;'):
                        ui.markdown(result['answer']).classes('text-body1')
            
            # Re-enable button
            if test_button:
                test_button.enable()
            
            # Don't call reload_callback here - it would close the dialog
            # The callback is only needed when closing the dialog
        
        def close_and_reload():
            dialog.close()
            reload_callback()
        
        with ui.row().classes('w-full justify-end gap-2 mt-4'):
            ui.button('Schließen', on_click=close_and_reload).props('flat')
            test_button = ui.button('Test ausführen', icon='play_arrow', on_click=run_test, color='primary')
    
    dialog.open()


def set_default_provider(config: AIConfig, reload_callback):
    """Set a provider as the default"""
    db = get_db()
    try:
        # Remove default from all providers
        db.query(AIConfig).update({AIConfig.is_default: False})
        
        # Set this provider as default
        db_config = db.query(AIConfig).filter(AIConfig.id == config.id).first()
        if db_config:
            db_config.is_default = True
        
        db.commit()
        Toast.success(f'{config.display_name} ist jetzt der Standard-Provider')
        
    except Exception as e:
        Toast.error(f'Fehler: {str(e)}')
    finally:
        db.close()
    
    reload_callback()


def render_smtp_config(user):
    """Render SMTP configuration management"""
    # Import the smtp_config module
    from .smtp_config import load_smtp_configs

    with ui.column().classes('w-full gap-4'):
        # Header with add button
        with ui.row().classes('w-full items-center justify-between'):
            ui.label('SMTP Configuration').classes('text-h5 font-bold')
            ui.button(
                'Add SMTP Server',
                icon='add',
                on_click=lambda: show_smtp_add_dialog(user, smtp_container)
            ).props('color=primary')

        # SMTP servers list container
        smtp_container = ui.column().classes('w-full gap-4')
        load_smtp_configs(user, smtp_container)


def show_smtp_add_dialog(user, container):
    """Show dialog to add SMTP configuration"""
    from .smtp_config import show_add_smtp_dialog
    show_add_smtp_dialog(user, container)


def render_overview(user):
    """Render admin overview"""
    db = get_db()
    try:
        # Get counts
        total_users = db.query(User).count()
        active_users = db.query(User).filter(User.is_active == True).count()
        total_servers = db.query(Server).count()
        active_servers = db.query(Server).filter(Server.is_active == True).count()
        total_teams = db.query(Team).count()
        total_databases = db.query(Database).count()

        # Recent activity - eagerly load the user relationship
        from sqlalchemy.orm import joinedload
        recent_logs = db.query(AuditLog).options(
            joinedload(AuditLog.user)
        ).order_by(
            AuditLog.created_at.desc()
        ).limit(10).all()

    finally:
        db.close()

    with ui.column().classes('w-full gap-6'):
        # System statistics
        ui.label('System Overview').classes('text-h5 font-bold')

        with ui.row().classes('w-full gap-4'):
            render_stat_card('Total Users', str(total_users), 'people', PRIMARY_COLOR)
            render_stat_card('Active Users', str(active_users), 'check_circle', SUCCESS_COLOR)
            render_stat_card('Total Servers', str(total_servers), 'storage', PRIMARY_COLOR)
            render_stat_card('Active Servers', str(active_servers), 'check_circle', SUCCESS_COLOR)

        with ui.row().classes('w-full gap-4'):
            render_stat_card('Teams', str(total_teams), 'group', PRIMARY_COLOR)
            render_stat_card('Databases', str(total_databases), 'folder', PRIMARY_COLOR)

        # Recent activity
        with Card(title='Recent Activity', icon='history'):
            if not recent_logs:
                ui.label('No recent activity.').classes('text-grey-7')
            else:
                with ui.column().classes('w-full gap-2'):
                    for log in recent_logs:
                        with ui.card().classes('w-full p-3').style('background-color: #f5f5f5;'):
                            with ui.row().classes('w-full items-center justify-between'):
                                with ui.column().classes('gap-1'):
                                    ui.label(log.action.replace('_', ' ').title()).classes(
                                        'font-bold'
                                    )
                                    ui.label(log.details or 'No details').classes(
                                        'text-caption text-grey-7'
                                    )
                                    ui.label(f'User ID: {log.user_id}').classes(
                                        'text-caption text-grey-7'
                                    )
                                ui.label(format_datetime(log.created_at)).classes(
                                    'text-caption text-grey-7'
                                )


def render_stat_card(title, value, icon, color):
    """Render a statistics card"""
    with ui.card().classes('flex-1 p-4').style(f'border-left: 4px solid {color};'):
        with ui.row().classes('items-center justify-between w-full'):
            with ui.column().classes('gap-1'):
                ui.label(title).classes('text-caption text-grey-7')
                ui.label(value).classes('text-h5 font-bold')
            ui.icon(icon, size='lg').style(f'color: {color}; opacity: 0.6;')


def render_users_management(user):
    """Render users management section"""
    users_container = ui.column().classes('w-full gap-4')

    with ui.column().classes('w-full gap-4'):
        # Header with add button
        with ui.row().classes('w-full items-center justify-between'):
            ui.label('User Management').classes('text-h5 font-bold')
            ui.button(
                'Add User',
                icon='person_add',
                on_click=lambda: show_add_user_dialog(user, users_container)
            ).props('color=primary')

        # Users table
        with users_container:
            load_users_table(user, users_container)


def load_users_table(admin_user, container):
    """Load and display users table"""
    container.clear()

    db = get_db()
    try:
        users = db.query(User).order_by(User.created_at.desc()).all()

        with container:
            with ui.card().classes('w-full p-4'):
                if not users:
                    ui.label('No users found.').classes('text-grey-7')
                else:
                    for user in users:
                        render_user_row(admin_user, user, container)

    finally:
        db.close()


def render_user_row(admin_user, user, container):
    """Render a user row"""
    with ui.card().classes('w-full p-3 mb-2').style('background-color: #f9f9f9;'):
        with ui.row().classes('w-full items-center justify-between'):
            # User info
            with ui.column().classes('flex-1 gap-1'):
                with ui.row().classes('items-center gap-2'):
                    ui.icon('person', size='md').classes('text-primary')
                    ui.label(user.username).classes('text-h6 font-bold')
                    StatusBadge.render(
                        'Active' if user.is_active else 'Inactive',
                        user.is_active
                    )
                    if user.is_admin:
                        ui.badge('Admin', color='orange')

                ui.label(f'Email: {user.email}').classes('text-grey-7')
                if user.full_name:
                    ui.label(f'Name: {user.full_name}').classes('text-grey-7')
                ui.label(f'Last Login: {format_datetime(user.last_login)}').classes('text-grey-7')

            # Actions
            with ui.row().classes('gap-2'):
                # Don't allow disabling own account
                if user.id != admin_user.id:
                    if user.is_active:
                        ui.button(
                            'Deactivate',
                            icon='block',
                            on_click=lambda u=user: handle_deactivate_user(
                                admin_user, u, container
                            )
                        ).props('flat dense color=warning')
                    else:
                        ui.button(
                            'Activate',
                            icon='check_circle',
                            on_click=lambda u=user: handle_activate_user(
                                admin_user, u, container
                            )
                        ).props('flat dense color=positive')

                    ui.button(
                        'Delete',
                        icon='delete',
                        on_click=lambda u=user: confirm_delete_user(admin_user, u, container)
                    ).props('flat dense color=negative')
                else:
                    ui.label('(You)').classes('text-caption text-grey-7')


def show_add_user_dialog(admin_user, container):
    """Show dialog to add a new user"""
    with ui.dialog() as dialog, ui.card().classes('w-full p-6').style('min-width: 500px;'):
        ui.label('Add New User').classes('text-h5 font-bold mb-4')

        username_input = FormField.text(
            label='Username',
            placeholder='username',
            required=True
        )

        email_input = FormField.text(
            label='Email',
            placeholder='user@example.com',
            required=True
        )

        full_name_input = FormField.text(
            label='Full Name',
            placeholder='Full Name (Optional)'
        )

        password_input = FormField.password(
            label='Password',
            placeholder='Password',
            required=True
        )

        is_admin_checkbox = FormField.checkbox(
            label='Admin User',
            value=False
        )

        error_label = ui.label('').classes('text-negative mt-2')
        error_label.visible = False

        async def handle_save():
            """Handle user creation"""
            username = username_input.value.strip()
            email = email_input.value.strip()
            full_name = full_name_input.value.strip() or None
            password = password_input.value
            is_admin = is_admin_checkbox.value

            if not username or not email or not password:
                error_label.text = 'Please fill in all required fields'
                error_label.visible = True
                return

            try:
                db = get_db()
                new_user = register_user(
                    db=db,
                    username=username,
                    email=email,
                    password=password,
                    full_name=full_name,
                    is_admin=is_admin
                )

                # Create audit log
                create_audit_log(
                    db=db,
                    user_id=admin_user.id,
                    action='user_created_by_admin',
                    resource_type='user',
                    resource_id=new_user.id,
                    details=f'Admin created user: {username}',
                    auto_commit=True
                )

                db.close()

                Toast.success(f'User "{username}" created successfully!')
                dialog.close()

                # Reload users
                load_users_table(admin_user, container)

            except UserExistsError as e:
                error_label.text = str(e)
                error_label.visible = True
            except ValueError as e:
                error_label.text = str(e)
                error_label.visible = True
            except Exception as e:
                error_label.text = f'Error creating user: {str(e)}'
                error_label.visible = True

        with ui.row().classes('w-full justify-end gap-2 mt-4'):
            ui.button('Cancel', on_click=dialog.close).props('flat')
            ui.button('Create User', on_click=handle_save, color='primary')

    dialog.open()


def handle_activate_user(admin_user, user, container):
    """Activate a user"""
    try:
        db = get_db()
        activate_user(db, user.id, admin_user.id)
        db.close()

        Toast.success(f'User "{user.username}" activated successfully!')

        # Reload users
        load_users_table(admin_user, container)

    except Exception as e:
        Toast.error(f'Error activating user: {str(e)}')


def handle_deactivate_user(admin_user, user, container):
    """Deactivate a user"""
    try:
        db = get_db()
        deactivate_user(db, user.id, admin_user.id)
        db.close()

        Toast.success(f'User "{user.username}" deactivated successfully!')

        # Reload users
        load_users_table(admin_user, container)

    except Exception as e:
        Toast.error(f'Error deactivating user: {str(e)}')


def confirm_delete_user(admin_user, user, container):
    """Confirm and delete a user"""
    def handle_delete():
        try:
            db = get_db()

            # Create audit log before deletion
            create_audit_log(
                db=db,
                user_id=admin_user.id,
                action='user_deleted',
                resource_type='user',
                resource_id=user.id,
                details=f'Deleted user: {user.username}',
                auto_commit=True
            )

            # Delete user (cascades to servers, teams, etc.)
            db.query(User).filter(User.id == user.id).delete()
            db.commit()
            db.close()

            Toast.success(f'User "{user.username}" deleted successfully!')

            # Reload users
            load_users_table(admin_user, container)

        except Exception as e:
            Toast.error(f'Error deleting user: {str(e)}')

    ConfirmDialog.show(
        title='Delete User',
        message=f'Are you sure you want to delete user "{user.username}"? This will also delete all their servers, teams, and data.',
        on_confirm=handle_delete,
        confirm_text='Delete',
        danger=True
    )


def render_audit_logs(user):
    """Render audit logs section"""
    with ui.column().classes('w-full gap-4'):
        ui.label('Audit Logs').classes('text-h5 font-bold')

        # Filters
        with ui.row().classes('w-full gap-4 mb-4'):
            action_filter = ui.select(
                label='Action',
                options=['All'] + [
                    'login', 'logout', 'user_created', 'user_deleted',
                    'server_created', 'server_updated', 'server_deleted',
                    'team_synced', 'database_synced'
                ],
                value='All'
            ).classes('flex-1')

            user_filter = ui.input(
                label='Username',
                placeholder='Filter by username'
            ).classes('flex-1')

        logs_container = ui.column().classes('w-full gap-2')

        def load_logs():
            """Load and display audit logs"""
            logs_container.clear()

            db = get_db()
            try:
                from sqlalchemy.orm import joinedload
                query = db.query(AuditLog).options(joinedload(AuditLog.user))

                # Apply filters
                if action_filter.value != 'All':
                    query = query.filter(AuditLog.action == action_filter.value)

                if user_filter.value:
                    query = query.join(User).filter(
                        User.username.ilike(f'%{user_filter.value}%')
                    )

                logs = query.order_by(AuditLog.created_at.desc()).limit(100).all()

                with logs_container:
                    if not logs:
                        ui.label('No audit logs found.').classes('text-grey-7')
                    else:
                        for log in logs:
                            with ui.card().classes('w-full p-3').style(
                                'background-color: #f9f9f9;'
                            ):
                                with ui.row().classes('w-full items-start justify-between'):
                                    with ui.column().classes('flex-1 gap-1'):
                                        ui.label(
                                            log.action.replace('_', ' ').title()
                                        ).classes('font-bold')
                                        ui.label(log.details or 'No details').classes(
                                            'text-grey-7'
                                        )
                                        ui.label(f'User ID: {log.user_id}').classes(
                                            'text-caption text-grey-7'
                                        )
                                        if log.ip_address:
                                            ui.label(f'IP: {log.ip_address}').classes(
                                                'text-caption text-grey-7'
                                            )
                                    with ui.column().classes('items-end gap-1'):
                                        ui.label(format_datetime(log.created_at)).classes(
                                            'text-caption text-grey-7'
                                        )
                                        if log.resource_type:
                                            ui.badge(log.resource_type, color='info')

            finally:
                db.close()

        # Load initial logs
        load_logs()

        # Reload on filter change
        action_filter.on('update:model-value', lambda: load_logs())
        user_filter.on('keyup.enter', lambda: load_logs())

        ui.button('Refresh', icon='refresh', on_click=load_logs).props('flat')


def render_statistics(user):
    """Render statistics section"""
    db = get_db()
    try:
        # User statistics
        total_users = db.query(User).count()
        active_users = db.query(User).filter(User.is_active == True).count()
        admin_users = db.query(User).filter(User.is_admin == True).count()

        # Server statistics
        total_servers = db.query(Server).count()
        active_servers = db.query(Server).filter(Server.is_active == True).count()
        # Now GitHub is stored in User model, not Server
        users_with_github = db.query(User).filter(
            User.github_token_encrypted.isnot(None)
        ).count()

        # Team and database statistics
        total_teams = db.query(Team).count()
        active_teams = db.query(Team).filter(Team.is_active == True).count()
        total_databases = db.query(Database).count()
        excluded_databases = db.query(Database).filter(
            Database.is_excluded == True
        ).count()

        # Activity statistics
        total_logins = db.query(AuditLog).filter(AuditLog.action == 'login').count()
        total_syncs = db.query(AuditLog).filter(
            AuditLog.action == 'database_synced'
        ).count()

    finally:
        db.close()

    with ui.column().classes('w-full gap-6'):
        # User statistics
        with Card(title='User Statistics', icon='people'):
            with ui.column().classes('w-full gap-3'):
                ui.label(f'Total Users: {total_users}').classes('text-h6')
                ui.label(f'Active Users: {active_users}').classes('text-grey-7')
                ui.label(f'Admin Users: {admin_users}').classes('text-grey-7')
                ui.label(f'Inactive Users: {total_users - active_users}').classes('text-grey-7')

        # Server statistics
        with Card(title='Server Statistics', icon='storage'):
            with ui.column().classes('w-full gap-3'):
                ui.label(f'Total Servers: {total_servers}').classes('text-h6')
                ui.label(f'Active Servers: {active_servers}').classes('text-grey-7')
                ui.label(f'Users with GitHub: {users_with_github}').classes('text-grey-7')

        # Team and database statistics
        with Card(title='Team & Database Statistics', icon='folder'):
            with ui.column().classes('w-full gap-3'):
                ui.label(f'Total Teams: {total_teams}').classes('text-h6')
                ui.label(f'Active Teams: {active_teams}').classes('text-grey-7')
                ui.label(f'Total Databases: {total_databases}').classes('text-grey-7')
                ui.label(f'Excluded Databases: {excluded_databases}').classes('text-grey-7')
                ui.label(
                    f'Synced Databases: {total_databases - excluded_databases}'
                ).classes('text-grey-7')

        # Activity statistics
        with Card(title='Activity Statistics', icon='analytics'):
            with ui.column().classes('w-full gap-3'):
                ui.label(f'Total Logins: {total_logins}').classes('text-h6')
                ui.label(f'Total Syncs: {total_syncs}').classes('text-grey-7')
