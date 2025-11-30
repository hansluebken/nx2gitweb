"""
Ninox Code Extractor
Extracts Ninox script code from database structure JSON and organizes it into files.
"""
import re
from typing import Dict, List, Optional, Any
from dataclasses import dataclass


# Known Ninox code fields
CODE_FIELDS = [
    # Formula/Script fields
    'fn',              # Formula fields
    'globalCode',      # Global database code
    
    # Triggers
    'afterCreate',     # Trigger after record creation
    'afterUpdate',     # Trigger after record update
    'beforeShow',      # Trigger before view is shown
    'afterHide',       # Trigger after view is hidden
    'beforeDelete',    # Trigger before record deletion
    'onClick',         # Button click handler
    'onOpen',          # Trigger when opening
    'onClose',         # Trigger when closing
    'trigger',         # General triggers
    
    # Dynamic choice fields
    'dchoiceValues',   # Dynamic choice values
    'dchoiceCaption',  # Dynamic choice caption formula
    'dchoiceColor',    # Dynamic choice color formula
    'dchoiceIcon',     # Dynamic choice icon formula
    
    # Permissions/Constraints
    'constraint',      # Constraint formula
    'visibility',      # Visibility formulas
    'canRead',         # Read permission formula
    'canWrite',        # Write permission formula
    'canCreate',       # Create permission formula
    'canDelete',       # Delete permission formula
    
    # Validation
    'validation',      # Validation formulas
    
    # View-specific (handled separately in Views)
    'expression',      # Expression in Views
    'filter',          # Filter in Views
    
    # Other
    'printout',        # Print layout code
    'color',           # Color formulas (if script-based)
]

# Human-readable names for code types
CODE_TYPE_NAMES = {
    # Formula/Script
    'fn': 'Formula Field',
    'globalCode': 'Global Code',
    
    # Triggers
    'afterCreate': 'After Create Trigger',
    'afterUpdate': 'After Update Trigger',
    'beforeShow': 'Before Show Trigger',
    'afterHide': 'After Hide Trigger',
    'beforeDelete': 'Before Delete Trigger',
    'onClick': 'Button Click Handler',
    'onOpen': 'On Open Trigger',
    'onClose': 'On Close Trigger',
    'trigger': 'Trigger',
    
    # Dynamic choice
    'dchoiceValues': 'Dynamic Choice Values',
    'dchoiceCaption': 'Dynamic Choice Caption',
    'dchoiceColor': 'Dynamic Choice Color',
    'dchoiceIcon': 'Dynamic Choice Icon',
    
    # Permissions/Constraints
    'constraint': 'Constraint Formula',
    'visibility': 'Visibility Formula',
    'canRead': 'Can Read Permission',
    'canWrite': 'Can Write Permission',
    'canCreate': 'Can Create Permission',
    'canDelete': 'Can Delete Permission',
    
    # Validation
    'validation': 'Validation Formula',
    
    # View-specific
    'expression': 'View Expression',
    'filter': 'View Filter',
    
    # Other
    'printout': 'Print Layout',
    'color': 'Color Formula',
}


@dataclass
class CodeItem:
    """Represents a single piece of extracted code"""
    table_id: str
    table_name: str
    field_id: str
    field_name: str
    code_type: str
    code: str
    context: str  # Additional context (e.g., view name)
    
    def get_file_path(self) -> str:
        """Generate the file path for this code item"""
        # Sanitize names for file system
        table = sanitize_filename(self.table_name) if self.table_name else '_database'
        
        if self.code_type == 'globalCode':
            return 'code/_global.nx'
        
        if self.context and self.context.startswith('[View:'):
            # View-related code
            view_name = self.context.replace('[View:', '').replace(']', '')
            view_name = sanitize_filename(view_name)
            return f'code/{table}/views/{view_name}.{self.code_type}.nx'
        
        if self.field_name:
            field = sanitize_filename(self.field_name)
            return f'code/{table}/{field}.{self.code_type}.nx'
        else:
            # Table-level code (afterCreate, afterUpdate on table)
            return f'code/{table}/_table.{self.code_type}.nx'
    
    def get_file_header(self) -> str:
        """Generate a header comment for the code file"""
        lines = [
            '# ' + '=' * 60,
        ]
        
        if self.table_name:
            lines.append(f'# Table: {self.table_name}')
        
        if self.field_name:
            lines.append(f'# Field: {self.field_name}')
        
        if self.context and not self.context.startswith('['):
            lines.append(f'# Context: {self.context}')
        elif self.context and self.context.startswith('[View:'):
            view_name = self.context.replace('[View:', '').replace(']', '')
            lines.append(f'# View: {view_name}')
        
        type_name = CODE_TYPE_NAMES.get(self.code_type, self.code_type)
        lines.append(f'# Type: {type_name}')
        lines.append('# ' + '=' * 60)
        lines.append('')
        
        return '\n'.join(lines)
    
    def get_file_content(self) -> str:
        """Generate the complete file content with header and code"""
        return self.get_file_header() + self.code


def sanitize_filename(name: str) -> str:
    """Sanitize a string to be used as a filename"""
    if not name:
        return '_unnamed'
    
    # Replace problematic characters
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    name = re.sub(r'\s+', '_', name)
    name = re.sub(r'_+', '_', name)
    name = name.strip('_.')
    
    # Limit length
    if len(name) > 50:
        name = name[:50]
    
    return name or '_unnamed'


def extract_code_from_structure(structure: Dict[str, Any], database_name: str = '') -> List[CodeItem]:
    """
    Extract all Ninox code from a database structure.
    
    Args:
        structure: The database structure JSON (from Ninox API)
        database_name: Name of the database for context
    
    Returns:
        List of CodeItem objects containing all extracted code
    """
    results = []
    schema = structure.get('schema', structure)
    
    # Extract global code
    global_code = schema.get('globalCode', '')
    if global_code and global_code.strip():
        results.append(CodeItem(
            table_id='',
            table_name='',
            field_id='',
            field_name='',
            code_type='globalCode',
            code=global_code,
            context=database_name
        ))
    
    # Extract code from tables
    types = schema.get('types', {})
    for table_id, table_data in types.items():
        if not isinstance(table_data, dict):
            continue
        
        # Use caption first, then name, then ID as fallback
        table_name = table_data.get('caption') or table_data.get('name') or table_id
        
        # Table-level triggers and permissions
        table_code_fields = [
            'afterCreate', 'afterUpdate', 'beforeShow', 'afterHide',
            'beforeDelete', 'onOpen', 'onClose', 'trigger',
            'canRead', 'canWrite', 'canCreate', 'canDelete',
            'printout'
        ]
        for code_field in table_code_fields:
            if code_field in table_data:
                code = table_data[code_field]
                if isinstance(code, str) and code.strip():
                    results.append(CodeItem(
                        table_id=table_id,
                        table_name=table_name,
                        field_id='',
                        field_name='',
                        code_type=code_field,
                        code=code,
                        context=''
                    ))
        
        # Field-level code
        fields = table_data.get('fields', {})
        for field_id, field_data in fields.items():
            if not isinstance(field_data, dict):
                continue
            
            # Use caption first, then name, then ID as fallback
            field_name = field_data.get('caption') or field_data.get('name') or field_id
            
            for code_field in CODE_FIELDS:
                if code_field in field_data:
                    code = field_data[code_field]
                    if isinstance(code, str) and code.strip():
                        # Skip very short non-code values
                        if len(code) < 3 and code_field == 'fn':
                            continue
                        results.append(CodeItem(
                            table_id=table_id,
                            table_name=table_name,
                            field_id=field_id,
                            field_name=field_name,
                            code_type=code_field,
                            code=code,
                            context=''
                        ))
        
        # UI/View-level code
        uis = table_data.get('uis', {})
        for ui_id, ui_data in uis.items():
            if not isinstance(ui_data, dict):
                continue
            
            # Use caption first, then name, then ID as fallback
            ui_name = ui_data.get('caption') or ui_data.get('name') or ui_id
            
            # View-level code fields
            view_code_fields = [
                'beforeShow', 'afterHide', 'onClick',
                'onOpen', 'onClose',
                'expression', 'filter'
            ]
            for code_field in view_code_fields:
                if code_field in ui_data:
                    code = ui_data[code_field]
                    if isinstance(code, str) and code.strip():
                        results.append(CodeItem(
                            table_id=table_id,
                            table_name=table_name,
                            field_id=ui_id,
                            field_name='',
                            code_type=code_field,
                            code=code,
                            context=f'[View:{ui_name}]'
                        ))
    
    return results


def generate_code_files(code_items: List[CodeItem]) -> Dict[str, str]:
    """
    Generate a dictionary of file paths to file contents.
    
    Args:
        code_items: List of CodeItem objects
    
    Returns:
        Dictionary mapping file paths to their contents
    """
    files = {}
    
    for item in code_items:
        path = item.get_file_path()
        content = item.get_file_content()
        files[path] = content
    
    return files


def generate_code_index(code_items: List[CodeItem], database_name: str = '') -> str:
    """
    Generate an index/README file for the code directory.
    
    Args:
        code_items: List of CodeItem objects
        database_name: Name of the database
    
    Returns:
        Markdown content for the index file
    """
    lines = [
        f'# Ninox Code: {database_name}',
        '',
        f'Total code items: {len(code_items)}',
        '',
        '## Summary by Type',
        '',
        '| Type | Count |',
        '|------|-------|',
    ]
    
    # Count by type
    by_type = {}
    for item in code_items:
        type_name = CODE_TYPE_NAMES.get(item.code_type, item.code_type)
        by_type[type_name] = by_type.get(type_name, 0) + 1
    
    for type_name, count in sorted(by_type.items(), key=lambda x: -x[1]):
        lines.append(f'| {type_name} | {count} |')
    
    lines.extend([
        '',
        '## Summary by Table',
        '',
        '| Table | Code Items |',
        '|-------|------------|',
    ])
    
    # Count by table
    by_table = {}
    for item in code_items:
        table = item.table_name or '(Global)'
        by_table[table] = by_table.get(table, 0) + 1
    
    for table, count in sorted(by_table.items()):
        lines.append(f'| {table} | {count} |')
    
    lines.extend([
        '',
        '## Files',
        '',
    ])
    
    # Group files by directory
    files_by_dir = {}
    for item in code_items:
        path = item.get_file_path()
        dir_path = '/'.join(path.split('/')[:-1])
        if dir_path not in files_by_dir:
            files_by_dir[dir_path] = []
        files_by_dir[dir_path].append((path, item))
    
    for dir_path in sorted(files_by_dir.keys()):
        lines.append(f'### {dir_path}/')
        lines.append('')
        for path, item in sorted(files_by_dir[dir_path], key=lambda x: x[0]):
            filename = path.split('/')[-1]
            desc = f'{item.field_name}' if item.field_name else ''
            if item.context:
                desc = item.context
            type_name = CODE_TYPE_NAMES.get(item.code_type, item.code_type)
            lines.append(f'- `{filename}` - {type_name}' + (f' ({desc})' if desc else ''))
        lines.append('')
    
    return '\n'.join(lines)


def extract_and_generate(structure: Dict[str, Any], database_name: str = '') -> Dict[str, str]:
    """
    Main function: Extract code from structure and generate all files.
    
    Args:
        structure: The database structure JSON
        database_name: Name of the database
    
    Returns:
        Dictionary mapping file paths to their contents, including index
    """
    # Extract code items
    code_items = extract_code_from_structure(structure, database_name)
    
    if not code_items:
        return {}
    
    # Generate code files
    files = generate_code_files(code_items)
    
    # Generate index
    index_content = generate_code_index(code_items, database_name)
    files['code/README.md'] = index_content
    
    return files
