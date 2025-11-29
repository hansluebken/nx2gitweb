"""
Ninox Code Viewer page for Ninox2Git
View and search extracted Ninox code files with syntax highlighting
"""
from nicegui import ui
import os
import json
from pathlib import Path
from ..database import get_db
from ..models.server import Server
from ..models.team import Team
from ..models.database import Database
from .components import (
    NavHeader, Card, Toast, EmptyState, PRIMARY_COLOR
)

# Base path for code storage
CODE_BASE_PATH = '/app/data/code'


def render(user):
    """Render the code viewer page"""
    ui.colors(primary=PRIMARY_COLOR)
    
    # Navigation header
    NavHeader(user, 'code-viewer').render()
    
    # Main content
    with ui.column().classes('w-full p-6 gap-4').style('max-width: 1800px; margin: 0 auto;'):
        ui.label('Ninox Code Viewer').classes('text-h4 font-bold mb-2')
        ui.label('Browse and search extracted Ninox scripts').classes('text-grey-7 mb-4')
        
        # Main layout: sidebar + code view
        with ui.row().classes('w-full gap-4').style('height: calc(100vh - 200px);'):
            # Left sidebar - file tree
            with ui.card().classes('p-4').style('width: 350px; height: 100%; overflow: auto;'):
                ui.label('Databases').classes('text-h6 font-bold mb-2')
                
                # Search box
                search_input = ui.input(
                    placeholder='Search code...',
                    on_change=lambda e: search_code(e.value, search_results_container)
                ).classes('w-full mb-4').props('outlined dense clearable')
                
                # Search results container (hidden by default)
                search_results_container = ui.column().classes('w-full').style('display: none;')
                
                # File tree container
                file_tree_container = ui.column().classes('w-full gap-1')
                
            # Right side - code display
            with ui.card().classes('flex-1 p-4').style('height: 100%; overflow: auto;'):
                # Code header
                code_header = ui.row().classes('w-full items-center justify-between mb-4')
                with code_header:
                    code_title = ui.label('Select a file to view').classes('text-h6 font-bold')
                    code_path_label = ui.label('').classes('text-grey-7 text-sm')
                
                # Code content with line numbers
                code_container = ui.column().classes('w-full')
                with code_container:
                    code_display = ui.html('').classes('w-full')
        
        # Load file tree
        load_file_tree(user, file_tree_container, code_title, code_path_label, code_display)


def load_file_tree(user, container, code_title, code_path_label, code_display):
    """Load the file tree showing available code files"""
    container.clear()
    
    if not os.path.exists(CODE_BASE_PATH):
        with container:
            ui.label('No code files found. Sync a database first.').classes('text-grey-7')
        return
    
    # Get servers the user has access to
    db = get_db()
    try:
        if user.is_admin:
            servers = db.query(Server).filter(Server.is_active == True).all()
        else:
            servers = db.query(Server).filter(
                Server.user_id == user.id,
                Server.is_active == True
            ).all()
        
        server_names = [s.name for s in servers]
    finally:
        db.close()
    
    # Scan code directory
    found_any = False
    
    with container:
        for server_dir in sorted(Path(CODE_BASE_PATH).iterdir()):
            if not server_dir.is_dir():
                continue
            
            # Check if user has access to this server
            server_name = server_dir.name
            # Sanitized names might differ, so we check loosely
            has_access = user.is_admin or any(
                server_name.lower() in s.lower() or s.lower() in server_name.lower() 
                for s in server_names
            )
            
            if not has_access:
                continue
            
            found_any = True
            
            # Server expander
            with ui.expansion(server_name, icon='dns').classes('w-full'):
                for team_dir in sorted(server_dir.iterdir()):
                    if not team_dir.is_dir():
                        continue
                    
                    # Team expander
                    with ui.expansion(team_dir.name, icon='group').classes('w-full ml-2'):
                        for db_dir in sorted(team_dir.iterdir()):
                            if not db_dir.is_dir():
                                continue
                            
                            code_dir = db_dir / 'code'
                            if not code_dir.exists():
                                continue
                            
                            # Database expander with code files
                            with ui.expansion(db_dir.name, icon='folder').classes('w-full ml-2'):
                                render_code_tree(
                                    code_dir, 
                                    str(code_dir),
                                    code_title, 
                                    code_path_label, 
                                    code_display
                                )
        
        if not found_any:
            ui.label('No code files found. Sync a database first.').classes('text-grey-7')


def render_code_tree(path: Path, base_path: str, code_title, code_path_label, code_display, level=0):
    """Recursively render code file tree"""
    
    # Sort: directories first, then files
    items = sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
    
    for item in items:
        if item.is_dir():
            # Skip empty directories
            if not any(item.iterdir()):
                continue
            
            # Directory expander
            with ui.expansion(item.name, icon='folder').classes('w-full'):
                render_code_tree(item, base_path, code_title, code_path_label, code_display, level + 1)
        else:
            # File button
            relative_path = str(item.relative_to(base_path))
            icon = get_file_icon(item.name)
            
            ui.button(
                item.name,
                icon=icon,
                on_click=lambda p=str(item), n=item.name, r=relative_path: show_code_file(
                    p, n, r, code_title, code_path_label, code_display
                )
            ).props('flat dense align=left').classes('w-full justify-start text-left')


def get_file_icon(filename: str) -> str:
    """Get appropriate icon for file type"""
    if filename.endswith('.nx'):
        return 'code'
    elif filename.endswith('.md'):
        return 'description'
    elif filename.endswith('.json'):
        return 'data_object'
    else:
        return 'insert_drive_file'


def show_code_file(file_path: str, filename: str, relative_path: str, code_title, code_path_label, code_display):
    """Display a code file with syntax highlighting and line numbers"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Update header
        code_title.text = filename
        code_path_label.text = relative_path
        
        # Generate HTML with line numbers and syntax highlighting
        html_content = generate_code_html(content, filename)
        code_display.content = html_content
        
    except Exception as e:
        code_title.text = 'Error'
        code_path_label.text = str(e)
        code_display.content = f'<pre style="color: red;">Error loading file: {e}</pre>'


def generate_code_html(content: str, filename: str) -> str:
    """Generate HTML with line numbers and basic syntax highlighting for Ninox code"""
    lines = content.split('\n')
    
    # Determine if it's a code file or markdown
    is_markdown = filename.endswith('.md')
    is_code = filename.endswith('.nx')
    
    html_lines = []
    
    # Style
    html_lines.append('''
    <style>
        .code-container {
            font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
            font-size: 13px;
            line-height: 1.5;
            background: #1e1e1e;
            color: #d4d4d4;
            border-radius: 8px;
            overflow: auto;
            max-height: calc(100vh - 350px);
        }
        .code-table {
            border-collapse: collapse;
            width: 100%;
        }
        .line-number {
            color: #858585;
            text-align: right;
            padding: 0 12px;
            user-select: none;
            border-right: 1px solid #404040;
            background: #252526;
            min-width: 50px;
            vertical-align: top;
        }
        .line-content {
            padding: 0 12px;
            white-space: pre;
            vertical-align: top;
        }
        .line-content:hover {
            background: #2a2d2e;
        }
        /* Ninox syntax highlighting */
        .keyword { color: #569cd6; }
        .function { color: #dcdcaa; }
        .string { color: #ce9178; }
        .number { color: #b5cea8; }
        .comment { color: #6a9955; }
        .operator { color: #d4d4d4; }
        .field { color: #9cdcfe; }
        /* Markdown */
        .md-header { color: #569cd6; font-weight: bold; }
        .md-bold { font-weight: bold; }
        .md-code { background: #2d2d2d; padding: 2px 4px; border-radius: 3px; }
    </style>
    <div class="code-container">
        <table class="code-table">
    ''')
    
    for i, line in enumerate(lines, 1):
        # Escape HTML
        escaped_line = escape_html(line)
        
        # Apply syntax highlighting
        if is_code:
            highlighted_line = highlight_ninox_syntax(escaped_line)
        elif is_markdown:
            highlighted_line = highlight_markdown(escaped_line)
        else:
            highlighted_line = escaped_line
        
        html_lines.append(f'''
            <tr>
                <td class="line-number">{i}</td>
                <td class="line-content">{highlighted_line}</td>
            </tr>
        ''')
    
    html_lines.append('</table></div>')
    
    return ''.join(html_lines)


def escape_html(text: str) -> str:
    """Escape HTML special characters"""
    return (text
        .replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
        .replace('"', '&quot;')
    )


def highlight_ninox_syntax(line: str) -> str:
    """Apply basic syntax highlighting for Ninox code"""
    import re
    
    # Skip if line is a comment header
    if line.strip().startswith('#'):
        return f'<span class="comment">{line}</span>'
    
    # Keywords
    keywords = [
        'if', 'then', 'else', 'end', 'let', 'do', 'for', 'in', 'while',
        'switch', 'case', 'default', 'function', 'return', 'and', 'or', 'not',
        'null', 'true', 'false', 'this', 'select', 'where', 'order by',
        'first', 'last', 'sum', 'count', 'avg', 'min', 'max', 'concat',
        'text', 'number', 'date', 'time', 'datetime', 'today', 'now',
        'contains', 'trim', 'upper', 'lower', 'length', 'substr',
        'year', 'month', 'day', 'weekday', 'hour', 'minute', 'second'
    ]
    
    result = line
    
    # Highlight strings (single quotes)
    result = re.sub(
        r"'([^']*)'",
        r'<span class="string">\'\1\'</span>',
        result
    )
    
    # Highlight strings (double quotes)
    result = re.sub(
        r'"([^"]*)"',
        r'<span class="string">"\1"</span>',
        result
    )
    
    # Highlight numbers
    result = re.sub(
        r'\b(\d+(?:\.\d+)?)\b',
        r'<span class="number">\1</span>',
        result
    )
    
    # Highlight keywords (word boundaries)
    for kw in keywords:
        pattern = rf'\b({kw})\b'
        result = re.sub(
            pattern,
            r'<span class="keyword">\1</span>',
            result,
            flags=re.IGNORECASE
        )
    
    # Highlight field references (word followed by dot or starting with uppercase after space)
    result = re.sub(
        r"'([A-Za-z][A-Za-z0-9_\s]*)'",
        r'<span class="field">\'\1\'</span>',
        result
    )
    
    # Highlight := operator
    result = result.replace(':=', '<span class="operator">:=</span>')
    
    return result


def highlight_markdown(line: str) -> str:
    """Apply basic highlighting for Markdown"""
    import re
    
    # Headers
    if line.startswith('#'):
        return f'<span class="md-header">{line}</span>'
    
    # Bold
    line = re.sub(r'\*\*([^*]+)\*\*', r'<span class="md-bold">\1</span>', line)
    
    # Inline code
    line = re.sub(r'`([^`]+)`', r'<span class="md-code">\1</span>', line)
    
    return line


def search_code(query: str, results_container):
    """Search through all code files"""
    results_container.clear()
    
    if not query or len(query) < 2:
        results_container.style('display: none;')
        return
    
    results_container.style('display: block;')
    
    results = []
    query_lower = query.lower()
    
    # Search through all code files
    if os.path.exists(CODE_BASE_PATH):
        for root, dirs, files in os.walk(CODE_BASE_PATH):
            for file in files:
                if file.endswith('.nx') or file.endswith('.md'):
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                        
                        if query_lower in content.lower():
                            # Find matching lines
                            lines = content.split('\n')
                            matches = []
                            for i, line in enumerate(lines, 1):
                                if query_lower in line.lower():
                                    matches.append((i, line.strip()[:80]))
                            
                            if matches:
                                rel_path = os.path.relpath(file_path, CODE_BASE_PATH)
                                results.append({
                                    'path': file_path,
                                    'rel_path': rel_path,
                                    'file': file,
                                    'matches': matches[:3]  # Limit to 3 matches per file
                                })
                    except:
                        pass
    
    with results_container:
        if not results:
            ui.label(f'No results for "{query}"').classes('text-grey-7')
        else:
            ui.label(f'Found {len(results)} files').classes('text-sm text-grey-7 mb-2')
            
            for result in results[:20]:  # Limit to 20 files
                with ui.card().classes('w-full p-2 mb-2'):
                    ui.label(result['file']).classes('font-bold text-sm')
                    ui.label(result['rel_path']).classes('text-caption text-grey-7')
                    
                    for line_num, line_text in result['matches']:
                        with ui.row().classes('items-center gap-2'):
                            ui.badge(str(line_num), color='primary').props('dense')
                            ui.label(line_text).classes('text-xs text-grey-8')
