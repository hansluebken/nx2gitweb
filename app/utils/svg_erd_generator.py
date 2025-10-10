"""
SVG ERD Generator for Ninox Databases
Generates clean, scalable SVG Entity-Relationship Diagrams using Graphviz
"""
import json
from typing import Dict, List, Any
from graphviz import Digraph
import re


class SvgErdGenerator:
    """Generate SVG ERD diagrams from Ninox database structure"""

    def __init__(self, json_structure: Dict[str, Any]):
        """Initialize ERD generator

        Args:
            json_structure: Ninox database structure JSON
        """
        self.structure = json_structure
        self.tables = {}
        self.relationships = []
        self._parse_structure()

    def _parse_structure(self):
        """Parse Ninox structure into tables and relationships"""
        if 'schema' not in self.structure or 'types' not in self.structure['schema']:
            return

        types = self.structure['schema']['types']

        # Parse each table
        for type_id, type_data in types.items():
            table_name = type_data.get('caption', type_id)
            self.tables[type_id] = {
                'name': table_name,
                'uuid': type_data.get('uuid'),
                'fields': [],
                'primary_key': None
            }

            # Parse fields
            if 'fields' in type_data:
                for field_id, field_data in type_data['fields'].items():
                    field_type = field_data.get('base', 'string')
                    field_caption = field_data.get('caption', field_id)
                    is_required = field_data.get('required', False)

                    # Store all reference information
                    field_info = {
                        'id': field_id,
                        'caption': field_caption,
                        'type': field_type,
                        'required': is_required,
                        'refTypeId': field_data.get('refTypeId'),
                        'refTypeUUID': field_data.get('refTypeUUID'),
                        'dbId': field_data.get('dbId'),  # External database reference
                        'dbName': field_data.get('dbName')  # External database name
                    }

                    # Check if it's the primary key
                    if field_id == 'id' or field_id.lower() == 'id':
                        self.tables[type_id]['primary_key'] = field_caption

                    self.tables[type_id]['fields'].append(field_info)

                    # Track relationships
                    if field_type in ['ref', 'rev']:
                        ref_type_id = field_data.get('refTypeId')
                        ref_type_uuid = field_data.get('refTypeUUID')

                        target_type = None
                        if ref_type_id and ref_type_id in types:
                            target_type = ref_type_id
                        elif ref_type_uuid:
                            for tid, tdata in types.items():
                                if tdata.get('uuid') == ref_type_uuid:
                                    target_type = tid
                                    break

                        if target_type:
                            self.relationships.append({
                                'from_table': type_id,
                                'to_table': target_type,
                                'field': field_caption,
                                'type': field_type,
                                'cardinality': '1:N' if field_type == 'ref' else 'N:M'
                            })

    def _get_field_type_display(self, field_type: str) -> str:
        """Get display name for field type"""
        type_map = {
            'string': 'Text',
            'text': 'LongText',
            'number': 'Number',
            'bool': 'Boolean',
            'date': 'Date',
            'datetime': 'DateTime',
            'time': 'Time',
            'choice': 'Choice',
            'multichoice': 'MultiChoice',
            'ref': 'Reference',
            'rev': 'ReverseRef',
            'email': 'Email',
            'phone': 'Phone',
            'url': 'URL',
            'file': 'File',
            'image': 'Image',
            'formula': 'Formula',
            'button': 'Action'
        }
        return type_map.get(field_type, field_type.title())

    def generate_erd_svg(self, output_format='svg') -> str:
        """Generate ERD diagram as SVG

        Args:
            output_format: Output format (svg, png, pdf)

        Returns:
            SVG content as string
        """
        # Create directed graph with optimized layout for compact diagrams
        dot = Digraph(comment='Database ERD', format=output_format)

        # Graph layout settings - optimized for compactness
        dot.attr(rankdir='LR')  # Left to Right (often more compact than TB)
        dot.attr('graph',
                 splines='polyline',  # Polyline instead of ortho for shorter lines
                 nodesep='0.5',       # Reduced from 1.0 - tables closer together
                 ranksep='0.8',       # Reduced from 1.5 - ranks closer
                 concentrate='true',  # Merge edges where possible
                 compound='true',     # Allow edges between clusters
                 overlap='false',     # Prevent node overlap
                 packMode='graph')    # Try to pack the graph tighter

        # Node settings
        dot.attr('node',
                 shape='plaintext',
                 fontname='Arial',
                 fontsize='10')

        # Edge settings - shorter and cleaner
        dot.attr('edge',
                 fontname='Arial',
                 fontsize='8',        # Smaller font for edge labels
                 color='#666666',
                 len='1.0')           # Preferred edge length (shorter)

        # Add tables as HTML-like labels
        for type_id, table in self.tables.items():
            label = self._create_table_label(table)
            dot.node(type_id, label=label)

        # Add relationships
        for rel in self.relationships:
            from_id = rel['from_table']
            to_id = rel['to_table']

            # Style based on relationship type
            if rel['type'] == 'ref':
                # One to many
                dot.edge(from_id, to_id,
                        label=rel['field'],
                        arrowhead='crow',
                        arrowtail='none',
                        dir='both',
                        color='#2196F3')
            else:
                # Many to many
                dot.edge(from_id, to_id,
                        label=rel['field'],
                        arrowhead='crow',
                        arrowtail='crow',
                        dir='both',
                        color='#FF9800')

        # Render to string
        return dot.pipe(format=output_format).decode('utf-8')

    def _create_table_label(self, table: Dict) -> str:
        """Create HTML-like label for a table node"""
        name = table['name']
        fields = table['fields']
        type_id = None

        # Find the type_id for this table (to resolve reverse refs)
        for tid, tbl in self.tables.items():
            if tbl['name'] == name:
                type_id = tid
                break

        # Build HTML table with 5 columns: REV-Info | Field | Type | ID | REF-Info
        html = '''<
<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0" CELLPADDING="4">
    <TR>
        <TD COLSPAN="5" BGCOLOR="#1976D2">
            <FONT COLOR="white"><B>{}</B></FONT>
        </TD>
    </TR>
'''.format(self._escape_html(name))

        # Add fields (limit to 15 for readability)
        field_count = 0
        for field in fields:
            if field_count >= 15:
                remaining = len(fields) - 15
                html += f'''    <TR>
        <TD COLSPAN="5" ALIGN="CENTER" BGCOLOR="#F5F5F5">
            <I>... {remaining} more fields ...</I>
        </TD>
    </TR>
'''
                break

            field_name = self._escape_html(field['caption'])
            field_type = self._get_field_type_display(field['type'])

            # Determine if it's a key
            is_pk = (field['id'] == 'id')
            is_ref = (field['type'] == 'ref')
            is_rev = (field['type'] == 'rev')

            # Color coding - different colors for REF and REV
            if is_pk:
                bgcolor = '#FFF9C4'  # Yellow for Primary Key
            elif is_ref:
                bgcolor = '#FFF3E0'  # Light orange/yellow for REF
            elif is_rev:
                bgcolor = '#C8E6C9'  # Light green for REV (reverse reference)
            else:
                bgcolor = 'white'

            icon = '🔑 ' if is_pk else '🔗 ' if is_ref else '↩️ ' if is_rev else ''
            required = ' *' if field['required'] else ''

            # Column 1 (left): REV source info - only for REV fields
            rev_source_info = ''
            if is_rev:
                # Find which table/field points to this table (the source of the reverse ref)
                for rel in self.relationships:
                    if rel['to_table'] == type_id and rel['type'] == 'ref':
                        source_table_name = self.tables[rel['from_table']]['name']
                        source_field = rel['field']
                        # Show: SourceTable.source_field (the REF field that points here)
                        rev_source_info = f'{self._escape_html(source_table_name)}.{self._escape_html(source_field)}'
                        break

            # Column 5 (right): REF/REV target info
            ref_target_info = ''
            if is_ref:
                # Show where this REF points to
                if field.get('dbId') or field.get('dbName'):
                    # External database reference
                    db_name = field.get('dbName', f"DB-{field.get('dbId', 'Unknown')}")
                    target_info = field.get('refTypeName', 'Table')
                    ref_target_info = f'→ {self._escape_html(db_name)}→{self._escape_html(target_info)}'
                else:
                    # Internal reference
                    for rel in self.relationships:
                        if rel['from_table'] == type_id and rel['field'] == field['caption'] and rel['type'] == 'ref':
                            target_table_name = self.tables[rel['to_table']]['name']
                            ref_target_info = f'→ {self._escape_html(target_table_name)}.id'
                            break

            # Build cells with appropriate colors
            # Left cell (REV source): Always light orange/yellow when filled
            if rev_source_info:
                left_cell = f'<TD ALIGN="RIGHT" BGCOLOR="#FFF3E0"><FONT POINT-SIZE="8">{rev_source_info}</FONT></TD>'
            else:
                left_cell = '<TD></TD>'

            # Right cell (REF target): Always light green when filled
            if ref_target_info:
                right_cell = f'<TD ALIGN="LEFT" BGCOLOR="#C8E6C9"><FONT POINT-SIZE="8">{ref_target_info}</FONT></TD>'
            else:
                right_cell = '<TD></TD>'

            html += f'''    <TR>
        {left_cell}
        <TD ALIGN="LEFT" BGCOLOR="{bgcolor}">{icon}{field_name}{required}</TD>
        <TD ALIGN="LEFT">{field_type}</TD>
        <TD ALIGN="LEFT">{field['id']}</TD>
        {right_cell}
    </TR>
'''
            field_count += 1

        html += '</TABLE>>'
        return html

    def _escape_html(self, text: str) -> str:
        """Escape HTML special characters"""
        if text is None:
            return ''
        return (str(text).replace('&', '&amp;')
                    .replace('<', '&lt;')
                    .replace('>', '&gt;')
                    .replace('"', '&quot;'))


def generate_svg_erd(json_structure: Dict[str, Any]) -> str:
    """Generate SVG ERD for a Ninox database

    Args:
        json_structure: Ninox database structure JSON

    Returns:
        SVG content as string
    """
    generator = SvgErdGenerator(json_structure)
    return generator.generate_erd_svg(output_format='svg')


# Test function
if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        with open(sys.argv[1], 'r', encoding='utf-8') as f:
            structure = json.load(f)

        svg_content = generate_svg_erd(structure)

        # Save to file
        output_file = sys.argv[1].replace('.json', '-erd.svg')
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(svg_content)

        print(f"✓ ERD generated: {output_file}")
        print(f"  Size: {len(svg_content)} bytes")
