"""
Chat page for Ninox Database Assistant
Real-time chat with Gemini AI about database structure
"""
from nicegui import ui, app
import asyncio
import uuid
import json
import logging
from datetime import datetime
from ..database import get_db
from ..models.server import Server
from ..models.team import Team
from ..models.database import Database
from ..models.ai_config import AIConfig, AIProvider
from ..utils.encryption import get_encryption_manager
from ..utils.github_utils import sanitize_name, get_repo_name_from_server
from ..api.github_manager import GitHubManager
from ..services.chat_service import get_chat_service, NinoxChatService
from .components import NavHeader, PRIMARY_COLOR

logger = logging.getLogger(__name__)


def render(user):
    """Render the chat page"""
    
    ui.colors(primary=PRIMARY_COLOR)
    NavHeader(user, 'chat').render()
    
    # Session state
    chat_state = {
        'service': None,
        'session_id': None,
        'selected_server': None,
        'selected_team': None,
        'selected_database': None,
        'context_loaded': False,
        'messages': [],
        'is_loading': False,
    }
    
    with ui.column().classes('w-full max-w-5xl mx-auto p-4 gap-4'):
        # Header
        with ui.row().classes('w-full items-center gap-4'):
            ui.icon('chat', size='lg').classes('text-primary')
            ui.label('Ninox Chat').classes('text-h4 font-bold')
            ui.label('Frag Gemini zu deiner Datenbank').classes('text-grey-6')
        
        # Selection row
        with ui.card().classes('w-full p-4'):
            with ui.row().classes('w-full items-end gap-4 flex-wrap'):
                # Server selection
                server_select = ui.select(
                    label='Server',
                    options=[],
                    with_input=True
                ).classes('min-w-48')
                
                # Team selection
                team_select = ui.select(
                    label='Team',
                    options=[],
                    with_input=True
                ).classes('min-w-48').props('disable')
                
                # Database selection
                db_select = ui.select(
                    label='Datenbank',
                    options=[],
                    with_input=True
                ).classes('min-w-48').props('disable')
                
                # Load context button
                load_btn = ui.button(
                    'Chat starten',
                    icon='play_arrow',
                    color='primary'
                ).props('disable')
                
                # Status indicator
                status_label = ui.label('').classes('text-sm text-grey-6')
        
        # Chat container
        chat_container = ui.column().classes('w-full').style('display: none;')
        
        with chat_container:
            # Chat info bar
            with ui.row().classes('w-full items-center justify-between p-2 bg-grey-1 rounded'):
                chat_info = ui.label('').classes('text-sm font-medium')
                with ui.row().classes('items-center gap-2'):
                    token_label = ui.label('Tokens: ↓0 ↑0').classes('text-xs text-grey-6')
                    model_label = ui.label('').classes('text-xs text-grey-6')
            
            # Messages area
            messages_container = ui.scroll_area().classes('w-full border rounded').style('height: 500px;')
            
            # Input area
            with ui.row().classes('w-full items-end gap-2'):
                message_input = ui.textarea(
                    placeholder='Nachricht eingeben... (Enter zum Senden, Shift+Enter für neue Zeile)'
                ).classes('flex-1').props('autogrow rows=1 outlined')
                
                send_btn = ui.button(
                    icon='send',
                    color='primary'
                ).props('round').classes('mb-1')
    
    # Load servers
    def load_servers():
        db = get_db()
        try:
            servers = db.query(Server).filter(Server.user_id == user.id).all()
            server_options = {s.id: s.name for s in servers}
            server_select.options = server_options
            server_select.update()
        finally:
            db.close()
    
    # On server change
    def on_server_change(e):
        server_id = e.value
        if not server_id:
            team_select.options = []
            team_select.props('disable')
            return
        
        chat_state['selected_server'] = server_id
        
        db = get_db()
        try:
            teams = db.query(Team).filter(
                Team.server_id == server_id,
                Team.is_active == True
            ).all()
            team_options = {t.id: t.name for t in teams}
            team_select.options = team_options
            team_select.props(remove='disable')
            team_select.value = None
            db_select.options = []
            db_select.props('disable')
            load_btn.props('disable')
            team_select.update()
        finally:
            db.close()
    
    # On team change
    def on_team_change(e):
        team_id = e.value
        if not team_id:
            db_select.options = []
            db_select.props('disable')
            return
        
        chat_state['selected_team'] = team_id
        
        db = get_db()
        try:
            databases = db.query(Database).filter(
                Database.team_id == team_id,
                Database.is_excluded == False
            ).all()
            # Only show databases with github_path (already synced)
            db_options = {d.id: d.name for d in databases if d.github_path}
            if db_options:
                db_select.options = db_options
                db_select.props(remove='disable')
            else:
                db_select.options = {}
                status_label.text = 'Keine synchronisierten Datenbanken gefunden'
            db_select.value = None
            load_btn.props('disable')
            db_select.update()
        finally:
            db.close()
    
    # On database change
    def on_db_change(e):
        if e.value:
            chat_state['selected_database'] = e.value
            load_btn.props(remove='disable')
        else:
            load_btn.props('disable')
    
    # Load context and start chat
    async def start_chat():
        if not chat_state['selected_database']:
            ui.notify('Bitte wähle eine Datenbank aus', type='warning')
            return
        
        load_btn.props('loading disable')
        status_label.text = 'Lade Datenbankstruktur...'
        
        try:
            db = get_db()
            try:
                # Get database info
                database = db.query(Database).get(chat_state['selected_database'])
                team = db.query(Team).get(chat_state['selected_team'])
                server = db.query(Server).get(chat_state['selected_server'])
                
                if not database or not database.github_path:
                    raise ValueError("Datenbank nicht gefunden oder nicht synchronisiert")
                
                # Get structure from GitHub
                enc_manager = get_encryption_manager()
                github_token = enc_manager.decrypt(user.github_token_encrypted)
                github = GitHubManager(github_token, user.github_organization)
                
                repo_name = get_repo_name_from_server(server)
                repo = github.ensure_repository(repo_name)
                
                structure_path = f"{database.github_path}/{sanitize_name(database.name)}-structure.json"
                structure_content = github.get_file_content(repo, structure_path)
                
                if not structure_content:
                    raise ValueError(f"Strukturdatei nicht gefunden: {structure_path}")
                
                structure_json = json.loads(structure_content)
                
                # Get chat service
                service = get_chat_service()
                if not service:
                    raise ValueError("Gemini ist nicht konfiguriert. Bitte unter Admin → KI-Konfiguration einrichten.")
                
                # Create session
                session_id = str(uuid.uuid4())
                service.create_session(session_id, database.name, structure_json)
                
                chat_state['service'] = service
                chat_state['session_id'] = session_id
                chat_state['context_loaded'] = True
                chat_state['messages'] = []
                
                # Update UI
                chat_container.style('display: block;')
                chat_info.text = f'Chat mit: {database.name}'
                model_label.text = f'Modell: {service.model}'
                status_label.text = ''
                
                # Clear messages
                messages_container.clear()
                
                # Add welcome message
                with messages_container:
                    render_message(
                        'assistant',
                        f'Hallo! Ich bin dein Ninox-Assistent für die Datenbank **"{database.name}"**.\n\n'
                        f'Ich kenne die Struktur mit {len(structure_json.get("types", []))} Tabellen und kann dir helfen bei:\n'
                        f'- Fragen zur Datenbankstruktur\n'
                        f'- Ninox-Formeln schreiben und erklären\n'
                        f'- Best Practices und Optimierungen\n'
                        f'- Fehlersuche in Formeln\n\n'
                        f'Stelle mir deine Fragen!'
                    )
                
                load_btn.props(remove='loading disable')
                load_btn.text = 'Neu starten'
                load_btn._props['icon'] = 'refresh'
                
                ui.notify('Chat gestartet!', type='positive')
                
                # Focus input
                message_input.run_method('focus')
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error starting chat: {e}")
            status_label.text = f'Fehler: {str(e)}'
            load_btn.props(remove='loading disable')
            ui.notify(f'Fehler: {str(e)}', type='negative')
    
    # Render a chat message
    def render_message(role: str, content: str, is_streaming: bool = False):
        """Render a chat message bubble"""
        is_user = role == 'user'
        
        with ui.row().classes(f'w-full {"justify-end" if is_user else "justify-start"} mb-2'):
            with ui.card().classes(
                f'max-w-3xl p-3 {"bg-primary text-white" if is_user else "bg-grey-2"}'
            ).style('border-radius: 16px;'):
                if is_user:
                    ui.label(content).classes('whitespace-pre-wrap')
                else:
                    # Markdown for assistant
                    msg_container = ui.column().classes('w-full')
                    with msg_container:
                        ui.markdown(content).classes('w-full')
                    
                    if is_streaming:
                        # Return container for updating
                        return msg_container
        
        return None
    
    # Send message
    async def send_message():
        message = message_input.value.strip()
        if not message:
            return
        
        if not chat_state['context_loaded'] or not chat_state['service']:
            ui.notify('Bitte erst eine Datenbank auswählen und Chat starten', type='warning')
            return
        
        if chat_state['is_loading']:
            return
        
        chat_state['is_loading'] = True
        send_btn.props('loading disable')
        message_input.props('disable')
        
        # Clear input
        user_msg = message
        message_input.value = ''
        
        # Add user message
        with messages_container:
            render_message('user', user_msg)
        
        # Scroll to bottom
        await asyncio.sleep(0.1)
        messages_container.scroll_to(percent=1.0)
        
        # Add assistant message placeholder with streaming
        with messages_container:
            with ui.row().classes('w-full justify-start mb-2'):
                with ui.card().classes('max-w-3xl p-3 bg-grey-2').style('border-radius: 16px;') as msg_card:
                    msg_content = ui.markdown('').classes('w-full')
        
        try:
            # Stream response
            service = chat_state['service']
            session_id = chat_state['session_id']
            
            full_response = ""
            
            # Use non-streaming for now (NiceGUI streaming is complex)
            # TODO: Implement proper streaming with SSE
            response = service.chat(session_id, user_msg)
            full_response = response
            msg_content.content = full_response
            
            # Update token count
            session = service.get_session(session_id)
            if session:
                token_label.text = f'Tokens: ↓{session.total_input_tokens:,} ↑{session.total_output_tokens:,}'
            
        except Exception as e:
            logger.error(f"Chat error: {e}")
            msg_content.content = f'**Fehler:** {str(e)}'
            ui.notify(f'Fehler: {str(e)}', type='negative')
        
        finally:
            chat_state['is_loading'] = False
            send_btn.props(remove='loading disable')
            message_input.props(remove='disable')
            message_input.run_method('focus')
            
            # Scroll to bottom
            await asyncio.sleep(0.1)
            messages_container.scroll_to(percent=1.0)
    
    # Event handlers
    server_select.on('update:model-value', on_server_change)
    team_select.on('update:model-value', on_team_change)
    db_select.on('update:model-value', on_db_change)
    load_btn.on_click(start_chat)
    send_btn.on_click(send_message)
    
    # Handle Enter key in textarea
    async def handle_keydown(e):
        if e.args.get('key') == 'Enter' and not e.args.get('shiftKey'):
            await send_message()
    
    message_input.on('keydown', handle_keydown)
    
    # Load servers on page load
    load_servers()
