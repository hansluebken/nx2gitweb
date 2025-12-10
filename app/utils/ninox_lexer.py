"""
Ninox Syntax Highlighting
Custom syntax highlighting for Ninox script language.

This module provides HTML-based syntax highlighting for Ninox code,
supporting keywords, operators, strings, comments, and built-in functions.
"""
import re
from typing import List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum


class TokenType(Enum):
    """Token types for Ninox syntax"""
    KEYWORD = "keyword"
    OPERATOR = "operator"
    STRING = "string"
    NUMBER = "number"
    COMMENT = "comment"
    FUNCTION = "function"
    BUILTIN = "builtin"
    FIELD = "field"
    TABLE = "table"
    PUNCTUATION = "punctuation"
    IDENTIFIER = "identifier"
    WHITESPACE = "whitespace"
    NEWLINE = "newline"


@dataclass
class Token:
    """Represents a single token"""
    type: TokenType
    value: str
    start: int
    end: int


# Ninox keywords
KEYWORDS = {
    # Control flow
    'if', 'then', 'else', 'end', 'switch', 'case', 'default',
    'for', 'do', 'while', 'break', 'continue',
    'try', 'catch', 'throw',
    
    # Declarations
    'let', 'var', 'function',
    
    # Operators
    'and', 'or', 'not', 'in', 'like',
    
    # Values
    'true', 'false', 'null', 'this', 'me',
    
    # Context modifiers
    'as', 'database', 'server', 'transaction', 'user',
    
    # Data operations
    'select', 'from', 'where', 'order', 'by', 'group', 'limit',
    'asc', 'desc', 'distinct',
}

# Ninox built-in functions
BUILTIN_FUNCTIONS = {
    # Record operations
    'create', 'delete', 'duplicate', 'record', 'records',
    'first', 'last', 'item', 'count', 'sum', 'avg', 'min', 'max',
    
    # String functions
    'text', 'number', 'upper', 'lower', 'trim', 'length',
    'substr', 'replace', 'split', 'join', 'contains',
    'format', 'formatNumber', 'parseNumber',
    
    # Date functions
    'today', 'now', 'date', 'time', 'datetime',
    'year', 'month', 'day', 'hour', 'minute', 'second',
    'weekday', 'week', 'quarter',
    'dateAdd', 'dateDiff', 'dateFormat',
    'startOfDay', 'endOfDay', 'startOfWeek', 'endOfWeek',
    'startOfMonth', 'endOfMonth', 'startOfYear', 'endOfYear',
    
    # Math functions
    'abs', 'ceil', 'floor', 'round', 'sqrt', 'pow',
    'sin', 'cos', 'tan', 'asin', 'acos', 'atan',
    'log', 'exp', 'random',
    
    # Array functions
    'array', 'unique', 'sort', 'reverse', 'slice',
    'concat', 'indexOf', 'includes', 'filter', 'map',
    
    # UI functions
    'alert', 'confirm', 'prompt', 'dialog',
    'popupRecord', 'openRecord', 'closePopup',
    'openPrintLayout', 'printRecord',
    
    # File functions
    'importFile', 'exportFile', 'downloadFile',
    'importCSV', 'importJSON', 'exportCSV', 'exportJSON',
    
    # HTTP functions
    'http', 'httpGet', 'httpPost', 'httpPut', 'httpDelete',
    
    # Email
    'sendEmail', 'email',
    
    # Utility
    'debug', 'print', 'sleep', 'eval',
    'typeof', 'isnull', 'isempty', 'isEmpty',
    'coalesce', 'choose', 'switch',
    
    # UI State
    'setStyle', 'getStyle', 'focus', 'blur',
    
    # Navigation
    'navigate', 'openUrl', 'openTable', 'openView',
    
    # User
    'userId', 'userName', 'userEmail', 'userRoles',
    'hasRole', 'isAdmin',
    
    # Database info
    'databaseId', 'databaseName', 'tableId', 'tableName',
    'fieldId', 'fieldName',
    
    # Archiving
    'archive', 'unarchive', 'isArchived',
    
    # Clipboard
    'copyToClipboard', 'readFromClipboard',
    
    # JSON
    'parseJSON', 'formatJSON', 'json',
    
    # Colors
    'rgb', 'rgba', 'hex', 'color',
    
    # Location
    'location', 'geoDistance',
}

# CSS classes for each token type
TOKEN_CSS_CLASSES = {
    TokenType.KEYWORD: 'nx-keyword',
    TokenType.OPERATOR: 'nx-operator',
    TokenType.STRING: 'nx-string',
    TokenType.NUMBER: 'nx-number',
    TokenType.COMMENT: 'nx-comment',
    TokenType.FUNCTION: 'nx-function',
    TokenType.BUILTIN: 'nx-builtin',
    TokenType.FIELD: 'nx-field',
    TokenType.TABLE: 'nx-table',
    TokenType.PUNCTUATION: 'nx-punctuation',
    TokenType.IDENTIFIER: 'nx-identifier',
    TokenType.WHITESPACE: '',
    TokenType.NEWLINE: '',
}

# Color scheme (VS Code Dark+ inspired)
CSS_STYLES = """
<style>
.ninox-code {
    font-family: 'Fira Code', 'Consolas', 'Monaco', 'Courier New', monospace;
    font-size: 14px;
    line-height: 1.6;
    background: #ffffff;
    color: #24292e;
    padding: 0;
    border-radius: 0;
    overflow: auto;
    tab-size: 4;
    border: none;
    height: 100%;
    width: 100%;
}
.ninox-code-table {
    border-collapse: collapse;
    width: 100%;
    margin: 0;
}
.nx-line-number {
    color: #6e7781;
    text-align: right;
    padding: 0 12px;
    user-select: none;
    border-right: 1px solid #e1e4e8;
    background: #f6f8fa;
    min-width: 50px;
    vertical-align: top;
    font-size: 12px;
}
.nx-line-content {
    padding: 0 16px;
    white-space: pre;
    vertical-align: top;
    text-align: left;
}
.nx-line-content:hover {
    background: #f6f8fa;
}
/* Token colors - GitHub Light theme */
.nx-keyword {
    color: #d73a49;
    font-weight: 600;
}
.nx-operator {
    color: #005cc5;
}
.nx-string {
    color: #032f62;
}
.nx-number {
    color: #005cc5;
}
.nx-comment {
    color: #6a737d;
    font-style: italic;
}
.nx-function {
    color: #6f42c1;
    font-weight: 500;
}
.nx-builtin {
    color: #005cc5;
    font-weight: 500;
}
.nx-field {
    color: #24292e;
}
.nx-table {
    color: #005cc5;
}
.nx-punctuation {
    color: #24292e;
}
.nx-identifier {
    color: #24292e;
}
/* Highlight matches in search */
.nx-highlight {
    background: #fff3cd;
    border-radius: 2px;
    padding: 1px 2px;
}
/* Current line indicator */
.nx-current-line {
    background: #f1f8ff !important;
}
</style>
"""


def tokenize(code: str) -> List[Token]:
    """
    Tokenize Ninox code into a list of tokens.
    
    Args:
        code: Ninox code string
        
    Returns:
        List of Token objects
    """
    tokens = []
    pos = 0
    
    while pos < len(code):
        token = None
        
        # Newline
        if code[pos] == '\n':
            token = Token(TokenType.NEWLINE, '\n', pos, pos + 1)
            pos += 1
        
        # Whitespace (not newline)
        elif code[pos] in ' \t\r':
            end = pos
            while end < len(code) and code[end] in ' \t\r':
                end += 1
            token = Token(TokenType.WHITESPACE, code[pos:end], pos, end)
            pos = end
        
        # Single-line comment //
        elif code[pos:pos+2] == '//':
            end = code.find('\n', pos)
            if end == -1:
                end = len(code)
            token = Token(TokenType.COMMENT, code[pos:end], pos, end)
            pos = end
        
        # Multi-line comment --- ... ---
        elif code[pos:pos+3] == '---':
            end = code.find('---', pos + 3)
            if end == -1:
                end = len(code)
            else:
                end += 3
            token = Token(TokenType.COMMENT, code[pos:end], pos, end)
            pos = end
        
        # String (double quotes)
        elif code[pos] == '"':
            end = pos + 1
            while end < len(code):
                if code[end] == '\\' and end + 1 < len(code):
                    end += 2
                elif code[end] == '"':
                    end += 1
                    break
                else:
                    end += 1
            token = Token(TokenType.STRING, code[pos:end], pos, end)
            pos = end
        
        # String (single quotes)
        elif code[pos] == "'":
            end = pos + 1
            while end < len(code):
                if code[end] == '\\' and end + 1 < len(code):
                    end += 2
                elif code[end] == "'":
                    end += 1
                    break
                else:
                    end += 1
            token = Token(TokenType.STRING, code[pos:end], pos, end)
            pos = end
        
        # Number
        elif code[pos].isdigit() or (code[pos] == '.' and pos + 1 < len(code) and code[pos+1].isdigit()):
            end = pos
            has_dot = False
            while end < len(code):
                if code[end].isdigit():
                    end += 1
                elif code[end] == '.' and not has_dot:
                    has_dot = True
                    end += 1
                elif code[end] in 'eE' and end + 1 < len(code) and (code[end+1].isdigit() or code[end+1] in '+-'):
                    end += 1
                    if end < len(code) and code[end] in '+-':
                        end += 1
                else:
                    break
            token = Token(TokenType.NUMBER, code[pos:end], pos, end)
            pos = end
        
        # Assignment operator :=
        elif code[pos:pos+2] == ':=':
            token = Token(TokenType.OPERATOR, ':=', pos, pos + 2)
            pos += 2
        
        # Comparison operators
        elif code[pos:pos+2] in ('<=', '>=', '!=', '<>'):
            token = Token(TokenType.OPERATOR, code[pos:pos+2], pos, pos + 2)
            pos += 2
        
        # Single char operators
        elif code[pos] in '+-*/%=<>':
            token = Token(TokenType.OPERATOR, code[pos], pos, pos + 1)
            pos += 1
        
        # Punctuation
        elif code[pos] in '()[]{},.;:':
            token = Token(TokenType.PUNCTUATION, code[pos], pos, pos + 1)
            pos += 1
        
        # Identifier or keyword
        elif code[pos].isalpha() or code[pos] == '_':
            end = pos
            while end < len(code) and (code[end].isalnum() or code[end] == '_'):
                end += 1
            word = code[pos:end]
            word_lower = word.lower()
            
            # Check if it's a keyword
            if word_lower in KEYWORDS:
                token = Token(TokenType.KEYWORD, word, pos, end)
            # Check if it's a built-in function (followed by parenthesis)
            elif word_lower in BUILTIN_FUNCTIONS:
                # Look ahead for (
                lookahead = end
                while lookahead < len(code) and code[lookahead] in ' \t':
                    lookahead += 1
                if lookahead < len(code) and code[lookahead] == '(':
                    token = Token(TokenType.BUILTIN, word, pos, end)
                else:
                    token = Token(TokenType.IDENTIFIER, word, pos, end)
            # Check for table reference (uppercase letters/numbers pattern like A, B3, ZZ)
            elif re.match(r'^[A-Z][A-Z0-9]{0,3}$', word):
                # Could be a table or field ID
                # Look ahead for dot to determine if it's a table reference
                lookahead = end
                while lookahead < len(code) and code[lookahead] in ' \t':
                    lookahead += 1
                if lookahead < len(code) and code[lookahead] == '.':
                    token = Token(TokenType.TABLE, word, pos, end)
                else:
                    token = Token(TokenType.FIELD, word, pos, end)
            else:
                token = Token(TokenType.IDENTIFIER, word, pos, end)
            
            pos = end
        
        # Unknown character - treat as identifier
        else:
            token = Token(TokenType.IDENTIFIER, code[pos], pos, pos + 1)
            pos += 1
        
        if token:
            tokens.append(token)
    
    return tokens


def escape_html(text: str) -> str:
    """Escape HTML special characters"""
    return (text
        .replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
        .replace('"', '&quot;')
    )


def highlight_code(
    code: str,
    highlight_text: Optional[str] = None,
    show_line_numbers: bool = True,
    max_height: str = "calc(100vh - 380px)"
) -> str:
    """
    Generate HTML with syntax highlighting for Ninox code.
    
    Args:
        code: Ninox code to highlight
        highlight_text: Optional text to highlight (for search results)
        show_line_numbers: Whether to show line numbers
        max_height: CSS max-height for the container
        
    Returns:
        HTML string with syntax highlighted code
    """
    if not code:
        return '<div class="ninox-code"><span class="nx-comment">// No code</span></div>'
    
    tokens = tokenize(code)
    
    # Build highlighted HTML for each line
    lines = ['']
    current_line = 0
    
    for token in tokens:
        if token.type == TokenType.NEWLINE:
            lines.append('')
            current_line += 1
        else:
            css_class = TOKEN_CSS_CLASSES.get(token.type, '')
            escaped_value = escape_html(token.value)
            
            # Apply highlight if needed
            if highlight_text and highlight_text.lower() in token.value.lower():
                # Wrap matching text in highlight span
                pattern = re.compile(re.escape(highlight_text), re.IGNORECASE)
                escaped_value = pattern.sub(
                    lambda m: f'<span class="nx-highlight">{escape_html(m.group())}</span>',
                    token.value
                )
                escaped_value = escape_html(token.value)
                if highlight_text.lower() in token.value.lower():
                    # Find and wrap the match
                    idx = token.value.lower().find(highlight_text.lower())
                    if idx >= 0:
                        before = escape_html(token.value[:idx])
                        match = escape_html(token.value[idx:idx+len(highlight_text)])
                        after = escape_html(token.value[idx+len(highlight_text):])
                        escaped_value = f'{before}<span class="nx-highlight">{match}</span>{after}'
            
            if css_class:
                lines[current_line] += f'<span class="{css_class}">{escaped_value}</span>'
            else:
                lines[current_line] += escaped_value
    
    # Build final HTML
    html_parts = [CSS_STYLES]
    html_parts.append(f'<div class="ninox-code" style="max-height: {max_height};">')
    
    if show_line_numbers:
        html_parts.append('<table class="ninox-code-table">')
        for i, line in enumerate(lines, 1):
            html_parts.append(f'''
                <tr>
                    <td class="nx-line-number">{i}</td>
                    <td class="nx-line-content">{line or '&nbsp;'}</td>
                </tr>
            ''')
        html_parts.append('</table>')
    else:
        for line in lines:
            html_parts.append(f'<div class="nx-line-content">{line or "&nbsp;"}</div>')
    
    html_parts.append('</div>')
    
    return ''.join(html_parts)


def highlight_code_simple(code: str) -> str:
    """
    Simple one-line syntax highlighting without line numbers.
    Useful for inline code display.
    """
    if not code:
        return ''
    
    tokens = tokenize(code)
    html_parts = [CSS_STYLES, '<span class="ninox-code" style="display: inline; padding: 2px 6px;">']
    
    for token in tokens:
        if token.type == TokenType.NEWLINE:
            html_parts.append(' ')  # Replace newline with space
        else:
            css_class = TOKEN_CSS_CLASSES.get(token.type, '')
            escaped = escape_html(token.value)
            if css_class:
                html_parts.append(f'<span class="{css_class}">{escaped}</span>')
            else:
                html_parts.append(escaped)
    
    html_parts.append('</span>')
    return ''.join(html_parts)


def format_code(code: str, indent_size: int = 4) -> str:
    """
    Format Ninox code with proper indentation.
    
    Args:
        code: Ninox code to format
        indent_size: Number of spaces per indent level
        
    Returns:
        Formatted code string
    """
    if not code:
        return code
    
    # Keywords that increase indent
    indent_after = {'do', 'then', '{'}
    # Keywords that decrease indent before
    dedent_before = {'end', 'else', '}'}
    # Keywords that get their own line
    own_line = {'let', 'for', 'if', 'switch', 'case', 'else', 'end'}
    
    tokens = tokenize(code)
    result = []
    indent_level = 0
    line_start = True
    prev_token = None
    
    for token in tokens:
        value = token.value
        value_lower = value.lower() if token.type in (TokenType.KEYWORD, TokenType.IDENTIFIER) else value
        
        # Handle dedent before certain keywords
        if token.type == TokenType.KEYWORD and value_lower in dedent_before:
            indent_level = max(0, indent_level - 1)
        
        if token.type == TokenType.PUNCTUATION and value == '}':
            indent_level = max(0, indent_level - 1)
        
        # Handle newlines
        if token.type == TokenType.NEWLINE:
            result.append('\n')
            line_start = True
            continue
        
        # Skip whitespace at line start (we'll add our own indent)
        if token.type == TokenType.WHITESPACE and line_start:
            continue
        
        # Add indent at line start
        if line_start and token.type not in (TokenType.WHITESPACE, TokenType.NEWLINE):
            result.append(' ' * (indent_level * indent_size))
            line_start = False
        
        # Check if we should add newline before certain keywords
        if token.type == TokenType.KEYWORD and value_lower in own_line:
            if not line_start and result and result[-1] not in '\n':
                result.append('\n')
                result.append(' ' * (indent_level * indent_size))
        
        # Add the token
        result.append(value)
        
        # Handle indent after certain keywords/punctuation
        if token.type == TokenType.KEYWORD and value_lower in indent_after:
            indent_level += 1
            result.append('\n')
            result.append(' ' * (indent_level * indent_size))
            line_start = False
        
        if token.type == TokenType.PUNCTUATION and value == '{':
            indent_level += 1
            result.append('\n')
            result.append(' ' * (indent_level * indent_size))
            line_start = False
        
        # Add newline after semicolon
        if token.type == TokenType.PUNCTUATION and value == ';':
            result.append('\n')
            line_start = True
        
        prev_token = token
    
    return ''.join(result).strip()


def get_code_preview(code: str, max_length: int = 100) -> str:
    """
    Get a short preview of code for display in lists.
    
    Args:
        code: Full code
        max_length: Maximum length of preview
        
    Returns:
        Shortened code preview
    """
    if not code:
        return ''
    
    # Replace newlines with spaces
    preview = ' '.join(code.split())
    
    if len(preview) > max_length:
        preview = preview[:max_length - 3] + '...'
    
    return preview
