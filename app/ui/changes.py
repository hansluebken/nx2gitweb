"""
Changes page for Ninox2Git
Shows all changelog entries with filtering and search capabilities
"""
from nicegui import ui
from datetime import datetime, timedelta
from typing import Optional, List
from sqlalchemy.orm import joinedload
from ..database import get_db
from ..models.server import Server
from ..models.team import Team
from ..models.database import Database
from ..models.changelog import ChangeLog
from .components import (
    NavHeader, Card, Toast, EmptyState, format_datetime,
    PRIMARY_COLOR, SUCCESS_COLOR, WARNING_COLOR
)


def render(user):
    """
    Render the changes page
    
    Args:
        user: Current user object
    """
    ui.colors(primary=PRIMARY_COLOR)
    
    # Navigation header
    NavHeader(user, 'changes').render()
    
    # Main content
    with ui.column().classes('w-full p-6 gap-6').style('max-width: 1400px; margin: 0 auto;'):
        ui.label('Änderungshistorie').classes('text-h4 font-bold mb-2')
        ui.label(
            'Übersicht aller Änderungen an Ninox-Datenbanken mit KI-generierten Beschreibungen.'
        ).classes('text-grey-7 mb-4')
        
        # Filter section
        filter_container = ui.row().classes('w-full gap-4 mb-4')
        
        # Results container
        results_container = ui.column().classes('w-full gap-4')
        
        # Pagination state
        state = {
            'page': 0,
            'page_size': 20,
            'total': 0,
            'filters': {
                'server_id': None,
                'team_id': None,
                'database_id': None,
                'date_from': None,
                'date_to': None,
                'search': '',
            }
        }
        
        # Build filter UI
        with filter_container:
            render_filters(user, state, results_container)
        
        # Initial load
        load_changes(user, state, results_container)


def render_filters(user, state: dict, results_container):
    """Render filter controls"""
    db = get_db()
    try:
        # Get servers for filter
        if user.is_admin:
            servers = db.query(Server).filter(Server.is_active == True).all()
        else:
            servers = db.query(Server).filter(
                Server.user_id == user.id,
                Server.is_active == True
            ).all()
        
        server_options = {s.id: s.name for s in servers}
        server_options_list = [{'label': 'Alle Server', 'value': None}] + [
            {'label': name, 'value': id} for id, name in server_options.items()
        ]
        
    finally:
        db.close()
    
    # Server filter
    server_select = ui.select(
        label='Server',
        options=server_options_list,
        value=None,
        on_change=lambda e: on_server_change(e.value, state, results_container, team_select, database_select, user)
    ).classes('w-48').props('outlined dense')
    
    # Team filter (populated dynamically)
    team_select = ui.select(
        label='Team',
        options=[{'label': 'Alle Teams', 'value': None}],
        value=None,
        on_change=lambda e: on_team_change(e.value, state, results_container, database_select, user)
    ).classes('w-48').props('outlined dense')
    
    # Database filter (populated dynamically)
    database_select = ui.select(
        label='Datenbank',
        options=[{'label': 'Alle Datenbanken', 'value': None}],
        value=None,
        on_change=lambda e: on_database_change(e.value, state, results_container, user)
    ).classes('w-48').props('outlined dense')
    
    # Date range
    with ui.row().classes('gap-2'):
        date_from = ui.input(
            label='Von',
            placeholder='TT.MM.JJJJ'
        ).classes('w-32').props('outlined dense')
        
        date_to = ui.input(
            label='Bis',
            placeholder='TT.MM.JJJJ'
        ).classes('w-32').props('outlined dense')
    
    # Search
    search_input = ui.input(
        label='Suche',
        placeholder='In Beschreibungen suchen...'
    ).classes('w-64').props('outlined dense clearable')
    
    # Search button
    ui.button(
        'Suchen',
        icon='search',
        on_click=lambda: apply_search_filters(
            state, results_container, user,
            search_input.value,
            date_from.value,
            date_to.value
        )
    ).props('dense')
    
    # Reset button
    ui.button(
        'Zurücksetzen',
        icon='refresh',
        on_click=lambda: reset_filters(
            state, results_container, user,
            server_select, team_select, database_select,
            search_input, date_from, date_to
        )
    ).props('flat dense')


def on_server_change(server_id, state, results_container, team_select, database_select, user):
    """Handle server filter change"""
    state['filters']['server_id'] = server_id
    state['filters']['team_id'] = None
    state['filters']['database_id'] = None
    state['page'] = 0
    
    # Update team options
    db = get_db()
    try:
        if server_id:
            teams = db.query(Team).filter(Team.server_id == server_id).all()
            team_options = [{'label': 'Alle Teams', 'value': None}] + [
                {'label': t.name, 'value': t.id} for t in teams
            ]
        else:
            team_options = [{'label': 'Alle Teams', 'value': None}]
        
        team_select.options = team_options
        team_select.value = None
        database_select.options = [{'label': 'Alle Datenbanken', 'value': None}]
        database_select.value = None
    finally:
        db.close()
    
    load_changes(user, state, results_container)


def on_team_change(team_id, state, results_container, database_select, user):
    """Handle team filter change"""
    state['filters']['team_id'] = team_id
    state['filters']['database_id'] = None
    state['page'] = 0
    
    # Update database options
    db = get_db()
    try:
        if team_id:
            databases = db.query(Database).filter(Database.team_id == team_id).all()
            db_options = [{'label': 'Alle Datenbanken', 'value': None}] + [
                {'label': d.name, 'value': d.id} for d in databases
            ]
        else:
            db_options = [{'label': 'Alle Datenbanken', 'value': None}]
        
        database_select.options = db_options
        database_select.value = None
    finally:
        db.close()
    
    load_changes(user, state, results_container)


def on_database_change(database_id, state, results_container, user):
    """Handle database filter change"""
    state['filters']['database_id'] = database_id
    state['page'] = 0
    load_changes(user, state, results_container)


def apply_search_filters(state, results_container, user, search_text, date_from, date_to):
    """Apply text search and date filters"""
    state['filters']['search'] = search_text or ''
    
    # Parse dates
    try:
        if date_from:
            state['filters']['date_from'] = datetime.strptime(date_from, '%d.%m.%Y')
        else:
            state['filters']['date_from'] = None
    except ValueError:
        state['filters']['date_from'] = None
    
    try:
        if date_to:
            state['filters']['date_to'] = datetime.strptime(date_to, '%d.%m.%Y')
        else:
            state['filters']['date_to'] = None
    except ValueError:
        state['filters']['date_to'] = None
    
    state['page'] = 0
    load_changes(user, state, results_container)


def reset_filters(state, results_container, user, server_select, team_select, database_select, search_input, date_from, date_to):
    """Reset all filters"""
    state['filters'] = {
        'server_id': None,
        'team_id': None,
        'database_id': None,
        'date_from': None,
        'date_to': None,
        'search': '',
    }
    state['page'] = 0
    
    server_select.value = None
    team_select.options = [{'label': 'Alle Teams', 'value': None}]
    team_select.value = None
    database_select.options = [{'label': 'Alle Datenbanken', 'value': None}]
    database_select.value = None
    search_input.value = ''
    date_from.value = ''
    date_to.value = ''
    
    load_changes(user, state, results_container)


def load_changes(user, state: dict, container):
    """Load and display changelog entries"""
    container.clear()
    
    db = get_db()
    try:
        # Build query
        query = db.query(ChangeLog).join(Database).join(Team).join(Server)
        
        # Apply user filter (non-admins can only see their servers)
        if not user.is_admin:
            query = query.filter(Server.user_id == user.id)
        
        # Apply filters
        filters = state['filters']
        
        if filters['server_id']:
            query = query.filter(Server.id == filters['server_id'])
        
        if filters['team_id']:
            query = query.filter(Team.id == filters['team_id'])
        
        if filters['database_id']:
            query = query.filter(ChangeLog.database_id == filters['database_id'])
        
        if filters['date_from']:
            query = query.filter(ChangeLog.commit_date >= filters['date_from'])
        
        if filters['date_to']:
            # Add one day to include the entire end date
            end_date = filters['date_to'] + timedelta(days=1)
            query = query.filter(ChangeLog.commit_date < end_date)
        
        if filters['search']:
            search_term = f"%{filters['search']}%"
            query = query.filter(
                (ChangeLog.ai_summary.ilike(search_term)) |
                (ChangeLog.ai_details.ilike(search_term)) |
                (ChangeLog.commit_message.ilike(search_term))
            )
        
        # Get total count
        total = query.count()
        state['total'] = total
        
        # Apply pagination
        page_size = state['page_size']
        offset = state['page'] * page_size
        
        changelogs = query.order_by(
            ChangeLog.commit_date.desc()
        ).offset(offset).limit(page_size).all()
        
        with container:
            # Results header
            render_results_header(state, total)
            
            if not changelogs:
                render_empty_state()
            else:
                # Results list
                for changelog in changelogs:
                    render_changelog_card(changelog, db)
                
                # Pagination
                if total > page_size:
                    render_pagination(state, container, user)
    
    finally:
        db.close()


def render_results_header(state: dict, total: int):
    """Render results count and active filters"""
    filters = state['filters']
    active_filters = []
    
    if filters['server_id']:
        active_filters.append('Server')
    if filters['team_id']:
        active_filters.append('Team')
    if filters['database_id']:
        active_filters.append('Datenbank')
    if filters['date_from'] or filters['date_to']:
        active_filters.append('Zeitraum')
    if filters['search']:
        active_filters.append(f'Suche: "{filters["search"]}"')
    
    with ui.row().classes('w-full items-center justify-between mb-4'):
        ui.label(f'{total} Änderungen gefunden').classes('text-h6')
        
        if active_filters:
            with ui.row().classes('items-center gap-2'):
                ui.label('Filter:').classes('text-sm text-grey-7')
                for f in active_filters:
                    ui.badge(f, color='primary').props('dense')


def render_empty_state():
    """Render empty state when no changes found"""
    with ui.column().classes('w-full items-center justify-center p-12 gap-4'):
        ui.icon('history', size='4rem', color='grey')
        ui.label('Keine Änderungen gefunden').classes('text-h6 text-grey-7')
        ui.label(
            'Passen Sie die Filter an oder führen Sie eine Synchronisierung durch.'
        ).classes('text-grey-6 text-center')


def render_changelog_card(changelog: ChangeLog, db):
    """Render a single changelog card"""
    # Get database info
    database = db.query(Database).filter(Database.id == changelog.database_id).first()
    team = db.query(Team).filter(Team.id == database.team_id).first() if database else None
    server = db.query(Server).filter(Server.id == team.server_id).first() if team else None
    
    # Format date
    date_str = changelog.commit_date.strftime('%d.%m.%Y %H:%M') if changelog.commit_date else 'Unbekannt'
    
    with ui.card().classes('w-full p-4'):
        # Header row
        with ui.row().classes('w-full items-start justify-between mb-3'):
            # Left: Database path and date
            with ui.column().classes('gap-1'):
                # Breadcrumb path
                with ui.row().classes('items-center gap-1'):
                    if server:
                        ui.label(server.name).classes('text-xs text-grey-6')
                        ui.icon('chevron_right', size='xs').classes('text-grey-5')
                    if team:
                        ui.label(team.name).classes('text-xs text-grey-6')
                        ui.icon('chevron_right', size='xs').classes('text-grey-5')
                    if database:
                        ui.label(database.name).classes('text-sm font-bold')
                
                # Date
                with ui.row().classes('items-center gap-2'):
                    ui.icon('schedule', size='xs').classes('text-grey-6')
                    ui.label(date_str).classes('text-sm text-grey-7')
            
            # Right: Stats and badges
            with ui.row().classes('items-center gap-2'):
                if changelog.files_changed > 0:
                    ui.badge(f'{changelog.files_changed} Datei(en)', color='grey').props('dense')
                if changelog.additions > 0:
                    ui.badge(f'+{changelog.additions}', color='positive').props('dense')
                if changelog.deletions > 0:
                    ui.badge(f'-{changelog.deletions}', color='negative').props('dense')
                if changelog.has_token_info:
                    ui.badge(f'{changelog.total_tokens} Tokens', color='amber').props('dense')
                if changelog.ai_provider:
                    ui.badge(changelog.ai_provider, color='purple').props('dense')
        
        # AI Summary
        if changelog.ai_summary:
            ui.label(changelog.ai_summary).classes('text-grey-8 mb-3')
        elif changelog.commit_message:
            msg = changelog.commit_message[:200]
            if len(changelog.commit_message) > 200:
                msg += '...'
            ui.label(msg).classes('text-grey-7 italic mb-3')
        
        # Changed items preview
        if changelog.changed_items:
            tables = changelog.changed_tables
            if tables:
                with ui.row().classes('items-center gap-2 mb-3'):
                    ui.icon('table_chart', size='xs').classes('text-grey-6')
                    ui.label(f'Tabellen: {", ".join(tables[:5])}').classes('text-xs text-grey-6')
                    if len(tables) > 5:
                        ui.label(f'+{len(tables) - 5} weitere').classes('text-xs text-grey-5')
        
        # Expandable details
        if changelog.ai_details or changelog.diff_patch:
            with ui.expansion('Details anzeigen', icon='expand_more').classes('w-full').props('dense'):
                if changelog.ai_details:
                    ui.markdown(changelog.ai_details).classes('text-sm mb-4')
                
                if changelog.changed_items:
                    ui.label('Geänderte Elemente:').classes('font-bold text-sm mb-2')
                    with ui.column().classes('gap-1 mb-4'):
                        for item in changelog.changed_items[:15]:
                            render_changed_item_inline(item)
                        if len(changelog.changed_items) > 15:
                            ui.label(f'... und {len(changelog.changed_items) - 15} weitere').classes('text-xs text-grey-6')
                
                if changelog.diff_patch:
                    with ui.expansion('Diff anzeigen', icon='code').classes('w-full').props('dense'):
                        ui.html(render_diff_html(changelog.diff_patch), sanitize=False).classes('w-full')
        
        # Footer with commit link
        with ui.row().classes('w-full items-center justify-between mt-2'):
            with ui.row().classes('items-center gap-4'):
                if changelog.commit_url:
                    ui.link(
                        f'Commit {changelog.short_sha}',
                        changelog.commit_url,
                        new_tab=True
                    ).classes('text-xs')
                else:
                    ui.label(f'Commit {changelog.short_sha}').classes('text-xs text-grey-6')
                
                # Token details
                if changelog.has_token_info:
                    with ui.row().classes('items-center gap-1'):
                        ui.icon('token', size='xs').classes('text-amber-600')
                        ui.label(f'↓{changelog.ai_input_tokens or 0} ↑{changelog.ai_output_tokens or 0}').classes('text-xs text-grey-6')
            
            # Action buttons
            with ui.row().classes('gap-2'):
                if database:
                    ui.button(
                        'Zur Datenbank',
                        icon='folder',
                        on_click=lambda d=database: ui.navigate.to(f'/sync?database={d.id}')
                    ).props('flat dense size=sm')


def render_changed_item_inline(item: dict):
    """Render a changed item inline"""
    table = item.get('table', '?')
    field = item.get('field', '')
    code_type = item.get('code_type', '')
    change_type = item.get('change_type', 'modified')
    
    icon_map = {
        'added': ('add_circle', 'positive'),
        'modified': ('edit', 'primary'),
        'removed': ('remove_circle', 'negative'),
        'renamed': ('drive_file_rename_outline', 'warning'),
    }
    icon, color = icon_map.get(change_type, ('circle', 'grey'))
    
    path_parts = [table]
    if field:
        path_parts.append(field)
    if code_type:
        path_parts.append(code_type)
    path = '.'.join(path_parts)
    
    with ui.row().classes('items-center gap-1'):
        ui.icon(icon, size='xs').classes(f'text-{color}')
        ui.label(path).classes('text-xs font-mono')
        
        # Show additions/deletions
        adds = item.get('additions', 0)
        dels = item.get('deletions', 0)
        if adds > 0:
            ui.label(f'+{adds}').classes('text-xs text-positive')
        if dels > 0:
            ui.label(f'-{dels}').classes('text-xs text-negative')


def render_diff_html(diff_patch: str) -> str:
    """Render diff with syntax highlighting"""
    if not diff_patch:
        return '<span class="text-grey-6">Kein Diff verfügbar</span>'
    
    lines = diff_patch.split('\n')
    html_parts = ['''
    <style>
        .diff-container {
            font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
            font-size: 12px;
            line-height: 1.4;
            background: #1e1e1e;
            color: #d4d4d4;
            border-radius: 4px;
            padding: 8px;
            overflow-x: auto;
            max-height: 400px;
        }
        .diff-line-add { background: rgba(40, 167, 69, 0.2); color: #98c379; }
        .diff-line-del { background: rgba(220, 53, 69, 0.2); color: #e06c75; }
        .diff-line-header { color: #61afef; font-weight: bold; }
    </style>
    <div class="diff-container">
    ''']
    
    for line in lines:
        escaped_line = (line
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;'))
        
        if line.startswith('+') and not line.startswith('+++'):
            html_parts.append(f'<div class="diff-line-add">{escaped_line}</div>')
        elif line.startswith('-') and not line.startswith('---'):
            html_parts.append(f'<div class="diff-line-del">{escaped_line}</div>')
        elif line.startswith('@@') or line.startswith('---') or line.startswith('+++'):
            html_parts.append(f'<div class="diff-line-header">{escaped_line}</div>')
        else:
            html_parts.append(f'<div>{escaped_line}</div>')
    
    html_parts.append('</div>')
    return ''.join(html_parts)


def render_pagination(state: dict, container, user):
    """Render pagination controls"""
    total = state['total']
    page_size = state['page_size']
    current_page = state['page']
    total_pages = (total + page_size - 1) // page_size
    
    with ui.row().classes('w-full justify-center items-center gap-2 mt-4'):
        # Previous button
        ui.button(
            icon='chevron_left',
            on_click=lambda: go_to_page(current_page - 1, state, container, user)
        ).props('flat dense').bind_enabled_from(state, 'page', lambda p: p > 0)
        
        # Page info
        ui.label(f'Seite {current_page + 1} von {total_pages}').classes('text-grey-7')
        
        # Next button
        ui.button(
            icon='chevron_right',
            on_click=lambda: go_to_page(current_page + 1, state, container, user)
        ).props('flat dense').bind_enabled_from(
            state, 'page', 
            lambda p: (p + 1) * state['page_size'] < state['total']
        )


def go_to_page(page: int, state: dict, container, user):
    """Navigate to a specific page"""
    state['page'] = max(0, page)
    load_changes(user, state, container)
