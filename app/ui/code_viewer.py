"""
Ninox Code Viewer page for Ninox2Git
Hierarchische Darstellung von Ninox-Codefeldern
Schema: datenbankname.tabelle.feld.codefeld
"""
from nicegui import ui
import os
import json
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from ..database import get_db
from ..models.server import Server
from ..models.team import Team
from ..models.database import Database
from ..models.changelog import ChangeLog
from .components import (
    NavHeader, Card, Toast, EmptyState, PRIMARY_COLOR
)

# Base path for code storage
CODE_BASE_PATH = '/app/data/code'


# Code fields to extract from different levels
DATABASE_CODE_FIELDS = ['afterOpen', 'globalCode']
TABLE_CODE_FIELDS = ['afterCreate', 'afterUpdate', 'beforeShow', 'afterHide', 
                     'beforeDelete', 'onOpen', 'onClose', 'trigger',
                     'canRead', 'canWrite', 'canCreate', 'canDelete', 'printout']
FIELD_CODE_FIELDS = ['fn', 'afterUpdate', 'visibility', 'canWrite', 'canRead',
                     'onClick', 'beforeShow', 'afterHide', 'constraint', 'validation',
                     'dchoiceValues', 'dchoiceCaption', 'dchoiceColor', 'dchoiceIcon',
                     'expression', 'filter', 'color', 'customDataExp']


@dataclass
class CodeEntry:
    """Represents a code entry with hierarchical path"""
    database_name: str
    table_name: Optional[str]
    field_name: Optional[str]
    code_type: str
    code: str
    level: int  # 1=database, 2=table, 3=field
    formatted_code: Optional[str] = None  # Formatted version with field names and structure (only for reports)
    
    @property
    def path(self) -> str:
        """Full hierarchical path like DB.Tabelle.Feld.codefeld"""
        parts = [self.database_name]
        if self.table_name:
            parts.append(self.table_name)
        if self.field_name:
            parts.append(self.field_name)
        parts.append(self.code_type)
        return '.'.join(parts)


def extract_code_from_structure(structure: Dict[str, Any], database_name: str) -> List[CodeEntry]:
    """
    Extract all code entries from a Ninox database structure.
    Returns a list of CodeEntry objects with hierarchical paths.
    """
    entries = []
    
    # Handle nested schema structure
    schema = structure.get('schema', structure)
    if 'schema' in schema:
        schema = schema.get('schema', schema)
    
    # Ebene 1: Database-level code
    for code_field in DATABASE_CODE_FIELDS:
        code = schema.get(code_field, '')
        if code and isinstance(code, str) and code.strip():
            entries.append(CodeEntry(
                database_name=database_name,
                table_name=None,
                field_name=None,
                code_type=code_field,
                code=unescape_code(code),
                level=1
            ))
    
    # Process tables
    types = schema.get('types', {})
    for table_id, table_data in types.items():
        if not isinstance(table_data, dict):
            continue
        
        # Get table name (prefer caption over ID)
        table_name = table_data.get('caption') or table_data.get('name') or table_id
        
        # Ebene 2: Table-level code
        for code_field in TABLE_CODE_FIELDS:
            code = table_data.get(code_field, '')
            if code and isinstance(code, str) and code.strip():
                entries.append(CodeEntry(
                    database_name=database_name,
                    table_name=table_name,
                    field_name=None,
                    code_type=code_field,
                    code=unescape_code(code),
                    level=2
                ))
        
        # Ebene 3: Field-level code
        fields = table_data.get('fields', {})
        for field_id, field_data in fields.items():
            if not isinstance(field_data, dict):
                continue
            
            field_name = field_data.get('caption') or field_data.get('name') or field_id
            
            for code_field in FIELD_CODE_FIELDS:
                code = field_data.get(code_field, '')
                if code and isinstance(code, str) and code.strip():
                    # Skip very short formulas that are just field references
                    if code_field == 'fn' and len(code) < 3:
                        continue
                    entries.append(CodeEntry(
                        database_name=database_name,
                        table_name=table_name,
                        field_name=field_name,
                        code_type=code_field,
                        code=unescape_code(code),
                        level=3
                    ))
        
        # UI elements (buttons, views, tabs with code)
        uis = table_data.get('uis', {})
        for ui_id, ui_data in uis.items():
            if not isinstance(ui_data, dict):
                continue
            
            ui_name = ui_data.get('caption') or ui_data.get('name') or ui_id
            
            for code_field in FIELD_CODE_FIELDS:
                code = ui_data.get(code_field, '')
                if code and isinstance(code, str) and code.strip():
                    entries.append(CodeEntry(
                        database_name=database_name,
                        table_name=table_name,
                        field_name=ui_name,
                        code_type=code_field,
                        code=unescape_code(code),
                        level=3
                    ))
    
    return entries


# Code fields to extract from reports
REPORT_CODE_FIELDS = ['customDataExp', 'filter', 'sortExp']

# All unique code field types for filtering
ALL_CODE_TYPES = sorted(set(
    DATABASE_CODE_FIELDS + 
    TABLE_CODE_FIELDS + 
    FIELD_CODE_FIELDS + 
    REPORT_CODE_FIELDS +
    ['expression']  # Also used in report columns
))


def build_field_id_map(schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build a comprehensive mapping from IDs to names.
    Returns: {
        'tables': {table_id: table_name},
        'fields': {table_id: {field_id: field_name}},
        'all_fields': {field_id: field_name}  # flattened for quick lookup
    }
    """
    result = {
        'tables': {},
        'fields': {},
        'all_fields': {}
    }
    
    # Handle nested schema structure
    if 'schema' in schema:
        schema = schema.get('schema', schema)
    if 'schema' in schema:
        schema = schema.get('schema', schema)
    
    types = schema.get('types', {})
    for table_id, table_data in types.items():
        if not isinstance(table_data, dict):
            continue
        
        table_name = table_data.get('caption') or table_data.get('name') or table_id
        result['tables'][table_id] = table_name
        result['fields'][table_id] = {}
        
        # Map fields
        fields = table_data.get('fields', {})
        for field_id, field_data in fields.items():
            if isinstance(field_data, dict):
                field_name = field_data.get('caption') or field_data.get('name') or field_id
                result['fields'][table_id][field_id] = field_name
                result['all_fields'][field_id] = field_name
        
        # Map UI elements (buttons, tabs, etc.)
        uis = table_data.get('uis', {})
        for ui_id, ui_data in uis.items():
            if isinstance(ui_data, dict):
                ui_name = ui_data.get('caption') or ui_data.get('name') or ui_id
                result['fields'][table_id][ui_id] = ui_name
                result['all_fields'][ui_id] = ui_name
    
    return result


def replace_field_ids_with_names(code: str, field_map: Dict[str, Any], table_id: str | None = None) -> str:
    """
    Replace field IDs in code with their human-readable names.
    Handles patterns like: A, B3.K2, record(QB,1), P1, Q1, L2, H2, Y1, etc.
    """
    import re
    
    if not code or not field_map:
        return code
    
    tables = field_map.get('tables', {})
    fields_by_table = field_map.get('fields', {})
    all_fields = field_map.get('all_fields', {})
    
    # For backward compatibility: if field_map is old format (dict of dicts without 'tables' key)
    if 'tables' not in field_map:
        all_fields = {}
        for tid, flds in field_map.items():
            if isinstance(flds, dict):
                all_fields.update(flds)
        tables = {}
        fields_by_table = field_map
    
    # Get table-specific fields if available
    if table_id and table_id in fields_by_table:
        table_fields = fields_by_table[table_id]
    else:
        table_fields = all_fields
    
    result = code
    
    # 1. Replace table.field patterns (e.g., B3.K2 -> TableName.FieldName)
    def replace_table_field(match):
        tbl_id = match.group(1)
        fld_id = match.group(2)
        tbl_name = tables.get(tbl_id, tbl_id)
        # Look up field in that specific table first
        if tbl_id in fields_by_table and fld_id in fields_by_table[tbl_id]:
            fld_name = fields_by_table[tbl_id][fld_id]
        else:
            fld_name = all_fields.get(fld_id, fld_id)
        # Quote field name if it contains spaces
        if ' ' in fld_name:
            fld_name = f"'{fld_name}'"
        if ' ' in tbl_name:
            tbl_name = f"'{tbl_name}'"
        return f"{tbl_name}.{fld_name}"
    
    # Match TableID.FieldID patterns - IDs can be 1-4 chars: A, AB, A1, AB1, A12, etc.
    result = re.sub(r'\b([A-Z][A-Z0-9]{0,3})\.([A-Z][A-Z0-9]{0,3})\b', replace_table_field, result)
    
    # 2. Replace record(TableID, ...) patterns
    def replace_record_table(match):
        tbl_id = match.group(1)
        rest = match.group(2)
        tbl_name = tables.get(tbl_id, tbl_id)
        if ' ' in tbl_name:
            tbl_name = f"'{tbl_name}'"
        return f"record({tbl_name},{rest})"
    
    result = re.sub(r'\brecord\(([A-Z][A-Z0-9]{0,3}),([^)]+)\)', replace_record_table, result)
    
    # 3. Replace field IDs after a dot (e.g., variable.P -> variable.Feldname)
    # This handles cases like: i.E, record(...).Q, me.P
    def replace_dotted_field(match):
        prefix = match.group(1)  # The dot
        field_id = match.group(2)
        if field_id in table_fields:
            name = table_fields[field_id]
        elif field_id in all_fields:
            name = all_fields[field_id]
        else:
            return match.group(0)
        # Quote if contains spaces
        if ' ' in name:
            return f"{prefix}'{name}'"
        return f"{prefix}{name}"
    
    # Match .FIELD_ID patterns (field ID after a dot)
    # Field IDs are 1-4 uppercase chars optionally followed by digits: A, AB, A1, AB1, A12, etc.
    result = re.sub(r'(\.)([A-Z][A-Z0-9]{0,3})(?![A-Za-z0-9_])', replace_dotted_field, result)
    
    # 4. Replace standalone field IDs - sort by length (longest first) to avoid partial replacements
    # Collect all known field IDs
    known_ids = set(table_fields.keys()) | set(all_fields.keys())
    # Sort by length descending so longer IDs are replaced first (e.g., P1 before P)
    sorted_ids = sorted(known_ids, key=len, reverse=True)
    
    for field_id in sorted_ids:
        # Get the name
        if field_id in table_fields:
            name = table_fields[field_id]
        elif field_id in all_fields:
            name = all_fields[field_id]
        else:
            continue
        
        # Quote if contains spaces
        if ' ' in name:
            replacement = f"'{name}'"
        else:
            replacement = name
        
        # Build pattern that matches the field ID as a standalone identifier
        # Not preceded by: quote, word char, or dot (dot case handled above)
        # Not followed by alphanumeric
        pattern = r'(?<![.\'\w])' + re.escape(field_id) + r'(?![A-Za-z0-9_])'
        result = re.sub(pattern, replacement, result)
    
    return result


def format_ninox_code_structured(code: str) -> str:
    """
    Format Ninox code with proper indentation and structure.
    Handles: let, do, end, if, then, else, for, switch, case, function blocks, etc.
    """
    if not code:
        return code
    
    # Keywords that increase indentation
    indent_increase = ['do', 'then', 'else', 'function']
    # Keywords that decrease indentation
    indent_decrease = ['end', 'else']
    # Keywords that start a new block on same line
    block_starters = ['let', 'for', 'if', 'switch', 'case', 'function']
    
    result_lines = []
    indent_level = 0
    indent_str = '    '  # 4 spaces
    
    # First, add line breaks after semicolons and around block keywords
    # But preserve strings
    formatted = code
    
    # Tokenize while preserving strings
    tokens = []
    i = 0
    current_token = ''
    in_string = False
    string_char = None
    
    while i < len(formatted):
        char = formatted[i]
        
        # Handle string start/end
        if char in '"\'':
            if not in_string:
                if current_token:
                    tokens.append(current_token)
                    current_token = ''
                in_string = True
                string_char = char
                current_token = char
            elif char == string_char:
                current_token += char
                tokens.append(current_token)
                current_token = ''
                in_string = False
                string_char = None
            else:
                current_token += char
        elif in_string:
            current_token += char
        elif char == ';':
            if current_token:
                tokens.append(current_token)
            tokens.append(';')
            tokens.append('\n')
            current_token = ''
        elif char == '(':
            if current_token:
                tokens.append(current_token)
            tokens.append('(')
            current_token = ''
        elif char == ')':
            if current_token:
                tokens.append(current_token)
            tokens.append(')')
            current_token = ''
        elif char == '{':
            if current_token:
                tokens.append(current_token)
            tokens.append('{')
            tokens.append('\n')
            current_token = ''
        elif char == '}':
            if current_token:
                tokens.append(current_token)
            tokens.append('\n')
            tokens.append('}')
            current_token = ''
        elif char == ',':
            if current_token:
                tokens.append(current_token)
            tokens.append(',')
            current_token = ''
        elif char == ':':
            if current_token:
                tokens.append(current_token)
            tokens.append(':')
            current_token = ''
        elif char in ' \t\n\r':
            if current_token:
                tokens.append(current_token)
                current_token = ''
            if char == '\n':
                tokens.append('\n')
        else:
            current_token += char
        i += 1
    
    if current_token:
        tokens.append(current_token)
    
    # Now process tokens and build formatted output
    result = []
    indent_level = 0
    line_start = True
    prev_token = ''
    
    for token in tokens:
        token_lower = token.lower() if isinstance(token, str) else ''
        
        # Handle indentation decrease before the token
        if token_lower in ['end', 'else']:
            indent_level = max(0, indent_level - 1)
        
        if token == '\n':
            result.append('\n')
            line_start = True
        elif token_lower in ['do', 'then']:
            result.append(' ' + token + '\n')
            indent_level += 1
            line_start = True
        elif token_lower == 'else':
            result.append('\n' + (indent_str * indent_level) + token)
            indent_level += 1
            line_start = False
        elif token_lower == 'end':
            if not line_start:
                result.append('\n')
            result.append(indent_str * indent_level + token)
            line_start = False
        elif token_lower == 'let':
            if not line_start:
                result.append('\n')
            result.append(indent_str * indent_level + token + ' ')
            line_start = False
        elif token_lower == 'for':
            if not line_start:
                result.append('\n')
            result.append(indent_str * indent_level + token + ' ')
            line_start = False
        elif token_lower == 'if':
            if not line_start:
                result.append('\n')
            result.append(indent_str * indent_level + token + ' ')
            line_start = False
        elif token_lower == 'switch':
            if not line_start:
                result.append('\n')
            result.append(indent_str * indent_level + token + ' ')
            line_start = False
        elif token_lower == 'case':
            if not line_start:
                result.append('\n')
            result.append(indent_str * indent_level + token + ' ')
            line_start = False
        elif token == '{':
            result.append(token + '\n')
            indent_level += 1
            line_start = True
        elif token == '}':
            indent_level = max(0, indent_level - 1)
            if not line_start:
                result.append('\n')
            result.append(indent_str * indent_level + token)
            line_start = False
        elif token == ':':
            result.append(token + ' ')
            line_start = False
        elif token == ',':
            result.append(token + '\n')
            line_start = True
        elif token == ';':
            result.append(token)
            line_start = False
        else:
            if line_start and token.strip():
                result.append(indent_str * indent_level + token)
                line_start = False
            elif token.strip():
                # Add space before token if previous wasn't special
                if prev_token not in ['(', ':', ',', '\n', ''] and not prev_token.endswith(' '):
                    result.append(' ')
                result.append(token)
                line_start = False
        
        if token.strip():
            prev_token = token
    
    # Clean up multiple newlines
    formatted_result = ''.join(result)
    while '\n\n\n' in formatted_result:
        formatted_result = formatted_result.replace('\n\n\n', '\n\n')
    
    # Remove trailing whitespace from lines
    lines = formatted_result.split('\n')
    lines = [line.rstrip() for line in lines]
    
    return '\n'.join(lines).strip()


def format_report_code(code: str, field_map: Dict[str, Any] | None = None, table_id: str | None = None) -> str:
    """
    Format report code: replace field IDs with names and apply structured formatting.
    """
    if not code:
        return code
    
    result = code
    
    # First replace field IDs with names
    if field_map:
        result = replace_field_ids_with_names(result, field_map, table_id)
    
    # Then apply structured formatting
    result = format_ninox_code_structured(result)
    
    return result


def extract_code_from_reports(reports: List[Dict[str, Any]], database_name: str, 
                              field_map: Dict[str, Dict[str, str]] | None = None) -> List[CodeEntry]:
    """
    Extract all code entries from Ninox reports.
    Returns a list of CodeEntry objects with hierarchical paths.
    """
    entries = []
    
    if not reports or not isinstance(reports, list):
        return entries
    
    for report in reports:
        if not isinstance(report, dict):
            continue
        
        report_name = report.get('name') or report.get('caption') or f"Report_{report.get('id', 'unknown')}"
        table_id = report.get('tid')  # Table ID the report belongs to
        
        # Extract code fields from report
        for code_field in REPORT_CODE_FIELDS:
            code = report.get(code_field, '')
            if code and isinstance(code, str) and code.strip():
                raw_code = unescape_code(code)
                # Generate formatted version for reports
                formatted = format_report_code(raw_code, field_map, table_id)
                entries.append(CodeEntry(
                    database_name=database_name,
                    table_name='[Reports]',
                    field_name=report_name,
                    code_type=code_field,
                    code=raw_code,
                    level=3,
                    formatted_code=formatted
                ))
        
        # Check for columns with expressions
        columns = report.get('columns', [])
        if isinstance(columns, list):
            for col in columns:
                if not isinstance(col, dict):
                    continue
                col_name = col.get('caption') or col.get('name') or 'Column'
                for code_field in ['expression', 'filter', 'customDataExp']:
                    code = col.get(code_field, '')
                    if code and isinstance(code, str) and code.strip():
                        raw_code = unescape_code(code)
                        formatted = format_report_code(raw_code, field_map, table_id)
                        entries.append(CodeEntry(
                            database_name=database_name,
                            table_name='[Reports]',
                            field_name=f"{report_name}.{col_name}",
                            code_type=code_field,
                            code=raw_code,
                            level=3,
                            formatted_code=formatted
                        ))
    
    return entries


def extract_code_from_views(views: List[Dict[str, Any]], database_name: str,
                            field_map: Dict[str, Dict[str, str]] | None = None) -> List[CodeEntry]:
    """
    Extract all code entries from Ninox views.
    Returns a list of CodeEntry objects with hierarchical paths.
    """
    entries = []
    
    if not views or not isinstance(views, list):
        return entries
    
    for view in views:
        if not isinstance(view, dict):
            continue
        
        view_name = view.get('name') or view.get('caption') or f"View_{view.get('id', 'unknown')}"
        table_id = view.get('tid')  # Table ID the view belongs to
        
        # Extract code fields from view
        for code_field in ['filter', 'sortExp', 'customDataExp']:
            code = view.get(code_field, '')
            if code and isinstance(code, str) and code.strip():
                entries.append(CodeEntry(
                    database_name=database_name,
                    table_name='[Views]',
                    field_name=view_name,
                    code_type=code_field,
                    code=unescape_code(code),
                    level=3
                ))
    
    return entries


def unescape_code(code: str) -> str:
    """Remove escape sequences to make code readable"""
    if not code:
        return code
    
    # Remove surrounding quotes if present (Ninox stores code as quoted strings)
    if len(code) >= 2 and code.startswith('"') and code.endswith('"'):
        code = code[1:-1]
    
    # Replace escaped quotes with real quotes
    code = code.replace('\\"', '"')
    code = code.replace("\\'", "'")
    # Replace escaped newlines
    code = code.replace('\\n', '\n')
    code = code.replace('\\t', '\t')
    return code


def add_code_structure(code: str) -> str:
    """
    Add newlines and indentation to compressed Ninox code.
    Handles: let, do, end, if, then, else, for, switch, case, {, }
    """
    if not code:
        return code
    
    # Check if code has structure outside of strings
    # If newlines exist only inside strings, we still need to format
    has_structure = False
    in_str = False
    str_char = None
    for idx, c in enumerate(code):
        if c in '"\'':
            if not in_str:
                in_str = True
                str_char = c
            elif c == str_char and (idx == 0 or code[idx-1] != '\\'):
                in_str = False
        elif c == '\n' and not in_str:
            has_structure = True
            break
    
    if has_structure:
        return code
    
    result = []
    indent = 0
    i = 0
    in_string = False
    string_char = None
    
    # Keywords that start a block (increase indent after)
    block_start = ['do', 'then', '{']
    # Keywords that end a block (decrease indent before)
    block_end = ['end', '}']
    # Keywords that get their own line
    newline_before = ['let', 'for', 'if', 'switch', 'case', 'else']
    
    while i < len(code):
        char = code[i]
        
        # Track string state
        if char in '"\'':
            if not in_string:
                in_string = True
                string_char = char
            elif char == string_char and (i == 0 or code[i-1] != '\\'):
                in_string = False
                string_char = None
            result.append(char)
            i += 1
            continue
        
        if in_string:
            result.append(char)
            i += 1
            continue
        
        # Check for keywords
        keyword_found = False
        
        # Check block end keywords (decrease indent)
        for kw in block_end:
            if code[i:i+len(kw)] == kw and (i == 0 or not code[i-1].isalnum()):
                if i + len(kw) >= len(code) or not code[i+len(kw)].isalnum():
                    indent = max(0, indent - 1)
                    if result and result[-1] not in '\n\t':
                        result.append('\n')
                        result.append('\t' * indent)
                    result.append(kw)
                    i += len(kw)
                    keyword_found = True
                    break
        
        if keyword_found:
            continue
        
        # Check newline-before keywords
        for kw in newline_before:
            if code[i:i+len(kw)] == kw and (i == 0 or not code[i-1].isalnum()):
                if i + len(kw) >= len(code) or not code[i+len(kw)].isalnum():
                    if result and result[-1] not in '\n\t' and len(result) > 0:
                        result.append('\n')
                        result.append('\t' * indent)
                    result.append(kw)
                    i += len(kw)
                    keyword_found = True
                    break
        
        if keyword_found:
            continue
        
        # Check block start keywords (increase indent)
        for kw in block_start:
            if code[i:i+len(kw)] == kw and (i == 0 or not code[i-1].isalnum()):
                if kw in ['{'] or i + len(kw) >= len(code) or not code[i+len(kw)].isalnum():
                    result.append(kw)
                    i += len(kw)
                    indent += 1
                    result.append('\n')
                    result.append('\t' * indent)
                    keyword_found = True
                    break
        
        if keyword_found:
            continue
        
        # Handle semicolons - newline after
        if char == ';':
            result.append(char)
            result.append('\n')
            result.append('\t' * indent)
            i += 1
            continue
        
        # Handle commas - only newline in objects (after {), not in function calls
        if char == ',':
            result.append(char)
            # Check if we're inside an object literal (last { was not followed by function-like pattern)
            # Simple heuristic: if indent > 0 and we recently saw a { that started a block
            # Look back to see if we're in an object vs function call
            in_object = False
            paren_depth = 0
            brace_depth = 0
            for j in range(len(result) - 1, -1, -1):
                c = result[j]
                if c == ')':
                    paren_depth += 1
                elif c == '(':
                    paren_depth -= 1
                    if paren_depth < 0:
                        # We're inside a function call
                        break
                elif c == '}':
                    brace_depth += 1
                elif c == '{':
                    brace_depth -= 1
                    if brace_depth < 0:
                        # We're inside an object literal
                        in_object = True
                        break
            
            if in_object:
                result.append('\n')
                result.append('\t' * indent)
            else:
                result.append(' ')  # Just add space after comma in function calls
            i += 1
            continue
        
        result.append(char)
        i += 1
    
    return ''.join(result)


def format_ninox_code(code: str) -> str:
    """
    Format Ninox code to be more readable:
    - Remove unnecessary parentheses
    - Add newlines and indentation
    - Add spaces around operators
    """
    if not code:
        return code
    
    code = code.strip()
    
    # First, add structure with newlines and indentation
    code = add_code_structure(code)
    
    # Remove unnecessary parentheses (multiple passes for nested parens)
    code = remove_unnecessary_parens(code)
    
    # Add newlines after semicolons (but not inside strings)
    result = []
    in_string = False
    string_char = None
    i = 0
    while i < len(code):
        char = code[i]
        
        # Track string state
        if char in '"\'':
            if not in_string:
                in_string = True
                string_char = char
            elif char == string_char and (i == 0 or code[i-1] != '\\'):
                in_string = False
                string_char = None
        
        result.append(char)
        
        # Add newline after semicolon (outside strings)
        if char == ';' and not in_string:
            # Skip any whitespace after semicolon, then add newline
            j = i + 1
            while j < len(code) and code[j] in ' \t':
                j += 1
            # Check if next non-space char is not already a newline
            if j < len(code) and code[j] not in '\n\r':
                result.append('\n')
                # Skip the whitespace we already checked
                i = j - 1
        
        i += 1
    
    code = ''.join(result)
    
    # Add spaces around := operator (outside strings)
    code = format_operator(code, ':=')
    
    # Add spaces around + operator (outside strings, careful with ++)
    code = format_operator(code, '+', exclude_double=True)
    
    # Add spaces around - operator (outside strings, careful with --)
    code = format_operator(code, '-', exclude_double=True)
    
    # Clean up: trim whitespace from each line
    lines = code.split('\n')
    lines = [line.strip() for line in lines]
    code = '\n'.join(lines)
    
    return code


def remove_unnecessary_parens(code: str) -> str:
    """
    Remove unnecessary parentheses from code.
    Handles both outer parens and simple expression parens like (A + B).
    """
    if not code:
        return code
    
    # Multiple passes to handle nested cases
    for _ in range(3):
        old_code = code
        
        # Remove outer parentheses if they wrap the entire expression
        code = code.strip()
        if code.startswith('(') and code.endswith(')'):
            depth = 0
            is_outer = True
            in_string = False
            string_char = None
            for i, char in enumerate(code):
                # Track strings
                if char in '"\'':
                    if not in_string:
                        in_string = True
                        string_char = char
                    elif char == string_char and (i == 0 or code[i-1] != '\\'):
                        in_string = False
                        string_char = None
                
                if not in_string:
                    if char == '(':
                        depth += 1
                    elif char == ')':
                        depth -= 1
                    # If depth becomes 0 before the end, parens are not outer
                    if depth == 0 and i < len(code) - 1:
                        is_outer = False
                        break
            if is_outer:
                code = code[1:-1].strip()
        
        # Remove parentheses around simple expressions after :=
        # Pattern: := (expr) where expr has no semicolons
        import re
        
        def remove_assignment_parens(match):
            """Remove parens after := if they contain a simple expression"""
            prefix = match.group(1)  # :=
            content = match.group(2)  # content inside parens
            
            # Don't remove if content has semicolons (multiple statements)
            if ';' in content:
                return match.group(0)
            
            # Don't remove if content has unbalanced parens
            depth = 0
            for c in content:
                if c == '(':
                    depth += 1
                elif c == ')':
                    depth -= 1
                if depth < 0:
                    return match.group(0)
            
            return f'{prefix} {content}'
        
        # Match := followed by (content) - but not inside strings
        # This is a simplified approach
        code = re.sub(r'(:=)\s*\(([^;]+?)\)(?=\s*[;\n]|$)', remove_assignment_parens, code)
        
        if code == old_code:
            break
    
    return code


def format_operator(code: str, op: str, exclude_double: bool = False) -> str:
    """Add spaces around an operator, respecting strings"""
    result = []
    in_string = False
    string_char = None
    i = 0
    
    while i < len(code):
        char = code[i]
        
        # Track string state
        if char in '"\'':
            if not in_string:
                in_string = True
                string_char = char
            elif char == string_char and (i == 0 or code[i-1] != '\\'):
                in_string = False
                string_char = None
        
        # Check for operator
        if not in_string and code[i:i+len(op)] == op:
            # Check for double operator (++, --)
            if exclude_double and i + len(op) < len(code) and code[i + len(op)] == op[0]:
                result.append(char)
                i += 1
                continue
            
            # Check if already has space before
            if result and result[-1] not in ' \t\n(':
                result.append(' ')
            
            result.append(op)
            i += len(op)
            
            # Check if already has space after
            if i < len(code) and code[i] not in ' \t\n)':
                result.append(' ')
            continue
        
        result.append(char)
        i += 1
    
    return ''.join(result)


def find_database_files(user) -> List[Dict[str, Any]]:
    """Find all database JSON files (structure.json, complete-backup.json, reports.json) the user has access to"""
    results = []
    
    if not os.path.exists(CODE_BASE_PATH):
        return results
    
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
    
    # Scan directory structure
    for server_dir in Path(CODE_BASE_PATH).iterdir():
        if not server_dir.is_dir():
            continue
        
        server_name = server_dir.name
        has_access = user.is_admin or any(
            server_name.lower() in s.lower() or s.lower() in server_name.lower()
            for s in server_names
        )
        
        if not has_access:
            continue
        
        for team_dir in server_dir.iterdir():
            if not team_dir.is_dir():
                continue
            
            for db_dir in team_dir.iterdir():
                if not db_dir.is_dir():
                    continue
                
                # Check for available files
                structure_file = db_dir / 'structure.json'
                backup_file = db_dir / 'complete-backup.json'
                reports_file = db_dir / 'reports.json'
                views_file = db_dir / 'views.json'
                
                if structure_file.exists() or backup_file.exists():
                    results.append({
                        'server': server_name,
                        'team': team_dir.name,
                        'database': db_dir.name,
                        'structure_path': str(structure_file) if structure_file.exists() else None,
                        'backup_path': str(backup_file) if backup_file.exists() else None,
                        'reports_path': str(reports_file) if reports_file.exists() else None,
                        'views_path': str(views_file) if views_file.exists() else None,
                    })
    
    return results


def render(user):
    """Render the code viewer page"""
    ui.colors(primary=PRIMARY_COLOR)
    
    # Navigation header
    NavHeader(user, 'code-viewer').render()
    
    # Get all available database files
    all_database_files = find_database_files(user)
    
    # Build server -> team -> database hierarchy
    hierarchy = {}
    for df in all_database_files:
        server = df['server']
        team = df['team']
        database = df['database']
        
        if server not in hierarchy:
            hierarchy[server] = {}
        if team not in hierarchy[server]:
            hierarchy[server][team] = []
        hierarchy[server][team].append(df)
    
    # Main content
    with ui.column().classes('w-full p-6 gap-4').style('max-width: 1800px; margin: 0 auto;'):
        ui.label('Ninox Code Viewer').classes('text-h4 font-bold mb-2')
        ui.label('Hierarchische Darstellung von Ninox-Codefeldern').classes('text-grey-7 mb-4')
        
        # Filter dropdowns
        with ui.row().classes('w-full gap-4 mb-4'):
            server_options = list(hierarchy.keys()) if hierarchy else []
            server_select = ui.select(
                label='Server',
                options=server_options,
                value=server_options[0] if server_options else None
            ).classes('flex-1')
            
            team_select = ui.select(
                label='Team',
                options=[],
                value=None
            ).classes('flex-1')
            
            database_select = ui.select(
                label='Datenbank',
                options=[],
                value=None
            ).classes('flex-1')
        
        # Main layout: tree on left, code on right (vertical split)
        with ui.splitter(value=35).classes('w-full').style('height: calc(100vh - 280px);') as splitter:
            # Left section - hierarchical tree
            with splitter.before:
                with ui.card().classes('w-full h-full p-4').style('overflow: auto;'):
                    ui.label('Code-Hierarchie').classes('text-h6 font-bold mb-2')
                    
                    # Search box
                    search_input = ui.input(
                        placeholder='Text im Code suchen...'
                    ).classes('w-full mb-2').props('outlined dense clearable')
                    
                    # Code type filter - multiple select
                    code_type_select = ui.select(
                        label='Code-Typen filtern',
                        options=ALL_CODE_TYPES,
                        multiple=True,
                        value=[]
                    ).classes('w-full mb-2').props('outlined dense clearable use-chips')
                    
                    # Filter status display
                    filter_status = ui.label('').classes('text-sm text-grey-7 mb-2')
                    
                    # Search results container (hidden by default)
                    search_results_container = ui.column().classes('w-full').style('display: none;')
                    
                    # Tree container
                    tree_container = ui.column().classes('w-full')
                
            # Right section - code display
            with splitter.after:
                with ui.card().classes('w-full h-full p-4').style('overflow: auto;'):
                    # Code header with hierarchical path and copy button
                    with ui.row().classes('w-full items-center gap-2'):
                        code_path_display = ui.label('Wähle ein Codefeld aus').classes('text-h6 font-bold font-mono flex-grow')
                        copy_button = ui.button(icon='content_copy', on_click=lambda: None).props('flat dense round').classes('text-grey-7')
                        copy_button.visible = False
                        copy_button.tooltip('Code kopieren')
                    code_separator = ui.html('<div style="border-bottom: 2px solid #666; margin: 8px 0 16px 0; width: 100%;"></div>', sanitize=False)
                    
                    # Code content - with tabs for formatted version (reports only)
                    code_container = ui.column().classes('w-full')
                    with code_container:
                        # Tabs container (hidden by default, shown for reports)
                        tabs_container = ui.row().classes('w-full mb-2')
                        tabs_container.visible = False
                        with tabs_container:
                            with ui.tabs().classes('w-full') as code_tabs:
                                original_tab = ui.tab('Original', icon='code')
                                formatted_tab = ui.tab('Formatiert', icon='auto_fix_high')
                        
                        # Tab panels
                        with ui.tab_panels(code_tabs, value=original_tab).classes('w-full') as tab_panels:
                            with ui.tab_panel(original_tab):
                                code_display = ui.html('', sanitize=False).classes('w-full')
                            with ui.tab_panel(formatted_tab):
                                formatted_display = ui.html('', sanitize=False).classes('w-full')
                    
                    # Change history section (collapsible)
                    ui.separator().classes('my-4')
                    history_expansion = ui.expansion(
                        'Änderungshistorie',
                        icon='history',
                        value=False
                    ).classes('w-full')
                    history_expansion.visible = False
                    
                    with history_expansion:
                        history_container = ui.column().classes('w-full gap-2')
                        with history_container:
                            ui.label('Wähle ein Codefeld aus, um die Historie zu sehen.').classes('text-grey-7')
        
        # Store state for filtering and UI elements
        state = {
            'hierarchy': hierarchy,
            'all_files': all_database_files,
            'current_entries': [],
            'active_code_filters': set(),
            'search_text': '',
            'current_code': '',  # Store current code for copy function
            'current_entry': None,  # Currently selected code entry
            'current_database_id': None,  # Current database ID for changelog lookup
            'ui': {
                'code_path_display': code_path_display,
                'code_display': code_display,
                'formatted_display': formatted_display,
                'tabs_container': tabs_container,
                'code_tabs': code_tabs,
                'original_tab': original_tab,
                'tree_container': tree_container,
                'filter_status': filter_status,
                'code_type_select': code_type_select,
                'search_input': search_input,
                'copy_button': copy_button,
                'history_expansion': history_expansion,
                'history_container': history_container,
            }
        }
        
        async def copy_code_to_clipboard():
            """Copy current code to clipboard"""
            code = state.get('current_code', '')
            if code:
                await ui.run_javascript(f'navigator.clipboard.writeText({repr(code)})')
                ui.notify('Code kopiert!', type='positive', position='top')
        
        copy_button.on('click', copy_code_to_clipboard)
        
        def apply_filters():
            """Apply text search and code type filters to the tree"""
            entries = state['current_entries']
            text_filter = state['search_text'].lower().strip()
            # Get type filters from the select element
            type_filters = set(code_type_select.value) if code_type_select.value else set()
            state['active_code_filters'] = type_filters
            
            # Filter entries
            filtered = []
            for entry in entries:
                # Check code type filter
                if type_filters and entry.code_type not in type_filters:
                    continue
                # Check text filter
                if text_filter:
                    if text_filter not in entry.path.lower() and text_filter not in entry.code.lower():
                        continue
                filtered.append(entry)
            
            # Update filter status
            if text_filter or type_filters:
                status_parts = []
                if type_filters:
                    status_parts.append(f"Typen: {', '.join(sorted(type_filters))}")
                if text_filter:
                    status_parts.append(f"Text: '{text_filter}'")
                filter_status.text = f"Filter aktiv: {' | '.join(status_parts)} ({len(filtered)}/{len(entries)} Einträge)"
            else:
                filter_status.text = f"{len(entries)} Code-Einträge"
            
            # Re-render tree with filtered entries
            tree_container.clear()
            with tree_container:
                if filtered:
                    db_name = database_select.value or 'Datenbank'
                    render_database_tree(filtered, db_name, state)
                else:
                    ui.label('Keine Einträge entsprechen dem Filter.').classes('text-grey-7')
        
        def on_code_type_change(e):
            """Handle code type select change"""
            apply_filters()
        
        def clear_all_filters():
            """Clear all filters"""
            state['active_code_filters'].clear()
            state['search_text'] = ''
            search_input.value = ''
            search_input.update()
            code_type_select.value = []
            code_type_select.update()
            apply_filters()
        
        def on_text_search(e=None):
            """Handle text search input"""
            # Lese direkt vom Input-Element
            new_value = search_input.value if search_input.value else ''
            state['search_text'] = new_value
            apply_filters()
        
        # Connect code type select change handler
        code_type_select.on('update:model-value', on_code_type_change)
        
        # Connect text search
        search_input.on('change', on_text_search)
        search_input.on('clear', on_text_search)
        
        def update_teams(e=None):
            """Update team dropdown when server changes"""
            server = server_select.value
            if server and server in hierarchy:
                teams = list(hierarchy[server].keys())
                team_select.options = teams
                team_select.value = teams[0] if teams else None
                team_select.update()
                update_databases()
            else:
                team_select.options = []
                team_select.value = None
                team_select.update()
                database_select.options = []
                database_select.value = None
                database_select.update()
        
        def update_databases(e=None):
            """Update database dropdown when team changes"""
            server = server_select.value
            team = team_select.value
            if server and team and server in hierarchy and team in hierarchy[server]:
                databases = [df['database'] for df in hierarchy[server][team]]
                database_select.options = databases
                database_select.value = databases[0] if databases else None
                database_select.update()
                load_selected_database()
            else:
                database_select.options = []
                database_select.value = None
                database_select.update()
        
        def load_selected_database(e=None):
            """Load code tree for selected database"""
            server = server_select.value
            team = team_select.value
            database = database_select.value
            
            if not all([server, team, database]):
                tree_container.clear()
                with tree_container:
                    ui.label('Bitte Server, Team und Datenbank auswählen.').classes('text-grey-7')
                return
            
            # Find the matching database file
            selected_file = None
            for df in hierarchy.get(server, {}).get(team, []):
                if df['database'] == database:
                    selected_file = df
                    break
            
            if selected_file:
                load_single_database(
                    selected_file,
                    tree_container,
                    state
                )
        
        # Bind events
        server_select.on('update:model-value', update_teams)
        team_select.on('update:model-value', update_databases)
        database_select.on('update:model-value', load_selected_database)
        
        # Initial load
        if server_options:
            update_teams()


def load_single_database(df, container, state):
    """Load code tree for a single database file"""
    container.clear()
    
    try:
        db_name = df['database']
        entries = []
        
        # Load structure.json or complete-backup.json
        schema = {}
        field_map = {}
        
        if df.get('backup_path'):
            # Prefer complete-backup.json as it contains everything
            with open(df['backup_path'], 'r', encoding='utf-8') as f:
                backup = json.load(f)
            
            # Extract from schema
            schema = backup.get('schema', {})
            field_map = build_field_id_map(schema)
            entries.extend(extract_code_from_structure(schema, db_name))
            
            # Extract from reports (with field ID to name mapping)
            reports = backup.get('reports', [])
            entries.extend(extract_code_from_reports(reports, db_name, field_map))
            
            # Extract from views (with field ID to name mapping)
            views = backup.get('views', [])
            entries.extend(extract_code_from_views(views, db_name, field_map))
            
        elif df.get('structure_path'):
            # Fallback to structure.json
            with open(df['structure_path'], 'r', encoding='utf-8') as f:
                schema = json.load(f)
            field_map = build_field_id_map(schema)
            entries.extend(extract_code_from_structure(schema, db_name))
        
        # Also check for separate reports.json if not in backup
        if df.get('reports_path') and not df.get('backup_path'):
            with open(df['reports_path'], 'r', encoding='utf-8') as f:
                reports = json.load(f)
            entries.extend(extract_code_from_reports(reports, db_name, field_map))
        
        # Also check for separate views.json if not in backup
        if df.get('views_path') and not df.get('backup_path'):
            with open(df['views_path'], 'r', encoding='utf-8') as f:
                views = json.load(f)
            entries.extend(extract_code_from_views(views, db_name, field_map))
        
        # Store entries for search
        state['current_entries'] = entries
        
        # Look up database ID for changelog queries
        db = get_db()
        try:
            database = db.query(Database).filter(
                Database.name == db_name
            ).first()
            if database:
                state['current_database_id'] = database.id
            else:
                state['current_database_id'] = None
        finally:
            db.close()
        
        # Reset current entry and hide history
        state['current_entry'] = None
        ui_state = state.get('ui', {})
        history_expansion = ui_state.get('history_expansion')
        if history_expansion:
            history_expansion.visible = False
        
        # Reset filters when loading new database
        state['active_code_filters'].clear()
        state['search_text'] = ''
        
        # Reset UI filter elements
        ui_state = state.get('ui', {})
        filter_status = ui_state.get('filter_status')
        clear_filters_btn = ui_state.get('clear_filters_btn')
        code_type_chips = ui_state.get('code_type_chips', {})
        search_input_elem = ui_state.get('search_input')
        
        if filter_status:
            filter_status.text = f"{len(entries)} Code-Einträge"
        code_type_select_elem = ui_state.get('code_type_select')
        if code_type_select_elem:
            code_type_select_elem.value = []
            code_type_select_elem.update()
        if search_input_elem:
            search_input_elem.value = ''
            search_input_elem.update()
        
        with container:
            if entries:
                # Render directly without database expander (already filtered)
                render_database_tree(
                    entries, 
                    db_name, 
                    state
                )
            else:
                ui.label('Keine Code-Felder in dieser Datenbank gefunden.').classes('text-grey-7')
        
    except Exception as e:
        with container:
            ui.label(f'Fehler beim Laden: {str(e)}').classes('text-red-7')


def render_database_tree(entries: List[CodeEntry], db_name: str, state: Dict):
    """Render the tree for a single database"""
    
    # Group entries by level and table
    db_level = [e for e in entries if e.level == 1]
    by_table = {}
    
    for e in entries:
        if e.level >= 2 and e.table_name:
            if e.table_name not in by_table:
                by_table[e.table_name] = {'table': [], 'fields': {}}
            if e.level == 2:
                by_table[e.table_name]['table'].append(e)
            elif e.level == 3 and e.field_name:
                if e.field_name not in by_table[e.table_name]['fields']:
                    by_table[e.table_name]['fields'][e.field_name] = []
                by_table[e.table_name]['fields'][e.field_name].append(e)
    
    # Render database-level code (Ebene 1)
    for entry in db_level:
        render_code_button(entry, state)
    
    # Render tables (Ebene 2)
    for table_name in sorted(by_table.keys()):
        table_data = by_table[table_name]
        
        # Use special icons for Reports and Views
        if table_name == '[Reports]':
            table_icon = 'assessment'
        elif table_name == '[Views]':
            table_icon = 'view_list'
        else:
            table_icon = 'table_chart'
        
        with ui.expansion(table_name, icon=table_icon).classes('w-full ml-4 text-sm'):
            # Table-level code
            for entry in table_data['table']:
                render_code_button(entry, state)
            
            # Fields (Ebene 3)
            for field_name in sorted(table_data['fields'].keys()):
                field_entries = table_data['fields'][field_name]
                
                if len(field_entries) == 1:
                    # Single code field - show directly
                    render_code_button(field_entries[0], state, indent=True)
                else:
                    # Multiple code fields - use expander
                    with ui.expansion(field_name, icon='text_fields').classes('w-full ml-4 text-sm'):
                        for entry in field_entries:
                            render_code_button(entry, state)


def render_code_button(entry: CodeEntry, state: Dict, indent=False):
    """Render a clickable button for a code entry"""
    # Determine icon based on code type
    icon_map = {
        'globalCode': 'public',
        'afterOpen': 'play_arrow',
        'afterCreate': 'add_circle',
        'afterUpdate': 'edit',
        'beforeDelete': 'delete',
        'fn': 'functions',
        'visibility': 'visibility',
        'onClick': 'touch_app',
        'canWrite': 'edit_off',
        'canRead': 'visibility_off',
        'canCreate': 'add_circle_outline',
        'canDelete': 'delete_outline',
        'dchoiceValues': 'list',
        'dchoiceCaption': 'label',
        'beforeShow': 'visibility',
        'afterHide': 'visibility_off',
        'customDataExp': 'data_object',
        'sortExp': 'sort',
        'expression': 'calculate',
    }
    icon = icon_map.get(entry.code_type, 'code')
    
    # Build display label - always show English code type name
    if entry.level == 3 and entry.field_name:
        # For field-level: show "Feldname.codeType" 
        label = f"{entry.field_name}.{entry.code_type}"
    else:
        # For database and table level: just show the code type
        label = entry.code_type
    
    classes = 'w-full justify-start text-left text-sm'
    if indent:
        classes += ' ml-4'
    
    ui.button(
        label,
        icon=icon,
        on_click=lambda e=entry, s=state: show_code_entry(e, s)
    ).props('flat dense align=left').classes(classes)


def show_code_entry(entry: CodeEntry, state: Dict):
    """Display a code entry with the hierarchical format"""
    ui_state = state.get('ui', {})
    code_path_display = ui_state.get('code_path_display')
    code_display = ui_state.get('code_display')
    formatted_display = ui_state.get('formatted_display')
    tabs_container = ui_state.get('tabs_container')
    code_tabs = ui_state.get('code_tabs')
    original_tab = ui_state.get('original_tab')
    copy_button = ui_state.get('copy_button')
    history_expansion = ui_state.get('history_expansion')
    history_container = ui_state.get('history_container')
    
    # Store current code and entry for copy function and history
    state['current_code'] = entry.code
    state['current_entry'] = entry
    
    # Update path display
    if code_path_display:
        code_path_display.text = entry.path
    
    # Show copy button
    if copy_button:
        copy_button.visible = True
    
    # Generate and display code HTML
    if code_display:
        html_content = generate_code_html(entry.code)
        code_display.content = html_content
    
    # Handle formatted code for reports
    if entry.formatted_code and formatted_display and tabs_container:
        formatted_html = generate_code_html(entry.formatted_code)
        formatted_display.content = formatted_html
        tabs_container.visible = True
        # Reset to original tab
        if code_tabs and original_tab:
            code_tabs.value = original_tab
    elif tabs_container:
        tabs_container.visible = False
        if formatted_display:
            formatted_display.content = ''
    
    # Load change history
    if history_expansion and history_container:
        load_code_history(entry, state, history_expansion, history_container)


def generate_code_html(code: str) -> str:
    """Generate HTML with line numbers for Ninox code"""
    lines = code.split('\n')
    
    html_parts = ['''
    <style>
        .code-container {
            font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
            font-size: 13px;
            line-height: 1.6;
            background: #1e1e1e;
            color: #d4d4d4;
            border-radius: 8px;
            overflow: auto;
            max-height: calc(100vh - 380px);
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
    </style>
    <div class="code-container">
        <table class="code-table">
    ''']
    
    for i, line in enumerate(lines, 1):
        escaped_line = escape_html(line)
        
        html_parts.append(f'''
            <tr>
                <td class="line-number">{i}</td>
                <td class="line-content">{escaped_line}</td>
            </tr>
        ''')
    
    html_parts.append('</table></div>')
    
    return ''.join(html_parts)


def escape_html(text: str) -> str:
    """Escape HTML special characters"""
    return (text
        .replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
        .replace('"', '&quot;')
    )


def search_code_entries(query: str, all_entries: List[CodeEntry], results_container, 
                        tree_container, state: Dict):
    """Search through all code entries"""
    results_container.clear()
    
    if not query or len(query) < 2:
        results_container.style('display: none;')
        tree_container.style('display: block;')
        return
    
    results_container.style('display: block;')
    tree_container.style('display: none;')
    
    query_lower = query.lower()
    matches = []
    
    for entry in all_entries:
        # Search in path and code
        if query_lower in entry.path.lower() or query_lower in entry.code.lower():
            matches.append(entry)
    
    with results_container:
        if not matches:
            ui.label(f'Keine Ergebnisse für "{query}"').classes('text-grey-7')
            ui.button(
                'Suche löschen',
                icon='clear',
                on_click=lambda: clear_search(results_container, tree_container)
            ).props('flat dense')
        else:
            ui.label(f'{len(matches)} Treffer gefunden').classes('text-sm text-grey-7 mb-2')
            ui.button(
                'Suche löschen',
                icon='clear',
                on_click=lambda: clear_search(results_container, tree_container)
            ).props('flat dense').classes('mb-2')
            
            for entry in matches[:50]:  # Limit results
                with ui.card().classes('w-full p-2 mb-2 cursor-pointer').on(
                    'click',
                    lambda e=entry, s=state: show_code_entry(e, s)
                ):
                    ui.label(entry.path).classes('font-bold text-sm font-mono')
                    # Show code preview
                    preview = entry.code[:100].replace('\n', ' ')
                    if len(entry.code) > 100:
                        preview += '...'
                    ui.label(preview).classes('text-xs text-grey-8 font-mono')


def clear_search(results_container, tree_container):
    """Clear search results and show tree again"""
    results_container.clear()
    results_container.style('display: none;')
    tree_container.style('display: block;')


def load_code_history(entry: CodeEntry, state: Dict, history_expansion, history_container):
    """
    Load and display change history for a code entry.
    Shows changelog entries from the database that match the code path.
    """
    history_container.clear()
    
    # Get the database ID from state
    database_id = state.get('current_database_id')
    
    # Try to find the database by name if ID not set
    if not database_id:
        db = get_db()
        try:
            database = db.query(Database).filter(
                Database.name == entry.database_name
            ).first()
            if database:
                database_id = database.id
                state['current_database_id'] = database_id
        finally:
            db.close()
    
    if not database_id:
        history_expansion.visible = False
        return
    
    # Load changelogs for this database
    db = get_db()
    try:
        changelogs = db.query(ChangeLog).filter(
            ChangeLog.database_id == database_id
        ).order_by(ChangeLog.commit_date.desc()).limit(20).all()
        
        # Filter changelogs that contain changes to this specific code entry
        # For now, show all changelogs for this database since the changed_items
        # often only contain schema-level changes, not detailed field changes
        relevant_changelogs = changelogs
        
        # Show history expansion if we have data
        if relevant_changelogs:
            history_expansion.visible = True
            history_expansion.text = f'Änderungshistorie ({len(relevant_changelogs)})'
            
            with history_container:
                for changelog in relevant_changelogs[:10]:  # Limit to 10 entries
                    render_changelog_entry(changelog, entry)
        else:
            # Show expansion with "no history" message
            history_expansion.visible = True
            history_expansion.text = 'Änderungshistorie'
            
            with history_container:
                ui.label('Keine Änderungshistorie verfügbar.').classes('text-grey-7 text-sm')
                ui.label(
                    'Die Historie wird bei zukünftigen Synchronisierungen aufgezeichnet.'
                ).classes('text-grey-6 text-xs')
    
    except Exception as e:
        history_expansion.visible = True
        with history_container:
            ui.label(f'Fehler beim Laden der Historie: {str(e)}').classes('text-negative text-sm')
    finally:
        db.close()


def render_changelog_entry(changelog: ChangeLog, entry: CodeEntry):
    """Render a single changelog entry in the history list"""
    
    # Format date
    date_str = changelog.commit_date.strftime('%d.%m.%Y %H:%M') if changelog.commit_date else 'Unbekannt'
    
    # Determine change indicator color
    change_color = 'primary'
    if changelog.additions > changelog.deletions:
        change_color = 'positive'
    elif changelog.deletions > changelog.additions:
        change_color = 'negative'
    
    with ui.card().classes('w-full p-3 mb-2').style('background-color: #f8f9fa;'):
        # Header row with date and stats
        with ui.row().classes('w-full items-center justify-between mb-2'):
            with ui.row().classes('items-center gap-2'):
                ui.icon('schedule', size='xs').classes('text-grey-7')
                ui.label(date_str).classes('text-sm font-medium')
            
            # Change stats badge
            with ui.row().classes('items-center gap-1'):
                if changelog.additions > 0:
                    ui.label(f'+{changelog.additions}').classes('text-positive text-xs')
                if changelog.deletions > 0:
                    ui.label(f'-{changelog.deletions}').classes('text-negative text-xs')
        
        # AI Summary (if available)
        if changelog.ai_summary:
            ui.label(changelog.ai_summary).classes('text-sm text-grey-8 mb-2')
        elif changelog.commit_message:
            # Fallback to commit message
            msg = changelog.commit_message[:100]
            if len(changelog.commit_message) > 100:
                msg += '...'
            ui.label(msg).classes('text-sm text-grey-7 mb-2 italic')
        
        # Details expansion (if AI details available)
        if changelog.ai_details or changelog.diff_patch:
            with ui.expansion('Details anzeigen', icon='expand_more').classes('w-full').props('dense'):
                if changelog.ai_details:
                    ui.markdown(changelog.ai_details).classes('text-sm')
                
                if changelog.diff_patch:
                    with ui.expansion('Diff anzeigen', icon='code').classes('w-full mt-2').props('dense'):
                        # Render diff with syntax highlighting
                        diff_html = render_diff_html(changelog.diff_patch)
                        ui.html(diff_html, sanitize=False).classes('w-full')
        
        # Footer with commit info
        with ui.row().classes('w-full items-center justify-between mt-2'):
            if changelog.commit_url:
                ui.link(
                    f'Commit {changelog.short_sha}',
                    changelog.commit_url,
                    new_tab=True
                ).classes('text-xs text-primary')
            else:
                ui.label(f'Commit {changelog.short_sha}').classes('text-xs text-grey-6')
            
            with ui.row().classes('items-center gap-2'):
                # Token info
                if changelog.has_token_info:
                    ui.label(changelog.token_summary_text).classes('text-xs text-amber-600')
                
                if changelog.ai_provider:
                    ui.label(f'via {changelog.ai_provider}').classes('text-xs text-grey-5')


def render_diff_html(diff_patch: str) -> str:
    """Render a diff/patch with syntax highlighting"""
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
            max-height: 300px;
        }
        .diff-line-add {
            background: rgba(40, 167, 69, 0.2);
            color: #98c379;
        }
        .diff-line-del {
            background: rgba(220, 53, 69, 0.2);
            color: #e06c75;
        }
        .diff-line-header {
            color: #61afef;
            font-weight: bold;
        }
    </style>
    <div class="diff-container">
    ''']
    
    for line in lines:
        escaped_line = escape_html(line)
        
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
