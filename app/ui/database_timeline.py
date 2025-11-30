"""
Database Timeline Component for Ninox2Git
Shows change history for a database with AI-generated descriptions
"""
from nicegui import ui
from datetime import datetime
from typing import Optional, List
from ..database import get_db
from ..models.database import Database
from ..models.changelog import ChangeLog
from .components import Card, PRIMARY_COLOR, SUCCESS_COLOR, WARNING_COLOR


def show_database_timeline_dialog(database: Database):
    """
    Show a dialog with the database change timeline.
    
    Args:
        database: Database model instance
    """
    with ui.dialog() as dialog, ui.card().classes('w-full p-0').style('max-width: 800px; max-height: 90vh;'):
        # Header
        with ui.row().classes('w-full items-center justify-between p-4 bg-primary'):
            with ui.row().classes('items-center gap-3'):
                ui.icon('timeline', size='md', color='white')
                ui.label(f'Timeline: {database.name}').classes('text-h5 font-bold text-white')
            ui.button(icon='close', on_click=dialog.close).props('flat round dense color=white')
        
        # Content
        with ui.scroll_area().classes('w-full').style('height: calc(90vh - 80px);'):
            with ui.column().classes('w-full p-4 gap-4'):
                render_database_timeline(database)
    
    dialog.open()


def render_database_timeline(database: Database, max_entries: int = 50):
    """
    Render the timeline for a database.
    
    Args:
        database: Database model instance
        max_entries: Maximum number of entries to show
    """
    db = get_db()
    try:
        changelogs = db.query(ChangeLog).filter(
            ChangeLog.database_id == database.id
        ).order_by(ChangeLog.commit_date.desc()).limit(max_entries).all()
        
        if not changelogs:
            render_empty_timeline(database)
            return
        
        # Statistics summary
        render_timeline_stats(changelogs)
        
        ui.separator().classes('my-4')
        
        # Timeline entries
        ui.label('Änderungsverlauf').classes('text-h6 font-bold mb-2')
        
        for i, changelog in enumerate(changelogs):
            is_last = (i == len(changelogs) - 1)
            render_timeline_entry(changelog, is_last)
            
    finally:
        db.close()


def render_empty_timeline(database: Database):
    """Render empty state for timeline"""
    with ui.column().classes('w-full items-center justify-center p-8 gap-4'):
        ui.icon('history', size='4rem', color='grey')
        ui.label('Keine Änderungshistorie verfügbar').classes('text-h6 text-grey-7')
        ui.label(
            f'Die Historie für "{database.name}" wird bei zukünftigen '
            'Synchronisierungen automatisch aufgezeichnet.'
        ).classes('text-grey-6 text-center')
        
        with ui.card().classes('p-4 mt-4').style('background-color: #f5f5f5;'):
            ui.label('So funktioniert es:').classes('font-bold mb-2')
            with ui.column().classes('gap-1'):
                ui.label('1. Konfigurieren Sie einen KI-Provider im Admin-Panel').classes('text-sm')
                ui.label('2. Führen Sie eine Synchronisierung durch').classes('text-sm')
                ui.label('3. Änderungen werden automatisch analysiert und dokumentiert').classes('text-sm')


def render_timeline_stats(changelogs: List[ChangeLog]):
    """Render statistics summary for the timeline"""
    total_changes = len(changelogs)
    total_additions = sum(c.additions for c in changelogs)
    total_deletions = sum(c.deletions for c in changelogs)
    ai_analyzed = sum(1 for c in changelogs if c.has_ai_analysis)
    
    # Calculate total tokens
    total_input_tokens = sum(c.ai_input_tokens or 0 for c in changelogs)
    total_output_tokens = sum(c.ai_output_tokens or 0 for c in changelogs)
    total_tokens = total_input_tokens + total_output_tokens
    
    # Get unique tables changed
    tables_changed = set()
    for c in changelogs:
        if c.changed_items:
            for item in c.changed_items:
                if item.get('table'):
                    tables_changed.add(item['table'])
    
    with ui.row().classes('w-full gap-4 flex-wrap'):
        render_stat_mini_card('Änderungen', str(total_changes), 'history', PRIMARY_COLOR)
        render_stat_mini_card('Zeilen +', str(total_additions), 'add', SUCCESS_COLOR)
        render_stat_mini_card('Zeilen -', str(total_deletions), 'remove', '#ef5350')
        render_stat_mini_card('Tabellen', str(len(tables_changed)), 'table_chart', PRIMARY_COLOR)
        if ai_analyzed > 0:
            render_stat_mini_card('KI-Analysen', str(ai_analyzed), 'psychology', '#8B5CF6')
        if total_tokens > 0:
            # Format tokens with K suffix for readability
            token_display = f"{total_tokens:,}".replace(',', '.') if total_tokens < 10000 else f"{total_tokens // 1000}K"
            render_stat_mini_card('Tokens', token_display, 'token', '#F59E0B')


def render_stat_mini_card(title: str, value: str, icon: str, color: str):
    """Render a small statistics card"""
    with ui.card().classes('p-3').style(f'border-left: 3px solid {color}; min-width: 100px;'):
        with ui.row().classes('items-center gap-2'):
            ui.icon(icon, size='sm').style(f'color: {color};')
            with ui.column().classes('gap-0'):
                ui.label(value).classes('text-h6 font-bold')
                ui.label(title).classes('text-xs text-grey-7')


def render_timeline_entry(changelog: ChangeLog, is_last: bool = False):
    """
    Render a single timeline entry with vertical line connector.
    
    Args:
        changelog: ChangeLog model instance
        is_last: Whether this is the last entry (no connector line)
    """
    # Format date
    date_str = changelog.commit_date.strftime('%d.%m.%Y') if changelog.commit_date else 'Unbekannt'
    time_str = changelog.commit_date.strftime('%H:%M') if changelog.commit_date else ''
    
    with ui.row().classes('w-full'):
        # Left side: Timeline connector
        with ui.column().classes('items-center').style('width: 60px;'):
            # Date label
            ui.label(date_str).classes('text-xs text-grey-7 text-center')
            ui.label(time_str).classes('text-xs text-grey-6 text-center')
            
            # Dot
            dot_color = SUCCESS_COLOR if changelog.has_ai_analysis else '#9e9e9e'
            ui.html(f'''
                <div style="
                    width: 12px; 
                    height: 12px; 
                    border-radius: 50%; 
                    background-color: {dot_color};
                    margin: 8px 0;
                "></div>
            ''')
            
            # Vertical line (if not last)
            if not is_last:
                ui.html('''
                    <div style="
                        width: 2px; 
                        flex-grow: 1; 
                        background-color: #e0e0e0;
                        min-height: 40px;
                    "></div>
                ''')
        
        # Right side: Content card
        with ui.card().classes('flex-1 p-3 mb-2').style('background-color: #fafafa;'):
            # Header with stats
            with ui.row().classes('w-full items-center justify-between mb-2'):
                # Changed items summary
                if changelog.changed_items:
                    tables = changelog.changed_tables
                    if tables:
                        tables_text = ', '.join(tables[:3])
                        if len(tables) > 3:
                            tables_text += f' (+{len(tables) - 3})'
                        ui.label(tables_text).classes('font-medium text-sm')
                    else:
                        ui.label(f'{changelog.files_changed} Datei(en)').classes('font-medium text-sm')
                else:
                    ui.label(f'{changelog.files_changed} Datei(en)').classes('font-medium text-sm')
                
                # Stats badges
                with ui.row().classes('items-center gap-2'):
                    if changelog.additions > 0:
                        ui.badge(f'+{changelog.additions}', color='positive').props('dense')
                    if changelog.deletions > 0:
                        ui.badge(f'-{changelog.deletions}', color='negative').props('dense')
            
            # AI Summary
            if changelog.ai_summary:
                ui.label(changelog.ai_summary).classes('text-sm text-grey-8 mb-2')
            elif changelog.commit_message:
                # Fallback to commit message
                msg = changelog.commit_message[:150]
                if len(changelog.commit_message) > 150:
                    msg += '...'
                ui.label(msg).classes('text-sm text-grey-7 italic mb-2')
            
            # Details expansion
            if changelog.ai_details or changelog.changed_items:
                with ui.expansion('Details', icon='expand_more').classes('w-full').props('dense'):
                    if changelog.ai_details:
                        ui.markdown(changelog.ai_details).classes('text-sm')
                    
                    if changelog.changed_items:
                        ui.label('Geänderte Elemente:').classes('text-sm font-medium mt-2 mb-1')
                        with ui.column().classes('gap-1'):
                            for item in changelog.changed_items[:10]:
                                render_changed_item(item)
                            if len(changelog.changed_items) > 10:
                                ui.label(f'... und {len(changelog.changed_items) - 10} weitere').classes('text-xs text-grey-6')
            
            # Footer with commit info
            with ui.row().classes('w-full items-center justify-between mt-2'):
                with ui.row().classes('items-center gap-2'):
                    if changelog.commit_url:
                        ui.link(
                            f'Commit {changelog.short_sha}',
                            changelog.commit_url,
                            new_tab=True
                        ).classes('text-xs')
                    else:
                        ui.label(f'Commit {changelog.short_sha}').classes('text-xs text-grey-6')
                
                with ui.row().classes('items-center gap-3'):
                    # Token info
                    if changelog.has_token_info:
                        with ui.row().classes('items-center gap-1'):
                            ui.icon('token', size='xs').classes('text-amber-600')
                            ui.label(changelog.token_summary_text).classes('text-xs text-grey-6')
                    
                    # AI Provider info
                    if changelog.ai_provider:
                        with ui.row().classes('items-center gap-1'):
                            ui.icon('psychology', size='xs').classes('text-grey-6')
                            ui.label(changelog.ai_provider).classes('text-xs text-grey-6')


def render_changed_item(item: dict):
    """Render a single changed item"""
    table = item.get('table', '?')
    field = item.get('field', '')
    code_type = item.get('code_type', '')
    change_type = item.get('change_type', 'modified')
    
    # Icon based on change type
    icon_map = {
        'added': ('add_circle', 'positive'),
        'modified': ('edit', 'primary'),
        'removed': ('remove_circle', 'negative'),
        'renamed': ('drive_file_rename_outline', 'warning'),
    }
    icon, color = icon_map.get(change_type, ('circle', 'grey'))
    
    # Build path
    path_parts = [table]
    if field:
        path_parts.append(field)
    if code_type:
        path_parts.append(code_type)
    path = '.'.join(path_parts)
    
    with ui.row().classes('items-center gap-1'):
        ui.icon(icon, size='xs').classes(f'text-{color}')
        ui.label(path).classes('text-xs font-mono')


def render_timeline_inline(database_id: int, container, max_entries: int = 5):
    """
    Render a compact inline timeline (for embedding in other pages).
    
    Args:
        database_id: ID of the database
        container: UI container to render into
        max_entries: Maximum number of entries to show
    """
    container.clear()
    
    db = get_db()
    try:
        changelogs = db.query(ChangeLog).filter(
            ChangeLog.database_id == database_id
        ).order_by(ChangeLog.commit_date.desc()).limit(max_entries).all()
        
        with container:
            if not changelogs:
                ui.label('Keine Historie verfügbar').classes('text-grey-7 text-sm')
            else:
                for changelog in changelogs:
                    render_timeline_entry_compact(changelog)
    finally:
        db.close()


def render_timeline_entry_compact(changelog: ChangeLog):
    """Render a compact timeline entry for inline display"""
    date_str = changelog.commit_date.strftime('%d.%m.%Y %H:%M') if changelog.commit_date else ''
    
    with ui.row().classes('w-full items-start gap-2 py-1').style('border-bottom: 1px solid #eee;'):
        ui.label(date_str).classes('text-xs text-grey-6').style('min-width: 100px;')
        
        with ui.column().classes('flex-1 gap-0'):
            if changelog.ai_summary:
                summary = changelog.ai_summary[:80]
                if len(changelog.ai_summary) > 80:
                    summary += '...'
                ui.label(summary).classes('text-xs')
            else:
                ui.label(changelog.change_summary_text).classes('text-xs text-grey-7')
        
        with ui.row().classes('items-center gap-1'):
            if changelog.additions > 0:
                ui.label(f'+{changelog.additions}').classes('text-xs text-positive')
            if changelog.deletions > 0:
                ui.label(f'-{changelog.deletions}').classes('text-xs text-negative')
