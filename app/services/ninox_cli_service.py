"""
Ninox CLI Service
Wrapper for ninox-dev-cli to download/upload database schemas as YAML files.

This service provides Python bindings to execute the ninox CLI commands
and manage the downloaded YAML structure for AI-friendly code viewing.
"""
import os
import subprocess
import asyncio
import logging
import json
import shutil
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)

# Base paths
WEBAPP_ROOT = Path(__file__).parent.parent.parent  # /webapp
NPX_PATH = shutil.which('npx') or '/usr/bin/npx'
NINOX_CLI_DATA_PATH = os.getenv('NINOX_CLI_DATA_PATH', '/app/data/ninox-cli')


@dataclass
class NinoxEnvironment:
    """Configuration for a Ninox environment"""
    name: str
    domain: str
    api_key: str
    workspace_id: str
    
    def to_config_dict(self) -> Dict[str, Any]:
        """Convert to config.yaml format"""
        return {
            'domain': self.domain,
            'apiKey': self.api_key,
            'workspaceId': self.workspace_id
        }


@dataclass 
class DatabaseInfo:
    """Information about a downloaded database"""
    database_id: str
    name: str
    path: Path
    download_date: datetime
    table_count: int = 0
    has_global_code: bool = False


@dataclass
class DownloadResult:
    """Result of a database download operation"""
    success: bool
    database_id: str
    path: Optional[Path] = None
    error: Optional[str] = None
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = 0


class NinoxCLIService:
    """
    Service to interact with ninox-dev-cli.
    
    Manages:
    - Project initialization and configuration
    - Database listing, downloading and uploading
    - YAML file management
    """
    
    def __init__(self, project_path: Optional[str] = None):
        """
        Initialize the CLI service.
        
        Args:
            project_path: Path to the ninox-cli project directory.
                         If None, uses NINOX_CLI_DATA_PATH environment variable.
        """
        self.project_path = Path(project_path or NINOX_CLI_DATA_PATH)
        self.config_path = self.project_path / 'config.yaml'
        self._ensure_project_dir()
    
    def _ensure_project_dir(self):
        """Ensure the project directory exists"""
        self.project_path.mkdir(parents=True, exist_ok=True)
        # Create src/Objects directory for downloaded databases
        objects_path = self.project_path / 'src' / 'Objects'
        objects_path.mkdir(parents=True, exist_ok=True)
    
    def _run_ninox_command(
        self, 
        args: List[str], 
        timeout: int = 300,
        env_name: Optional[str] = None
    ) -> Tuple[int, str, str]:
        """
        Run a ninox CLI command.
        
        Args:
            args: Command arguments (without 'ninox' prefix)
            timeout: Command timeout in seconds
            env_name: Environment name to prepend to command
            
        Returns:
            Tuple of (return_code, stdout, stderr)
        """
        cmd = [NPX_PATH, 'ninox']
        
        # Insert environment name if provided (e.g., 'ninox DEV database list')
        if env_name:
            cmd.append(env_name)
        
        cmd.extend(args)
        
        logger.info(f"Running ninox command: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd,
                cwd=str(self.project_path),
                capture_output=True,
                text=True,
                timeout=timeout,
                env={**os.environ, 'NO_COLOR': '1'}  # Disable color output
            )
            
            logger.debug(f"Command stdout: {result.stdout[:500] if result.stdout else 'empty'}")
            if result.stderr:
                logger.debug(f"Command stderr: {result.stderr[:500]}")
            
            return result.returncode, result.stdout, result.stderr
            
        except subprocess.TimeoutExpired:
            logger.error(f"Command timed out after {timeout}s")
            return -1, "", f"Command timed out after {timeout} seconds"
        except Exception as e:
            logger.error(f"Command failed: {e}")
            return -1, "", str(e)
    
    async def _run_ninox_command_async(
        self,
        args: List[str],
        timeout: int = 300,
        env_name: Optional[str] = None
    ) -> Tuple[int, str, str]:
        """
        Run a ninox CLI command asynchronously.
        
        Args:
            args: Command arguments (without 'ninox' prefix)
            timeout: Command timeout in seconds
            env_name: Environment name to prepend to command
            
        Returns:
            Tuple of (return_code, stdout, stderr)
        """
        cmd = [NPX_PATH, 'ninox']
        
        if env_name:
            cmd.append(env_name)
        
        cmd.extend(args)
        
        logger.info(f"Running async ninox command: {' '.join(cmd)}")
        
        process = None
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(self.project_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, 'NO_COLOR': '1'}
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )
            
            return process.returncode or 0, stdout.decode(), stderr.decode()
            
        except asyncio.TimeoutError:
            logger.error(f"Async command timed out after {timeout}s")
            if process:
                process.kill()
            return -1, "", f"Command timed out after {timeout} seconds"
        except Exception as e:
            logger.error(f"Async command failed: {e}")
            return -1, "", str(e)
    
    def init_project(self, project_name: str = "ninox2git") -> bool:
        """
        Initialize a new ninox-cli project.
        
        Args:
            project_name: Name for the project
            
        Returns:
            True if successful
        """
        if self.config_path.exists():
            logger.info("Project already initialized")
            return True
        
        code, stdout, stderr = self._run_ninox_command(['project', 'init', project_name])
        
        if code != 0:
            logger.error(f"Failed to init project: {stderr}")
            return False
        
        logger.info(f"Project initialized: {project_name}")
        return True
    
    def configure_environment(self, env: NinoxEnvironment) -> bool:
        """
        Configure a Ninox environment in config.yaml.
        
        Args:
            env: Environment configuration
            
        Returns:
            True if successful
        """
        import yaml
        
        config = {'environments': {}}
        
        # Load existing config if present
        if self.config_path.exists():
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f) or {'environments': {}}
        
        # Add/update environment
        config['environments'][env.name] = env.to_config_dict()
        
        # Write config
        with open(self.config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
        
        logger.info(f"Configured environment: {env.name}")
        return True
    
    def list_databases(self, env_name: str) -> List[Dict[str, str]]:
        """
        List all databases in a workspace.
        
        Args:
            env_name: Environment name from config.yaml
            
        Returns:
            List of database info dicts with 'id' and 'name'
        """
        code, stdout, stderr = self._run_ninox_command(
            ['database', 'list'],
            env_name=env_name
        )
        
        if code != 0:
            logger.error(f"Failed to list databases: {stderr}")
            return []
        
        # Parse output (format: "ID: xxx, Name: yyy")
        databases = []
        for line in stdout.strip().split('\n'):
            line = line.strip()
            if not line or line.startswith('ID') or line.startswith('-'):
                continue
            
            # Try to parse "id  name" format
            parts = line.split(None, 1)
            if len(parts) >= 2:
                databases.append({
                    'id': parts[0].strip(),
                    'name': parts[1].strip()
                })
        
        return databases
    
    async def list_databases_async(self, env_name: str) -> List[Dict[str, str]]:
        """Async version of list_databases"""
        code, stdout, stderr = await self._run_ninox_command_async(
            ['database', 'list'],
            env_name=env_name
        )
        
        if code != 0:
            logger.error(f"Failed to list databases: {stderr}")
            return []
        
        databases = []
        for line in stdout.strip().split('\n'):
            line = line.strip()
            if not line or line.startswith('ID') or line.startswith('-'):
                continue
            
            parts = line.split(None, 1)
            if len(parts) >= 2:
                databases.append({
                    'id': parts[0].strip(),
                    'name': parts[1].strip()
                })
        
        return databases
    
    def download_database(
        self, 
        env_name: str, 
        database_id: str,
        timeout: int = 300
    ) -> DownloadResult:
        """
        Download a database schema as YAML files.
        
        Args:
            env_name: Environment name from config.yaml
            database_id: Database ID to download
            timeout: Timeout in seconds
            
        Returns:
            DownloadResult with success status and path
        """
        start_time = datetime.now()
        
        code, stdout, stderr = self._run_ninox_command(
            ['database', 'download', '-i', database_id],
            timeout=timeout,
            env_name=env_name
        )
        
        duration = (datetime.now() - start_time).total_seconds()
        
        if code != 0:
            return DownloadResult(
                success=False,
                database_id=database_id,
                error=stderr or stdout,
                stdout=stdout,
                stderr=stderr,
                duration_seconds=duration
            )
        
        # Find the downloaded database directory
        db_path = self._find_database_path(database_id)
        
        return DownloadResult(
            success=True,
            database_id=database_id,
            path=db_path,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=duration
        )
    
    async def download_database_async(
        self,
        env_name: str,
        database_id: str,
        timeout: int = 300
    ) -> DownloadResult:
        """Async version of download_database"""
        start_time = datetime.now()
        
        code, stdout, stderr = await self._run_ninox_command_async(
            ['database', 'download', '-i', database_id],
            timeout=timeout,
            env_name=env_name
        )
        
        duration = (datetime.now() - start_time).total_seconds()
        
        if code != 0:
            return DownloadResult(
                success=False,
                database_id=database_id,
                error=stderr or stdout,
                stdout=stdout,
                stderr=stderr,
                duration_seconds=duration
            )
        
        db_path = self._find_database_path(database_id)
        
        return DownloadResult(
            success=True,
            database_id=database_id,
            path=db_path,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=duration
        )
    
    def _find_database_path(self, database_id: str) -> Optional[Path]:
        """
        Find the path to a downloaded database.
        
        The ninox-cli stores databases in src/Objects/database_<id>/
        """
        objects_path = self.project_path / 'src' / 'Objects'
        
        # Look for directory matching database_<id>
        for dir_path in objects_path.iterdir():
            if dir_path.is_dir() and database_id in dir_path.name:
                return dir_path
        
        return None
    
    def get_downloaded_databases(self) -> List[DatabaseInfo]:
        """
        Get list of all downloaded databases.
        
        Returns:
            List of DatabaseInfo for each downloaded database
        """
        objects_path = self.project_path / 'src' / 'Objects'
        
        if not objects_path.exists():
            return []
        
        databases = []
        
        for dir_path in objects_path.iterdir():
            if not dir_path.is_dir():
                continue
            
            # NEW: Check for metadata file first (new structure with clear names)
            dir_name = dir_path.name
            metadata_file = dir_path / '.ninox-metadata.json'

            if metadata_file.exists():
                # New structure: read from metadata
                try:
                    import json
                    with open(metadata_file, 'r') as f:
                        meta = json.load(f)
                    db_id = meta['database_id']
                    db_name = meta['database_name']
                except Exception as e:
                    logger.warning(f"Could not read metadata from {metadata_file}: {e}")
                    db_id = dir_name
                    db_name = dir_name
            else:
                # Old structure: extract from directory name
                if dir_name.startswith('database_'):
                    db_id = dir_name.replace('database_', '')
                else:
                    db_id = dir_name

                # Try to get database name from database.yaml
                db_name = db_id
                db_yaml = dir_path / 'database.yaml'
                if db_yaml.exists():
                    try:
                        import yaml
                        with open(db_yaml, 'r') as f:
                            db_data = yaml.safe_load(f)
                        db_name = db_data.get('database', {}).get('name', db_id)
                    except Exception:
                        pass
            
            # Count tables
            tables_dir = dir_path / 'tables'
            table_count = 0
            if tables_dir.exists():
                table_count = len([f for f in tables_dir.iterdir() if f.is_dir()])
            
            # Check for global code
            has_global = False
            schema_yaml = dir_path / 'database.yaml'
            if schema_yaml.exists():
                try:
                    import yaml
                    with open(schema_yaml, 'r') as f:
                        content = f.read()
                    has_global = 'globalCode' in content
                except Exception:
                    pass
            
            # Get modification time
            mtime = datetime.fromtimestamp(dir_path.stat().st_mtime)
            
            databases.append(DatabaseInfo(
                database_id=db_id,
                name=db_name,
                path=dir_path,
                download_date=mtime,
                table_count=table_count,
                has_global_code=has_global
            ))
        
        return sorted(databases, key=lambda d: d.name)
    
    def get_database_yaml_structure(self, database_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the full YAML structure of a database.
        
        Args:
            database_id: Database ID
            
        Returns:
            Dict representing the full database structure
        """
        db_path = self._find_database_path(database_id)
        if not db_path:
            return None
        
        return self._load_database_yaml_recursive(db_path)
    
    def _load_database_yaml_recursive(self, db_path: Path) -> Dict[str, Any]:
        """
        Recursively load all YAML files from a database directory.
        
        Args:
            db_path: Path to database directory
            
        Returns:
            Combined dict of all YAML data
        """
        import yaml
        
        result = {
            'path': str(db_path),
            'database': {},
            'tables': {},
            'views': [],
            'reports': []
        }
        
        # Load database.yaml
        db_yaml = db_path / 'database.yaml'
        if db_yaml.exists():
            try:
                with open(db_yaml, 'r', encoding='utf-8') as f:
                    result['database'] = yaml.safe_load(f) or {}
            except Exception as e:
                logger.error(f"Error loading {db_yaml}: {e}")
        
        # Load tables
        tables_dir = db_path / 'tables'
        if tables_dir.exists():
            for table_dir in tables_dir.iterdir():
                if table_dir.is_dir():
                    table_data = self._load_table_yaml(table_dir)
                    if table_data:
                        table_name = table_data.get('caption') or table_dir.name
                        result['tables'][table_name] = table_data
        
        # Load views if present
        views_yaml = db_path / 'views.yaml'
        if views_yaml.exists():
            try:
                with open(views_yaml, 'r', encoding='utf-8') as f:
                    result['views'] = yaml.safe_load(f) or []
            except Exception as e:
                logger.error(f"Error loading {views_yaml}: {e}")
        
        # Load reports if present
        reports_yaml = db_path / 'reports.yaml'
        if reports_yaml.exists():
            try:
                with open(reports_yaml, 'r', encoding='utf-8') as f:
                    result['reports'] = yaml.safe_load(f) or []
            except Exception as e:
                logger.error(f"Error loading {reports_yaml}: {e}")
        
        return result
    
    def _load_table_yaml(self, table_dir: Path) -> Optional[Dict[str, Any]]:
        """
        Load all YAML files for a table.
        
        Args:
            table_dir: Path to table directory
            
        Returns:
            Combined table data
        """
        import yaml
        
        result = {}
        
        # Load table.yaml (main table definition)
        table_yaml = table_dir / 'table.yaml'
        if table_yaml.exists():
            try:
                with open(table_yaml, 'r', encoding='utf-8') as f:
                    result = yaml.safe_load(f) or {}
            except Exception as e:
                logger.error(f"Error loading {table_yaml}: {e}")
                return None
        
        # Load fields
        fields_dir = table_dir / 'fields'
        if fields_dir.exists():
            result['fields'] = {}
            for field_file in fields_dir.glob('*.yaml'):
                try:
                    with open(field_file, 'r', encoding='utf-8') as f:
                        field_data = yaml.safe_load(f) or {}
                    field_name = field_file.stem
                    result['fields'][field_name] = field_data
                except Exception as e:
                    logger.error(f"Error loading {field_file}: {e}")
        
        # Load UIs (buttons, tabs, etc.)
        uis_dir = table_dir / 'uis'
        if uis_dir.exists():
            result['uis'] = {}
            for ui_file in uis_dir.glob('*.yaml'):
                try:
                    with open(ui_file, 'r', encoding='utf-8') as f:
                        ui_data = yaml.safe_load(f) or {}
                    ui_name = ui_file.stem
                    result['uis'][ui_name] = ui_data
                except Exception as e:
                    logger.error(f"Error loading {ui_file}: {e}")
        
        return result


# Singleton instance
_cli_service: Optional[NinoxCLIService] = None


def get_ninox_cli_service() -> NinoxCLIService:
    """Get or create the singleton CLI service instance"""
    global _cli_service
    if _cli_service is None:
        _cli_service = NinoxCLIService()
    return _cli_service


def configure_ninox_environment_from_server(
    server_name: str,
    domain: str, 
    api_key: str,
    workspace_id: str
) -> bool:
    """
    Helper to configure a Ninox environment from a server configuration.
    
    Args:
        server_name: Unique name for this environment
        domain: Ninox domain (e.g., https://mycompany.ninox.com)
        api_key: API key for authentication
        workspace_id: Workspace/Team ID
        
    Returns:
        True if configuration was successful
    """
    service = get_ninox_cli_service()
    
    # Initialize project if needed
    service.init_project()
    
    # Configure environment
    env = NinoxEnvironment(
        name=server_name,
        domain=domain,
        api_key=api_key,
        workspace_id=workspace_id
    )
    
    return service.configure_environment(env)
