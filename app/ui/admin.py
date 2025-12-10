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
from ..models.bookstack_config import BookstackConfig
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
            prompts_tab = ui.tab('Prompt-Verwaltung', icon='edit_note')
            bookstack_tab = ui.tab('BookStack', icon='menu_book')
            ninox_docs_tab = ui.tab('Ninox Docs', icon='auto_stories')
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

            # Prompt Management panel
            with ui.tab_panel(prompts_tab):
                render_prompt_management(user)

            # BookStack panel
            with ui.tab_panel(bookstack_tab):
                render_bookstack_config(user)

            # Ninox Docs panel
            with ui.tab_panel(ninox_docs_tab):
                render_ninox_docs(user)

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
        
        # Instructions - expandable documentation
        with ui.expansion('Schritt-für-Schritt Anleitung: Google Cloud Console einrichten', icon='help_outline').classes('w-full bg-blue-50'):
            with ui.column().classes('gap-4 p-4'):
                
                # Step 1: Project
                with ui.card().classes('w-full p-3 bg-white'):
                    ui.label('Schritt 1: Google Cloud Projekt erstellen').classes('font-bold text-primary')
                    with ui.column().classes('gap-1 text-sm mt-2'):
                        ui.label('1. Öffnen Sie https://console.cloud.google.com')
                        ui.label('2. Klicken Sie oben links auf das Projekt-Dropdown (neben "Google Cloud")')
                        ui.label('3. Klicken Sie auf "NEUES PROJEKT"')
                        ui.label('4. Projektname eingeben, z.B. "Ninox2Git"')
                        ui.label('5. Organisation auswählen (falls vorhanden)')
                        ui.label('6. Klicken Sie auf "ERSTELLEN"')
                        ui.label('7. Warten Sie bis das Projekt erstellt ist und wählen Sie es aus')
                
                # Step 2: APIs
                with ui.card().classes('w-full p-3 bg-white'):
                    ui.label('Schritt 2: APIs aktivieren').classes('font-bold text-primary')
                    with ui.column().classes('gap-1 text-sm mt-2'):
                        ui.label('1. Im linken Menü: "APIs und Dienste" → "Bibliothek"')
                        ui.label('2. Suchen Sie nach "Google Drive API" und klicken Sie darauf')
                        ui.label('3. Klicken Sie auf "AKTIVIEREN"')
                        ui.label('4. Gehen Sie zurück zur Bibliothek (Pfeil links oben)')
                        ui.label('5. Suchen Sie nach "Google Docs API" und klicken Sie darauf')
                        ui.label('6. Klicken Sie auf "AKTIVIEREN"')
                    with ui.card().classes('w-full p-2 bg-amber-50 mt-2'):
                        ui.label('Hinweis: Beide APIs werden für die Drive-Upload-Funktion benötigt.').classes('text-xs text-amber-800')
                
                # Step 3: OAuth Consent Screen
                with ui.card().classes('w-full p-3 bg-white'):
                    ui.label('Schritt 3: OAuth-Zustimmungsbildschirm konfigurieren').classes('font-bold text-primary')
                    with ui.column().classes('gap-1 text-sm mt-2'):
                        ui.label('1. Im linken Menü: "APIs und Dienste" → "OAuth-Zustimmungsbildschirm"')
                        ui.label('2. User Type auswählen:')
                        with ui.column().classes('ml-4 gap-1'):
                            ui.label('• "Intern" - Nur für Benutzer Ihrer Google Workspace Organisation')
                            ui.label('• "Extern" - Für alle Google-Konten (erfordert Verifizierung)')
                        ui.label('3. Klicken Sie auf "ERSTELLEN"')
                        ui.label('4. App-Informationen ausfüllen:')
                        with ui.column().classes('ml-4 gap-1'):
                            ui.label('• App-Name: "Ninox2Git" (oder Ihr gewünschter Name)')
                            ui.label('• User-Support-E-Mail: Ihre E-Mail-Adresse')
                            ui.label('• App-Logo: Optional')
                        ui.label('5. App-Domain: Leer lassen oder Ihre Domain eintragen')
                        ui.label('6. Entwicklerkontakt: Ihre E-Mail-Adresse')
                        ui.label('7. Klicken Sie auf "SPEICHERN UND FORTFAHREN"')
                
                # Step 4: Scopes
                with ui.card().classes('w-full p-3 bg-white'):
                    ui.label('Schritt 4: Bereiche (Scopes) hinzufügen').classes('font-bold text-primary')
                    with ui.column().classes('gap-1 text-sm mt-2'):
                        ui.label('1. Klicken Sie auf "BEREICHE HINZUFÜGEN ODER ENTFERNEN"')
                        ui.label('2. Suchen und aktivieren Sie folgende Bereiche:')
                        with ui.card().classes('w-full p-2 bg-grey-1 mt-1 mb-1'):
                            ui.label('.../auth/userinfo.email').classes('font-mono text-xs')
                            ui.label('.../auth/userinfo.profile').classes('font-mono text-xs')
                            ui.label('openid').classes('font-mono text-xs')
                        ui.label('3. Für Google Drive zusätzlich:')
                        with ui.card().classes('w-full p-2 bg-grey-1 mt-1 mb-1'):
                            ui.label('.../auth/drive.file').classes('font-mono text-xs')
                            ui.label('.../auth/documents').classes('font-mono text-xs')
                        ui.label('4. Klicken Sie auf "AKTUALISIEREN"')
                        ui.label('5. Klicken Sie auf "SPEICHERN UND FORTFAHREN"')
                
                # Step 5: Test Users (if External)
                with ui.card().classes('w-full p-3 bg-white'):
                    ui.label('Schritt 5: Testbenutzer (nur bei "Extern")').classes('font-bold text-primary')
                    with ui.column().classes('gap-1 text-sm mt-2'):
                        ui.label('1. Wenn Sie "Extern" gewählt haben:')
                        ui.label('2. Klicken Sie auf "+ ADD USERS"')
                        ui.label('3. Fügen Sie E-Mail-Adressen der Testbenutzer hinzu')
                        ui.label('4. Klicken Sie auf "SPEICHERN UND FORTFAHREN"')
                    with ui.card().classes('w-full p-2 bg-amber-50 mt-2'):
                        ui.label('Hinweis: Bei "Intern" ist dieser Schritt nicht erforderlich.').classes('text-xs text-amber-800')
                
                # Step 6: Create Credentials
                with ui.card().classes('w-full p-3 bg-white'):
                    ui.label('Schritt 6: OAuth 2.0 Client-ID erstellen').classes('font-bold text-primary')
                    with ui.column().classes('gap-1 text-sm mt-2'):
                        ui.label('1. Im linken Menü: "APIs und Dienste" → "Anmeldedaten"')
                        ui.label('2. Klicken Sie oben auf "+ ANMELDEDATEN ERSTELLEN"')
                        ui.label('3. Wählen Sie "OAuth-Client-ID"')
                        ui.label('4. Anwendungstyp: "Webanwendung"')
                        ui.label('5. Name: "Ninox2Git Web Client" (oder beliebig)')
                        ui.label('6. Autorisierte JavaScript-Quellen: Leer lassen')
                        ui.label('7. Autorisierte Weiterleitungs-URIs:')
                        
                        # Show the redirect URI
                        import os
                        app_url = os.getenv('APP_URL', 'http://localhost:8765')
                        redirect_uri = f"{app_url}/auth/google/callback"
                        
                        with ui.card().classes('w-full p-2 bg-green-50 mt-1 mb-1'):
                            ui.label('Kopieren Sie diese URI:').classes('text-xs text-green-800')
                            with ui.row().classes('items-center gap-2'):
                                uri_label = ui.label(redirect_uri).classes('font-mono text-sm font-bold')
                                ui.button(
                                    icon='content_copy',
                                    on_click=lambda: ui.run_javascript(f'navigator.clipboard.writeText("{redirect_uri}"); ')
                                ).props('flat dense size=sm').tooltip('In Zwischenablage kopieren')
                        
                        ui.label('8. Klicken Sie auf "ERSTELLEN"')
                        ui.label('9. Ein Popup erscheint mit Ihren Anmeldedaten:')
                        with ui.column().classes('ml-4 gap-1'):
                            ui.label('• Client-ID: Kopieren Sie diese (endet mit .apps.googleusercontent.com)')
                            ui.label('• Clientschlüssel: Kopieren Sie diesen')
                        ui.label('10. Fügen Sie beide Werte unten in die Konfiguration ein')
                
                # Step 7: Google Drive Setup
                with ui.card().classes('w-full p-3 bg-white'):
                    ui.label('Schritt 7: Google Drive Shared Drive erstellen (optional)').classes('font-bold text-primary')
                    with ui.column().classes('gap-1 text-sm mt-2'):
                        ui.label('Für die "Upload Drive" Funktion:')
                        ui.label('1. Öffnen Sie https://drive.google.com')
                        ui.label('2. Im linken Menü: "Geteilte Ablagen"')
                        ui.label('3. Klicken Sie auf "+ Neu" → "Neue geteilte Ablage"')
                        ui.label('4. Name eingeben: "ninox2git" (oder Ihr gewünschter Name)')
                        ui.label('5. Klicken Sie auf "Erstellen"')
                        ui.label('6. Rechtsklick auf die Ablage → "Mitglieder verwalten"')
                        ui.label('7. Fügen Sie alle Benutzer hinzu, die hochladen sollen (als "Mitbearbeiter")')
                        ui.label('8. Fügen Sie Benutzer, die nur lesen sollen (als "Betrachter") hinzu')
                    with ui.card().classes('w-full p-2 bg-blue-50 mt-2'):
                        ui.label('Der Name der Shared Drive muss unten bei "Shared Drive Name" eingetragen werden.').classes('text-xs text-blue-800')
                
                # Troubleshooting
                with ui.card().classes('w-full p-3 bg-red-50'):
                    ui.label('Fehlerbehebung').classes('font-bold text-red-800')
                    with ui.column().classes('gap-2 text-sm mt-2'):
                        with ui.row().classes('gap-2'):
                            ui.label('•').classes('text-red-800')
                            ui.label('"Error 400: redirect_uri_mismatch" → Die Redirect URI stimmt nicht überein. Prüfen Sie die URI in den Google-Anmeldedaten.')
                        with ui.row().classes('gap-2'):
                            ui.label('•').classes('text-red-800')
                            ui.label('"Error 403: access_denied" → Der Benutzer ist nicht als Testbenutzer hinzugefügt (bei "Extern") oder die Domain ist nicht erlaubt.')
                        with ui.row().classes('gap-2'):
                            ui.label('•').classes('text-red-800')
                            ui.label('"Shared Drive nicht gefunden" → Prüfen Sie den Namen und ob der Benutzer Zugriff auf die Shared Drive hat.')
        
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
                        
                        ui.separator().classes('my-4')
                        
                        # Google Drive Section
                        ui.label('Google Drive Integration').classes('text-h6 font-bold mb-2')
                        ui.label(
                            'Ermöglicht OAuth-Benutzern, JSON-Dateien als Google Docs in einen Shared Drive hochzuladen.'
                        ).classes('text-sm text-grey-6 mb-4')
                        
                        drive_enabled_switch = ui.switch(
                            'Google Drive aktiviert',
                            value=getattr(config, 'drive_enabled', False)
                        ).classes('mb-2')
                        
                        drive_folder_input = ui.input(
                            label='Shared Drive Name',
                            value=getattr(config, 'drive_shared_folder_name', '') or '',
                            placeholder='ninox2git'
                        ).classes('w-full mb-2')
                        
                        ui.label(
                            'Der Name des Shared Drives in Google Drive. '
                            'Ordnerstruktur wird automatisch erstellt: server/team/datenbank/komplett.json'
                        ).classes('text-sm text-grey-6 mb-2')
                        
                        with ui.card().classes('w-full p-3 bg-amber-50 mb-4'):
                            ui.label('Wichtig: Google APIs aktivieren').classes('font-bold text-sm')
                            with ui.column().classes('gap-1 text-xs'):
                                ui.label('In der Google Cloud Console müssen aktiviert sein:')
                                ui.label('- Google Drive API')
                                ui.label('- Google Docs API')
                        
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
                                
                                # Drive settings
                                config.drive_enabled = drive_enabled_switch.value
                                config.drive_shared_folder_name = drive_folder_input.value.strip() or None
                                
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

        # Prompt template selection (for documentation)
        from ..models.prompt_template import PromptTemplate, PromptType
        db_temp = get_db()
        try:
            doc_prompts = db_temp.query(PromptTemplate).filter(
                PromptTemplate.prompt_type == PromptType.DOCUMENTATION.value,
                PromptTemplate.is_active == True
            ).all()

            prompt_options = {p.id: f"{p.name} {'[Standard]' if p.is_default else ''}" for p in doc_prompts}
            prompt_options[0] = "Standard-Prompt (automatisch)"

            prompt_select = ui.select(
                label='Dokumentations-Prompt',
                options=prompt_options,
                value=config.doc_prompt_template_id if config.doc_prompt_template_id else 0
            ).classes('w-full mb-4')
            ui.label('Wählen Sie einen Prompt für die Doku-Generierung oder lassen Sie es auf Standard').classes('text-xs text-grey-6')
        finally:
            db_temp.close()

        # Advanced settings
        with ui.expansion('Erweiterte Einstellungen', icon='tune').classes('w-full mb-4'):
            with ui.column().classes('w-full gap-2 p-2'):
                max_tokens_input = ui.number(
                    label='Max Tokens',
                    value=config.max_tokens,
                    min=100,
                    max=128000,  # Gemini 3 Pro supports up to 65K, but allow higher for future models
                    step=1000
                ).classes('w-full')
                ui.label('Empfohlen: 16000-32000 für Dokumentation').classes('text-xs text-grey-6')
                
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
            prompt_template_id = prompt_select.value if prompt_select.value != 0 else None

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
                db_config.doc_prompt_template_id = prompt_template_id
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


def render_ninox_docs(user):
    """Render Ninox Documentation scraper panel"""
    from ..services.ninox_docs_service import get_ninox_docs_service, ScrapeProgress
    from ..utils.encryption import get_encryption_manager
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    
    encryption = get_encryption_manager()
    service = get_ninox_docs_service()
    
    with ui.column().classes('w-full gap-4'):
        ui.label('Ninox Dokumentation').classes('text-h5 font-bold')
        ui.label(
            'Laden Sie die komplette Ninox-Dokumentation (Funktionen + API) vom Ninox Forum herunter '
            'und speichern Sie sie in einem GitHub Repository für die Claude AI Integration.'
        ).classes('text-grey-7 mb-4')
        
        # Info card
        with ui.card().classes('w-full p-4 bg-blue-50'):
            with ui.row().classes('items-center gap-3'):
                ui.icon('info', size='md', color='primary')
                with ui.column().classes('gap-1'):
                    ui.label(f'Verfügbare Dokumentation: {service.get_function_count()} Funktionen + {service.get_api_doc_count()} API-Artikel + {service.get_print_doc_count()} Drucken-Artikel').classes('font-bold')
                    ui.label('Die Dokumentation wird vom forum.ninox.de geladen und als 3 separate Markdown-Dateien erstellt.').classes('text-sm')
        
        ui.separator().classes('my-4')
        
        # GitHub Settings Info
        db = get_db()
        try:
            db_user = db.query(User).filter(User.id == user.id).first()
            has_github = db_user and db_user.github_token_encrypted
            github_org = db_user.github_organization if db_user else None
        finally:
            db.close()
        
        if not has_github:
            with ui.card().classes('w-full p-4 bg-amber-50'):
                with ui.row().classes('items-center gap-3'):
                    ui.icon('warning', size='md', color='warning')
                    with ui.column().classes('gap-1'):
                        ui.label('GitHub nicht konfiguriert').classes('font-bold text-amber-800')
                        ui.label('Bitte konfigurieren Sie zuerst Ihren GitHub Token im Profil, um die Dokumentation hochladen zu können.').classes('text-sm text-amber-700')
                        ui.button(
                            'Zum Profil',
                            icon='person',
                            on_click=lambda: ui.navigate.to('/profile')
                        ).props('flat color=warning').classes('mt-2')
        else:
            with ui.card().classes('w-full p-4 bg-green-50'):
                with ui.row().classes('items-center gap-3'):
                    ui.icon('check_circle', size='md', color='positive')
                    with ui.column().classes('gap-1'):
                        ui.label('GitHub konfiguriert').classes('font-bold text-green-800')
                        org_text = f"Organisation: {github_org}" if github_org else "Persönliches Repository"
                        ui.label(f'{org_text} | Repository: ninox-docs').classes('text-sm text-green-700')
        
        ui.separator().classes('my-4')
        
        # Progress container
        progress_container = ui.column().classes('w-full gap-2')
        progress_container.visible = False
        
        # Result container
        result_container = ui.column().classes('w-full gap-2 mt-4')
        
        # Store for scraped data
        scraped_data = {'docs': None}
        
        async def run_scraper():
            """Run the documentation scraper"""
            progress_container.visible = True
            progress_container.clear()
            result_container.clear()
            
            # Disable button
            scrape_button.disable()
            
            with progress_container:
                progress_label = ui.label('Starte Download...').classes('font-bold')
                progress_bar = ui.linear_progress(value=0, show_value=False).classes('w-full')
                current_func_label = ui.label('').classes('text-grey-7 text-sm')
            
            def update_progress(progress: ScrapeProgress):
                """Update progress UI"""
                pct = progress.current / progress.total if progress.total > 0 else 0
                progress_bar.value = pct
                progress_label.text = f'Download: {progress.current}/{progress.total}'
                current_func_label.text = f'Aktuell: {progress.current_function}'
            
            # Run scraper in thread pool - scrape ALL documentation (functions + API)
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor() as executor:
                all_docs = await loop.run_in_executor(
                    executor,
                    lambda: service.scrape_all_documentation(update_progress, delay=0.5)
                )
            
            scraped_data['docs'] = all_docs
            
            # Show result
            progress_container.visible = False
            result_container.clear()
            
            func_count = len(all_docs.get('functions', {}))
            api_count = len(all_docs.get('api', {}))
            print_count = len(all_docs.get('print', {}))
            
            with result_container:
                if func_count > 0 or api_count > 0 or print_count > 0:
                    with ui.card().classes('w-full p-4 bg-green-50'):
                        with ui.row().classes('items-center gap-3'):
                            ui.icon('check_circle', size='md', color='positive')
                            ui.label(f'{func_count} Funktionen + {api_count} API-Artikel + {print_count} Drucken-Artikel erfolgreich geladen!').classes('font-bold text-green-800')
                    
                    # Show errors if any
                    if service.progress.errors:
                        with ui.expansion(f'Fehler ({len(service.progress.errors)})', icon='warning').classes('w-full bg-amber-50'):
                            for error in service.progress.errors:
                                ui.label(f'• {error}').classes('text-sm text-amber-800')
                    
                    # Upload button
                    if has_github:
                        ui.button(
                            'Zu GitHub hochladen',
                            icon='cloud_upload',
                            on_click=lambda: upload_to_github(all_docs),
                            color='primary'
                        ).classes('mt-4')
                else:
                    with ui.card().classes('w-full p-4 bg-red-50'):
                        with ui.row().classes('items-center gap-3'):
                            ui.icon('error', size='md', color='negative')
                            ui.label('Fehler beim Laden der Dokumentation').classes('font-bold text-red-800')
            
            # Re-enable button
            scrape_button.enable()
        
        async def upload_to_github(all_docs: dict):
            """Upload documentation to GitHub as three separate files"""
            result_container.clear()
            
            with result_container:
                with ui.row().classes('items-center gap-2'):
                    ui.spinner(size='sm')
                    ui.label('Erstelle 3 Markdown-Dateien und lade zu GitHub hoch...').classes('text-grey-7')
            
            # Get GitHub credentials
            db = get_db()
            try:
                db_user = db.query(User).filter(User.id == user.id).first()
                if not db_user or not db_user.github_token_encrypted:
                    raise ValueError("GitHub Token nicht konfiguriert")
                
                github_token = encryption.decrypt(db_user.github_token_encrypted)
                github_org = db_user.github_organization
            finally:
                db.close()
            
            # Create separate markdown files
            functions_md = service.create_functions_markdown(all_docs.get('functions', {}))
            api_md = service.create_api_markdown(all_docs.get('api', {}))
            print_md = service.create_print_markdown(all_docs.get('print', {}))
            
            # Upload in thread pool
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor() as executor:
                result = await loop.run_in_executor(
                    executor,
                    lambda: service.upload_separate_files_to_github(
                        functions_md,
                        api_md,
                        print_md,
                        github_token,
                        github_org,
                        "ninox-docs"
                    )
                )
            
            result_container.clear()
            
            with result_container:
                if result.get('success'):
                    with ui.card().classes('w-full p-4 bg-green-50'):
                        with ui.column().classes('gap-2'):
                            with ui.row().classes('items-center gap-3'):
                                ui.icon('check_circle', size='md', color='positive')
                                ui.label('Erfolgreich hochgeladen!').classes('font-bold text-green-800')
                            
                            ui.label(f'Repository: {result.get("url")}').classes('text-sm')
                            ui.label('3 Dateien erstellt: NINOX_FUNKTIONEN.md + NINOX_API.md + NINOX_DRUCKEN.md').classes('text-sm text-green-700')
                            
                            with ui.row().classes('gap-2 mt-2 flex-wrap'):
                                ui.button(
                                    'Repository öffnen',
                                    icon='open_in_new',
                                    on_click=lambda: ui.run_javascript(f'window.open("{result.get("url")}", "_blank")')
                                ).props('flat color=primary')
                                ui.button(
                                    'Funktionen öffnen',
                                    icon='functions',
                                    on_click=lambda: ui.run_javascript(f'window.open("{result.get("functions_url")}", "_blank")')
                                ).props('flat color=primary')
                                ui.button(
                                    'API öffnen',
                                    icon='api',
                                    on_click=lambda: ui.run_javascript(f'window.open("{result.get("api_url")}", "_blank")')
                                ).props('flat color=primary')
                                ui.button(
                                    'Drucken öffnen',
                                    icon='print',
                                    on_click=lambda: ui.run_javascript(f'window.open("{result.get("print_url")}", "_blank")')
                                ).props('flat color=primary')
                else:
                    with ui.card().classes('w-full p-4 bg-red-50'):
                        with ui.row().classes('items-center gap-3'):
                            ui.icon('error', size='md', color='negative')
                            with ui.column().classes('gap-1'):
                                ui.label('Fehler beim Hochladen').classes('font-bold text-red-800')
                                ui.label(result.get('error', 'Unbekannter Fehler')).classes('text-sm text-red-700')
        
        # Main action button
        scrape_button = ui.button(
            'Dokumentation herunterladen',
            icon='download',
            on_click=run_scraper,
            color='primary'
        ).classes('mt-4')
        
        # Instructions
        with ui.expansion('Anleitung: Claude AI Integration', icon='help_outline').classes('w-full mt-6 bg-grey-1'):
            with ui.column().classes('gap-4 p-4'):
                ui.markdown("""
### So verwenden Sie die Ninox-Dokumentation mit Claude AI:

1. **Dokumentation herunterladen**: Klicken Sie auf "Dokumentation herunterladen" um alle NinoxScript-Funktionen vom Forum zu laden.

2. **Zu GitHub hochladen**: Nach dem Download können Sie die kombinierte Markdown-Datei in Ihr privates GitHub Repository hochladen.

3. **Claude Project erstellen**: 
   - Öffnen Sie [claude.ai](https://claude.ai) und erstellen Sie ein neues Project
   - Gehen Sie zu "Project Knowledge" und wählen Sie "Connect to GitHub"
   - Wählen Sie das Repository `ninox-docs` und die Datei `NINOX_FUNKTIONEN.md`

4. **Ninox-Code generieren lassen**: Claude kann nun alle NinoxScript-Funktionen nachschlagen und korrekten Code generieren.

### Empfohlener System-Prompt für Claude:

```
Du bist ein Ninox-Experte und hilfst beim Schreiben von NinoxScript-Code.
Verwende die Ninox-Funktionsreferenz aus dem Project Knowledge, um korrekten Code zu generieren.
Antworte auf Deutsch und erkläre den Code.
```
                """)


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


def render_prompt_management(user):
    """Render prompt template management panel"""
    from ..models.prompt_template import PromptTemplate, PromptType
    
    with ui.column().classes('w-full gap-4'):
        ui.label('Prompt-Verwaltung').classes('text-h5 font-bold')
        ui.label(
            'Verwalten Sie Prompt-Templates für KI-Generierungen. '
            'Erstellen Sie eigene Prompts und verknüpfen Sie diese mit AI-Providern.'
        ).classes('text-grey-7 mb-4')
        
        # Add new prompt button
        with ui.row().classes('w-full justify-between items-center mb-4'):
            ui.button(
                'Neuer Prompt',
                icon='add',
                on_click=lambda: show_prompt_edit_dialog(None, user, prompts_container, load_prompts)
            ).props('color=primary')
        
        # Container for prompt cards
        prompts_container = ui.column().classes('w-full gap-4')
        
        def load_prompts():
            """Load and display all prompt templates"""
            prompts_container.clear()
            
            db = get_db()
            try:
                prompts = db.query(PromptTemplate).order_by(
                    PromptTemplate.prompt_type,
                    PromptTemplate.is_default.desc(),
                    PromptTemplate.name
                ).all()
                
                if not prompts:
                    with prompts_container:
                        ui.label('Keine Prompts vorhanden').classes('text-grey-6')
                else:
                    # Group by type
                    by_type = {}
                    for p in prompts:
                        if p.prompt_type not in by_type:
                            by_type[p.prompt_type] = []
                        by_type[p.prompt_type] = []
                    
                    for p in prompts:
                        by_type[p.prompt_type].append(p)
                    
                    with prompts_container:
                        for prompt_type, prompt_list in by_type.items():
                            ui.label(f'{prompt_list[0].type_label if prompt_list else prompt_type}').classes('text-h6 font-bold mt-4 mb-2')
                            for prompt in prompt_list:
                                render_prompt_card(prompt, user, prompts_container, load_prompts)
                        
            finally:
                db.close()
        
        load_prompts()


def render_prompt_card(prompt: "PromptTemplate", user, container, reload_callback):
    """Render a single prompt template card"""
    from ..models.prompt_template import PromptTemplate
    
    border_style = 'border-left: 4px solid #9333EA;'
    if prompt.is_default:
        border_style = 'border: 2px solid #9333EA;'
    
    with ui.card().classes('w-full p-4').style(border_style):
        with ui.row().classes('w-full items-start justify-between'):
            # Prompt info
            with ui.column().classes('flex-1 gap-2'):
                with ui.row().classes('items-center gap-2'):
                    ui.icon('edit_note', size='md').classes('text-purple')
                    ui.label(prompt.name).classes('text-h6 font-bold')
                    
                    if prompt.is_default:
                        ui.badge('Standard', color='primary')
                    if not prompt.is_active:
                        ui.badge('Inaktiv', color='grey')
                
                if prompt.description:
                    ui.label(prompt.description).classes('text-grey-7 text-sm')
                
                # Metadata
                with ui.row().classes('items-center gap-4 text-xs text-grey-6 mt-2'):
                    ui.label(f'Typ: {prompt.type_label}')
                    ui.label(f'Version: {prompt.version}')
                    if prompt.created_by:
                        ui.label(f'Erstellt von: {prompt.created_by}')
                    ui.label(f'Erstellt: {format_datetime(prompt.created_at) if hasattr(prompt, "created_at") and prompt.created_at else "N/A"}')
                
                # Preview
                preview_text = prompt.prompt_text[:200] + '...' if len(prompt.prompt_text) > 200 else prompt.prompt_text
                with ui.expansion('Prompt-Vorschau', icon='visibility').classes('w-full mt-2'):
                    ui.markdown(f'```\n{preview_text}\n```').classes('text-xs')
            
            # Actions
            with ui.column().classes('gap-2'):
                ui.button(
                    'Bearbeiten',
                    icon='edit',
                    on_click=lambda p=prompt: show_prompt_edit_dialog(p, user, container, reload_callback)
                ).props('flat dense color=primary')
                
                if not prompt.is_default:
                    ui.button(
                        'Als Standard',
                        icon='star',
                        on_click=lambda p=prompt: set_default_prompt(p, reload_callback)
                    ).props('flat dense color=warning')
                
                ui.button(
                    'Löschen',
                    icon='delete',
                    on_click=lambda p=prompt: delete_prompt(p, reload_callback)
                ).props('flat dense color=negative')


def show_prompt_edit_dialog(prompt: "PromptTemplate" = None, user=None, container=None, reload_callback=None):
    """Show dialog to create or edit a prompt template"""
    from ..models.prompt_template import PromptTemplate, PromptType
    
    is_new = prompt is None
    
    with ui.dialog() as dialog, ui.card().classes('p-6').style('min-width: 800px; max-width: 1000px;'):
        ui.label('Neuer Prompt' if is_new else f'Prompt bearbeiten: {prompt.name}').classes('text-h5 font-bold mb-4')
        
        with ui.column().classes('w-full gap-4'):
            # Name
            name_input = ui.input(
                label='Name',
                placeholder='z.B. Standard Dokumentation',
                value=prompt.name if prompt else ''
            ).classes('w-full')
            
            # Description
            desc_input = ui.textarea(
                label='Beschreibung',
                placeholder='Kurze Beschreibung des Prompts...',
                value=prompt.description if prompt and prompt.description else ''
            ).classes('w-full')
            
            # Type
            type_options = {
                'documentation': 'Dokumentation',
                'changelog': 'Changelog',
                'code_review': 'Code Review',
                'custom': 'Benutzerdefiniert'
            }
            type_select = ui.select(
                label='Typ',
                options=type_options,
                value=prompt.prompt_type if prompt else 'documentation'
            ).classes('w-full')
            
            # Prompt text (large textarea)
            prompt_input = ui.textarea(
                label='Prompt-Text',
                placeholder='Geben Sie hier den Prompt ein...',
                value=prompt.prompt_text if prompt else ''
            ).classes('w-full').style('min-height: 400px; font-family: monospace;')
            
            # Active checkbox
            is_active_cb = ui.checkbox(
                'Aktiv',
                value=prompt.is_active if prompt else True
            )
            
            # Default checkbox
            is_default_cb = ui.checkbox(
                'Als Standard für diesen Typ verwenden',
                value=prompt.is_default if prompt else False
            )
        
        # Buttons
        with ui.row().classes('w-full justify-end gap-2 mt-4'):
            ui.button('Abbrechen', on_click=dialog.close).props('flat')
            ui.button(
                'Speichern' if is_new else 'Aktualisieren',
                icon='save',
                on_click=lambda: save_prompt(
                    dialog,
                    prompt,
                    name_input.value,
                    desc_input.value,
                    type_select.value,
                    prompt_input.value,
                    is_active_cb.value,
                    is_default_cb.value,
                    user,
                    reload_callback
                )
            ).props('color=primary')
    
    dialog.open()


def save_prompt(dialog, existing_prompt, name, description, prompt_type, prompt_text, is_active, is_default, user, reload_callback):
    """Save or update a prompt template"""
    from ..models.prompt_template import PromptTemplate
    
    try:
        if not name or not prompt_text:
            ui.notify('Name und Prompt-Text sind erforderlich', type='negative')
            return
        
        db = get_db()
        try:
            if existing_prompt:
                # Update existing
                existing_prompt.name = name
                existing_prompt.description = description
                existing_prompt.prompt_type = prompt_type
                existing_prompt.prompt_text = prompt_text
                existing_prompt.is_active = is_active
                existing_prompt.is_default = is_default
                existing_prompt.last_modified_by = user.username
                existing_prompt.version += 1
                
                db.merge(existing_prompt)
            else:
                # Create new
                new_prompt = PromptTemplate(
                    name=name,
                    description=description,
                    prompt_type=prompt_type,
                    prompt_text=prompt_text,
                    is_active=is_active,
                    is_default=is_default,
                    created_by=user.username,
                    version=1
                )
                db.add(new_prompt)
            
            # If set as default, unset other defaults for this type
            if is_default:
                db.query(PromptTemplate).filter(
                    PromptTemplate.prompt_type == prompt_type,
                    PromptTemplate.id != (existing_prompt.id if existing_prompt else -1)
                ).update({'is_default': False})
            
            db.commit()
            
            ui.notify(f'Prompt {"aktualisiert" if existing_prompt else "erstellt"}!', type='positive')
            dialog.close()
            
            if reload_callback:
                reload_callback()
                
        finally:
            db.close()
            
    except Exception as e:
        ui.notify(f'Fehler beim Speichern: {str(e)}', type='negative')


def set_default_prompt(prompt: "PromptTemplate", reload_callback):
    """Set a prompt as default for its type"""
    from ..models.prompt_template import PromptTemplate
    
    db = get_db()
    try:
        # Unset all defaults for this type
        db.query(PromptTemplate).filter(
            PromptTemplate.prompt_type == prompt.prompt_type
        ).update({'is_default': False})
        
        # Set this as default
        prompt.is_default = True
        db.merge(prompt)
        db.commit()
        
        ui.notify(f'{prompt.name} ist jetzt der Standard-Prompt', type='positive')
        
        if reload_callback:
            reload_callback()
            
    finally:
        db.close()


def delete_prompt(prompt: "PromptTemplate", reload_callback):
    """Delete a prompt template"""
    from ..models.prompt_template import PromptTemplate
    
    def confirm_delete():
        db = get_db()
        try:
            db.query(PromptTemplate).filter(PromptTemplate.id == prompt.id).delete()
            db.commit()
            
            ui.notify(f'Prompt "{prompt.name}" gelöscht', type='positive')
            
            if reload_callback:
                reload_callback()
                
        finally:
            db.close()
    
    ConfirmDialog(
        title='Prompt löschen?',
        message=f'Möchten Sie den Prompt "{prompt.name}" wirklich löschen?',
        on_confirm=confirm_delete
    ).show()


def render_bookstack_config(user):
    """Render BookStack configuration panel"""
    from ..models.bookstack_config import BookstackConfig
    
    encryption = get_encryption_manager()
    
    with ui.column().classes('w-full gap-4'):
        ui.label('BookStack-Konfiguration').classes('text-h5 font-bold')
        ui.label(
            'Konfigurieren Sie BookStack-Instanzen für die automatische Dokumentations-Übertragung. '
            'Pro Server kann eine BookStack-Instanz mit vordefiniertem Shelf (Regal) konfiguriert werden.'
        ).classes('text-grey-7 mb-4')
        
        # Container for server configs
        bookstack_container = ui.column().classes('w-full gap-4')
        
        def load_bookstack_configs():
            """Load and display BookStack configurations for all servers"""
            bookstack_container.clear()
            
            db = get_db()
            try:
                # Get all active servers
                servers = db.query(Server).filter(Server.is_active == True).all()
                
                if not servers:
                    with bookstack_container:
                        ui.label('Keine aktiven Server vorhanden').classes('text-grey-6')
                    return
                
                with bookstack_container:
                    for server in servers:
                        # Get or create BookStack config for this server
                        bs_config = db.query(BookstackConfig).filter(
                            BookstackConfig.server_id == server.id
                        ).first()
                        
                        render_bookstack_card(server, bs_config, user, bookstack_container, load_bookstack_configs)
                        
            finally:
                db.close()
        
        load_bookstack_configs()


def render_bookstack_card(server: Server, config: BookstackConfig, user, container, reload_callback):
    """Render BookStack configuration card for a server"""
    encryption = get_encryption_manager()
    
    is_configured = config and config.is_configured
    border_style = 'border-left: 4px solid #7C3AED;' if is_configured else 'border-left: 4px solid #D1D5DB;'
    
    with ui.card().classes('w-full p-4').style(border_style):
        with ui.row().classes('w-full items-center justify-between'):
            # Server info
            with ui.row().classes('items-center gap-3'):
                ui.icon('menu_book', size='lg').classes('text-purple')
                with ui.column().classes('gap-1'):
                    with ui.row().classes('items-center gap-2'):
                        ui.label(f'Server: {server.name}').classes('text-h6 font-bold')
                        
                        if is_configured:
                            ui.badge('Konfiguriert', color='purple')
                            if config.is_active:
                                ui.badge('Aktiv', color='positive')
                        else:
                            ui.badge('Nicht konfiguriert', color='grey')
                    
                    # Show URL and shelf if configured
                    if config:
                        ui.label(f'URL: {config.url}').classes('text-sm text-grey-7')
                        ui.label(f'Shelf: {config.default_shelf_name}').classes('text-sm text-grey-7')
                        
                        # Connection status
                        if config.last_test_success is True:
                            ui.label('✓ Verbindung erfolgreich').classes('text-positive text-xs')
                        elif config.last_test_success is False:
                            ui.label(f'✗ Verbindungsfehler: {config.last_test_error[:50] if config.last_test_error else "Unbekannt"}').classes('text-negative text-xs')
            
            # Actions
            with ui.row().classes('gap-2'):
                ui.button(
                    'Konfigurieren',
                    icon='settings',
                    on_click=lambda: show_bookstack_config_dialog(server, config, user, reload_callback)
                ).props('flat dense color=primary')
                
                if is_configured:
                    ui.button(
                        'Testen',
                        icon='check_circle',
                        on_click=lambda: test_bookstack_connection(server, config, reload_callback)
                    ).props('flat dense color=purple')


def show_bookstack_config_dialog(server: Server, config: BookstackConfig, user, reload_callback):
    """Show dialog to configure BookStack for a server"""
    from ..models.bookstack_config import BookstackConfig
    
    encryption = get_encryption_manager()
    
    # Decrypt existing token if available
    existing_token = ""
    if config and config.api_token_encrypted:
        try:
            existing_token = encryption.decrypt(config.api_token_encrypted)
        except:
            existing_token = ""
    
    with ui.dialog() as dialog, ui.card().classes('p-6').style('min-width: 600px;'):
        ui.label(f'BookStack konfigurieren: {server.name}').classes('text-h5 font-bold mb-4')
        
        with ui.column().classes('w-full gap-4'):
            # URL input
            url_input = ui.input(
                label='BookStack URL',
                placeholder='https://docs.firma.de',
                value=config.url if config else ''
            ).classes('w-full')
            ui.label('Vollständige URL Ihrer BookStack-Instanz').classes('text-xs text-grey-6')
            
            # API Token input
            token_input = ui.input(
                label='API-Token',
                placeholder='Token ID:Token Secret',
                password=True,
                password_toggle_button=True,
                value=existing_token
            ).classes('w-full')
            ui.label('Format: token_id:token_secret (aus BookStack Einstellungen)').classes('text-xs text-grey-6')
            
            # Shelf name input
            shelf_input = ui.input(
                label='Standard-Shelf-Name (Regal)',
                placeholder='Ninox Datenbanken',
                value=config.default_shelf_name if config else 'Ninox Datenbanken'
            ).classes('w-full')
            ui.label('Name des Regals, in dem alle Datenbank-Bücher gespeichert werden').classes('text-xs text-grey-6')
            
            # Active switch
            is_active_switch = ui.switch(
                'Aktiv',
                value=config.is_active if config else True
            )
        
        error_label = ui.label('').classes('text-negative')
        error_label.visible = False
        
        async def save_config():
            """Save BookStack configuration"""
            url = url_input.value.strip()
            token = token_input.value.strip()
            shelf_name = shelf_input.value.strip()
            is_active = is_active_switch.value
            
            if not url:
                error_label.text = 'Bitte geben Sie eine URL ein'
                error_label.visible = True
                return
            
            if not token:
                error_label.text = 'Bitte geben Sie einen API-Token ein'
                error_label.visible = True
                return
            
            if not shelf_name:
                error_label.text = 'Bitte geben Sie einen Shelf-Namen ein'
                error_label.visible = True
                return
            
            db = get_db()
            try:
                if config:
                    # Update existing
                    config.url = url
                    config.api_token_encrypted = encryption.encrypt(token)
                    config.default_shelf_name = shelf_name
                    config.is_active = is_active
                    config.last_test_success = None  # Reset test status
                    db.merge(config)
                else:
                    # Create new
                    new_config = BookstackConfig(
                        server_id=server.id,
                        url=url,
                        api_token_encrypted=encryption.encrypt(token),
                        default_shelf_name=shelf_name,
                        is_active=is_active
                    )
                    db.add(new_config)
                
                db.commit()
                
                Toast.success(f'BookStack konfiguriert für {server.name}')
                dialog.close()
                reload_callback()
                
            except Exception as e:
                error_label.text = f'Fehler beim Speichern: {str(e)}'
                error_label.visible = True
            finally:
                db.close()
        
        # Buttons
        with ui.row().classes('w-full justify-end gap-2 mt-4'):
            ui.button('Abbrechen', on_click=dialog.close).props('flat')
            ui.button('Speichern', icon='save', on_click=save_config).props('color=primary')
    
    dialog.open()


def test_bookstack_connection(server: Server, config: BookstackConfig, reload_callback):
    """Test connection to BookStack"""
    from ..api.bookstack_client import BookStackClient
    from ..utils.encryption import get_encryption_manager
    
    encryption = get_encryption_manager()
    
    try:
        # Decrypt token
        api_token = encryption.decrypt(config.api_token_encrypted)
        
        # Create client
        client = BookStackClient(config.url, api_token)
        
        # Test connection
        ui.notify('Teste Verbindung zu BookStack...', type='info')
        success, error = client.test_connection()
        
        # Update config
        db = get_db()
        try:
            config.last_test_at = datetime.now()
            config.last_test_success = success
            config.last_test_error = error if not success else None
            db.merge(config)
            db.commit()
        finally:
            db.close()
        
        if success:
            Toast.success(f'✓ Verbindung zu BookStack erfolgreich!')
        else:
            Toast.error(f'✗ Verbindung fehlgeschlagen: {error}')
        
        reload_callback()
        
    except Exception as e:
        Toast.error(f'Fehler beim Testen: {str(e)}')
