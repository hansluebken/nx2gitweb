"""
Ninox to Mermaid ERD Generator
Converts Ninox database structure JSON to Mermaid ERD diagrams
"""
import json
from typing import Dict, List, Any, Tuple
import re


class NinoxToMermaidConverter:
    """Convert Ninox database structure to Mermaid ERD diagrams"""

    # Mapping Ninox field types to ERD types (Mermaid compatible)
    TYPE_MAPPING = {
        'string': 'string',
        'text': 'text',
        'number': 'number',
        'bool': 'boolean',
        'date': 'date',
        'datetime': 'datetime',
        'time': 'time',
        'choice': 'string',  # Mermaid doesn't support enum
        'multichoice': 'string',  # Mermaid doesn't support arrays
        'file': 'string',
        'image': 'string',
        'ref': 'int',  # Foreign key as int
        'rev': 'int',  # Reverse reference as int
        'email': 'string',
        'phone': 'string',
        'url': 'string',
        'location': 'string',
        'color': 'string',
        'icon': 'string',
        'formula': 'string',  # Computed field
        'button': 'string'  # Action
    }

    def __init__(self, json_structure: Dict[str, Any], max_tables_per_diagram: int = 10):
        """Initialize the converter

        Args:
            json_structure: The Ninox database structure
            max_tables_per_diagram: Maximum tables per diagram for readability
        """
        self.structure = json_structure
        self.max_tables = max_tables_per_diagram
        self.tables = {}
        self.relationships = []
        self._parse_structure()

    def _parse_structure(self):
        """Parse the Ninox structure into tables and relationships"""
        if 'schema' not in self.structure or 'types' not in self.structure['schema']:
            return

        types = self.structure['schema']['types']

        # Parse each table (type)
        for type_id, type_data in types.items():
            table_name = self._sanitize_name(type_data.get('caption', type_id))
            self.tables[type_id] = {
                'name': table_name,
                'caption': type_data.get('caption', type_id),
                'fields': [],
                'references': []
            }

            # Parse fields
            if 'fields' in type_data:
                for field_id, field_data in type_data['fields'].items():
                    field_type = field_data.get('base', 'string')
                    field_caption = field_data.get('caption', field_id)

                    # Store field info
                    field_info = {
                        'id': field_id,
                        'caption': field_caption,
                        'type': field_type,
                        'erd_type': self.TYPE_MAPPING.get(field_type, 'string'),
                        'required': field_data.get('required', False)
                    }

                    self.tables[type_id]['fields'].append(field_info)

                    # Check for relationships
                    if field_type in ['ref', 'rev']:
                        # Reference to another table
                        ref_type = field_data.get('type')
                        if ref_type and ref_type in types:
                            self.relationships.append({
                                'from': type_id,
                                'to': ref_type,
                                'field': field_caption,
                                'type': 'one-to-many' if field_type == 'ref' else 'many-to-many'
                            })
                            self.tables[type_id]['references'].append({
                                'field': field_caption,
                                'target': ref_type
                            })

    def _sanitize_name(self, name: str) -> str:
        """Sanitize names for Mermaid compatibility"""
        # Replace spaces and special chars with underscores
        name = re.sub(r'[^\w\s-]', '', name)
        name = re.sub(r'[-\s]+', '_', name)
        return name.upper()

    def generate_overview(self) -> str:
        """Generate an overview diagram showing all tables without fields"""
        if not self.tables:
            return "graph TB\n    EMPTY[No tables found]"

        mermaid = "graph TB\n"
        mermaid += "    %% Overview of all tables\n"

        # Add all tables as nodes
        for type_id, table in self.tables.items():
            field_count = len(table['fields'])
            table_name = table['name']
            mermaid += f'    {table_name}["{table["caption"]}<br/>{field_count} fields"]\n'

        # Add relationships as connections
        for rel in self.relationships:
            from_table = self.tables[rel['from']]['name']
            to_table = self.tables[rel['to']]['name']
            mermaid += f'    {from_table} --> {to_table}\n'

        return mermaid

    def generate_relationships(self) -> str:
        """Generate a diagram showing only relationships between tables"""
        if not self.relationships:
            return "erDiagram\n    %% No relationships found"

        mermaid = "erDiagram\n"
        mermaid += "    %% Table relationships\n\n"

        # Track which tables are involved in relationships
        involved_tables = set()

        # Add relationships
        for rel in self.relationships:
            from_table = self.tables[rel['from']]['name']
            to_table = self.tables[rel['to']]['name']
            involved_tables.add(rel['from'])
            involved_tables.add(rel['to'])

            if rel['type'] == 'one-to-many':
                mermaid += f'    {from_table} ||--o{{ {to_table} : "{rel["field"]}"\n'
            else:
                mermaid += f'    {from_table} }}o--o{{ {to_table} : "{rel["field"]}"\n'

        # Add table definitions (only involved tables, no fields)
        mermaid += "\n    %% Table definitions (structure only)\n"
        for type_id in involved_tables:
            if type_id in self.tables:
                table = self.tables[type_id]
                mermaid += f'    {table["name"]} {{\n'
                mermaid += f'        string table_info "Table: {table["caption"]}"\n'
                mermaid += f'    }}\n\n'

        return mermaid

    def generate_table_detail(self, type_id: str) -> str:
        """Generate detailed ERD for a single table with all fields"""
        if type_id not in self.tables:
            return f"erDiagram\n    %% Table {type_id} not found"

        table = self.tables[type_id]
        mermaid = "erDiagram\n"
        mermaid += f'    %% Table: {table["caption"]}\n\n'

        # Add the table with all fields
        mermaid += f'    {table["name"]} {{\n'

        for field in table['fields']:
            field_type = field['erd_type']
            field_name = self._sanitize_field_name(field['caption'])
            required = "PK" if field['id'] == 'id' else "NOT NULL" if field['required'] else ""

            # Format the field line
            if field['type'] in ['ref', 'rev']:
                # Foreign key - use int type and mark as FK in comment
                mermaid += f'        int {field_name} "{field["caption"]} (FK)"\n'
            else:
                # Regular field with optional required marker
                if required:
                    mermaid += f'        {field_type} {field_name} "{field["caption"]} ({required})"\n'
                else:
                    mermaid += f'        {field_type} {field_name} "{field["caption"]}"\n'

        mermaid += '    }\n'

        # Add relationships for this table
        if table['references']:
            mermaid += '\n    %% Relationships\n'
            for ref in table['references']:
                target_table = self.tables.get(ref['target'])
                if target_table:
                    mermaid += f'    {table["name"]} ||--o{{ {target_table["name"]} : "{ref["field"]}"\n'

        return mermaid

    def _sanitize_field_name(self, name: str) -> str:
        """Sanitize field names for Mermaid - must be valid identifiers"""
        # Remove all non-alphanumeric characters except underscores
        name = re.sub(r'[^\w]', '_', name)
        # Replace multiple underscores with single one
        name = re.sub(r'_+', '_', name)
        # Remove leading/trailing underscores
        name = name.strip('_')
        # Ensure it starts with a letter (prefix with 'f_' if it starts with number)
        if name and name[0].isdigit():
            name = f'f_{name}'
        # If empty, use generic name
        if not name:
            name = 'field'
        return name.lower()

    def generate_full_erd(self) -> str:
        """Generate complete ERD with all tables and fields"""
        if not self.tables:
            return "erDiagram\n    %% No tables found"

        mermaid = "erDiagram\n"
        mermaid += f"    %% Database: {self.structure.get('settings', {}).get('name', 'Unknown')}\n"
        mermaid += f"    %% Tables: {len(self.tables)}\n\n"

        # Check if we need to split
        if len(self.tables) > self.max_tables:
            mermaid += f"    %% WARNING: {len(self.tables)} tables exceed limit of {self.max_tables}\n"
            mermaid += "    %% Consider using grouped ERDs for better readability\n\n"

        # Add all tables with fields
        for type_id, table in self.tables.items():
            mermaid += f'    {table["name"]} {{\n'

            # Add up to 10 fields (to keep it readable)
            field_count = 0
            for field in table['fields']:
                if field_count >= 10:
                    mermaid += f'        string more_fields "... and {len(table["fields"]) - 10} more fields"\n'
                    break

                field_type = field['erd_type']
                field_name = self._sanitize_field_name(field['caption'])

                # Use proper Mermaid syntax for fields
                if field['type'] in ['ref', 'rev']:
                    mermaid += f'        int {field_name}\n'
                else:
                    mermaid += f'        {field_type} {field_name}\n'
                field_count += 1

            mermaid += '    }\n\n'

        # Add relationships
        if self.relationships:
            mermaid += "    %% Relationships\n"
            for rel in self.relationships:
                from_table = self.tables[rel['from']]['name']
                to_table = self.tables[rel['to']]['name']

                if rel['type'] == 'one-to-many':
                    mermaid += f'    {from_table} ||--o{{ {to_table} : "{rel["field"]}"\n'
                else:
                    mermaid += f'    {from_table} }}o--o{{ {to_table} : "{rel["field"]}"\n'

        return mermaid

    def generate_grouped_erds(self) -> Dict[str, str]:
        """Generate grouped ERDs for large databases

        Returns:
            Dictionary with group names as keys and Mermaid diagrams as values
        """
        # For now, simple implementation - split into chunks
        # In future, could group by relationships
        groups = {}
        table_list = list(self.tables.items())

        for i in range(0, len(table_list), self.max_tables):
            chunk = dict(table_list[i:i + self.max_tables])
            group_name = f"group_{i // self.max_tables + 1}"

            # Create a temporary converter with just this chunk
            temp_structure = {
                'settings': self.structure.get('settings', {}),
                'schema': {
                    'types': {k: self.structure['schema']['types'][k] for k in chunk.keys()}
                }
            }

            temp_converter = NinoxToMermaidConverter(temp_structure, self.max_tables)
            groups[group_name] = temp_converter.generate_full_erd()

        return groups

    def generate_index_markdown(self) -> str:
        """Generate an index markdown file with links to all diagrams"""
        db_name = self.structure.get('settings', {}).get('name', 'Database')

        md = f"# {db_name} - Entity Relationship Diagrams\n\n"
        md += f"**Generated from Ninox database structure**\n\n"
        md += f"## Statistics\n"
        md += f"- Tables: {len(self.tables)}\n"
        md += f"- Relationships: {len(self.relationships)}\n"
        md += f"- Total fields: {sum(len(t['fields']) for t in self.tables.values())}\n\n"

        md += "## Available Diagrams\n\n"
        md += "### Overview\n"
        md += "- [Table Overview](./erd-overview.md) - All tables with connections\n"
        md += "- [Relationships](./erd-relationships.md) - Focus on table relationships\n\n"

        if len(self.tables) <= self.max_tables:
            md += "### Complete ERD\n"
            md += "- [Full ERD](./erd-full.md) - All tables with fields\n\n"
        else:
            md += "### Grouped ERDs\n"
            md += f"*Database has {len(self.tables)} tables, split into groups for readability*\n\n"
            group_count = (len(self.tables) + self.max_tables - 1) // self.max_tables
            for i in range(group_count):
                md += f"- [Group {i + 1}](./erd-group-{i + 1}.md)\n"

        md += "\n### Individual Tables\n"
        for type_id, table in self.tables.items():
            md += f"- [{table['caption']}](./tables/{table['name'].lower()}.md) "
            md += f"({len(table['fields'])} fields)\n"

        return md

    def should_split(self) -> bool:
        """Check if the database should be split into multiple diagrams"""
        return len(self.tables) > self.max_tables


def generate_all_diagrams(json_structure: Dict[str, Any]) -> Dict[str, str]:
    """Generate all ERD diagrams for a Ninox database

    Args:
        json_structure: The Ninox database structure JSON

    Returns:
        Dictionary with file paths as keys and content as values
    """
    converter = NinoxToMermaidConverter(json_structure)
    files = {}

    # Always generate overview and relationships
    files['erd-overview.md'] = f"# Table Overview\n\n```mermaid\n{converter.generate_overview()}\n```\n"
    files['erd-relationships.md'] = f"# Table Relationships\n\n```mermaid\n{converter.generate_relationships()}\n```\n"

    # Generate full or grouped ERDs
    if converter.should_split():
        # Generate grouped ERDs
        groups = converter.generate_grouped_erds()
        for i, (group_name, diagram) in enumerate(groups.items(), 1):
            files[f'erd-group-{i}.md'] = f"# ERD Group {i}\n\n```mermaid\n{diagram}\n```\n"
    else:
        # Generate single full ERD
        files['erd-full.md'] = f"# Complete ERD\n\n```mermaid\n{converter.generate_full_erd()}\n```\n"

    # Generate individual table diagrams
    for type_id, table in converter.tables.items():
        table_name = table['name'].lower()
        files[f'tables/{table_name}.md'] = (
            f"# Table: {table['caption']}\n\n"
            f"```mermaid\n{converter.generate_table_detail(type_id)}\n```\n"
        )

    # Generate index
    files['README.md'] = converter.generate_index_markdown()

    return files


# Test function
if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        with open(sys.argv[1], 'r', encoding='utf-8') as f:
            structure = json.load(f)

        converter = NinoxToMermaidConverter(structure)

        print("=== OVERVIEW ===")
        print(converter.generate_overview())
        print("\n=== RELATIONSHIPS ===")
        print(converter.generate_relationships())

        if converter.tables:
            first_table = list(converter.tables.keys())[0]
            print(f"\n=== DETAIL FOR {first_table} ===")
            print(converter.generate_table_detail(first_table))