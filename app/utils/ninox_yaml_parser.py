"""
Ninox YAML Parser and Code Extractor
Parses YAML files from ninox-dev-cli and extracts all code locations.

Supports all 24 code locations across:
- Database level (3): afterOpen, beforeOpen, globalCode
- Table level (4): afterCreate, afterUpdate, afterDelete, beforeDelete
- Field level (12): fn, afterUpdate, afterCreate, constraint, dchoiceValues, 
                   dchoiceCaption, dchoiceColor, dchoiceIcon, referenceFormat,
                   visibility, onClick, onDoubleClick
- UI level (5): fn, onClick, beforeShow, afterShow, afterHide
"""
import os
import re
import yaml
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Set, Iterator
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class CodeLevel(Enum):
    """Level where code is defined"""
    DATABASE = 1
    TABLE = 2
    FIELD = 3
    UI = 4
    REPORT = 5
    VIEW = 6


class CodeCategory(Enum):
    """Category of code for filtering"""
    GLOBAL = "global"           # Global database code
    TRIGGER = "trigger"         # Event triggers (afterCreate, afterUpdate, etc.)
    FORMULA = "formula"         # Formula fields (fn)
    BUTTON = "button"           # Button click handlers
    VISIBILITY = "visibility"   # Visibility conditions
    PERMISSION = "permission"   # Permission formulas
    DYNAMIC_CHOICE = "dchoice"  # Dynamic choice formulas
    VALIDATION = "validation"   # Validation/Constraint formulas
    REFERENCE = "reference"     # Reference format formulas
    VIEW = "view"               # View expressions
    REPORT = "report"           # Report expressions
    OTHER = "other"


# All code fields organized by level
DATABASE_CODE_FIELDS = {
    'afterOpen': CodeCategory.TRIGGER,
    'beforeOpen': CodeCategory.TRIGGER,
    'globalCode': CodeCategory.GLOBAL,
}

TABLE_CODE_FIELDS = {
    'afterCreate': CodeCategory.TRIGGER,
    'afterUpdate': CodeCategory.TRIGGER,
    'afterDelete': CodeCategory.TRIGGER,
    'beforeDelete': CodeCategory.TRIGGER,
    'canRead': CodeCategory.PERMISSION,
    'canWrite': CodeCategory.PERMISSION,
    'canCreate': CodeCategory.PERMISSION,
    'canDelete': CodeCategory.PERMISSION,
    'printout': CodeCategory.OTHER,
}

FIELD_CODE_FIELDS = {
    'fn': CodeCategory.FORMULA,
    'afterUpdate': CodeCategory.TRIGGER,
    'afterCreate': CodeCategory.TRIGGER,
    'constraint': CodeCategory.VALIDATION,
    'dchoiceValues': CodeCategory.DYNAMIC_CHOICE,
    'dchoiceCaption': CodeCategory.DYNAMIC_CHOICE,
    'dchoiceColor': CodeCategory.DYNAMIC_CHOICE,
    'dchoiceIcon': CodeCategory.DYNAMIC_CHOICE,
    'referenceFormat': CodeCategory.REFERENCE,
    'visibility': CodeCategory.VISIBILITY,
    'onClick': CodeCategory.BUTTON,
    'onDoubleClick': CodeCategory.BUTTON,
    'canRead': CodeCategory.PERMISSION,
    'canWrite': CodeCategory.PERMISSION,
    'validation': CodeCategory.VALIDATION,
    'color': CodeCategory.OTHER,
}

UI_CODE_FIELDS = {
    'fn': CodeCategory.BUTTON,  # Button script / View query
    'onClick': CodeCategory.BUTTON,
    'beforeShow': CodeCategory.TRIGGER,
    'afterShow': CodeCategory.TRIGGER,
    'afterHide': CodeCategory.TRIGGER,
    'expression': CodeCategory.VIEW,
    'filter': CodeCategory.VIEW,
}

REPORT_CODE_FIELDS = {
    'customDataExp': CodeCategory.REPORT,
    'filter': CodeCategory.REPORT,
    'sortExp': CodeCategory.REPORT,
    'expression': CodeCategory.REPORT,  # In columns
}

VIEW_CODE_FIELDS = {
    'filter': CodeCategory.VIEW,
    'sortExp': CodeCategory.VIEW,
    'customDataExp': CodeCategory.VIEW,
}

# Human-readable names for code types
CODE_TYPE_NAMES = {
    # Database level
    'afterOpen': 'After Open (DB)',
    'beforeOpen': 'Before Open (DB)',
    'globalCode': 'Global Code',
    
    # Table level  
    'afterCreate': 'After Create',
    'afterUpdate': 'After Update',
    'afterDelete': 'After Delete',
    'beforeDelete': 'Before Delete',
    
    # Field level
    'fn': 'Formula',
    'constraint': 'Constraint',
    'dchoiceValues': 'Dynamic Choice Values',
    'dchoiceCaption': 'Dynamic Choice Caption',
    'dchoiceColor': 'Dynamic Choice Color',
    'dchoiceIcon': 'Dynamic Choice Icon',
    'referenceFormat': 'Reference Format',
    'visibility': 'Visibility',
    'onClick': 'On Click',
    'onDoubleClick': 'On Double Click',
    
    # UI level
    'beforeShow': 'Before Show',
    'afterShow': 'After Show',
    'afterHide': 'After Hide',
    'expression': 'Expression',
    'filter': 'Filter',
    
    # Permissions
    'canRead': 'Can Read',
    'canWrite': 'Can Write',
    'canCreate': 'Can Create',
    'canDelete': 'Can Delete',
    
    # Other
    'validation': 'Validation',
    'printout': 'Print Layout',
    'color': 'Color Formula',
    'customDataExp': 'Custom Data Expression',
    'sortExp': 'Sort Expression',
}

# Category display names
CATEGORY_NAMES = {
    CodeCategory.GLOBAL: 'Global Code',
    CodeCategory.TRIGGER: 'Triggers',
    CodeCategory.FORMULA: 'Formulas',
    CodeCategory.BUTTON: 'Buttons',
    CodeCategory.VISIBILITY: 'Visibility',
    CodeCategory.PERMISSION: 'Permissions',
    CodeCategory.DYNAMIC_CHOICE: 'Dynamic Choices',
    CodeCategory.VALIDATION: 'Validation',
    CodeCategory.REFERENCE: 'References',
    CodeCategory.VIEW: 'Views',
    CodeCategory.REPORT: 'Reports',
    CodeCategory.OTHER: 'Other',
}


@dataclass
class CodeLocation:
    """Represents a single code location in a Ninox database"""
    # Hierarchy
    database_name: str
    database_id: str
    table_name: Optional[str] = None
    table_id: Optional[str] = None
    element_name: Optional[str] = None  # Field or UI element name
    element_id: Optional[str] = None
    
    # Code info
    code_type: str = ""
    code: str = ""
    level: CodeLevel = CodeLevel.DATABASE
    category: CodeCategory = CodeCategory.OTHER
    
    # Metadata
    element_base_type: Optional[str] = None  # e.g., 'button', 'formula', 'ref'
    yaml_path: str = ""  # Path in YAML file
    file_path: Optional[str] = None  # Source YAML file
    line_count: int = 0
    
    def __post_init__(self):
        """Calculate derived fields"""
        if self.code:
            self.line_count = len(self.code.split('\n'))
    
    @property
    def path(self) -> str:
        """Full hierarchical path like DB.Table.Field.codeType"""
        parts = [self.database_name]
        if self.table_name:
            parts.append(self.table_name)
        if self.element_name:
            parts.append(self.element_name)
        parts.append(self.code_type)
        return '.'.join(parts)
    
    @property
    def short_path(self) -> str:
        """Shorter path without database name"""
        parts = []
        if self.table_name:
            parts.append(self.table_name)
        if self.element_name:
            parts.append(self.element_name)
        parts.append(self.code_type)
        return '.'.join(parts)
    
    @property
    def type_display_name(self) -> str:
        """Human-readable name for the code type"""
        return CODE_TYPE_NAMES.get(self.code_type, self.code_type)
    
    @property
    def category_name(self) -> str:
        """Human-readable category name"""
        return CATEGORY_NAMES.get(self.category, 'Other')
    
    @property
    def icon(self) -> str:
        """Material icon name for this code type"""
        icon_map = {
            'globalCode': 'public',
            'afterOpen': 'play_arrow',
            'beforeOpen': 'schedule',
            'afterCreate': 'add_circle',
            'afterUpdate': 'edit',
            'afterDelete': 'delete',
            'beforeDelete': 'delete_outline',
            'fn': 'functions',
            'visibility': 'visibility',
            'onClick': 'touch_app',
            'onDoubleClick': 'ads_click',
            'beforeShow': 'visibility',
            'afterShow': 'visibility',
            'afterHide': 'visibility_off',
            'canWrite': 'edit_off',
            'canRead': 'visibility_off',
            'canCreate': 'add_circle_outline',
            'canDelete': 'delete_outline',
            'dchoiceValues': 'list',
            'dchoiceCaption': 'label',
            'dchoiceColor': 'palette',
            'dchoiceIcon': 'emoji_symbols',
            'constraint': 'rule',
            'validation': 'check_circle',
            'referenceFormat': 'link',
            'expression': 'calculate',
            'filter': 'filter_list',
            'customDataExp': 'data_object',
            'sortExp': 'sort',
            'printout': 'print',
            'color': 'palette',
        }
        return icon_map.get(self.code_type, 'code')
    
    def matches_filter(
        self,
        text_query: Optional[str] = None,
        categories: Optional[Set[CodeCategory]] = None,
        code_types: Optional[Set[str]] = None,
        levels: Optional[Set[CodeLevel]] = None,
        tables: Optional[Set[str]] = None
    ) -> bool:
        """
        Check if this code location matches the given filters.
        
        Args:
            text_query: Text to search in path and code
            categories: Set of categories to include
            code_types: Set of code types to include
            levels: Set of levels to include
            tables: Set of table names to include
            
        Returns:
            True if matches all provided filters
        """
        # Text search
        if text_query:
            query_lower = text_query.lower()
            if query_lower not in self.path.lower() and query_lower not in self.code.lower():
                return False
        
        # Category filter
        if categories and self.category not in categories:
            return False
        
        # Code type filter
        if code_types and self.code_type not in code_types:
            return False
        
        # Level filter
        if levels and self.level not in levels:
            return False
        
        # Table filter
        if tables and self.table_name not in tables:
            return False
        
        return True


@dataclass
class NinoxDatabase:
    """Represents a complete Ninox database structure from YAML"""
    database_id: str
    name: str
    path: Path
    version: Optional[int] = None
    
    # Structure
    tables: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    views: List[Dict[str, Any]] = field(default_factory=list)
    reports: List[Dict[str, Any]] = field(default_factory=list)
    
    # Raw data
    database_yaml: Dict[str, Any] = field(default_factory=dict)
    
    # Statistics
    code_locations: List[CodeLocation] = field(default_factory=list)
    
    @property
    def table_count(self) -> int:
        return len(self.tables)
    
    @property
    def code_count(self) -> int:
        return len(self.code_locations)
    
    @property
    def has_global_code(self) -> bool:
        return any(c.code_type == 'globalCode' for c in self.code_locations)

    def to_dict_for_docs(self) -> Dict[str, Any]:
        """
        Convert NinoxDatabase to dict format expected by doc_generator.

        Returns:
            Dict with structure suitable for AI documentation generation
        """
        # Convert tables to list format with statistics
        tables_list = []
        for table_name, table_data in self.tables.items():
            fields = table_data.get('fields', {})

            # Extract table-level code
            table_code = {}
            for code_key in ['afterCreate', 'afterUpdate', 'afterDelete', 'beforeDelete']:
                if code_key in table_data:
                    table_code[code_key] = table_data[code_key]

            tables_list.append({
                'name': table_data.get('caption', table_name),
                'id': table_name,
                'field_count': len(fields),
                'code': table_code,
                'fields': [
                    {
                        'name': field_data.get('caption', field_id),
                        'id': field_id,
                        'type': field_data.get('base', 'string'),
                        'required': field_data.get('required', False),
                        'refTypeId': field_data.get('refTypeId'),
                        'refTypeUUID': field_data.get('refTypeUUID'),
                        'dbId': field_data.get('dbId'),
                        'dbName': field_data.get('dbName'),
                        # Include code locations
                        'fn': field_data.get('fn'),  # Formula
                        'onClick': field_data.get('onClick'),  # Button click
                        'constraint': field_data.get('constraint'),  # Validation
                        'visibility': field_data.get('visibility'),  # Visibility formula
                        'canRead': field_data.get('canRead'),  # Read permission
                        'canWrite': field_data.get('canWrite'),  # Write permission
                    }
                    for field_id, field_data in fields.items()
                ]
            })

        # Extract global database code
        global_code = {}
        for code_key in ['globalCode', 'afterOpen', 'beforeOpen']:
            if hasattr(self, code_key):
                code_value = getattr(self, code_key, None)
                if code_value:
                    global_code[code_key] = code_value

        return {
            'name': self.name,
            'database_id': self.database_id,
            'table_count': self.table_count,
            'code_count': self.code_count,
            'global_code': global_code,
            'tables': tables_list
        }


def unescape_yaml_string(value: str) -> str:
    """
    Unescape YAML string values to make code readable.
    """
    if not value or not isinstance(value, str):
        return value or ""
    
    # Remove surrounding quotes if present
    if len(value) >= 2:
        if (value.startswith('"') and value.endswith('"')) or \
           (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
    
    # Unescape common sequences
    value = value.replace('\\n', '\n')
    value = value.replace('\\t', '\t')
    value = value.replace('\\"', '"')
    value = value.replace("\\'", "'")
    value = value.replace('\\\\', '\\')
    
    return value


def load_yaml_file(file_path: Path) -> Optional[Dict[str, Any]]:
    """Safely load a YAML file"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logger.error(f"Error loading YAML file {file_path}: {e}")
        return None


class NinoxYAMLParser:
    """
    Parser for ninox-dev-cli YAML structure.
    
    Expected directory structure:
    database_<id>/
    ├── database.yaml       # Database metadata and schema settings
    ├── tables/
    │   └── <table_name>/
    │       ├── table.yaml  # Table definition
    │       ├── fields/
    │       │   └── <field_name>.yaml
    │       └── uis/
    │           └── <ui_name>.yaml
    ├── views.yaml          # Optional
    └── reports.yaml        # Optional
    """
    
    def __init__(self, base_path: str):
        """
        Initialize parser.
        
        Args:
            base_path: Path to the ninox-cli project root (contains src/Objects/)
        """
        self.base_path = Path(base_path)
        self.objects_path = self.base_path / 'src' / 'Objects'
    
    def get_all_databases(self) -> List[NinoxDatabase]:
        """
        Find and load all downloaded databases.
        
        Returns:
            List of NinoxDatabase objects
        """
        databases = []
        
        if not self.objects_path.exists():
            logger.warning(f"Objects path does not exist: {self.objects_path}")
            return databases
        
        for db_dir in self.objects_path.iterdir():
            if not db_dir.is_dir():
                continue
            
            db = self.load_database(db_dir)
            if db:
                databases.append(db)
        
        return sorted(databases, key=lambda d: d.name.lower())
    
    def load_database(self, db_path: Path) -> Optional[NinoxDatabase]:
        """
        Load a complete database from its directory.
        
        Args:
            db_path: Path to database directory
            
        Returns:
            NinoxDatabase object or None if invalid
        """
        # Extract database ID from directory name
        dir_name = db_path.name
        if dir_name.startswith('database_'):
            db_id = dir_name.replace('database_', '')
        else:
            db_id = dir_name
        
        # Load database.yaml - try different naming patterns
        db_yaml_path = db_path / 'database.yaml'
        if not db_yaml_path.exists():
            # ninox-dev-cli uses database_<name>.yaml pattern
            yaml_files = list(db_path.glob('database_*.yaml'))
            if yaml_files:
                db_yaml_path = yaml_files[0]  # Use first match
            else:
                logger.warning(f"No database YAML found in {db_path}")
                return None
        
        yaml_data = load_yaml_file(db_yaml_path)
        if not yaml_data:
            return None
        
        # ninox-dev-cli wraps data in 'database' key
        db_yaml = yaml_data.get('database', yaml_data)
        
        # Extract database info - can be in 'settings' or directly
        db_settings = db_yaml.get('settings', {})
        db_name = db_settings.get('name') or db_yaml.get('name') or db_yaml.get('caption') or db_id
        version = db_yaml.get('version')
        
        db = NinoxDatabase(
            database_id=db_id,
            name=db_name,
            path=db_path,
            version=version,
            database_yaml=db_yaml
        )
        
        # Load tables - ninox-dev-cli uses table_* directories in root
        for item in db_path.iterdir():
            if item.is_dir() and item.name.startswith('table_'):
                table_data = self._load_table(item)
                if table_data:
                    table_name = table_data.get('caption') or table_data.get('name') or item.name
                    db.tables[table_name] = table_data
                    db.tables[table_name]['_dir_name'] = item.name
        
        # Load views
        views_path = db_path / 'views.yaml'
        if views_path.exists():
            views_data = load_yaml_file(views_path)
            if views_data:
                db.views = views_data if isinstance(views_data, list) else [views_data]
        
        # Load reports
        reports_path = db_path / 'reports.yaml'
        if reports_path.exists():
            reports_data = load_yaml_file(reports_path)
            if reports_data:
                db.reports = reports_data if isinstance(reports_data, list) else [reports_data]
        
        # Extract all code locations
        db.code_locations = self.extract_code_locations(db)
        
        return db
    
    def _load_table(self, table_dir: Path) -> Optional[Dict[str, Any]]:
        """Load a table from ninox-dev-cli structure"""
        # ninox-dev-cli puts table_*.yaml in the directory
        table_yaml_files = list(table_dir.glob('table_*.yaml'))
        if not table_yaml_files:
            return None
        
        table_yaml = table_yaml_files[0]
        yaml_data = load_yaml_file(table_yaml)
        if not yaml_data:
            return None
        
        # ninox-dev-cli wraps data in 'table' key
        table_data = yaml_data.get('table', yaml_data)
        
        # In ninox-dev-cli, fields and UIs are embedded in the table YAML
        # No separate field/ui subdirectories
        
        return table_data
    
    def extract_code_locations(self, db: NinoxDatabase) -> List[CodeLocation]:
        """
        Extract all code locations from a database.
        
        Args:
            db: NinoxDatabase to extract from
            
        Returns:
            List of CodeLocation objects
        """
        locations = []
        
        # 1. Database-level code
        locations.extend(self._extract_database_code(db))
        
        # 2. Table-level code
        for table_name, table_data in db.tables.items():
            locations.extend(self._extract_table_code(db, table_name, table_data))
            
            # 3. Field-level code
            fields = table_data.get('fields', {})
            for field_name, field_data in fields.items():
                locations.extend(self._extract_field_code(
                    db, table_name, table_data, field_name, field_data
                ))
            
            # 4. UI-level code
            uis = table_data.get('uis', {})
            for ui_name, ui_data in uis.items():
                locations.extend(self._extract_ui_code(
                    db, table_name, table_data, ui_name, ui_data
                ))
        
        # 5. View-level code
        for view in db.views:
            locations.extend(self._extract_view_code(db, view))
        
        # 6. Report-level code
        for report in db.reports:
            locations.extend(self._extract_report_code(db, report))
        
        return locations
    
    def _extract_database_code(self, db: NinoxDatabase) -> List[CodeLocation]:
        """Extract database-level code"""
        locations = []
        
        # Check in database.yaml schema section
        schema = db.database_yaml.get('database', {}).get('schema', {})
        if not schema:
            schema = db.database_yaml.get('schema', {})
        
        for code_type, category in DATABASE_CODE_FIELDS.items():
            code = schema.get(code_type, '')
            if code and isinstance(code, str) and code.strip():
                locations.append(CodeLocation(
                    database_name=db.name,
                    database_id=db.database_id,
                    code_type=code_type,
                    code=unescape_yaml_string(code),
                    level=CodeLevel.DATABASE,
                    category=category,
                    yaml_path=f"database.schema.{code_type}",
                    file_path=str(db.path / 'database.yaml')
                ))
        
        return locations
    
    def _extract_table_code(
        self, 
        db: NinoxDatabase, 
        table_name: str, 
        table_data: Dict[str, Any]
    ) -> List[CodeLocation]:
        """Extract table-level code"""
        locations = []
        table_id = table_data.get('_dir_name', table_name)
        
        for code_type, category in TABLE_CODE_FIELDS.items():
            code = table_data.get(code_type, '')
            if code and isinstance(code, str) and code.strip():
                locations.append(CodeLocation(
                    database_name=db.name,
                    database_id=db.database_id,
                    table_name=table_name,
                    table_id=table_id,
                    code_type=code_type,
                    code=unescape_yaml_string(code),
                    level=CodeLevel.TABLE,
                    category=category,
                    yaml_path=f"tables.{table_name}.{code_type}",
                    file_path=str(db.path / 'tables' / table_id / 'table.yaml')
                ))
        
        return locations
    
    def _extract_field_code(
        self,
        db: NinoxDatabase,
        table_name: str,
        table_data: Dict[str, Any],
        field_name: str,
        field_data: Dict[str, Any]
    ) -> List[CodeLocation]:
        """Extract field-level code"""
        locations = []
        table_id = table_data.get('_dir_name', table_name)
        field_id = field_data.get('_file_name', field_name)
        
        # Get display name
        display_name = field_data.get('caption') or field_data.get('name') or field_name
        base_type = field_data.get('base')
        
        for code_type, category in FIELD_CODE_FIELDS.items():
            code = field_data.get(code_type, '')
            if code and isinstance(code, str) and code.strip():
                # Skip very short formula fields that are just references
                if code_type == 'fn' and len(code) < 3:
                    continue
                
                locations.append(CodeLocation(
                    database_name=db.name,
                    database_id=db.database_id,
                    table_name=table_name,
                    table_id=table_id,
                    element_name=display_name,
                    element_id=field_id,
                    code_type=code_type,
                    code=unescape_yaml_string(code),
                    level=CodeLevel.FIELD,
                    category=category,
                    element_base_type=base_type,
                    yaml_path=f"tables.{table_name}.fields.{field_name}.{code_type}",
                    file_path=str(db.path / 'tables' / table_id / 'fields' / f'{field_id}.yaml')
                ))
        
        return locations
    
    def _extract_ui_code(
        self,
        db: NinoxDatabase,
        table_name: str,
        table_data: Dict[str, Any],
        ui_name: str,
        ui_data: Dict[str, Any]
    ) -> List[CodeLocation]:
        """Extract UI element code"""
        locations = []
        table_id = table_data.get('_dir_name', table_name)
        ui_id = ui_data.get('_file_name', ui_name)
        
        # Get display name
        display_name = ui_data.get('caption') or ui_data.get('name') or ui_name
        base_type = ui_data.get('base')
        
        for code_type, category in UI_CODE_FIELDS.items():
            code = ui_data.get(code_type, '')
            if code and isinstance(code, str) and code.strip():
                locations.append(CodeLocation(
                    database_name=db.name,
                    database_id=db.database_id,
                    table_name=table_name,
                    table_id=table_id,
                    element_name=display_name,
                    element_id=ui_id,
                    code_type=code_type,
                    code=unescape_yaml_string(code),
                    level=CodeLevel.UI,
                    category=category,
                    element_base_type=base_type,
                    yaml_path=f"tables.{table_name}.uis.{ui_name}.{code_type}",
                    file_path=str(db.path / 'tables' / table_id / 'uis' / f'{ui_id}.yaml')
                ))
        
        return locations
    
    def _extract_view_code(
        self,
        db: NinoxDatabase,
        view: Dict[str, Any]
    ) -> List[CodeLocation]:
        """Extract view-level code"""
        locations = []
        
        view_name = view.get('name') or view.get('caption') or 'View'
        view_id = view.get('id', '')
        
        for code_type, category in VIEW_CODE_FIELDS.items():
            code = view.get(code_type, '')
            if code and isinstance(code, str) and code.strip():
                locations.append(CodeLocation(
                    database_name=db.name,
                    database_id=db.database_id,
                    table_name='[Views]',
                    element_name=view_name,
                    element_id=view_id,
                    code_type=code_type,
                    code=unescape_yaml_string(code),
                    level=CodeLevel.VIEW,
                    category=category,
                    yaml_path=f"views.{view_name}.{code_type}",
                    file_path=str(db.path / 'views.yaml')
                ))
        
        return locations
    
    def _extract_report_code(
        self,
        db: NinoxDatabase,
        report: Dict[str, Any]
    ) -> List[CodeLocation]:
        """Extract report-level code"""
        locations = []
        
        report_name = report.get('name') or report.get('caption') or 'Report'
        report_id = report.get('id', '')
        
        # Report-level code
        for code_type, category in REPORT_CODE_FIELDS.items():
            if code_type == 'expression':
                continue  # Handle in columns
            code = report.get(code_type, '')
            if code and isinstance(code, str) and code.strip():
                locations.append(CodeLocation(
                    database_name=db.name,
                    database_id=db.database_id,
                    table_name='[Reports]',
                    element_name=report_name,
                    element_id=report_id,
                    code_type=code_type,
                    code=unescape_yaml_string(code),
                    level=CodeLevel.REPORT,
                    category=category,
                    yaml_path=f"reports.{report_name}.{code_type}",
                    file_path=str(db.path / 'reports.yaml')
                ))
        
        # Report column expressions
        columns = report.get('columns', [])
        if isinstance(columns, list):
            for i, col in enumerate(columns):
                if not isinstance(col, dict):
                    continue
                col_name = col.get('caption') or col.get('name') or f'Column{i}'
                
                for code_type in ['expression', 'filter']:
                    code = col.get(code_type, '')
                    if code and isinstance(code, str) and code.strip():
                        locations.append(CodeLocation(
                            database_name=db.name,
                            database_id=db.database_id,
                            table_name='[Reports]',
                            element_name=f"{report_name}.{col_name}",
                            element_id=f"{report_id}_col{i}",
                            code_type=code_type,
                            code=unescape_yaml_string(code),
                            level=CodeLevel.REPORT,
                            category=CodeCategory.REPORT,
                            yaml_path=f"reports.{report_name}.columns.{col_name}.{code_type}",
                            file_path=str(db.path / 'reports.yaml')
                        ))
        
        return locations


def search_code_locations(
    locations: List[CodeLocation],
    query: str,
    case_sensitive: bool = False
) -> List[CodeLocation]:
    """
    Search through code locations.
    
    Args:
        locations: List of code locations to search
        query: Search query
        case_sensitive: Whether search is case sensitive
        
    Returns:
        Filtered list of matching locations
    """
    if not query:
        return locations
    
    if not case_sensitive:
        query = query.lower()
    
    results = []
    for loc in locations:
        search_text = loc.path + '\n' + loc.code
        if not case_sensitive:
            search_text = search_text.lower()
        
        if query in search_text:
            results.append(loc)
    
    return results


def filter_code_locations(
    locations: List[CodeLocation],
    categories: Optional[Set[CodeCategory]] = None,
    code_types: Optional[Set[str]] = None,
    levels: Optional[Set[CodeLevel]] = None,
    tables: Optional[Set[str]] = None,
    text_query: Optional[str] = None
) -> List[CodeLocation]:
    """
    Filter code locations by multiple criteria.
    
    Args:
        locations: List of code locations
        categories: Filter by categories
        code_types: Filter by code types
        levels: Filter by levels
        tables: Filter by table names
        text_query: Text search query
        
    Returns:
        Filtered list
    """
    return [
        loc for loc in locations
        if loc.matches_filter(
            text_query=text_query,
            categories=categories,
            code_types=code_types,
            levels=levels,
            tables=tables
        )
    ]


def group_by_table(locations: List[CodeLocation]) -> Dict[str, List[CodeLocation]]:
    """Group code locations by table name"""
    groups: Dict[str, List[CodeLocation]] = {}
    
    for loc in locations:
        table = loc.table_name or '(Database)'
        if table not in groups:
            groups[table] = []
        groups[table].append(loc)
    
    return groups


def group_by_category(locations: List[CodeLocation]) -> Dict[CodeCategory, List[CodeLocation]]:
    """Group code locations by category"""
    groups: Dict[CodeCategory, List[CodeLocation]] = {}
    
    for loc in locations:
        if loc.category not in groups:
            groups[loc.category] = []
        groups[loc.category].append(loc)
    
    return groups


def get_statistics(locations: List[CodeLocation]) -> Dict[str, Any]:
    """
    Calculate statistics for code locations.
    
    Returns dict with:
    - total_count: Total number of code locations
    - by_level: Count by level
    - by_category: Count by category
    - by_type: Count by code type
    - by_table: Count by table
    - total_lines: Total lines of code
    """
    stats = {
        'total_count': len(locations),
        'by_level': {},
        'by_category': {},
        'by_type': {},
        'by_table': {},
        'total_lines': 0
    }
    
    for loc in locations:
        # By level
        level_name = loc.level.name
        stats['by_level'][level_name] = stats['by_level'].get(level_name, 0) + 1
        
        # By category
        cat_name = loc.category_name
        stats['by_category'][cat_name] = stats['by_category'].get(cat_name, 0) + 1
        
        # By type
        type_name = loc.code_type
        stats['by_type'][type_name] = stats['by_type'].get(type_name, 0) + 1
        
        # By table
        table = loc.table_name or '(Database)'
        stats['by_table'][table] = stats['by_table'].get(table, 0) + 1
        
        # Lines
        stats['total_lines'] += loc.line_count
    
    return stats


def convert_yaml_to_json_structure(database: 'NinoxDatabase') -> Dict[str, Any]:
    """
    Convert a YAML-based NinoxDatabase to JSON structure format expected by ERD generators.
    
    This allows ERD generators designed for JSON to work with YAML databases.
    The YAML format already contains all the schema information we need.
    
    Args:
        database: NinoxDatabase instance from YAML parser
        
    Returns:
        Dictionary in Ninox JSON structure format with settings and schema
    """
    json_structure = {
        'settings': {
            'name': database.name,
            'icon': database.database_yaml.get('icon', ''),
            'color': database.database_yaml.get('color', ''),
        },
        'schema': {
            'seq': 0,
            'version': database.version or 0,
            'nextTypeId': len(database.tables) + 1,
            'types': {}
        }
    }
    
    # Track table names to type IDs for reference resolution
    table_name_to_id = {}  # table_name -> type_id
    type_id_counter = 1
    
    # Convert tables - they're already in dict format from YAML
    for table_name, table_data in database.tables.items():
        # Assign a type ID (use letter for first 26 tables, then T1, T2, ...)
        if type_id_counter <= 26:
            type_id = chr(64 + type_id_counter)  # A, B, C, ...
        else:
            type_id = f"T{type_id_counter - 26}"
        
        table_name_to_id[table_name] = type_id
        type_id_counter += 1
        
        # Table already has the right structure from YAML
        # Copy it directly, but ensure required fields exist
        type_entry = {
            'caption': table_data.get('caption', table_name),
            'captions': table_data.get('captions', {}),
            'icon': table_data.get('icon', ''),
            'hidden': table_data.get('hidden', False),
            'nextFieldId': table_data.get('nextFieldId', 0),
            'fields': table_data.get('fields', {}),  # Already in correct format
            'uuid': table_data.get('uuid', f'uuid-{type_id}'),
            'order': table_data.get('order', type_id_counter - 2)
        }
        
        # Copy any code fields that might exist
        for code_field in TABLE_CODE_FIELDS:
            if code_field in table_data:
                type_entry[code_field] = table_data[code_field]
        
        json_structure['schema']['types'][type_id] = type_entry
    
    return json_structure
