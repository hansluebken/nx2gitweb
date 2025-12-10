"""
Ninox Scripts Markdown Generator
Generates SCRIPTS.md file from YAML structure, matching Ninox "Entwicklung > YAML-Code" display format.
"""

import logging
from typing import List, Dict, Any
from datetime import datetime
from .ninox_yaml_parser import NinoxYAMLParser, CodeLocation, CodeLevel

logger = logging.getLogger(__name__)


def generate_scripts_md(yaml_db: Any) -> str:
    """
    Generate SCRIPTS.md file from a NinoxDatabase object.

    The format matches Ninox's "Entwicklung > YAML-Code" view:
    - (Database) (line_count)
    - (Ohne Feld) (line_count)
    - Element-Name (line_count)

    Args:
        yaml_db: NinoxDatabase object from NinoxYAMLParser

    Returns:
        Markdown formatted string with all scripts
    """
    lines = []

    # Header
    lines.append(f"# Scripts: {yaml_db.name}")
    lines.append("")
    lines.append(f"> Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("> This file contains all scripts from the database in the same structure as 'Entwicklung > YAML-Code'")
    lines.append("")

    # Extract all code locations using the parser
    parser = NinoxYAMLParser(str(yaml_db.path.parent))
    code_locations = parser.extract_code_locations(yaml_db)

    if not code_locations:
        lines.append("*No scripts found.*")
        return "\n".join(lines)

    # Group code locations by hierarchy
    grouped = _group_code_locations(code_locations)

    # Generate sections
    # 1. Database-level code
    if 'database' in grouped:
        lines.extend(_generate_database_section(grouped['database']))

    # 2. Table-level sections
    for table_name in sorted(grouped.get('tables', {}).keys()):
        table_data = grouped['tables'][table_name]
        lines.extend(_generate_table_section(table_name, table_data))

    return "\n".join(lines)


def _group_code_locations(locations: List[CodeLocation]) -> Dict[str, Any]:
    """
    Group code locations by hierarchy: database, tables, fields, uis

    Returns structure:
    {
        'database': [CodeLocation, ...],
        'tables': {
            'TableName': {
                'table_code': [CodeLocation, ...],
                'fields': {
                    'FieldName': [CodeLocation, ...]
                },
                'uis': {
                    'UIName': [CodeLocation, ...]
                }
            }
        }
    }
    """
    grouped = {
        'database': [],
        'tables': {}
    }

    for loc in locations:
        if loc.level == CodeLevel.DATABASE:
            grouped['database'].append(loc)

        elif loc.table_name:
            # Initialize table structure
            if loc.table_name not in grouped['tables']:
                grouped['tables'][loc.table_name] = {
                    'table_code': [],
                    'fields': {},
                    'uis': {}
                }

            table_data = grouped['tables'][loc.table_name]

            if loc.level == CodeLevel.TABLE:
                table_data['table_code'].append(loc)

            elif loc.level == CodeLevel.FIELD and loc.element_name:
                if loc.element_name not in table_data['fields']:
                    table_data['fields'][loc.element_name] = []
                table_data['fields'][loc.element_name].append(loc)

            elif loc.level == CodeLevel.UI and loc.element_name:
                if loc.element_name not in table_data['uis']:
                    table_data['uis'][loc.element_name] = []
                table_data['uis'][loc.element_name].append(loc)

    return grouped


def _generate_database_section(db_code: List[CodeLocation]) -> List[str]:
    """Generate database-level code section"""
    lines = []

    lines.append("## Database")
    lines.append("")

    for code_loc in sorted(db_code, key=lambda x: x.code_type):
        line_count = code_loc.line_count
        lines.append(f"### (Database) ({line_count})")
        lines.append(f"**{code_loc.type_display_name}**")
        lines.append("")
        lines.append("```javascript")
        lines.append(code_loc.code)
        lines.append("```")
        lines.append("")

    return lines


def _generate_table_section(table_name: str, table_data: Dict[str, Any]) -> List[str]:
    """Generate table section with all code (table-level, fields, uis)"""
    lines = []

    lines.append("---")
    lines.append(f"## Table: {table_name}")
    lines.append("")

    # Table-level code (triggers like afterCreate, afterUpdate)
    if table_data['table_code']:
        lines.append("### Table Triggers")
        lines.append("")

        for code_loc in sorted(table_data['table_code'], key=lambda x: x.code_type):
            line_count = code_loc.line_count
            lines.append(f"#### (Without Field) ({line_count})")
            lines.append(f"**{code_loc.type_display_name}**")
            lines.append("")
            lines.append("```javascript")
            lines.append(code_loc.code)
            lines.append("```")
            lines.append("")

    # Field-level code
    if table_data['fields']:
        lines.append("### Fields")
        lines.append("")

        for field_name in sorted(table_data['fields'].keys()):
            field_codes = table_data['fields'][field_name]

            for code_loc in sorted(field_codes, key=lambda x: x.code_type):
                line_count = code_loc.line_count
                lines.append(f"#### {field_name} ({line_count})")
                lines.append(f"**{code_loc.type_display_name}**")
                lines.append("")
                lines.append("```javascript")
                lines.append(code_loc.code)
                lines.append("```")
                lines.append("")

    # UI-level code (views, buttons, forms)
    if table_data['uis']:
        lines.append("### UI Elements")
        lines.append("")

        for ui_name in sorted(table_data['uis'].keys()):
            ui_codes = table_data['uis'][ui_name]

            for code_loc in sorted(ui_codes, key=lambda x: x.code_type):
                line_count = code_loc.line_count
                lines.append(f"#### {ui_name} ({line_count})")
                lines.append(f"**{code_loc.type_display_name}**")
                lines.append("")
                lines.append("```javascript")
                lines.append(code_loc.code)
                lines.append("```")
                lines.append("")

    return lines
