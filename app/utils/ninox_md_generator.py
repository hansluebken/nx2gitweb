"""
Ninox Markdown Documentation Generator

Converts complete-backup.json to a comprehensive Markdown documentation file.
"""

import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


def clean_code(code: str) -> str:
    """
    Formatiert Ninox-Code aus JSON-String in lesbaren Block.
    Ninox escaped Zeilenumbrüche, Tabs und Quotes.
    """
    if not code:
        return ""
    code = code.replace('\\r\\n', '\n').replace('\\n', '\n').replace('\\t', '\t').replace('\\"', '"')
    return code.strip()


def find_recursive(data: Dict, key: str) -> Any:
    """Findet einen Key in tiefer Verschachtelung."""
    if not isinstance(data, dict):
        return None
    if key in data:
        return data[key]
    for k, v in data.items():
        if isinstance(v, dict):
            res = find_recursive(v, key)
            if res is not None:
                return res
    return None


def get_db_context(data: Dict[str, Any]) -> Dict[str, Any]:
    """Sammelt Infos über DB-Name und externe DBs."""
    info = {"name": "Unbenannt", "ext_dbs": {}}
    
    # Name finden
    if '_metadata' in data:
        info["name"] = data['_metadata'].get('database_name', 'Unbenannt')
    else:
        s = find_recursive(data, 'settings')
        if s:
            info["name"] = s.get('name', 'Unbenannt')

    # Externe DBs (knownDatabases)
    schema_data = data.get("schema", {})
    settings = schema_data.get("settings", {})
    known_dbs = settings.get('knownDatabases', [])
    
    if not known_dbs:
        # Try in schema.schema
        schema_info = schema_data.get("schema", {})
        known_dbs = schema_info.get('knownDatabases', [])
    
    for db in known_dbs:
        if 'dbId' in db:
            info["ext_dbs"][db['dbId']] = db.get('name', 'Unbekannte DB')
    
    return info


def generate_markdown_from_backup(backup_data: Dict[str, Any], database_name: str = "Database") -> str:
    """
    Generate comprehensive Markdown documentation from a Ninox complete-backup.json.
    
    Args:
        backup_data: The complete backup dictionary containing schema, views, reports
        database_name: Name of the database for the title
        
    Returns:
        Markdown formatted string
    """
    lines = []
    
    # Get database context (name, external DBs)
    db_context = get_db_context(backup_data)
    
    # Header
    lines.append(f"# 📚 Dokumentation: {database_name}")
    lines.append("")
    lines.append(f"> Generiert am: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")
    lines.append("> Diese Datei enthält die vollständige Struktur und **alle Skripte** der Datenbank.")
    lines.append("")
    
    # Extract components
    schema_data = backup_data.get("schema", {})
    views_data = backup_data.get("views", [])
    reports_data = backup_data.get("reports", [])
    metadata = backup_data.get("_metadata", {})
    
    # Database Settings
    settings = schema_data.get("settings", {})
    if settings:
        lines.append("## Datenbank-Einstellungen")
        lines.append("")
        lines.append(f"- **Name:** {settings.get('name', 'N/A')}")
        if settings.get('icon'):
            lines.append(f"- **Icon:** {settings.get('icon')}")
        if settings.get('color'):
            lines.append(f"- **Farbe:** {settings.get('color')}")
        lines.append("")
    
    # External databases info
    if db_context["ext_dbs"]:
        lines.append("### Externe Datenbanken")
        lines.append("")
        for db_id, db_name in db_context["ext_dbs"].items():
            lines.append(f"- `{db_id}`: {db_name}")
        lines.append("")
    
    # Schema overview
    schema_info = schema_data.get("schema", {})
    types = schema_info.get("types", {})
    
    # Build table map (ID -> caption)
    table_map = {tid: tdata.get("caption", tid) for tid, tdata in types.items()}
    
    # Table of Contents
    lines.append("## Inhaltsverzeichnis")
    lines.append("")
    if schema_info.get("globalCode"):
        lines.append("- [Globale Funktionen](#1-globale-funktionen)")
    lines.append(f"- [Tabellen & Logik ({len(types)})](#2-tabellen--logik)")
    if views_data:
        lines.append(f"- [Views ({len(views_data)})](#3-views)")
    if reports_data:
        lines.append(f"- [Reports ({len(reports_data)})](#4-reports)")
    lines.append("")
    
    # 1. Global Code Section (first, like in original)
    global_code = schema_info.get("globalCode", "")
    if global_code and global_code.strip():
        lines.append("---")
        lines.append("")
        lines.append("## 1. Globale Funktionen")
        lines.append("")
        lines.append("```javascript")
        lines.append(clean_code(global_code))
        lines.append("```")
        lines.append("")
    
    # After Open Code
    after_open = schema_info.get("afterOpen", "")
    if after_open and after_open.strip():
        lines.append("### After Open")
        lines.append("")
        lines.append("```javascript")
        lines.append(clean_code(after_open))
        lines.append("```")
        lines.append("")
    
    # 2. Tables Section
    lines.append("---")
    lines.append("")
    lines.append("## 2. Tabellen & Logik")
    lines.append("")
    
    # Sort tables by caption
    sorted_types = sorted(
        types.items(),
        key=lambda x: x[1].get("caption", x[0]).lower()
    )
    
    for type_id, type_data in sorted_types:
        table_md = _generate_table_section(type_id, type_data, table_map, db_context["ext_dbs"], types)
        lines.extend(table_md)
    
    # 3. Views Section
    if views_data:
        lines.append("---")
        lines.append("")
        lines.append("## 3. Views")
        lines.append("")
        
        # Group views by table
        views_by_table = _group_views_by_table(views_data, types)
        
        for table_name, table_views in sorted(views_by_table.items()):
            lines.append(f"### Views für: {table_name}")
            lines.append("")
            
            for view in table_views:
                view_md = _generate_view_section(view)
                lines.extend(view_md)
    
    # 4. Reports Section
    if reports_data:
        lines.append("---")
        lines.append("")
        lines.append("## 4. Reports")
        lines.append("")
        
        for report in reports_data:
            report_md = _generate_report_section(report)
            lines.extend(report_md)
    
    return "\n".join(lines)


def _generate_table_section(type_id: str, type_data: Dict[str, Any], 
                            table_map: Dict[str, str], ext_db_map: Dict[str, str],
                            all_types: Dict[str, Any] = None) -> List[str]:
    """Generate Markdown section for a single table."""
    lines = []
    
    caption = type_data.get("caption", type_id)
    icon = type_data.get("icon", "")
    hidden = type_data.get("hidden", False)
    
    # Table header
    lines.append("---")
    lines.append(f"### 📂 Tabelle: {caption} (ID: `{type_id}`)")
    if icon:
        lines.append(f"*Icon: {icon}*")
    if hidden:
        lines.append("*[versteckt]*")
    lines.append("")
    
    # Table-level Triggers
    triggers = _extract_table_triggers(type_data)
    if triggers:
        lines.append("#### ⚡ Tabellen-Trigger")
        lines.append("")
        for trigger_name, trigger_code in triggers:
            lines.append(f"**{trigger_name}:**")
            lines.append("")
            lines.append("```javascript")
            lines.append(clean_code(trigger_code))
            lines.append("```")
            lines.append("")
    
    # Fields
    fields = type_data.get("fields", {})
    if not fields:
        lines.append("*Keine Felder.*")
        lines.append("")
        return lines
    
    # Sort fields by order
    sorted_fields = sorted(
        fields.items(),
        key=lambda x: x[1].get("order", 999)
    )
    
    # Field Structure Table
    lines.append("#### 📋 Feld-Struktur")
    lines.append("")
    lines.append("| Feldname | ID | Typ | Referenz / Info |")
    lines.append("| :--- | :--- | :--- | :--- |")
    
    scripts_to_print = []  # Collect fields with code
    
    for field_id, field_data in sorted_fields:
        field_caption = field_data.get("caption", field_id)
        field_type = field_data.get("base", "unknown")
        
        # Get reference/extra info
        extra = _get_relation_info(field_data, table_map, ext_db_map, all_types)
        
        # Choice options
        if "values" in field_data and field_data["values"]:
            opts = []
            for k, v in field_data["values"].items():
                opt_caption = v.get("caption", k) if isinstance(v, dict) else v
                opts.append(f"{k}:{opt_caption}")
            if opts:
                extra = f"Wahl: {', '.join(opts[:5])}"
                if len(opts) > 5:
                    extra += f" (+{len(opts)-5} mehr)"
        
        lines.append(f"| **{field_caption}** | `{field_id}` | {field_type} | {extra} |")
        
        # Collect code for this field
        field_code_blocks = _extract_field_code_blocks(field_data, field_caption, field_id)
        if field_code_blocks:
            scripts_to_print.append((field_caption, field_id, field_code_blocks))
    
    lines.append("")
    
    # Code Section for this table
    if scripts_to_print:
        lines.append("#### 📜 Skripte & Formeln")
        lines.append("")
        for field_name, field_id, blocks in scripts_to_print:
            lines.append(f"**Feld: '{field_name}' (ID: `{field_id}`)**")
            lines.append("")
            for label, code in blocks:
                lines.append(f"_{label}:_")
                lines.append("")
                lines.append("```javascript")
                lines.append(clean_code(code))
                lines.append("```")
                lines.append("")
    
    lines.append("")
    return lines


def _get_relation_info(field_data: Dict[str, Any], table_map: Dict[str, str], 
                       ext_db_map: Dict[str, str], all_types: Dict[str, Any] = None) -> str:
    """Erstellt lesbaren String für Verknüpfungen mit Feld-zu-Feld Referenz."""
    base = field_data.get("base", "")
    
    if base not in ["ref", "rev"]:
        return ""
    
    # Target table
    target_table_id = field_data.get("refTypeId") or field_data.get("refType", "")
    target_table_name = table_map.get(target_table_id, target_table_id)
    
    # Get the referenced field in the target table
    ref_field_id = field_data.get("refFieldId", "")
    ref_field_name = ""
    
    if ref_field_id and all_types and target_table_id in all_types:
        target_fields = all_types[target_table_id].get("fields", {})
        if ref_field_id in target_fields:
            ref_field_name = target_fields[ref_field_id].get("caption", ref_field_id)
    
    # Build the reference string
    if ref_field_name:
        target_str = f"`{target_table_name}.{ref_field_name}`"
    else:
        target_str = f"`{target_table_name}`"
    
    # Check if external
    ext_id = field_data.get("dbId", "")
    if ext_id:
        db_name = ext_db_map.get(ext_id, ext_id)
        return f"🔗 **EXTERN** zu {target_str} in DB `{db_name}`"
    
    rel_type = "Verknüpfung" if base == "ref" else "Rückverknüpfung"
    comp = " (Komposition)" if field_data.get("cascade") else ""
    
    return f"🔗 {rel_type} zu {target_str}{comp}"


def _extract_table_triggers(type_data: Dict[str, Any]) -> List[Tuple[str, str]]:
    """Extract all triggers from a table definition."""
    triggers = []
    
    trigger_fields = [
        ("afterCreate", "On Create"),
        ("beforeCreate", "Before Create"),
        ("afterUpdate", "On Update"),
        ("beforeUpdate", "Before Update"),
        ("afterDelete", "On Delete"),
        ("beforeDelete", "Before Delete"),
        ("print", "Print"),
    ]
    
    for field_name, display_name in trigger_fields:
        code = type_data.get(field_name, "")
        if code and code.strip():
            triggers.append((display_name, code))
    
    return triggers


def _extract_field_code_blocks(field_data: Dict[str, Any], caption: str, 
                                field_id: str) -> List[Tuple[str, str]]:
    """Extract all code blocks from a field."""
    code_blocks = []
    base = field_data.get("base", "")
    
    # Formula/Script (fn field - used for formulas and button scripts)
    fn = field_data.get("fn", "")
    if fn and fn.strip():
        label = "Skript" if base == "button" else "Formel"
        code_blocks.append((label, fn))
    
    # Also check "formula" key (alternative location)
    formula = field_data.get("formula", "")
    if formula and formula.strip() and formula != fn:
        code_blocks.append(("Formel", formula))
    
    # afterUpdate trigger on field
    after_update = field_data.get("afterUpdate", "")
    if after_update and after_update.strip():
        code_blocks.append(("Trigger (afterUpdate)", after_update))
    
    # onChange (alternative name)
    on_change = field_data.get("onChange", "")
    if on_change and on_change.strip() and on_change != after_update:
        code_blocks.append(("Trigger (onChange)", on_change))
    
    # Visibility formula
    visibility = field_data.get("visibility", "")
    if visibility and visibility.strip() and visibility not in ["true", "false", None, "True", "False"]:
        code_blocks.append(("Sichtbarkeit", visibility))
    
    # Dynamic choice values
    dchoice = field_data.get("dchoiceValues", "")
    if dchoice and dchoice.strip():
        code_blocks.append(("Dyn. Auswahlwerte", dchoice))
    
    # displayFormula
    display_formula = field_data.get("displayFormula", "")
    if display_formula and display_formula.strip():
        code_blocks.append(("Display-Formel", display_formula))
    
    # defaultValue (if it's a formula)
    default = field_data.get("defaultValue", "")
    if default and default.strip() and not default.replace('.', '').replace('-', '').isdigit():
        # Only include if it looks like code (not just a number)
        if any(c in default for c in ['(', ')', 'let', 'if', 'for', '+']):
            code_blocks.append(("Standardwert", default))
    
    return code_blocks


def _get_field_type_display(field_data: Dict[str, Any]) -> str:
    """Get a human-readable field type."""
    base = field_data.get("base", "unknown")
    
    type_map = {
        "string": "Text",
        "number": "Zahl",
        "boolean": "Ja/Nein",
        "date": "Datum",
        "datetime": "Datum/Zeit",
        "time": "Zeit",
        "timeinterval": "Zeitspanne",
        "choice": "Auswahl",
        "multiplechoice": "Mehrfachauswahl",
        "link": "Link",
        "ref": "Verweis",
        "rev": "Rückverweis",
        "image": "Bild",
        "file": "Datei",
        "user": "Benutzer",
        "color": "Farbe",
        "phone": "Telefon",
        "email": "E-Mail",
        "url": "URL",
        "location": "Standort",
        "html": "HTML",
        "appointment": "Termin",
        "formula": "Formel",
        "button": "Button",
        "fn": "Formel",
    }
    
    return type_map.get(base, base)


def _group_views_by_table(views: List[Dict], types: Dict) -> Dict[str, List]:
    """Group views by their associated table."""
    grouped = {}
    
    # Create type_id to caption mapping
    type_captions = {tid: tdata.get("caption", tid) for tid, tdata in types.items()}
    
    for view in views:
        type_id = view.get("typeId", "")
        table_name = type_captions.get(type_id, f"Tabelle {type_id}" if type_id else "Unbekannt")
        
        if table_name not in grouped:
            grouped[table_name] = []
        grouped[table_name].append(view)
    
    return grouped


def _generate_view_section(view: Dict[str, Any]) -> List[str]:
    """Generate Markdown section for a single view."""
    lines = []
    
    name = view.get("name", "Unbenannte View")
    view_type = view.get("type", "")
    
    lines.append(f"#### {name}")
    if view_type:
        lines.append(f"*Typ: {view_type}*")
    lines.append("")
    
    # Filter
    filter_code = view.get("filter", "")
    if filter_code and filter_code.strip():
        lines.append("**Filter:**")
        lines.append("")
        lines.append("```javascript")
        lines.append(clean_code(filter_code))
        lines.append("```")
        lines.append("")
    
    # Sort
    sort_code = view.get("sort", "")
    if sort_code and sort_code.strip():
        lines.append("**Sortierung:**")
        lines.append("")
        lines.append("```javascript")
        lines.append(clean_code(sort_code))
        lines.append("```")
        lines.append("")
    
    # Aggregate
    aggregate = view.get("aggregate", "")
    if aggregate and aggregate.strip():
        lines.append("**Aggregation:**")
        lines.append("")
        lines.append("```javascript")
        lines.append(clean_code(aggregate))
        lines.append("```")
        lines.append("")
    
    return lines


def _generate_report_section(report: Dict[str, Any]) -> List[str]:
    """Generate Markdown section for a single report."""
    lines = []
    
    name = report.get("name", "Unbenannter Report")
    
    lines.append(f"### {name}")
    lines.append("")
    
    # Report type/format
    report_format = report.get("format", "")
    if report_format:
        lines.append(f"*Format: {report_format}*")
        lines.append("")
    
    # Template code
    template = report.get("template", "")
    if template and template.strip():
        # Check if it's HTML
        if "<" in template and ">" in template:
            lines.append("**Template (HTML):**")
            lines.append("")
            lines.append("```html")
            # Truncate very long templates
            if len(template) > 2000:
                lines.append(clean_code(template[:2000]))
                lines.append("... (gekürzt)")
            else:
                lines.append(clean_code(template))
            lines.append("```")
        else:
            lines.append("**Template:**")
            lines.append("")
            lines.append("```")
            lines.append(clean_code(template))
            lines.append("```")
        lines.append("")
    
    # Code/script
    code = report.get("code", "") or report.get("script", "")
    if code and code.strip():
        lines.append("**Code:**")
        lines.append("")
        lines.append("```javascript")
        lines.append(clean_code(code))
        lines.append("```")
        lines.append("")
    
    return lines


# Convenience function for direct dict input
def generate_markdown(data: Dict[str, Any], name: str = "Database") -> str:
    """
    Convenience wrapper for generate_markdown_from_backup.
    
    Args:
        data: Complete backup dictionary
        name: Database name
        
    Returns:
        Markdown string
    """
    return generate_markdown_from_backup(data, name)
