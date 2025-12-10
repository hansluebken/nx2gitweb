"""
Synchronization page for Ninox2Git
"""
from nicegui import ui, background_tasks
from datetime import datetime
import asyncio
from ..database import get_db
from ..models.server import Server
from ..models.team import Team
from ..models.database import Database
from ..models.audit_log import AuditLog
from ..models.user_preference import UserPreference
from ..models.changelog import ChangeLog
from ..auth import create_audit_log
from ..utils.encryption import get_encryption_manager
from ..utils.github_utils import sanitize_name, get_repo_name_from_server
from ..utils.svg_erd_generator import generate_svg_erd
from ..utils.ninox_code_extractor import extract_and_generate as extract_ninox_code
from ..utils.ninox_md_generator import generate_markdown_from_backup
from ..api.ninox_client import NinoxClient
from ..api.github_manager import GitHubManager
from .components import (
    NavHeader, Card, FormField, Toast, EmptyState,
    StatusBadge, format_datetime, PRIMARY_COLOR, SUCCESS_COLOR
)
from .database_timeline import show_database_timeline_dialog
import json

# Cache for dependency scans to avoid re-scanning same databases
_dependency_cache = {}

# Global state to track open dialogs (prevents refresh during dialog viewing)
_dialog_open_state = {'count': 0}

# Track databases currently generating documentation with progress
_doc_generating = {}  # Dict: database_id -> {'current': 1, 'total': 3}

# Track background documentation generation tasks (persistent across pages)
_background_doc_tasks = {}  # Dict: task_id -> {database, status, progress, start_time, ...}

# Flag to force immediate refresh (set when doc generation starts)
_force_refresh = {'needed': False}


def clear_dependency_cache():
    """Clear the dependency cache (call after YAML sync)"""
    global _dependency_cache
    _dependency_cache = {}


def save_database_dependencies(team: Team, database_id: str):
    """
    Scan and save dependencies for a database after YAML sync.

    Args:
        team: Team model
        database_id: Ninox database ID that was just synced
    """
    import logging
    from ..models.database_dependency import DatabaseDependency

    logger = logging.getLogger(__name__)

    try:
        db = get_db()
        try:
            # Get the database object
            database = db.query(Database).filter(
                Database.team_id == team.id,
                Database.database_id == database_id
            ).first()

            if not database:
                logger.warning(f"Database not found: {database_id}")
                return

            # Clear existing dependencies for this database
            db.query(DatabaseDependency).filter(
                DatabaseDependency.source_database_id == database.id
            ).delete()

            # Scan for dependencies
            dependencies = find_database_dependencies(team, database_id)

            logger.info(f"Found {len(dependencies)} dependencies for {database.name}")

            # Save dependencies
            for dep_ninox_id in dependencies:
                # Find target database
                target_db = db.query(Database).filter(
                    Database.team_id == team.id,
                    Database.database_id == dep_ninox_id
                ).first()

                if target_db:
                    # Create dependency record
                    dep = DatabaseDependency(
                        source_database_id=database.id,
                        target_database_id=target_db.id,
                        source_ninox_id=database_id,
                        target_ninox_id=dep_ninox_id
                    )
                    db.add(dep)
                    logger.info(f"Saved dependency: {database.name} → {target_db.name}")
                else:
                    logger.warning(f"Target database not found: {dep_ninox_id}")

            db.commit()
            logger.info(f"✓ Saved {len(dependencies)} dependencies for {database.name}")

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Error saving dependencies for {database_id}: {e}")
        import traceback
        logger.error(traceback.format_exc())


def find_database_dependencies(team: Team, database_id: str, visited: set = None) -> set:
    """
    Find all databases that this database depends on (recursively).

    Args:
        team: Team model
        database_id: Database ID to check
        visited: Set of already visited database IDs (to avoid infinite loops)

    Returns:
        Set of database IDs that this database depends on
    """
    import logging
    from pathlib import Path
    import yaml

    logger = logging.getLogger(__name__)

    # Check cache first
    cache_key = f"{team.team_id}_{database_id}"
    if cache_key in _dependency_cache:
        logger.debug(f"Using cached dependencies for {database_id}")
        return _dependency_cache[cache_key].copy()

    if visited is None:
        visited = set()

    # Avoid infinite loops
    if database_id in visited:
        return set()

    visited.add(database_id)
    dependencies = set()

    try:
        # Get team-specific folder using clear names
        from ..services.ninox_cli_service import get_ninox_cli_service
        from ..utils.path_resolver import get_team_path
        from ..utils.metadata_helper import read_database_metadata

        server = team.server
        cli_service = get_ninox_cli_service()
        team_path = get_team_path(server, team)

        # Find database by ID - need to scan all databases in team
        db_path = None
        team_objects = team_path / 'src' / 'Objects'
        if team_objects.exists():
            for potential_db in team_objects.parent.parent.rglob('.ninox-metadata.json'):
                try:
                    metadata = read_database_metadata(potential_db.parent)
                    if metadata['database_id'] == database_id:
                        db_path = potential_db.parent / 'src' / 'Objects'
                        break
                except:
                    continue

        if not db_path:
            # Fallback: old structure or not found
            db_path = team_path / 'src' / 'Objects' / f'database_{database_id}'

        if not db_path.exists():
            logger.warning(f"Database path not found: {db_path}")
            return dependencies

        # Recursively scan all YAML files for dbId references
        for yaml_file in db_path.rglob('*.yaml'):
            try:
                with open(yaml_file, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)

                    # Search for dbId in the YAML structure
                    def find_dbid(obj, depth=0):
                        if depth > 20:  # Prevent deep recursion
                            return

                        if isinstance(obj, dict):
                            # Check for dbId key
                            if 'dbId' in obj and obj['dbId']:
                                ref_db_id = obj['dbId']
                                if ref_db_id != database_id:  # Don't include self
                                    dependencies.add(ref_db_id)
                                    logger.info(f"Found dependency: {database_id} -> {ref_db_id}")

                            # Recursively search in dict values
                            for value in obj.values():
                                find_dbid(value, depth + 1)

                        elif isinstance(obj, list):
                            # Recursively search in list items
                            for item in obj:
                                find_dbid(item, depth + 1)

                    find_dbid(data)

            except Exception as e:
                logger.debug(f"Could not parse {yaml_file}: {e}")
                continue

        # Recursively find dependencies of dependencies
        all_deps = dependencies.copy()
        for dep_id in dependencies:
            sub_deps = find_database_dependencies(team, dep_id, visited)
            all_deps.update(sub_deps)

        # Cache the result
        _dependency_cache[cache_key] = all_deps.copy()
        logger.info(f"Cached {len(all_deps)} dependencies for {database_id}")

        return all_deps

    except Exception as e:
        logger.error(f"Error finding dependencies for {database_id}: {e}")
        return dependencies


def build_dependency_graph(team: Team, all_databases: list) -> dict:
    """
    Build a complete dependency graph for all databases in a team (efficient, one-time scan).

    Returns:
        Dict with 'dependencies' (what each DB needs) and 'dependents' (what needs each DB)
    """
    import logging
    logger = logging.getLogger(__name__)

    graph = {
        'dependencies': {},  # db_id -> set of db_ids it depends on
        'dependents': {}     # db_id -> set of db_ids that depend on it
    }

    # Initialize
    for db in all_databases:
        graph['dependencies'][db.database_id] = set()
        graph['dependents'][db.database_id] = set()

    # Scan each database once
    for db in all_databases:
        deps = find_database_dependencies(team, db.database_id)
        graph['dependencies'][db.database_id] = deps

        # Build reverse mapping
        for dep_id in deps:
            if dep_id in graph['dependents']:
                graph['dependents'][dep_id].add(db.database_id)

    logger.info(f"Built dependency graph for {len(all_databases)} databases")
    return graph


def find_dependent_databases(team: Team, database_id: str, all_databases: list = None) -> set:
    """
    Find all databases that depend on this database (recursively).
    Uses efficient graph-based approach.
    """
    import logging
    logger = logging.getLogger(__name__)

    try:
        # Get all databases for this team if not provided
        if all_databases is None:
            db = get_db()
            try:
                all_databases = db.query(Database).filter(Database.team_id == team.id).all()
            finally:
                db.close()

        # Build dependency graph once
        graph = build_dependency_graph(team, all_databases)

        # Get direct dependents
        dependents = graph['dependents'].get(database_id, set()).copy()

        # Recursively add dependents of dependents
        to_process = list(dependents)
        while to_process:
            current = to_process.pop()
            for dep in graph['dependents'].get(current, set()):
                if dep not in dependents:
                    dependents.add(dep)
                    to_process.append(dep)

        logger.info(f"Found {len(dependents)} databases that depend on {database_id}")
        return dependents

    except Exception as e:
        logger.error(f"Error finding dependents for {database_id}: {e}")
        return set()


def render(user, server_id_param=None, team_id_param=None):
    """
    Render the synchronization page

    Args:
        user: Current user object
        server_id_param: Optional server ID from URL parameter
        team_id_param: Optional team ID from URL parameter
    """
    import logging
    logger = logging.getLogger(__name__)

    ui.colors(primary=PRIMARY_COLOR)

    # Navigation header
    NavHeader(user, 'synchronization').render()

    # Log URL parameters if provided
    if server_id_param:
        logger.info(f"Server ID from URL parameter: {server_id_param}")
    if team_id_param:
        logger.info(f"Team ID from URL parameter: {team_id_param}")

    # Main content
    with ui.column().classes('w-full p-6 gap-6').style('max-width: 1400px; margin: 0 auto;'):
        ui.label('Synchronization').classes('text-h4 font-bold mb-4')
        # Server and team selectors
        selector_container = ui.column().classes('w-full')
        databases_container = ui.column().classes('w-full gap-4 mt-4')

        with selector_container:
            render_selectors(user, databases_container, server_id_param, team_id_param)


def render_selectors(user, databases_container, server_id_param=None, team_id_param=None):
    """Render server and team selectors"""
    import logging
    logger = logging.getLogger(__name__)

    db = get_db()
    try:
        # Get or create user preferences
        preferences = db.query(UserPreference).filter(UserPreference.user_id == user.id).first()
        if not preferences:
            preferences = UserPreference(user_id=user.id)
            db.add(preferences)
            db.commit()

        # If server_id_param or team_id_param is provided, use them for initial selection
        override_server = None
        override_team = None

        # First, check if server_id_param is provided
        if server_id_param:
            logger.info(f"Looking for server with ID: {server_id_param}")
            override_server = db.query(Server).filter(Server.id == server_id_param).first()
            if override_server:
                logger.info(f"Found server: {override_server.name}")
                preferences.last_selected_server_id = override_server.id
                db.commit()

        # Then, check if team_id_param is provided
        if team_id_param:
            logger.info(f"Looking for team with ID: {team_id_param}")
            team = db.query(Team).filter(Team.id == team_id_param).first()
            if team:
                logger.info(f"Found team: {team.name}, server_id: {team.server_id}")
                override_team = team
                # If server wasn't already set by server_id_param, get it from team
                if not override_server:
                    override_server = db.query(Server).filter(Server.id == team.server_id).first()
                # Update preferences to remember this selection
                preferences.last_selected_team_id = team.id
                preferences.last_selected_server_id = team.server_id
                db.commit()

        # Get user's servers
        if user.is_admin:
            servers = db.query(Server).filter(Server.is_active == True).all()
        else:
            servers = db.query(Server).filter(
                Server.user_id == user.id,
                Server.is_active == True
            ).all()

        if not servers:
            with databases_container:
                databases_container.clear()
                EmptyState.render(
                    icon='storage',
                    title='No Active Servers',
                    message='You need to add an active server before synchronizing.',
                    action_label='Add Server',
                    on_action=lambda: ui.navigate.to('/servers')
                )
            return

        # Create server options
        server_options = {server.name: server for server in servers}

        # Determine initial server selection
        initial_server = None
        if override_server:
            # Use the server from the team parameter
            initial_server = override_server.name
            logger.info(f"Using override server: {initial_server}")
        elif preferences.last_selected_server_id:
            # Try to find the last selected server
            for server in servers:
                if server.id == preferences.last_selected_server_id:
                    initial_server = server.name
                    break

        # If no saved preference or server not found, use the first one
        if not initial_server:
            initial_server = list(server_options.keys())[0] if server_options else None

        with ui.row().classes('w-full items-center gap-4'):
            server_select = ui.select(
                label='Select Server',
                options=list(server_options.keys()),
                value=initial_server
            ).classes('flex-1')

            team_select = ui.select(
                label='Select Team',
                options=[],
                value=None
            ).classes('flex-1')

        # Update teams when server changes
        def on_server_change(e=None):
            import logging
            logger = logging.getLogger(__name__)

            # Get current value from server_select directly, not from event
            current_server_name = server_select.value
            logger.info(f"=== SERVER CHANGE === Current server_select.value: {current_server_name}")

            if current_server_name and current_server_name in server_options:
                # Use a NEW db session for this event
                event_db = get_db()
                try:
                    server = server_options[current_server_name]
                    logger.info(f"Selected server: {server.name} (id={server.id})")

                    # Save server selection to preferences
                    pref = event_db.query(UserPreference).filter(UserPreference.user_id == user.id).first()
                    if pref:
                        pref.last_selected_server_id = server.id
                        event_db.commit()

                    teams = event_db.query(Team).filter(
                        Team.server_id == server.id,
                        Team.is_active == True
                    ).all()
                    logger.info(f"Found {len(teams)} teams for server {server.name}")

                    team_options = {team.name: team for team in teams}
                    team_select.options = list(team_options.keys())
                    logger.info(f"Set team_select.options to {len(team_select.options)} teams")

                    # Check if there's a saved team preference for this server or override
                    initial_team = None

                    # Check for override team first (when coming from Teams page)
                    if hasattr(e, 'is_initial_load') and e.is_initial_load and override_team and override_team.server_id == server.id:
                        initial_team = override_team.name
                        logger.info(f"Using override team: {initial_team}")
                    elif pref and pref.last_selected_team_id:
                        for team in teams:
                            if team.id == pref.last_selected_team_id and team.server_id == server.id:
                                initial_team = team.name
                                break

                    # Use saved team or first available
                    team_select.value = initial_team if initial_team else (list(team_options.keys())[0] if team_options else None)
                    logger.info(f"Set team_select.value to: {team_select.value}")

                    team_select.update()
                    logger.info("Called team_select.update()")

                    # Store team options for later use
                    team_select.team_options = team_options

                    # Load databases if team is selected
                    if team_select.value:
                        load_databases(
                            user,
                            server,
                            team_options[team_select.value],
                            databases_container
                        )
                finally:
                    event_db.close()

        # Update teams when server changes
        def on_team_change(e):
            import logging
            logger = logging.getLogger(__name__)

            # Get the actual value from team_select, not from event
            team_name = team_select.value
            logger.info(f"=== TEAM CHANGE EVENT === team_name={team_name}, server={server_select.value}")

            if team_name and server_select.value and hasattr(team_select, 'team_options'):
                server = server_options[server_select.value]
                team = team_select.team_options[team_name]
                logger.info(f"Loading databases for team: {team.name} (id={team.id})")

                # Save team selection to preferences
                event_db = get_db()
                try:
                    pref = event_db.query(UserPreference).filter(UserPreference.user_id == user.id).first()
                    if pref:
                        pref.last_selected_team_id = team.id
                        event_db.commit()
                finally:
                    event_db.close()

                load_databases(user, server, team, databases_container)
            else:
                logger.warning(f"Team change event but missing values: team={team_name}, server={server_select.value}")

        server_select.on('update:model-value', on_server_change)
        team_select.on('update:model-value', on_team_change)

        # Load initial teams and databases
        if server_select.value:
            # Call without event parameter, function uses server_select.value directly
            logger.info("Loading initial teams...")
            on_server_change()

    finally:
        db.close()


async def generate_ai_changelog(
    user, server, team, database,
    team_path, logger
):
    """
    Generate AI-powered changelog entry from local YAML git commits.
    Runs in background to not block the sync process.

    Args:
        user: Current user object
        server: Server object
        team: Team object
        database: Database object
        team_path: Path to team folder with local git repo (Path object)
        logger: Logger instance
    """
    from concurrent.futures import ThreadPoolExecutor
    from ..services.ai_changelog import get_ai_changelog_service
    from ..models.ai_config import AIConfig
    from pathlib import Path
    import subprocess
    from datetime import datetime

    try:
        # Check if AI is configured
        db = get_db()
        ai_config = db.query(AIConfig).filter(
            AIConfig.is_default == True,
            AIConfig.is_active == True,
            AIConfig.api_key_encrypted != None
        ).first()
        db.close()

        if not ai_config:
            logger.info("AI changelog skipped: No AI provider configured")
            return

        logger.info(f"Generating AI changelog for {database.name} from local YAML...")

        # Get the path to the database YAML folder in local git
        db_folder = team_path / 'src' / 'Objects' / f'database_{database.database_id}'

        if not db_folder.exists():
            logger.warning(f"Database folder not found: {db_folder}")
            return

        # Get latest commit SHA for this database folder
        result = subprocess.run(
            ['git', 'log', '-1', '--format=%H', '--', str(db_folder)],
            cwd=team_path,
            capture_output=True,
            text=True
        )

        if result.returncode != 0 or not result.stdout.strip():
            logger.warning(f"No commits found for {db_folder}")
            return

        commit_sha = result.stdout.strip()

        # Check if we already have a changelog for this commit
        db = get_db()
        existing = db.query(ChangeLog).filter(
            ChangeLog.database_id == database.id,
            ChangeLog.commit_sha == commit_sha
        ).first()
        db.close()

        if existing:
            logger.info(f"Changelog already exists for commit {commit_sha[:7]}")
            return

        # Get commit info
        commit_info_result = subprocess.run(
            ['git', 'log', '-1', '--format=%H%n%h%n%s%n%cI%n%an%n%ae', commit_sha],
            cwd=team_path,
            capture_output=True,
            text=True
        )

        if commit_info_result.returncode != 0:
            logger.error(f"Failed to get commit info")
            return

        lines = commit_info_result.stdout.strip().split('\n')
        commit_full_sha = lines[0]
        commit_short_sha = lines[1]
        commit_message = lines[2] if len(lines) > 2 else ''
        commit_date_str = lines[3] if len(lines) > 3 else ''
        author_name = lines[4] if len(lines) > 4 else ''
        author_email = lines[5] if len(lines) > 5 else ''

        # Parse commit date
        try:
            commit_date = datetime.fromisoformat(commit_date_str.replace('Z', '+00:00'))
        except:
            commit_date = datetime.utcnow()

        # Get diff for this commit (compare with previous commit)
        diff_result = subprocess.run(
            ['git', 'diff', f'{commit_sha}~1', commit_sha, '--', str(db_folder)],
            cwd=team_path,
            capture_output=True,
            text=True
        )

        if diff_result.returncode != 0:
            logger.warning(f"Could not get diff for commit {commit_short_sha}")
            diff_content = ""
        else:
            diff_content = diff_result.stdout

        # Get stats
        stats_result = subprocess.run(
            ['git', 'diff', '--stat', f'{commit_sha}~1', commit_sha, '--', str(db_folder)],
            cwd=team_path,
            capture_output=True,
            text=True
        )

        files_changed = 0
        additions = 0
        deletions = 0

        if stats_result.returncode == 0:
            # Parse stats: "X files changed, Y insertions(+), Z deletions(-)"
            stats_line = stats_result.stdout.strip().split('\n')[-1] if stats_result.stdout.strip() else ""
            import re
            files_match = re.search(r'(\d+) file', stats_line)
            add_match = re.search(r'(\d+) insertion', stats_line)
            del_match = re.search(r'(\d+) deletion', stats_line)

            if files_match:
                files_changed = int(files_match.group(1))
            if add_match:
                additions = int(add_match.group(1))
            if del_match:
                deletions = int(del_match.group(1))

        if not diff_content or diff_content.strip() == '':
            logger.info(f"No changes in YAML for commit {commit_short_sha} - skipping AI analysis")
            # Still create a basic changelog entry without AI
            db = get_db()
            changelog = ChangeLog(
                database_id=database.id,
                commit_sha=commit_full_sha,
                commit_date=commit_date,
                commit_message=commit_message,
                commit_url='',  # Local git, no URL
                files_changed=files_changed,
                additions=additions,
                deletions=deletions,
                ai_summary=None,
                ai_details=None,
            )
            db.add(changelog)
            db.commit()
            db.close()
            logger.info(f"Created basic changelog entry (no AI) for {commit_short_sha}")
            return

        # Run AI analysis in thread pool to not block
        loop = asyncio.get_event_loop()
        service = get_ai_changelog_service()

        def do_ai_analysis():
            """Blocking AI call"""
            context = {
                'database_name': database.name,
                'commit_message': commit_message,
                'files_changed': files_changed,
            }
            return service.analyze_diff(
                diff=diff_content,
                context=context
            )

        with ThreadPoolExecutor() as executor:
            analysis = await loop.run_in_executor(executor, do_ai_analysis)

        # Save changelog with AI analysis
        db = get_db()
        try:
            changelog = ChangeLog(
                database_id=database.id,
                commit_sha=commit_full_sha,
                commit_date=commit_date,
                commit_message=commit_message,
                commit_url='',  # Local git
                files_changed=files_changed,
                additions=additions,
                deletions=deletions,
                ai_summary=analysis.summary if analysis else None,
                ai_details=analysis.details if analysis else None,
            )
            db.add(changelog)
            db.commit()
            logger.info(f"✓ AI Changelog created for {commit_short_sha}: {analysis.summary if analysis else 'No summary'}")
        finally:
            db.close()

    except Exception as e:
        logger.error(f"Changelog generation failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
def create_database_panel(user, server, team, container):
    """
    Creates a refreshable database panel using @ui.refreshable.
    This allows the UI to update properly when the timer fires.
    """
    import logging
    from ..models.database import SyncStatus
    from ..services.background_sync import get_sync_manager
    
    logger = logging.getLogger(__name__)
    
    # Store timer reference
    refresh_timer_holder = {'timer': None}

    # Holder for refreshable components (for selective refresh)
    refresh_holder = {'progress': None, 'database_list': None}

    # Dialog state tracker (pause refresh when dialog is open)
    dialog_state = {'is_open': False}

    # Load filter state from user preferences
    db = get_db()
    try:
        from ..models.user_preference import UserPreference
        pref = db.query(UserPreference).filter(UserPreference.user_id == user.id).first()
        if pref and pref.preferences:
            saved_filter = pref.preferences.get('sync_show_only_active_dbs', False)
        else:
            saved_filter = False  # Default: alle anzeigen
    finally:
        db.close()

    # Filter checkbox state (shared across refreshes)
    show_only_active_dbs = {'value': saved_filter}

    # Refreshable progress box (separate from database list for performance)
    @ui.refreshable
    def progress_box():
        """Show active background documentation generation tasks"""
        if _background_doc_tasks:
            # Show background doc tasks
            for task_id, task in list(_background_doc_tasks.items()):
                status = task.get('status', 'running')
                phase = task.get('phase', 'unknown')
                db_name = task.get('database_name', 'Unknown')
                message = task.get('message', '')
                progress = task.get('progress', '')

                # Determine card color based on status
                if status == 'completed':
                    bg_color = 'bg-green-50 border-green-500'
                    icon_name = 'check_circle'
                    icon_color = 'green'
                elif status == 'failed':
                    bg_color = 'bg-red-50 border-red-500'
                    icon_name = 'error'
                    icon_color = 'red'
                else:
                    bg_color = 'bg-purple-50 border-purple-500'
                    icon_name = 'auto_awesome'
                    icon_color = 'purple'

                with ui.card().classes(f'w-full p-3 {bg_color} border-l-4 mb-2'):
                    with ui.row().classes('w-full items-center justify-between gap-3'):
                        with ui.row().classes('items-center gap-3 flex-1'):
                            if status == 'running':
                                ui.spinner(size='md', color=icon_color)
                            else:
                                ui.icon(icon_name, size='md', color=icon_color)

                            with ui.column().classes('gap-1'):
                                ui.label(f'Dokumentation: {db_name}').classes('text-sm font-bold')
                                ui.label(message).classes('text-xs text-grey-700')
                                if progress and status == 'running':
                                    ui.label(f'Fortschritt: {progress}').classes('text-xs text-grey-600')

                        # Remove button for completed/failed tasks
                        if status in ['completed', 'failed']:
                            def remove_task(tid=task_id):
                                _background_doc_tasks.pop(tid, None)
                                progress_box.refresh()

                            ui.button(
                                icon='close',
                                on_click=remove_task
                            ).props('flat dense round size=sm')

        elif _doc_generating:
            # Fallback: Show old-style doc generating (should not happen anymore)
            db = get_db()
            try:
                with ui.card().classes('w-full p-3 bg-purple-50 border-l-4 border-purple-500 mb-4'):
                    with ui.row().classes('w-full items-center gap-3'):
                        ui.spinner(size='md', color='purple')
                        with ui.column().classes('flex-1'):
                            ui.label('Dokumentation wird generiert:').classes('text-sm font-bold text-purple-900')
                            for db_id, progress in _doc_generating.items():
                                # Find database name
                                db_obj = db.query(Database).filter(Database.id == db_id).first()
                                if db_obj:
                                    current = progress.get('current', 0)
                                    total = progress.get('total', 1)
                                    progress_text = f"{db_obj.name}"
                                    if total > 1:
                                        progress_text += f" (Batch {current}/{total})"
                                    ui.label(progress_text).classes('text-xs text-purple-700')
            finally:
                db.close()

    @ui.refreshable
    def database_list():
        """Refreshable database list - call database_list.refresh() to update"""
        sync_manager = get_sync_manager()
        bulk_sync_active = sync_manager.is_bulk_sync_active(team.id)

        db = get_db()
        try:
            # Load all databases for this team
            all_databases = db.query(Database).filter(
                Database.team_id == team.id
            ).order_by(Database.name).all()

            # Filter based on checkbox
            if show_only_active_dbs['value']:
                databases = [d for d in all_databases if not d.is_excluded]
            else:
                databases = all_databases

            # Check sync status from DB
            syncing_count = sum(1 for d in databases if d.sync_status == SyncStatus.SYNCING.value)
            any_syncing = syncing_count > 0
            total_count = len([d for d in databases if not d.is_excluded])
            completed_count = total_count - syncing_count
            is_busy = bulk_sync_active or any_syncing

            # Auto-load only if NO databases exist in DB at all (not just filtered)
            if not all_databases:
                # Auto-load databases from server if none exist
                auto_load_triggered = {'done': False}  # Flag to prevent loop

                async def auto_load_databases():
                    # Prevent multiple triggers
                    if auto_load_triggered['done']:
                        logger.info(f"Auto-load already triggered for {team.name}, skipping")
                        return

                    auto_load_triggered['done'] = True

                    try:
                        from ..services.ninox_sync_service import get_ninox_sync_service
                        from ..api.ninox_client import NinoxClient
                        from ..utils.encryption import get_encryption_manager

                        logger.info(f"Auto-loading databases from server for team {team.name}...")

                        # Get encryption manager
                        enc = get_encryption_manager()

                        # Get server from database
                        db_conn = get_db()
                        try:
                            server_obj = db_conn.query(Server).filter(Server.id == server.id).first()
                            if server_obj:
                                api_key = enc.decrypt(server_obj.api_key_encrypted)
                                client = NinoxClient(server_obj.url, api_key)

                                # Fetch databases from Ninox
                                databases_data = client.get_databases(team.team_id)

                                # Save to database
                                for db_data in databases_data:
                                    db_id = db_data.get('id') or db_data.get('databaseId')
                                    db_name = db_data.get('name', f'Database {db_id}')

                                    if db_id:
                                        # Check if exists
                                        existing = db_conn.query(Database).filter(
                                            Database.team_id == team.id,
                                            Database.database_id == db_id
                                        ).first()

                                        if not existing:
                                            new_db = Database(
                                                team_id=team.id,
                                                database_id=db_id,
                                                name=db_name,
                                                is_excluded=False  # Default: active (not excluded)
                                            )
                                            db_conn.add(new_db)

                                db_conn.commit()
                                logger.info(f"✓ Loaded {len(databases_data)} databases for {team.name}")

                                ui.notify(f'✓ {len(databases_data)} Datenbanken vom Server geladen!', type='positive')

                                # Refresh UI to show new databases
                                load_databases(user, server, team, container, setup_refresh=False)
                        finally:
                            db_conn.close()

                    except Exception as e:
                        logger.error(f"Error auto-loading databases: {e}")
                        ui.notify(f'Fehler beim Laden: {str(e)}', type='negative')

                EmptyState.render(
                    icon='folder',
                    title='Keine Datenbanken',
                    message='Keine Datenbanken für dieses Team gefunden. Lade automatisch vom Server...',
                    action_label='Datenbanken laden',
                    on_action=lambda: ui.timer(0.1, auto_load_databases, once=True)
                )

                # Auto-trigger loading (only once)
                ui.timer(0.5, auto_load_databases, once=True)
            elif not databases and all_databases:
                # DBs exist but are filtered out
                EmptyState.render(
                    icon='filter_alt',
                    title='Keine Datenbanken sichtbar',
                    message=f'{len(all_databases)} Datenbanken sind ausgeblendet. Deaktivieren Sie den Filter "Nur aktive" oder aktivieren Sie die Datenbanken.',
                    action_label='Filter deaktivieren',
                    on_action=lambda: None  # Filter is already there
                )
            else:
                # Bulk actions header
                with ui.row().classes('w-full items-center justify-between mb-4'):
                    with ui.row().classes('items-center gap-2'):
                        ui.label('Databases').classes('text-h6 font-bold')

                        # Filter checkbox
                        filter_checkbox = ui.checkbox(
                            'Nur aktive',
                            value=show_only_active_dbs['value']
                        ).classes('ml-4')

                        def on_filter_change():
                            show_only_active_dbs['value'] = filter_checkbox.value

                            # Save to user preferences
                            db_pref = get_db()
                            try:
                                from ..models.user_preference import UserPreference
                                pref = db_pref.query(UserPreference).filter(UserPreference.user_id == user.id).first()
                                if pref:
                                    if not pref.preferences:
                                        pref.preferences = {}
                                    pref.preferences['sync_show_only_active_dbs'] = filter_checkbox.value
                                    db_pref.commit()
                            finally:
                                db_pref.close()

                            database_list.refresh()

                        filter_checkbox.on('update:model-value', on_filter_change)

                        # Show count
                        active_count = len([d for d in all_databases if not d.is_excluded])
                        if show_only_active_dbs['value'] and active_count < len(all_databases):
                            ui.label(f'({len(databases)} aktive von {len(all_databases)} gesamt)').classes('text-sm text-grey-7')
                        else:
                            ui.label(f'({len(databases)} gesamt)').classes('text-sm text-grey-7')

                        # Show different indicators for bulk sync vs individual sync
                        if bulk_sync_active:
                            # Bulk sync: show progress counter
                            ui.spinner(size='sm', color='primary')
                            ui.label(f'Bulk sync: {total_count - syncing_count}/{total_count}').classes('text-caption text-primary font-bold')
                        elif any_syncing:
                            # Individual sync: just show how many are syncing
                            ui.spinner(size='sm', color='primary')
                            ui.label(f'{syncing_count} syncing...').classes('text-caption text-primary')

                    # Bulk actions row
                    with ui.row().classes('gap-2'):
                        # Bulk sync button
                        ui.button(
                            'Sync All YAML',
                            icon='description',
                            on_click=lambda: sync_all_yaml(user, server, team, databases, container)
                        ).props(f'color=purple {"disable" if is_busy else ""}').tooltip(
                            'Alle nicht-ausgeschlossenen Datenbanken als YAML synchronisieren'
                        )

                        # Bulk toggle buttons
                        ui.button(
                            'Auto-Doku: Alle An/Aus',
                            icon='auto_awesome',
                            on_click=lambda: toggle_all_auto_docs(user, server, team, database_list)
                        ).props('flat dense color=purple').tooltip('Auto-Doku für alle DBs umschalten')

                        ui.button(
                            'Auto-ERD: Alle An/Aus',
                            icon='account_tree',
                            on_click=lambda: toggle_all_auto_erd(user, server, team, database_list)
                        ).props('flat dense color=blue').tooltip('Auto-ERD für alle DBs umschalten')

                # Database cards - pass bulk_sync_active, not is_busy
                # Each card checks its own sync_status for spinner
                for database in databases:
                    render_database_card(user, server, team, database, container, bulk_sync_active)
                    
        finally:
            db.close()
    
    def check_and_refresh():
        """Timer callback - check if still syncing/generating and refresh (skip if dialog open)"""
        # Skip refresh if any dialog is open (global state)
        if _dialog_open_state['count'] > 0:
            logger.debug(f"Skipping refresh - {_dialog_open_state['count']} dialog(s) open")
            return

        sync_manager = get_sync_manager()
        bulk_active = sync_manager.is_bulk_sync_active(team.id)

        db = get_db()
        try:
            syncing_count = db.query(Database).filter(
                Database.team_id == team.id,
                Database.sync_status == SyncStatus.SYNCING.value
            ).count()
            still_syncing = syncing_count > 0
        finally:
            db.close()

        # Check if any documentation is being generated
        docs_generating = len(_doc_generating) > 0
        background_tasks_active = len(_background_doc_tasks) > 0

        # Check if force refresh is needed
        force = _force_refresh['needed']

        if still_syncing or bulk_active:
            # Syncing - refresh full database list (to update sync status)
            logger.info(f"Auto-refresh: syncing={syncing_count}, bulk={bulk_active}")
            database_list.refresh()
        elif docs_generating or background_tasks_active or force:
            # Doc generation - smart refresh (only when needed)
            logger.info(f"Auto-refresh: docs_gen={len(_doc_generating)}, force={force}")

            # Reset force flag
            if force:
                _force_refresh['needed'] = False

            # Check if any batch count changed
            current_state = {db_id: f"{p.get('current', 0)}/{p.get('total', 1)}" for db_id, p in _doc_generating.items()}
            if not hasattr(check_and_refresh, '_last_doc_state'):
                check_and_refresh._last_doc_state = {}

            state_changed = current_state != check_and_refresh._last_doc_state
            check_and_refresh._last_doc_state = current_state

            # Refresh progress box (always)
            progress_box.refresh()

            # Check if any background task changed status
            background_task_completed = False
            if background_tasks_active:
                for task in _background_doc_tasks.values():
                    if task.get('status') in ['completed', 'failed']:
                        background_task_completed = True
                        break

            # Refresh database list when needed
            if force or state_changed or background_task_completed:
                logger.info(f"Refreshing database list (force={force}, state_changed={state_changed}, bg_completed={background_task_completed})")
                database_list.refresh()
            else:
                logger.debug("No changes - skipping database list refresh")
        else:
            # Nothing active - skip refresh
            logger.debug("Auto-refresh: idle")
    
    # Store refreshable components in holder
    refresh_holder['progress'] = progress_box
    refresh_holder['database_list'] = database_list

    # Render initial components
    with container:
        progress_box()  # Render progress box first (above database list)
        database_list()

        # Setup auto-refresh timer (5s interval - less intrusive when viewing dialogs)
        refresh_timer_holder['timer'] = ui.timer(5.0, check_and_refresh)


def load_databases(user, server, team, container, setup_refresh=True):
    """Load and display databases for a team"""
    container.clear()
    create_database_panel(user, server, team, container)


def render_database_card(user, server, team, database, container, bulk_sync_active=False):
    """Render a database card with sync status indicator"""
    from ..models.database import SyncStatus
    
    # Check current sync status
    is_syncing = database.sync_status == SyncStatus.SYNCING.value
    has_error = database.sync_status == SyncStatus.ERROR.value
    
    # Disable individual sync during bulk sync
    sync_disabled = bulk_sync_active or is_syncing
    
    with ui.card().classes('w-full p-4') as card:
        # Store card reference for refresh
        card._database_id = database.id
        
        with ui.row().classes('w-full items-start justify-between'):
            # Database info
            with ui.column().classes('flex-1 gap-2'):
                with ui.row().classes('items-center gap-2'):
                    # Show spinner if syncing, otherwise folder icon
                    if is_syncing:
                        ui.spinner(size='sm', color='primary').classes('sync-spinner')
                    else:
                        ui.icon('folder', size='md').classes('text-primary')
                    
                    ui.label(database.name).classes('text-h6 font-bold')

                    # Show status badges
                    is_generating_docs = database.id in _doc_generating
                    doc_progress = _doc_generating.get(database.id, {})

                    if database.is_excluded:
                        ui.badge('Excluded', color='warning')
                    elif is_syncing:
                        ui.badge('Syncing...', color='primary').props('outline')
                    elif is_generating_docs:
                        with ui.row().classes('items-center gap-1'):
                            ui.spinner(size='xs', color='purple')
                            progress_text = 'Generiert Doku...'
                            if doc_progress.get('total', 0) > 1:
                                # Show batch progress
                                current = doc_progress.get('current', 0)
                                total = doc_progress.get('total', 1)
                                progress_text = f'Doku Batch {current}/{total}'
                            ui.badge(progress_text, color='purple').props('outline')
                    elif has_error:
                        ui.badge('Error', color='negative')

                # Database ID and Server/Team info
                with ui.row().classes('items-center gap-2 flex-wrap'):
                    ui.label(f'ID: {database.database_id}').classes('text-grey-7 text-sm')
                    ui.label('•').classes('text-grey-5 text-sm')
                    ui.chip(f'{server.name}').props('dense outline color=grey-7').classes('text-xs')
                    ui.chip(f'{team.name}').props('dense outline color=grey-7').classes('text-xs')

                if database.github_path:
                    with ui.row().classes('items-center gap-2'):
                        ui.icon('github', size='sm').classes('text-grey-7')
                        ui.label(f'GitHub Path: {database.github_path}').classes('text-grey-7')

                if database.last_modified:
                    ui.label(f'Last Modified: {format_datetime(database.last_modified)}').classes(
                        'text-grey-7'
                    )

                # Auto-generate ERD and docs checkboxes
                def toggle_auto_erd(db_id, value):
                    db_conn = get_db()
                    try:
                        db_obj = db_conn.query(Database).filter(Database.id == db_id).first()
                        if db_obj:
                            db_obj.auto_generate_erd = value
                            db_conn.commit()
                    finally:
                        db_conn.close()

                def toggle_auto_docs(db_id, value):
                    db_conn = get_db()
                    try:
                        db_obj = db_conn.query(Database).filter(Database.id == db_id).first()
                        if db_obj:
                            db_obj.auto_generate_docs = value
                            db_conn.commit()
                    finally:
                        db_conn.close()

                with ui.row().classes('items-center gap-4 mt-1 flex-wrap'):
                    # Auto-ERD checkbox
                    with ui.row().classes('items-center gap-2'):
                        ui.icon('account_tree', size='xs').classes('text-blue')
                        auto_erd_cb = ui.checkbox(
                            'Auto-ERD',
                            value=database.auto_generate_erd if hasattr(database, 'auto_generate_erd') else True
                        ).classes('text-xs')
                        auto_erd_cb.on('update:model-value', lambda e, db_id=database.id: toggle_auto_erd(db_id, auto_erd_cb.value))
                        auto_erd_cb.tooltip('Automatische ERD-Generierung beim Sync (kostenlos)')

                    # Auto-Doku checkbox
                    with ui.row().classes('items-center gap-2'):
                        ui.icon('auto_awesome', size='xs').classes('text-purple')
                        auto_docs_cb = ui.checkbox(
                            'Auto-Doku (AI)',
                            value=database.auto_generate_docs
                        ).classes('text-xs')
                        auto_docs_cb.on('update:model-value', lambda e, db_id=database.id: toggle_auto_docs(db_id, auto_docs_cb.value))
                        auto_docs_cb.tooltip('Automatische AI-Dokumentation beim Sync generieren')

                # Show status: Sync, Documentation, BookStack
                with ui.column().classes('gap-1 mt-1'):
                    # Show last YAML sync
                    if database.last_modified:
                        with ui.row().classes('items-center gap-1'):
                            ui.icon('sync', size='xs').classes('text-blue')
                            ui.label(f'Sync: {format_datetime(database.last_modified)}').classes('text-xs text-grey-7')

                    # Show last documentation generation
                    latest_doc = database.latest_documentation if hasattr(database, 'latest_documentation') else None
                    if latest_doc and hasattr(latest_doc, 'generated_at') and latest_doc.generated_at:
                        with ui.row().classes('items-center gap-1'):
                            ui.icon('description', size='xs').classes('text-purple')
                            ui.label(f'Doku generiert: {format_datetime(latest_doc.generated_at)}').classes('text-xs text-grey-7')

                    # Show last BookStack sync
                    if hasattr(database, 'last_bookstack_sync') and database.last_bookstack_sync:
                        with ui.row().classes('items-center gap-1'):
                            ui.icon('cloud_done', size='xs').classes('text-green')
                            ui.label(f'BookStack: {format_datetime(database.last_bookstack_sync)}').classes('text-xs text-grey-7')

                # Show error message if sync failed
                if has_error and database.sync_error:
                    with ui.row().classes('items-center gap-1'):
                        ui.icon('error', size='xs', color='negative')
                        ui.label(database.sync_error[:100]).classes('text-caption text-negative')

            # Actions
            with ui.column().classes('gap-2'):
                # Einzelne Sync-Buttons entfernt - nur "Sync All YAML" wird verwendet
                # Grund: Alle DBs sind verknüpft, einzelnes Syncen führt zu Inkonsistenzen

                # YAML-based action buttons (always available after YAML sync)
                if not database.is_excluded:
                    with ui.row().classes('gap-1'):
                        # View ERD button - opens YAML-based ERD dialog
                        ui.button(
                            'View ERD',
                            icon='account_tree',
                            on_click=lambda d=database: show_yaml_erd_from_sync(d)
                        ).props('flat dense color=secondary').tooltip('Entity Relationship Diagram')

                        # Timeline button - shows YAML/Git change history
                        ui.button(
                            'Timeline',
                            icon='timeline',
                            on_click=lambda d=database: show_yaml_timeline_from_sync(d)
                        ).props('flat dense color=info').tooltip('Git Änderungshistorie')

                        # Generate Documentation button - triggers AI doc generation
                        is_generating = database.id in _doc_generating
                        gen_btn = ui.button(
                            'Generiert...' if is_generating else 'GEN DOKU',
                            icon='hourglass_empty' if is_generating else 'auto_awesome',
                            on_click=lambda d=database: generate_documentation_for_database(d, user, server, team, container)
                        ).props(f'flat dense color=purple {"loading" if is_generating else ""}')
                        gen_btn.tooltip('Dokumentation wird generiert...' if is_generating else 'Dokumentation mit AI generieren (im Hintergrund)')

                        # View Documentation button - shows the generated APPLICATION_DOCS.md
                        ui.button(
                            'VIEW DOKU',
                            icon='description',
                            on_click=lambda d=database: show_documentation_viewer(d, user, server)
                        ).props('flat dense color=deep-purple').tooltip('Dokumentation anzeigen')

                        # BookStack sync button - transfer docs to BookStack
                        has_bookstack = database.bookstack_book_id is not None if hasattr(database, 'bookstack_book_id') else False
                        ui.button(
                            '→ BOOKSTACK',
                            icon='cloud_upload' if not has_bookstack else 'cloud_done',
                            on_click=lambda d=database: sync_to_bookstack(d, user, server, team)
                        ).props(f'flat dense color={"purple" if not has_bookstack else "green"}').tooltip(
                            'Zu BookStack übertragen' if not has_bookstack else 'In BookStack aktualisieren'
                        )

                        # VIEW CODE button - navigates to YAML Code Viewer
                        ui.button(
                            'VIEW CODE',
                            icon='code',
                            on_click=lambda: ui.navigate.to('/yaml-code-viewer')
                        ).props('flat dense color=blue').tooltip('YAML Code durchsuchen')

                        # GitHub link to repository - using new clear name structure
                        from ..utils.github_utils import sanitize_name
                        github_repo_name = get_repo_name_from_server(server)
                        github_path = f"{sanitize_name(database.team.name)}/{sanitize_name(database.name)}"
                        github_url = f'https://github.com/{user.github_organization}/{github_repo_name}/tree/main/{github_path}'
                        ui.button(
                            'GITHUB',
                            icon='open_in_new',
                            on_click=lambda url=github_url: ui.navigate.to(url, new_tab=True)
                        ).props('flat dense')

                if database.is_excluded:
                    # Include with dependencies (smart button)
                    ui.button(
                        'Include + Abhängigkeiten',
                        icon='link',
                        on_click=lambda d=database: include_with_dependencies(
                            user, server, team, d, container
                        )
                    ).props('flat dense color=positive').tooltip('Datenbank mit allen Abhängigkeiten aktivieren')

                    # Simple include (without dependencies)
                    ui.button(
                        'Nur Include',
                        icon='add_circle',
                        on_click=lambda d=database: toggle_database_exclusion(
                            user, d, False, container
                        )
                    ).props('flat dense outline color=positive').tooltip('Nur diese Datenbank aktivieren')
                else:
                    # Exclude with dependents (smart button)
                    ui.button(
                        'Exclude + Abhängige',
                        icon='link_off',
                        on_click=lambda d=database: exclude_with_dependents(
                            user, server, team, d, container
                        )
                    ).props('flat dense color=warning').tooltip('Datenbank mit allen abhängigen DBs deaktivieren')

                    # Simple exclude (without dependents)
                    ui.button(
                        'Nur Exclude',
                        icon='block',
                        on_click=lambda d=database: toggle_database_exclusion(
                            user, d, True, container
                        )
                    ).props('flat dense outline color=warning').tooltip('Nur diese Datenbank deaktivieren')


def open_yaml_code_viewer_for_database(database: Database):
    """Open YAML Code Viewer filtered to specific database"""
    ui.open(f'/yaml-code-viewer?db={database.database_id}')


def show_documentation_viewer(database, user, server):
    """Show documentation viewer dialog with APPLICATION_DOCS.md content"""
    from ..utils.path_resolver import get_database_path
    from ..utils.github_utils import sanitize_name
    import logging
    logger = logging.getLogger(__name__)
    db_path = get_database_path(server, database.team, database.name)
    docs_file = db_path / "APPLICATION_DOCS.md"
    with ui.dialog() as dialog, ui.card().classes("w-full").style("max-width: 1200px; max-height: 90vh;"):
        with ui.row().classes("w-full items-center justify-between p-4 bg-purple text-white"):
            with ui.column().classes("gap-0"):
                ui.label(f"Dokumentation: {database.name}").classes("text-h5 font-bold")
                ui.label(f"{server.name} / {database.team.name}").classes("text-sm opacity-80")
            ui.button(icon="close", on_click=dialog.close).props("flat color=white round")
        with ui.column().classes("w-full p-4").style("max-height: 75vh; overflow-y: auto;"):
            if docs_file.exists():
                try:
                    with open(docs_file, "r", encoding="utf-8") as f:
                        markdown_content = f.read()
                    ui.markdown(markdown_content).classes("w-full")
                except Exception as e:
                    ui.label(f"Fehler: {str(e)}").classes("text-negative")
            else:
                with ui.column().classes("items-center gap-4 p-8"):
                    ui.icon("description", size="64px", color="grey")
                    ui.label("Keine Dokumentation vorhanden").classes("text-h6 text-grey-7")
    dialog.open()


def show_yaml_erd_from_sync(database: Database):
    """Show ERD dialog for YAML database from sync page"""
    from ..utils.ninox_yaml_parser import NinoxYAMLParser
    from ..services.ninox_cli_service import get_ninox_cli_service
    # Removed: convert_yaml_to_json_structure (no longer needed)
    from ..utils.svg_erd_generator import generate_svg_erd

    # Mark dialog as open (prevents auto-refresh)
    _dialog_open_state['count'] += 1

    def on_dialog_close():
        _dialog_open_state['count'] -= 1
        dialog.close()

    with ui.dialog() as dialog, ui.card().classes('w-full').style('max-width: 95vw; max-height: 95vh;'):
        with ui.row().classes('w-full items-center justify-between mb-4'):
            with ui.column().classes('gap-0'):
                ui.label(f'ERD: {database.name}').classes('text-h5 font-bold')
                ui.label(f'Database: {database.database_id}').classes('text-grey-7')
            ui.button(icon='close', on_click=on_dialog_close).props('flat round dense')

        erd_container = ui.column().classes('w-full').style('height: 80vh; overflow: hidden;')

        with erd_container:
            status_label = ui.label('Loading YAML database...').classes('text-h6')
            ui.spinner('dots', size='lg')

        dialog.open()
        
        async def load_erd():
            try:
                import logging
                from ..utils.path_resolver import get_team_path, get_database_path
                from ..models.server import Server
                from ..models.team import Team

                logger = logging.getLogger(__name__)

                # Load server in new session (database object might be detached)
                db = get_db()
                try:
                    team = db.query(Team).filter(Team.id == database.team.id).first()
                    server = db.query(Server).filter(Server.id == team.server_id).first()
                finally:
                    db.close()

                # Use database path with clear names
                cli_service = get_ninox_cli_service()
                db_path = get_database_path(server, database.team, database.name)

                # Check if pre-generated ERD exists (on database root level)
                erd_file = db_path / 'erd.svg'

                if erd_file.exists():
                    # Load pre-generated ERD (instant!)
                    status_label.text = 'Lade gespeichertes ERD...'
                    with open(erd_file, 'r', encoding='utf-8') as f:
                        svg_content = f.read()
                    logger.info(f"✓ Loaded pre-generated ERD from {erd_file}")
                else:
                    # Generate on-the-fly (fallback)
                    logger.info(f"Pre-generated ERD not found, generating now...")
                    parser = NinoxYAMLParser(str(db_path))

                    status_label.text = 'Finding database...'
                    databases = parser.get_all_databases()

                    if not databases:
                        raise Exception(
                            f"Database not found.\n"
                            f"Database: {database.name}\n"
                            f"Path: {db_path}\n"
                            f"Bitte synchronisieren Sie die Datenbank zuerst mit 'Sync All YAML'."
                        )

                    yaml_db = databases[0]

                    status_label.text = 'Generating diagram...'
                    svg_content = generate_svg_erd(yaml_db)
                
                if not svg_content or '<svg' not in svg_content:
                    raise Exception("SVG generation failed")
                
                erd_container.clear()
                
                with erd_container:
                    with ui.row().classes('w-full items-center gap-2 mb-2'):
                        ui.label('Zoom:').classes('text-sm')
                        ui.button('-', on_click=lambda: zoom_svg(-0.1)).props('dense flat')
                        ui.button('+', on_click=lambda: zoom_svg(0.1)).props('dense flat')
                        ui.button('Reset', on_click=lambda: reset_svg()).props('dense flat')
                    
                    svg_viewer = ui.html('', sanitize=False).classes('w-full').style('height: 70vh; overflow: auto; border: 1px solid #ccc; background: white;')
                    svg_html = f'<div id="svg-wrapper" style="transform: scale(1); transform-origin: top left; transition: transform 0.2s;">{svg_content}</div>'
                    svg_viewer.content = svg_html
                    
                    # Add mouse wheel zoom functionality
                    ui.run_javascript('''
                        const svgViewer = document.querySelector('.q-page');
                        if (svgViewer) {
                            svgViewer.addEventListener('wheel', function(e) {
                                // Check if Cmd (Mac) or Ctrl (Windows/Linux) is pressed
                                if (e.metaKey || e.ctrlKey) {
                                    e.preventDefault();
                                    
                                    const wrapper = document.getElementById('svg-wrapper');
                                    if (!wrapper) return;
                                    
                                    const currentScale = parseFloat(wrapper.style.transform.match(/scale\\(([^)]+)\\)/)?.[1] || 1);
                                    
                                    // Determine zoom direction (negative deltaY = zoom in)
                                    const delta = e.deltaY > 0 ? -0.1 : 0.1;
                                    const newScale = Math.max(0.1, Math.min(5, currentScale + delta));
                                    
                                    wrapper.style.transform = `scale(${newScale})`;
                                }
                            }, { passive: false });
                        }
                    ''')
                    
                    def zoom_svg(delta):
                        ui.run_javascript(f'''
                            const wrapper = document.getElementById('svg-wrapper');
                            const currentScale = parseFloat(wrapper.style.transform.match(/scale\\(([^)]+)\\)/)?.[1] || 1);
                            const newScale = Math.max(0.1, Math.min(5, currentScale + {delta}));
                            wrapper.style.transform = `scale(${{newScale}})`;
                        ''')
                    
                    def reset_svg():
                        ui.run_javascript('document.getElementById("svg-wrapper").style.transform = "scale(1)";')
                    
                    # Add keyboard shortcuts for zoom
                    ui.keyboard(on_key=lambda e: zoom_svg(0.1) if e.key == '+' or e.key == '=' else 
                                                  zoom_svg(-0.1) if e.key == '-' else 
                                                  reset_svg() if e.key == '0' else None)
                
                ui.notify('ERD generiert - Zoom: Cmd/Ctrl+Mausrad, +/- oder 0', type='positive')
                
            except Exception as e:
                import traceback
                logger = logging.getLogger(__name__)
                logger.error(f"ERD error: {e}\n{traceback.format_exc()}")
                
                erd_container.clear()
                with erd_container:
                    ui.icon('error', size='64px', color='negative')
                    ui.label('Error Generating ERD').classes('text-h6 text-negative')
                    ui.label(str(e)).classes('text-grey-7')
                ui.notify(f'Error: {e}', type='negative')
        
        ui.timer(0.1, load_erd, once=True)


def show_yaml_timeline_from_sync(database: Database):
    """Show Git timeline for YAML database"""
    from ..services.ninox_cli_service import get_ninox_cli_service
    from ..services.ninox_sync_service import get_git_log, get_commit_diff
    
    with ui.dialog() as dialog, ui.card().classes('w-full p-0').style('max-width: 900px; max-height: 90vh;'):
        with ui.row().classes('w-full items-center justify-between p-4 bg-purple'):
            with ui.row().classes('items-center gap-3'):
                ui.icon('timeline', size='md', color='white')
                ui.label(f'Timeline: {database.name}').classes('text-h5 font-bold text-white')
            ui.button(icon='close', on_click=dialog.close).props('flat round dense color=white')
        
        timeline_container = ui.scroll_area().classes('w-full').style('height: calc(90vh - 80px);')
        
        with timeline_container:
            status_label = ui.label('Loading...').classes('text-h6 p-4')
            ui.spinner('dots', size='lg').classes('mx-4')
        
        dialog.open()
        
        async def load_timeline():
            try:
                import logging
                logger = logging.getLogger(__name__)
                
                # Use team-specific path
                cli_service = get_ninox_cli_service()
                team_path = cli_service.project_path / f'team_{database.team.team_id}'
                commits = get_git_log(team_path, database.database_id, limit=50)
                
                if not commits:
                    timeline_container.clear()
                    with timeline_container:
                        ui.icon('history', size='4rem', color='grey')
                        ui.label('No Git history').classes('text-h6 text-grey-7')
                        ui.label('Run YAML sync to build history.').classes('text-grey-6')
                    return
                
                timeline_container.clear()
                
                with timeline_container:
                    with ui.column().classes('w-full p-4 gap-4'):
                        with ui.card().classes('w-full p-4 bg-purple-50'):
                            ui.label(f'{len(commits)} Commits').classes('text-h5 font-bold text-purple')
                        
                        ui.separator()
                        ui.label('Change History').classes('text-h6 font-bold')
                        
                        for i, commit in enumerate(commits):
                            with ui.card().classes('w-full p-3 mb-2'):
                                ui.label(commit['message']).classes('font-bold')
                                ui.label(f"{commit['author']} • {commit['sha'][:8]}").classes('text-xs text-grey-7')
                                if commit['date']:
                                    ui.label(commit['date'].strftime('%d.%m.%Y %H:%M')).classes('text-xs text-grey-7')
                
                ui.notify(f'{len(commits)} commits loaded', type='positive')
                
            except Exception as e:
                logger = logging.getLogger(__name__)
                logger.error(f"Timeline error: {e}")
                timeline_container.clear()
                with timeline_container:
                    ui.label('Error loading timeline').classes('text-negative')
                ui.notify(f'Error: {e}', type='negative')
        
        ui.timer(0.1, load_timeline, once=True)


def show_yaml_documentation_dialog(database: Database):
    """Generate and show documentation from YAML database"""
    from ..utils.ninox_yaml_parser import NinoxYAMLParser
    from ..services.ninox_cli_service import get_ninox_cli_service
    from ..services.doc_generator import DocumentationGenerator
    from ..database import get_db
    from ..models.ai_config import AIConfig
    from ..utils.encryption import get_encryption_manager
    
    with ui.dialog() as dialog, ui.card().classes('w-full').style('max-width: 1200px; max-height: 90vh;'):
        with ui.row().classes('w-full items-center justify-between mb-4 p-4'):
            ui.label(f'Dokumentation: {database.name}').classes('text-h5 font-bold')
            ui.button(icon='close', on_click=dialog.close).props('flat round dense')
        
        doc_container = ui.column().classes('w-full p-4').style('max-height: 80vh; overflow-y: auto;')
        
        with doc_container:
            status_label = ui.label('Lade YAML-Datenbank...').classes('text-h6')
            progress = ui.spinner('dots', size='lg')
        
        dialog.open()
        
        async def generate_docs():
            try:
                import logging
                logger = logging.getLogger(__name__)
                
                # Load YAML database from team-specific path
                cli_service = get_ninox_cli_service()
                team_path = cli_service.project_path / f'team_{database.team.team_id}'
                parser = NinoxYAMLParser(str(team_path))
                
                status_label.text = 'Suche Datenbank in YAML-Dateien...'
                databases = parser.get_all_databases()
                
                yaml_db = None
                for db in databases:
                    if db.database_id == database.database_id:
                        yaml_db = db
                        break
                
                if not yaml_db:
                    raise Exception(f"Datenbank {database.database_id} nicht in YAML gefunden. Bitte zuerst YAML-Sync durchführen.")
                
                # Build simplified structure directly from YAML (NO JSON!)
                status_label.text = 'Erstelle Struktur-Übersicht aus YAML...'
                
                def build_yaml_summary(yaml_db):
                    """Build simplified structure summary from YAML database (optimized for AI)"""
                    summary = {
                        'name': yaml_db.name,
                        'database_id': yaml_db.database_id,
                        'table_count': yaml_db.table_count,
                        'code_count': yaml_db.code_count,
                        'tables': []
                    }
                    
                    # Build table ID mapping first (for resolving references)
                    table_id_to_name = {}
                    for table_name, table_data in yaml_db.tables.items():
                        table_id = table_data.get('typeId', table_name)
                        table_caption = table_data.get('caption', table_name)
                        table_id_to_name[table_id] = table_caption
                    
                    # Add ALL table summaries with ALL fields for comprehensive documentation
                    for table_name, table_data in yaml_db.tables.items():
                        table_summary = {
                            'id': table_data.get('typeId', table_name),  # Include table ID for reference resolution
                            'name': table_data.get('caption', table_name),
                            'field_count': len(table_data.get('fields', {})),
                            'fields': []
                        }
                        
                        # Include ALL fields for comprehensive documentation
                        all_fields = list(table_data.get('fields', {}).items())
                        
                        # Add ALL field summaries
                        for field_id, field_data in all_fields:
                            field_type = field_data.get('base', 'unknown')
                            field_name = field_data.get('caption', field_id)
                            
                            # Field structure with name, type, and description hint
                            field_summary = {
                                'n': field_name, 
                                't': field_type
                            }
                            
                            # Add ref target for relationship mapping - resolve to table name
                            if field_type == 'ref':
                                ref_id = field_data.get('refTypeId', '')
                                if ref_id:
                                    # Resolve reference ID to table name
                                    ref_name = table_id_to_name.get(ref_id, ref_id)
                                    field_summary['r'] = ref_name
                            
                            # Add formula hint if present (for understanding calculated fields)
                            if field_type == 'formula' and field_data.get('formula'):
                                # Just indicate it's a formula, don't include the code
                                field_summary['f'] = True
                            
                            table_summary['fields'].append(field_summary)
                        
                        summary['tables'].append(table_summary)
                    
                    return summary
                
                yaml_summary = build_yaml_summary(yaml_db)
                
                # Get AI config
                status_label.text = 'Prüfe AI-Konfiguration...'
                db_session = get_db()
                try:
                    ai_config = db_session.query(AIConfig).filter(
                        AIConfig.provider == 'gemini',
                        AIConfig.is_active == True
                    ).first()
                    
                    if not ai_config or not ai_config.api_key_encrypted:
                        raise Exception("Keine aktive Gemini-Konfiguration gefunden. Bitte im Admin-Panel konfigurieren.")
                    
                    # Decrypt API key
                    encryption = get_encryption_manager()
                    api_key = encryption.decrypt(ai_config.api_key_encrypted)
                    
                    if not api_key:
                        raise Exception("API-Key konnte nicht entschlüsselt werden.")
                    
                finally:
                    db_session.close()
                
                # Generate documentation (in executor to avoid timeout)
                status_label.text = 'Generiere Dokumentation mit Gemini AI (kann 30-60s dauern)...'
                
                # Create progress indicator
                progress.set_visibility(True)
                
                # Run in executor to avoid blocking
                import asyncio
                loop = asyncio.get_event_loop()
                
                def generate_in_thread():
                    # Use YAML summary instead of JSON structure!
                    doc_gen = DocumentationGenerator(
                        api_key=api_key,
                        model=ai_config.model,
                        max_tokens=ai_config.max_tokens,
                        temperature=ai_config.temperature
                    )
                    return doc_gen.generate(yaml_summary, yaml_db.name)
                
                result = await loop.run_in_executor(None, generate_in_thread)
                
                if not result.success:
                    raise Exception(result.error or "Dokumentationsgenerierung fehlgeschlagen")
                
                # Display documentation
                doc_container.clear()
                
                with doc_container:
                    # Header with stats
                    with ui.row().classes('w-full justify-between items-center mb-4 p-4 bg-purple-50 rounded'):
                        with ui.column().classes('gap-1'):
                            ui.label('Dokumentation erfolgreich generiert').classes('font-bold text-purple')
                            if result.input_tokens and result.output_tokens:
                                ui.label(f'Tokens: {result.input_tokens} Input, {result.output_tokens} Output').classes('text-xs text-grey-7')
                        
                        ui.button(
                            'Als Markdown speichern',
                            icon='download',
                            on_click=lambda: download_markdown(result.content, yaml_db.name)
                        ).props('flat color=purple')
                    
                    # Render markdown
                    ui.markdown(result.content).classes('w-full')
                
                def download_markdown(content, db_name):
                    import base64
                    b64 = base64.b64encode(content.encode()).decode()
                    filename = f"{db_name.replace(' ', '_')}_dokumentation.md"
                    ui.run_javascript(f'''
                        const link = document.createElement('a');
                        link.href = 'data:text/markdown;base64,{b64}';
                        link.download = '{filename}';
                        link.click();
                    ''')
                
                logger.info(f"Documentation generated: {len(result.content)} chars")
                ui.notify('Dokumentation generiert', type='positive')
                
            except Exception as e:
                import traceback
                logger = logging.getLogger(__name__)
                logger.error(f"Documentation error: {e}\n{traceback.format_exc()}")
                
                doc_container.clear()
                with doc_container:
                    ui.icon('error', size='64px', color='negative')
                    ui.label('Fehler bei der Dokumentationsgenerierung').classes('text-h6 text-negative')
                    ui.label(str(e)).classes('text-grey-7')
                    
                    if 'Gemini' in str(e) or 'AI' in str(e):
                        ui.label('Tipp: Prüfen Sie die Gemini-Konfiguration im Admin-Panel.').classes('text-sm text-grey-6 mt-2')
                
                ui.notify(f'Fehler: {e}', type='negative')
        
        ui.timer(0.1, generate_docs, once=True)
    dialog.open()


def include_with_dependencies(user, server, team, database, container):
    """Show dialog to include database with all its dependencies"""
    import logging
    from ..models.database_dependency import DatabaseDependency

    logger = logging.getLogger(__name__)

    # Create dialog
    with ui.dialog() as dialog, ui.card().classes('w-full max-w-2xl'):
        with ui.column().classes('w-full gap-4 p-4'):
            # Header
            with ui.row().classes('w-full items-center gap-3 mb-2'):
                ui.icon('link', size='md', color='primary')
                ui.label(f'Include "{database.name}" mit Abhängigkeiten').classes('text-h6 font-bold')

            ui.separator()

            # Status
            status_label = ui.label('Lade Abhängigkeiten...').classes('text-sm text-grey-7')
            progress = ui.spinner('dots', size='md')

            # Results container
            results_container = ui.column().classes('w-full gap-2 mt-4')

    dialog.open()

    async def scan_and_show():
        """Load dependencies from database (fast!)"""
        try:
            # Get dependencies from database (no YAML scanning needed!)
            db = get_db()
            try:
                deps = db.query(DatabaseDependency).filter(
                    DatabaseDependency.source_database_id == database.id
                ).all()

                dependency_ids = {d.target_ninox_id for d in deps}
                logger.info(f"Loaded {len(dependency_ids)} dependencies from DB for {database.name}")
            finally:
                db.close()

            dependencies = dependency_ids

            # Get database objects
            db = get_db()
            try:
                dep_databases = []
                for dep_id in dependencies:
                    dep_db = db.query(Database).filter(
                        Database.team_id == team.id,
                        Database.database_id == dep_id
                    ).first()
                    if dep_db:
                        dep_databases.append(dep_db)

                # Update UI
                progress.visible = False

                if dependencies:
                    status_label.text = f'{len(dependencies)} Abhängigkeiten gefunden:'

                    with results_container:
                        ui.label('Diese Datenbanken werden auch aktiviert:').classes('text-sm font-medium mb-2')

                        for dep_db in dep_databases:
                            with ui.row().classes('items-center gap-2'):
                                status_icon = '🔒' if dep_db.is_excluded else '✅'
                                ui.label(f'{status_icon} {dep_db.name}').classes('text-sm')
                                if dep_db.is_excluded:
                                    ui.badge('wird aktiviert', color='positive')
                                else:
                                    ui.badge('bereits aktiv', color='grey')

                        ui.separator().classes('my-4')

                        # Buttons
                        with ui.row().classes('w-full justify-end gap-2'):
                            ui.button('Abbrechen', on_click=dialog.close).props('flat')
                            ui.button(
                                f'Alle aktivieren ({len(dependencies) + 1} DBs)',
                                icon='check_circle',
                                on_click=lambda: do_include_all(database, dep_databases, dialog)
                            ).props('color=positive')
                else:
                    status_label.text = 'Keine Abhängigkeiten gefunden'
                    with results_container:
                        ui.label('Diese Datenbank hat keine Verknüpfungen zu anderen DBs.').classes('text-sm text-grey-7')

                        with ui.row().classes('w-full justify-end gap-2 mt-4'):
                            ui.button('Abbrechen', on_click=dialog.close).props('flat')
                            ui.button(
                                'Nur diese aktivieren',
                                icon='check',
                                on_click=lambda: do_include_all(database, [], dialog)
                            ).props('color=primary')

            finally:
                db.close()

        except Exception as e:
            logger.error(f"Error scanning dependencies: {e}")
            progress.visible = False
            status_label.text = f'Fehler beim Scannen: {str(e)}'
            status_label.classes('text-negative')

    def do_include_all(main_db, dep_dbs, dlg):
        """Include main database and all dependencies"""
        db = get_db()
        try:
            # Include main database
            db_obj = db.query(Database).filter(Database.id == main_db.id).first()
            db_obj.is_excluded = False

            # Include all dependencies
            for dep_db in dep_dbs:
                if dep_db.is_excluded:
                    dep_db_obj = db.query(Database).filter(Database.id == dep_db.id).first()
                    dep_db_obj.is_excluded = False

            db.commit()

            # Audit log
            details = f'Included database: {main_db.name}'
            if dep_dbs:
                dep_names = [d.name for d in dep_dbs if d.is_excluded]
                if dep_names:
                    details += f' (with {len(dep_names)} dependencies: {", ".join(dep_names)})'

            create_audit_log(
                db=db,
                user_id=user.id,
                action='database_included',
                resource_type='database',
                resource_id=main_db.id,
                details=details,
                auto_commit=True
            )

            ui.notify(f'✅ {len(dep_dbs) + 1} Datenbanken aktiviert!', type='positive')

        finally:
            db.close()

        dlg.close()
        load_databases(user, server, team, container)

    # Start async scan
    ui.timer(0.1, scan_and_show, once=True)


def exclude_with_dependents(user, server, team, database, container):
    """Show dialog to exclude database with all databases that depend on it"""
    import logging
    from ..models.database_dependency import DatabaseDependency

    logger = logging.getLogger(__name__)

    # Create dialog
    with ui.dialog() as dialog, ui.card().classes('w-full max-w-2xl'):
        with ui.column().classes('w-full gap-4 p-4'):
            # Header
            with ui.row().classes('w-full items-center gap-3 mb-2'):
                ui.icon('block', size='md', color='warning')
                ui.label(f'Exclude "{database.name}" mit abhängigen DBs').classes('text-h6 font-bold')

            ui.separator()

            # Status
            status_label = ui.label('Lade abhängige Datenbanken...').classes('text-sm text-grey-7')
            progress = ui.spinner('dots', size='md')

            # Results container
            results_container = ui.column().classes('w-full gap-2 mt-4')

    dialog.open()

    async def scan_and_show():
        """Load dependents from database (fast!)"""
        try:
            # Get dependents from database (reverse lookup - what depends on THIS database)
            db = get_db()
            try:
                deps = db.query(DatabaseDependency).filter(
                    DatabaseDependency.target_database_id == database.id
                ).all()

                dependent_ids = {d.source_ninox_id for d in deps}
                logger.info(f"Loaded {len(dependent_ids)} dependents from DB for {database.name}")

                # Recursively find dependents of dependents
                all_dependent_ids = dependent_ids.copy()
                to_process = list(dependent_ids)

                while to_process:
                    current_id = to_process.pop()
                    current_db = db.query(Database).filter(
                        Database.team_id == team.id,
                        Database.database_id == current_id
                    ).first()

                    if current_db:
                        # Find what depends on current_db
                        sub_deps = db.query(DatabaseDependency).filter(
                            DatabaseDependency.target_database_id == current_db.id
                        ).all()

                        for sub_dep in sub_deps:
                            if sub_dep.source_ninox_id not in all_dependent_ids:
                                all_dependent_ids.add(sub_dep.source_ninox_id)
                                to_process.append(sub_dep.source_ninox_id)

            finally:
                db.close()

            dependents = all_dependent_ids

            # Get database objects
            db = get_db()
            try:
                dep_databases = []
                for dep_id in dependents:
                    dep_db = db.query(Database).filter(
                        Database.team_id == team.id,
                        Database.database_id == dep_id
                    ).first()
                    if dep_db:
                        dep_databases.append(dep_db)

                # Update UI
                progress.visible = False

                if dependents:
                    status_label.text = f'{len(dependents)} abhängige Datenbanken gefunden:'

                    with results_container:
                        ui.label('Diese Datenbanken hängen von dieser DB ab und werden auch deaktiviert:').classes('text-sm font-medium mb-2 text-warning')

                        for dep_db in dep_databases:
                            with ui.row().classes('items-center gap-2'):
                                status_icon = '✅' if not dep_db.is_excluded else '🔒'
                                ui.label(f'{status_icon} {dep_db.name}').classes('text-sm')
                                if not dep_db.is_excluded:
                                    ui.badge('wird deaktiviert', color='warning')
                                else:
                                    ui.badge('bereits inaktiv', color='grey')

                        ui.separator().classes('my-4')

                        # Buttons
                        with ui.row().classes('w-full justify-end gap-2'):
                            ui.button('Abbrechen', on_click=dialog.close).props('flat')
                            ui.button(
                                f'Alle deaktivieren ({len(dependents) + 1} DBs)',
                                icon='block',
                                on_click=lambda: do_exclude_all(database, dep_databases, dialog)
                            ).props('color=warning')
                else:
                    status_label.text = 'Keine abhängigen Datenbanken gefunden'
                    with results_container:
                        ui.label('Keine anderen DBs hängen von dieser ab.').classes('text-sm text-grey-7')

                        with ui.row().classes('w-full justify-end gap-2 mt-4'):
                            ui.button('Abbrechen', on_click=dialog.close).props('flat')
                            ui.button(
                                'Nur diese deaktivieren',
                                icon='block',
                                on_click=lambda: do_exclude_all(database, [], dialog)
                            ).props('color=warning')

            finally:
                db.close()

        except Exception as e:
            logger.error(f"Error scanning dependents: {e}")
            progress.visible = False
            status_label.text = f'Fehler beim Scannen: {str(e)}'
            status_label.classes('text-negative')

    def do_exclude_all(main_db, dep_dbs, dlg):
        """Exclude main database and all dependents"""
        db = get_db()
        try:
            # Exclude main database
            db_obj = db.query(Database).filter(Database.id == main_db.id).first()
            db_obj.is_excluded = True

            # Exclude all dependents
            for dep_db in dep_dbs:
                if not dep_db.is_excluded:
                    dep_db_obj = db.query(Database).filter(Database.id == dep_db.id).first()
                    dep_db_obj.is_excluded = True

            db.commit()

            # Audit log
            details = f'Excluded database: {main_db.name}'
            if dep_dbs:
                dep_names = [d.name for d in dep_dbs if not d.is_excluded]
                if dep_names:
                    details += f' (with {len(dep_names)} dependents: {", ".join(dep_names)})'

            create_audit_log(
                db=db,
                user_id=user.id,
                action='database_excluded',
                resource_type='database',
                resource_id=main_db.id,
                details=details,
                auto_commit=True
            )

            ui.notify(f'🚫 {len(dep_dbs) + 1} Datenbanken deaktiviert!', type='warning')

        finally:
            db.close()

        dlg.close()
        load_databases(user, server, team, container)

    # Start async scan
    ui.timer(0.1, scan_and_show, once=True)


def toggle_database_exclusion(user, database, is_excluded, container):
    """Toggle database exclusion status and automatically include dependencies"""
    import logging
    logger = logging.getLogger(__name__)

    try:
        db = get_db()

        # Get team first (needed for dependency resolution)
        team = db.query(Team).filter(Team.id == database.team_id).first()
        server = db.query(Server).filter(Server.id == team.server_id).first()

        # TODO: Auto-include/exclude temporarily disabled due to performance issues
        # Will be replaced with a manual "Include with Dependencies" button
        auto_included = []
        auto_excluded = []

        # Simple include/exclude without dependency checking (for now)
        logger.info(f"{'Excluding' if is_excluded else 'Including'} database {database.name} (no auto-dependency check)")

        # Update the main database
        db_obj = db.query(Database).filter(Database.id == database.id).first()
        db_obj.is_excluded = is_excluded
        db.commit()

        # Create audit log
        action = 'database_excluded' if is_excluded else 'database_included'
        details = f'{"Excluded" if is_excluded else "Included"} database: {database.name}'
        if auto_included:
            details += f' (Auto-included {len(auto_included)} dependencies: {", ".join(auto_included)})'
        if auto_excluded:
            details += f' (Auto-excluded {len(auto_excluded)} dependents: {", ".join(auto_excluded)})'

        create_audit_log(
            db=db,
            user_id=user.id,
            action=action,
            resource_type='database',
            resource_id=database.id,
            details=details,
            auto_commit=True
        )

        db.close()

        # Show success message
        status_text = 'excluded' if is_excluded else 'included'
        message = f'Database "{database.name}" {status_text} successfully!'

        if auto_included:
            message += f'\n\n✅ Automatisch aktiviert ({len(auto_included)} Abhängigkeiten):\n• ' + '\n• '.join(auto_included)

        if auto_excluded:
            message += f'\n\n🚫 Automatisch deaktiviert ({len(auto_excluded)} abhängige DBs):\n• ' + '\n• '.join(auto_excluded)

        Toast.success(message)

        # Reload databases
        load_databases(user, server, team, container)

    except Exception as e:
        Toast.error(f'Error updating database status: {str(e)}')


def show_erd_viewer_dialog(user, server, team, database):
    """Show ERD viewer dialog with SVG from GitHub"""
    import logging
    logger = logging.getLogger(__name__)

    # Create dialog
    with ui.dialog().props('maximized') as dialog:
        with ui.card().classes('w-full h-full'):
            # Header
            with ui.row().classes('w-full items-center justify-between p-4 bg-primary text-white'):
                with ui.column().classes('gap-1'):
                    ui.label(f'ERD: {database.name}').classes('text-h5 font-bold')
                    ui.label(f'{server.name} / {team.name}').classes('text-sm opacity-80')

                with ui.row().classes('gap-2'):
                    ui.button('Zoom In', icon='zoom_in', on_click=lambda: ui.run_javascript('if(window._erdPanZoom){window._erdPanZoom.zoomIn();}')).props('flat color=white')
                    ui.button('Zoom Out', icon='zoom_out', on_click=lambda: ui.run_javascript('if(window._erdPanZoom){window._erdPanZoom.zoomOut();}')).props('flat color=white')
                    ui.button('Reset', icon='center_focus_strong', on_click=lambda: ui.run_javascript('if(window._erdPanZoom){window._erdPanZoom.resetZoom();window._erdPanZoom.center();}')).props('flat color=white')
                    ui.button('Fit', icon='fit_screen', on_click=lambda: ui.run_javascript('if(window._erdPanZoom){window._erdPanZoom.fit();window._erdPanZoom.center();}')).props('flat color=white')
                    ui.button(icon='close', on_click=dialog.close).props('flat color=white')

            # Content area with SVG pan zoom stage
            with ui.column().classes('w-full').style('height: calc(100vh - 100px);'):
                # Loading indicator
                loading_container = ui.column().classes('w-full items-center gap-4 p-8')
                with loading_container:
                    ui.spinner(size='xl', color='primary')
                    status_label = ui.label('Loading ERD from GitHub...').classes('text-h6')

                # SVG container - create the stage HTML NOW before background task
                svg_container = ui.column().classes('w-full h-full').style('display: none;')
                with svg_container:
                    erd_stage = ui.html('''
                    <div id="erd-stage" style="width:100%;height:calc(100vh - 200px);border:1px solid #ccc;overflow:hidden;background:#fff;">
                      <div id="erd-viewport" style="width:100%;height:100%;"></div>
                    </div>
                    ''', sanitize=False)

                # Error container (initially hidden)
                error_container = ui.column().classes('w-full').style('display: none;')

    dialog.open()

    # Load SVG in background - use context to access UI elements
    from nicegui import context
    client_context = context.client

    async def load_svg():
        try:
            logger.info(f"Loading SVG ERD for {database.name} from GitHub...")

            if not user.github_token_encrypted or not user.github_organization:
                raise Exception("GitHub not configured")

            # Access UI elements through the saved client context
            with client_context:
                status_label.text = 'Fetching ERD from GitHub...'
            await asyncio.sleep(0.1)

            encryption = get_encryption_manager()
            github_token = encryption.decrypt(user.github_token_encrypted)
            repo_name = get_repo_name_from_server(server)

            github_mgr = GitHubManager(access_token=github_token, organization=user.github_organization)

            logger.info(f"Looking for repository: {repo_name} in organization: {user.github_organization}")
            repo = github_mgr.get_repository(repo_name)

            if not repo:
                # Try to list all repos to see what's available
                all_repos = [r.name for r in github_mgr.list_repositories()[:10]]
                logger.error(f"Repository '{repo_name}' not found. Available repos: {all_repos}")
                raise Exception(f"Repository '{repo_name}' not found. Available: {', '.join(all_repos[:5])}")

            # ERD is now on database root level (same as APPLICATION_DOCS.md)
            erd_path = f'{database.github_path}/erd.svg'

            with client_context:
                status_label.text = f'Loading: {erd_path}...'
            await asyncio.sleep(0.1)

            content = github_mgr.get_file_content(repo, erd_path)
            if not content:
                raise Exception(f"ERD file not found. Please sync this database first to generate the ERD.")

            # Hide loading, show SVG (containers already created)
            with client_context:
                loading_container.style('display: none;')
                svg_container.style('display: block;')

            # Inject SVG and initialize pan/zoom via JavaScript only
            svg_escaped = content.replace('`', '\\`').replace('</script>', '<\\/script>')
            init_script = f'''
            // Load svg-pan-zoom library
            if (typeof svgPanZoom === 'undefined') {{
              const script = document.createElement('script');
              script.src = 'https://cdn.jsdelivr.net/npm/svg-pan-zoom@3.6.1/dist/svg-pan-zoom.min.js';
              script.onload = function() {{ initErdViewer(); }};
              document.head.appendChild(script);
            }} else {{
              initErdViewer();
            }}

            function initErdViewer() {{
              const vp = document.getElementById('erd-viewport');
              if (!vp) return;

              vp.innerHTML = `{svg_escaped}`;
              const svg = vp.querySelector('svg');
              if (!svg) {{
                vp.innerHTML = '<div style="padding:40px;color:#b00;">No SVG found</div>';
                return;
              }}

              // Set SVG to fill container
              svg.removeAttribute('width');
              svg.removeAttribute('height');
              svg.setAttribute('width', '100%');
              svg.setAttribute('height', '100%');

              // Destroy existing instance
              if (window._erdPanZoom) {{
                try {{ window._erdPanZoom.destroy(); }} catch(e) {{}}
              }}

              // Initialize svg-pan-zoom
              window._erdPanZoom = svgPanZoom(svg, {{
                zoomEnabled: true,
                panEnabled: true,
                controlIconsEnabled: false,
                fit: true,
                center: true,
                minZoom: 0.1,
                maxZoom: 50,
                zoomScaleSensitivity: 0.3
              }});

              // Prevent default scroll
              const stage = document.getElementById('erd-stage');
              if (stage) {{
                stage.addEventListener('wheel', ev => ev.preventDefault(), {{ passive: false }});
              }}
            }}
            '''
            # Run JavaScript within client context
            with client_context:
                ui.run_javascript(init_script)

            logger.info(f"✓ SVG ERD loaded with pan/zoom: {len(content)} bytes")

        except Exception as e:
            logger.error(f"Error loading SVG: {e}")
            import traceback
            logger.error(traceback.format_exc())

            # Use client context to update UI
            with client_context:
                loading_container.style('display: none;')
                error_container.style('display: block;')
                with error_container:
                    with ui.card().classes('w-full p-4 bg-red-50'):
                        ui.icon('error', size='lg').classes('text-negative')
                        ui.label('Error Loading ERD').classes('text-h6 font-bold text-negative')
                        ui.label(str(e)).classes('text-sm mt-2')

    # Use asyncio.create_task instead of background_tasks (keeps UI context)
    asyncio.create_task(load_svg())


def show_documentation_dialog(user, server, team, database):
    """Show dialog for generating AI documentation"""
    import logging
    from concurrent.futures import ThreadPoolExecutor
    from ..services.doc_generator import DocumentationGenerator, get_documentation_generator
    from ..models.documentation import Documentation
    from ..models.ai_config import AIConfig, AIProvider
    # decrypt_value nicht benötigt - wird über get_encryption_manager() gemacht
    from ..utils.github_utils import get_repo_name_from_server
    
    logger = logging.getLogger(__name__)
    
    with ui.dialog() as dialog, ui.card().classes('w-full').style('max-width: 900px; max-height: 90vh;'):
        # Header
        with ui.row().classes('w-full items-center justify-between p-4').style(
            f'background: linear-gradient(135deg, #9333EA 0%, #7C3AED 100%);'
        ):
            with ui.row().classes('items-center gap-2'):
                ui.icon('description', size='md', color='white')
                ui.label(f'Dokumentation: {database.name}').classes('text-h6 text-white font-bold')
            ui.button(icon='close', on_click=dialog.close).props('flat color=white')
        
        # Content container
        content_container = ui.column().classes('w-full p-4 gap-4')
        
        with content_container:
            # Check if Gemini is configured
            db = get_db()
            try:
                gemini_config = db.query(AIConfig).filter(
                    AIConfig.provider == AIProvider.GEMINI.value,
                    AIConfig.is_active == True
                ).first()
                
                if not gemini_config or not gemini_config.api_key_encrypted:
                    with ui.card().classes('w-full p-4 bg-amber-50'):
                        with ui.row().classes('items-center gap-2'):
                            ui.icon('warning', color='orange')
                            ui.label('Gemini ist nicht konfiguriert').classes('text-h6 font-bold')
                        ui.label('Bitte konfigurieren Sie einen Gemini API-Key unter Admin → KI-Konfiguration.').classes('text-grey-7')
                        ui.button('Zu KI-Konfiguration', icon='settings', on_click=lambda: ui.navigate.to('/admin')).props('color=primary')
                    return
                
                # Get latest documentation if exists
                latest_doc = db.query(Documentation).filter(
                    Documentation.database_id == database.id
                ).order_by(Documentation.generated_at.desc()).first()
                
            finally:
                db.close()
            
            # Info section
            with ui.card().classes('w-full p-4 bg-blue-50'):
                ui.label('KI-Dokumentation generieren').classes('text-subtitle1 font-bold')
                ui.label(
                    'Analysiert die Datenbankstruktur mit Gemini und erstellt eine ausführliche '
                    'Markdown-Dokumentation. Diese wird im GitHub-Repository als APPLICATION_DOCS.md gespeichert.'
                ).classes('text-grey-7')
                
                with ui.row().classes('items-center gap-4 mt-2'):
                    ui.label(f'Modell: {gemini_config.model}').classes('text-sm text-grey-6')
                    ui.label(f'Max Tokens: Maximum').classes('text-sm text-grey-6')
                    if latest_doc:
                        ui.label(f'Letzte Generierung: {latest_doc.generated_at.strftime("%d.%m.%Y %H:%M")}').classes('text-sm text-grey-6')
            
            # Preview container (initially hidden)
            preview_container = ui.column().classes('w-full').style('display: none;')
            
            # Status container
            status_container = ui.column().classes('w-full items-center gap-4')
            
            # Buttons
            with ui.row().classes('w-full justify-end gap-2'):
                generate_btn = ui.button(
                    'Dokumentation generieren',
                    icon='auto_awesome',
                    color='purple'
                )
                save_btn = ui.button(
                    'In GitHub speichern',
                    icon='cloud_upload',
                    color='positive'
                ).props('disable')
        
        # Store generated content
        generated_content = {'markdown': None, 'result': None}
        
        async def generate_documentation():
            """Generate documentation using Gemini"""
            generate_btn.props('loading disable')
            
            with status_container:
                status_container.clear()
                ui.spinner(size='lg', color='purple')
                ui.label('Lade Datenbankstruktur aus GitHub...').classes('text-grey-7')
            
            try:
                # Get structure from GitHub
                db = get_db()
                try:
                    enc_manager = get_encryption_manager()
                    github_token = enc_manager.decrypt(user.github_token_encrypted)
                    github = GitHubManager(github_token, user.github_organization)
                    
                    repo_name = get_repo_name_from_server(server)
                    repo = github.ensure_repository(repo_name)
                    
                    # Find structure file
                    structure_path = f"{database.github_path}/{sanitize_name(database.name)}-structure.json"
                    structure_content = github.get_file_content(repo, structure_path)
                    
                    if not structure_content:
                        raise ValueError(f"Strukturdatei nicht gefunden: {structure_path}")
                    
                    structure_json = json.loads(structure_content)
                    
                    # Update status
                    status_container.clear()
                    with status_container:
                        ui.spinner(size='lg', color='purple')
                        ui.label('Generiere Dokumentation mit Gemini...').classes('text-grey-7')
                        ui.label('Dies kann 30-60 Sekunden dauern.').classes('text-sm text-grey-5')
                    
                    # Get generator
                    generator = get_documentation_generator()
                    if not generator:
                        raise ValueError("Gemini ist nicht konfiguriert")
                    
                    # Run in thread pool to avoid blocking
                    loop = asyncio.get_event_loop()
                    with ThreadPoolExecutor() as pool:
                        result = await loop.run_in_executor(
                            pool,
                            lambda: generator.generate(structure_json, database.name)
                        )
                    
                    if not result.success:
                        raise ValueError(result.error or "Unbekannter Fehler")
                    
                    # Store result
                    generated_content['markdown'] = result.content
                    generated_content['result'] = result
                    
                    # Show preview
                    status_container.clear()
                    preview_container.style('display: block;')
                    
                    with preview_container:
                        preview_container.clear()
                        with ui.card().classes('w-full'):
                            with ui.row().classes('w-full items-center justify-between p-2 bg-grey-2'):
                                ui.label('Vorschau').classes('font-bold')
                                with ui.row().classes('items-center gap-2'):
                                    if result.input_tokens:
                                        ui.badge(f'↓{result.input_tokens}', color='amber').props('dense')
                                    if result.output_tokens:
                                        ui.badge(f'↑{result.output_tokens}', color='amber').props('dense')
                            
                            # Markdown preview with scroll
                            with ui.scroll_area().classes('w-full').style('max-height: 400px;'):
                                ui.markdown(result.content).classes('p-4')
                    
                    # Enable save button
                    save_btn.props(remove='disable')
                    generate_btn.props(remove='loading disable')
                    generate_btn.text = 'Neu generieren'
                    
                    ui.notify('Dokumentation erfolgreich generiert!', type='positive')
                    
                finally:
                    db.close()
                    
            except Exception as e:
                logger.error(f"Error generating documentation: {e}")
                status_container.clear()
                with status_container:
                    ui.icon('error', size='lg', color='red')
                    ui.label('Fehler bei der Generierung').classes('text-h6 text-negative')
                    ui.label(str(e)).classes('text-grey-7')
                
                generate_btn.props(remove='loading disable')
                ui.notify(f'Fehler: {str(e)}', type='negative')
        
        async def save_to_github():
            """Save documentation to GitHub"""
            if not generated_content['markdown']:
                ui.notify('Keine Dokumentation zum Speichern', type='warning')
                return
            
            save_btn.props('loading disable')
            
            try:
                db = get_db()
                try:
                    enc_manager = get_encryption_manager()
                    github_token = enc_manager.decrypt(user.github_token_encrypted)
                    github = GitHubManager(github_token, user.github_organization)
                    
                    repo_name = get_repo_name_from_server(server)
                    repo = github.ensure_repository(repo_name)
                    
                    # Save to GitHub
                    doc_path = f"{database.github_path}/APPLICATION_DOCS.md"
                    commit_result = github.update_file(
                        repo,
                        doc_path,
                        generated_content['markdown'],
                        f"Update APPLICATION_DOCS.md via AI ({database.name})"
                    )
                    
                    # Save to database
                    result = generated_content['result']
                    doc = Documentation(
                        database_id=database.id,
                        content=generated_content['markdown'],
                        model=result.model,
                        input_tokens=result.input_tokens,
                        output_tokens=result.output_tokens,
                        github_synced=True,
                        github_synced_at=datetime.now(),
                        github_commit_sha=commit_result.sha if hasattr(commit_result, 'sha') else None
                    )
                    db.add(doc)
                    db.commit()
                    
                    ui.notify('Dokumentation erfolgreich in GitHub gespeichert!', type='positive')
                    save_btn.props(remove='loading')
                    save_btn.text = 'Gespeichert ✓'
                    
                finally:
                    db.close()
                    
            except Exception as e:
                logger.error(f"Error saving documentation: {e}")
                save_btn.props(remove='loading disable')
                ui.notify(f'Fehler beim Speichern: {str(e)}', type='negative')
        
        generate_btn.on_click(generate_documentation)
        save_btn.on_click(save_to_github)
    
    dialog.open()

    dialog.open()


# ============================================================================
# YAML Sync Functions (ninox-dev-cli integration)
# ============================================================================

async def handle_yaml_sync_click(user, server, team, database, container):
    """Handle YAML sync for a single database (uses database Auto-ERD/Auto-Doku settings)"""
    import logging
    from ..services.ninox_sync_service import get_ninox_sync_service

    logger = logging.getLogger(__name__)

    logger.info(f"Starting YAML sync for database: {database.name} ({database.database_id})")

    try:
        sync_service = get_ninox_sync_service()

        # Show notification
        auto_erd = getattr(database, 'auto_generate_erd', True)
        auto_docs = database.auto_generate_docs
        ui.notify(
            f'Starte YAML-Sync für {database.name}...\n'
            f'ERD: {"✓" if auto_erd else "⏭"} | Doku: {"✓" if auto_docs else "⏭"}',
            type='info'
        )

        # Perform sync (will use database settings automatically)
        result = await sync_service.sync_database_async(
            server,
            team,
            database.database_id,
            user=user
        )

        if result.success:
            logger.info(f"YAML sync successful for {database.name} in {result.duration_seconds:.1f}s")

            # Scan and save dependencies in background
            logger.info(f"Scanning dependencies for {database.name}...")
            save_database_dependencies(team, database.database_id)

            ui.notify(
                f'✅ YAML-Sync erfolgreich: {database.name} ({result.duration_seconds:.1f}s)',
                type='positive'
            )
        else:
            logger.error(f"YAML sync failed for {database.name}: {result.error}")
            ui.notify(f'YAML-Sync fehlgeschlagen: {result.error}', type='negative')

    except Exception as e:
        logger.error(f"Error in YAML sync for {database.name}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        ui.notify(f'Fehler beim YAML-Sync: {str(e)}', type='negative')


async def sync_all_yaml(user, server, team, databases, container):
    """Sync YAML for all databases in background (uses per-database Auto-ERD/Auto-Doku settings)"""
    import logging
    from ..services.background_sync import get_sync_manager

    logger = logging.getLogger(__name__)

    # Filter out excluded databases
    active_databases = [d for d in databases if not d.is_excluded]

    if not active_databases:
        ui.notify('Keine aktiven Datenbanken zum Synchronisieren', type='warning')
        return

    # Count DBs with auto-docs and auto-erd enabled
    docs_enabled_dbs = [d for d in active_databases if d.auto_generate_docs]
    erd_enabled_dbs = [d for d in active_databases if getattr(d, 'auto_generate_erd', True)]

    # Start all databases in background using BackgroundSyncManager
    sync_manager = get_sync_manager()
    sync_manager.start_bulk_sync(team.id, len(active_databases))

    # No need to set skip flags - each database uses its own settings

    # Start each sync in background
    for db in active_databases:
        sync_manager.start_sync(user, server, team, db)

    # Show notification with info about settings
    ui.notify(
        f'🚀 Sync gestartet!\n\n'
        f'📦 {len(active_databases)} Datenbanken werden synchronisiert\n'
        f'🎨 ERD: {len(erd_enabled_dbs)} DBs (per Auto-ERD Einstellung)\n'
        f'📄 Doku: {len(docs_enabled_dbs)} DBs (per Auto-Doku Einstellung)\n\n'
        f'✅ Sie können die Seite verlassen - der Sync läuft weiter!\n'
        f'🔄 Seite aktualisiert sich alle 5 Sekunden.\n\n'
        f'💡 Tipp: Ändern Sie die Auto-ERD/Auto-Doku Einstellungen in den Datenbank-Karten',
        type='info',
        timeout=8000
    )

    logger.info(f"✓ Background sync started: {len(active_databases)} DBs | ERD: {len(erd_enabled_dbs)} DBs | Docs: {len(docs_enabled_dbs)} DBs")

    # Refresh UI immediately to show "Syncing..." status
    load_databases(user, server, team, container)


def toggle_all_auto_docs(user, server: Server, team: Team, database_list_refreshable):
    """Toggle auto_generate_docs for all databases in team"""
    db = get_db()
    try:
        databases = db.query(Database).filter(Database.team_id == team.id).all()

        if not databases:
            return

        # Toggle to opposite of current state (use first DB as reference)
        new_state = not databases[0].auto_generate_docs

        for db_obj in databases:
            db_obj.auto_generate_docs = new_state

        db.commit()

        ui.notify(
            f'✓ Auto-Doku {"aktiviert" if new_state else "deaktiviert"} für {len(databases)} Datenbanken',
            type='positive'
        )

        # Refresh the database list
        database_list_refreshable.refresh()

    finally:
        db.close()


def toggle_all_auto_erd(user, server: Server, team: Team, database_list_refreshable):
    """Toggle auto_generate_erd for all databases in team"""
    db = get_db()
    try:
        databases = db.query(Database).filter(Database.team_id == team.id).all()

        if not databases:
            return

        # Toggle to opposite of current state
        new_state = not getattr(databases[0], 'auto_generate_erd', True)

        for db_obj in databases:
            db_obj.auto_generate_erd = new_state

        db.commit()

        ui.notify(
            f'✓ Auto-ERD {"aktiviert" if new_state else "deaktiviert"} für {len(databases)} Datenbanken',
            type='positive'
        )

        # Refresh the database list
        database_list_refreshable.refresh()

    finally:
        db.close()


def generate_documentation_for_database(database: Database, user, server: Server, team: Team, container):
    """Show dialog for documentation generation with optional sync"""
    import logging
    from ..models.database_dependency import DatabaseDependency
    from ..utils.path_resolver import get_database_path
    from datetime import datetime

    logger = logging.getLogger(__name__)

    # Check if already generating
    if database.id in _doc_generating:
        ui.notify(f'Dokumentation für {database.name} wird bereits generiert!', type='warning')
        return

    logger.info(f"Documentation generation dialog opened for: {database.name}")

    # Scan for dependencies directly from YAML files (always up-to-date)
    linked_dbs = []
    db = get_db()
    try:
        # Read YAML to find cross-DB references
        db_path = get_database_path(server, team, database.name)

        if db_path and db_path.exists():
            from ..utils.ninox_yaml_parser import NinoxYAMLParser

            parser = NinoxYAMLParser(str(db_path))
            databases = parser.get_all_databases()

            if databases:
                yaml_db = databases[0]

                # Find all fields with cross-DB references
                external_db_ids = set()
                for table_name, table_data in yaml_db.tables.items():
                    for field_id, field_data in table_data.get('fields', {}).items():
                        # Check for external DB reference
                        db_id = field_data.get('dbId')
                        db_name = field_data.get('dbName')

                        if db_id and db_id != database.database_id:
                            external_db_ids.add(db_id)
                        elif db_name:
                            external_db_ids.add(db_name)

                logger.info(f"Found {len(external_db_ids)} external DB references in YAML: {external_db_ids}")

                # Look up these databases in our system
                for ext_db_id in external_db_ids:
                    # Try to find by database_id or name
                    target_db = db.query(Database).filter(
                        (Database.database_id == ext_db_id) | (Database.name == ext_db_id)
                    ).first()

                    if target_db:
                        # Calculate time since last sync
                        time_since_sync = "nie"
                        if target_db.last_modified:
                            delta = datetime.utcnow() - target_db.last_modified
                            hours = int(delta.total_seconds() / 3600)
                            if hours < 1:
                                time_since_sync = "vor < 1 Std."
                            elif hours < 24:
                                time_since_sync = f"vor {hours} Std."
                            else:
                                days = int(hours / 24)
                                time_since_sync = f"vor {days} Tag{'en' if days > 1 else ''}"

                        linked_dbs.append({
                            'db': target_db,
                            'time_since_sync': time_since_sync
                        })
                        logger.info(f"  Found linked DB: {target_db.name} (last sync: {time_since_sync})")
                    else:
                        logger.warning(f"External DB '{ext_db_id}' referenced but not found in system")

        # Check when main database was last synced
        main_time_since_sync = "nie"
        if database.last_modified:
            delta = datetime.utcnow() - database.last_modified
            hours = int(delta.total_seconds() / 3600)
            if hours < 1:
                main_time_since_sync = "vor < 1 Std."
            elif hours < 24:
                main_time_since_sync = f"vor {hours} Std."
            else:
                days = int(hours / 24)
                main_time_since_sync = f"vor {days} Tag{'en' if days > 1 else ''}"

    finally:
        db.close()

    logger.info(f"Found {len(linked_dbs)} linked databases for {database.name}")

    # Mark dialog as open (prevents auto-refresh)
    _dialog_open_state['count'] += 1

    def on_dialog_close():
        """Cleanup when dialog closes"""
        _dialog_open_state['count'] -= 1
        dialog.close()

    # Show options dialog
    with ui.dialog() as dialog, ui.card().classes('w-full').style('max-width: 600px;'):
        with ui.row().classes('w-full items-center justify-between p-4 bg-purple text-white'):
            ui.label(f'Dokumentation generieren: {database.name}').classes('text-h6 font-bold')
            close_btn = ui.button(icon='close', on_click=on_dialog_close).props('flat color=white round')

        # Options container
        options_container = ui.column().classes('w-full p-6 gap-4')
        with options_container:
            ui.label('Sync-Optionen:').classes('text-subtitle1 font-bold')

            # Main sync checkbox
            with ui.column().classes('gap-2'):
                sync_main_cb = ui.checkbox(
                    f'YAML vorher neu von Ninox syncen',
                    value=False
                ).classes('text-base')

                with ui.row().classes('items-center gap-2 ml-8'):
                    ui.icon('schedule', size='xs', color='grey')
                    ui.label(f'Letzter Sync: {main_time_since_sync}').classes('text-xs text-grey-6')

                ui.label('Empfohlen wenn Datenbankstruktur geändert wurde').classes('text-xs text-grey-6 ml-8')

            # Show linked databases if any
            if linked_dbs:
                ui.separator()

                with ui.column().classes('gap-2'):
                    with ui.row().classes('items-center gap-2'):
                        ui.icon('link', size='sm', color='blue')
                        ui.label(f'{len(linked_dbs)} verknüpfte Datenbank{"en" if len(linked_dbs) > 1 else ""} gefunden:').classes('text-subtitle2 font-bold')

                    # List linked databases
                    for linked in linked_dbs:
                        with ui.row().classes('items-center gap-2 ml-6'):
                            ui.icon('database', size='xs', color='grey')
                            ui.label(f"{linked['db'].name}").classes('text-sm')
                            ui.label(f"({linked['time_since_sync']})").classes('text-xs text-grey-6')

                    # Cascade sync checkbox
                    sync_cascade_cb = ui.checkbox(
                        'Verknüpfte DBs auch neu syncen',
                        value=False
                    ).classes('text-sm mt-2')
                    sync_cascade_cb.bind_enabled_from(sync_main_cb, 'value')
                    ui.label('Nur aktiv wenn YAML-Sync aktiviert ist').classes('text-xs text-grey-6 ml-8')
            else:
                sync_cascade_cb = None

            ui.separator()

            # Info about what will be generated
            with ui.row().classes('items-center gap-2'):
                ui.icon('info', size='sm', color='blue')
                ui.label('Wird generiert: APPLICATION_DOCS.md + SCRIPTS.md').classes('text-sm text-grey-7')

            # Buttons
            with ui.row().classes('w-full justify-end gap-2 mt-4'):
                ui.button('Abbrechen', on_click=on_dialog_close).props('flat')

                def start_generation():
                    # Get options
                    do_sync = sync_main_cb.value
                    do_cascade = sync_cascade_cb.value if sync_cascade_cb else False

                    # Close dialog immediately
                    on_dialog_close()

                    # Start background task
                    import uuid
                    import threading
                    from datetime import datetime

                    task_id = f"doc_gen_{database.id}_{uuid.uuid4().hex[:8]}"

                    # Create task info
                    _background_doc_tasks[task_id] = {
                        'database_id': database.id,
                        'database_name': database.name,
                        'status': 'running',
                        'phase': 'sync' if do_sync else 'generating',
                        'progress': '0/0',
                        'start_time': datetime.now(),
                        'do_sync': do_sync,
                        'do_cascade': do_cascade,
                        'total_dbs': 1 + (len(linked_dbs) if do_cascade else 0),
                        'synced_dbs': 0,
                        'message': 'Startet...'
                    }

                    logger.info(f"Starting background doc generation task: {task_id}")

                    # Start in background thread
                    def run_task():
                        _run_background_doc_generation(
                            task_id, database, user, server, team,
                            linked_dbs, do_sync, do_cascade
                        )

                    thread = threading.Thread(target=run_task, daemon=True)
                    thread.start()

                    # Force refresh to show progress bar
                    _force_refresh['needed'] = True

                ui.button('Generieren', icon='auto_awesome', on_click=start_generation).props('color=purple')

        # Progress container (initially hidden)
        progress_container = ui.column().classes('w-full p-6 gap-4 items-center').style('display: none;')

    dialog.open()


def _run_background_doc_generation(task_id, database, user, server, team, linked_dbs, do_sync, do_cascade):
    """Run documentation generation in background with progress tracking"""
    import logging
    import asyncio
    from datetime import datetime
    from ..utils.path_resolver import get_database_path
    from ..services.ninox_sync_service import get_ninox_sync_service

    logger = logging.getLogger(__name__)

    try:
        logger.info(f"=== Background doc generation started: {task_id} ===")
        logger.info(f"Options: sync={do_sync}, cascade={do_cascade}, linked_dbs={len(linked_dbs)}")

        task = _background_doc_tasks[task_id]

        # Phase 1: Optional Sync
        if do_sync:
            task['phase'] = 'sync'
            task['message'] = 'Synchronisiere YAML...'

            dbs_to_sync = [database]
            if do_cascade and linked_dbs:
                dbs_to_sync.extend([linked['db'] for linked in linked_dbs])

            total_dbs = len(dbs_to_sync)
            logger.info(f"Will sync {total_dbs} databases")

            # Sync each database
            from ..models.team import Team as TeamModel
            sync_service = get_ninox_sync_service()

            for i, db_item in enumerate(dbs_to_sync):
                db_name = db_item.name
                db_id = db_item.database_id

                task['message'] = f'Syncen ({i+1}/{total_dbs}): {db_name}'
                task['progress'] = f'{i+1}/{total_dbs}'
                logger.info(f"Syncing {i+1}/{total_dbs}: {db_name}")

                try:
                    # Get fresh team from database
                    db_conn = get_db()
                    try:
                        db_fresh = db_conn.query(Database).filter(Database.id == db_item.id).first()
                        if db_fresh:
                            db_team = db_conn.query(TeamModel).filter(TeamModel.id == db_fresh.team_id).first()
                        else:
                            db_team = team
                    finally:
                        db_conn.close()

                    # Sync
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                    result = loop.run_until_complete(
                        sync_service.sync_database_async(
                            server, db_team, db_id,
                            timeout=600,  # 10 minutes for large databases
                            user=user,
                            generate_erd=True,
                            generate_docs=False
                        )
                    )
                    loop.close()

                    if result.success:
                        task['synced_dbs'] = i + 1
                        logger.info(f"✓ Synced {db_name}")

                        # Update database status after successful sync
                        db_conn = get_db()
                        try:
                            db_fresh = db_conn.query(Database).filter(Database.id == db_item.id).first()
                            if db_fresh:
                                db_fresh.sync_status = 'idle'
                                db_fresh.sync_error = None
                                db_fresh.last_modified = datetime.now()

                                # Commit database status first
                                db_conn.commit()

                                # Create audit log entry with auto_commit (uses own session)
                                create_audit_log(
                                    db=None,
                                    user_id=user.id,
                                    action='database_synced',
                                    resource_type='database',
                                    resource_id=db_fresh.id,
                                    details=f'Cascade sync: {db_name}',
                                    auto_commit=True
                                )
                                logger.info(f"✓ Updated database status and created audit log for {db_name}")
                        finally:
                            db_conn.close()
                    else:
                        logger.warning(f"Sync failed for {db_name}: {result.error}")

                except Exception as e:
                    logger.error(f"Error syncing {db_name}: {e}")

            logger.info(f"✓ Sync phase completed ({total_dbs} DBs)")

        # Phase 2: Generate Documentation
        task['phase'] = 'generating'
        task['message'] = 'Generiere Dokumentation...'
        task['progress'] = '0/1'

        logger.info(f"Starting documentation generation")

        db_path = get_database_path(server, team, database.name)

        if not db_path or not db_path.exists():
            raise Exception(f"Database path not found: {db_path}")

        from ..utils.ninox_yaml_parser import NinoxYAMLParser
        from ..services.doc_generator import get_documentation_generator

        parser = NinoxYAMLParser(str(db_path))
        databases = parser.get_all_databases()

        if not databases:
            raise Exception(f"No databases found in {db_path}")

        yaml_db = databases[0]
        generator = get_documentation_generator()

        if not generator:
            raise Exception("Gemini not configured")

        def batch_progress(current, total):
            task['message'] = f'Generiere Doku (Batch {current}/{total})'
            task['progress'] = f'{current}/{total}'

        structure_dict = yaml_db.to_dict_for_docs()
        result = generator.generate(structure_dict, yaml_db.name, progress_callback=batch_progress)

        if not result.success:
            raise Exception(f"Documentation generation failed: {result.error}")

        # Phase 3: Save
        task['phase'] = 'saving'
        task['message'] = 'Speichere Dokumentation...'

        from ..models.documentation import Documentation
        from ..services.ninox_sync_service import commit_changes

        db_conn = get_db()
        try:
            # Save to database
            doc = Documentation(
                database_id=database.id,
                content=result.content,
                model=result.model,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens
            )
            db_conn.add(doc)
            db_conn.commit()

            # Save to files
            docs_file = db_path / 'APPLICATION_DOCS.md'
            docs_file.parent.mkdir(parents=True, exist_ok=True)

            with open(docs_file, 'w', encoding='utf-8') as f:
                f.write(result.content)

            from ..utils.scripts_md_generator import generate_scripts_md
            scripts_content = generate_scripts_md(yaml_db)
            scripts_file = db_path / 'SCRIPTS.md'

            with open(scripts_file, 'w', encoding='utf-8') as f:
                f.write(scripts_content)

            # Commit and push
            server_path = db_path.parent.parent
            commit_changes(server_path, f"Update documentation and scripts for {yaml_db.name}")

            if user and user.github_token_encrypted:
                import subprocess
                subprocess.run(['git', 'push'], cwd=server_path, capture_output=True)

        finally:
            db_conn.close()

        # Success!
        task['status'] = 'completed'
        task['phase'] = 'done'
        task['message'] = 'Erfolgreich abgeschlossen!'
        task['end_time'] = datetime.now()
        task['total_tokens'] = result.input_tokens + result.output_tokens

        logger.info(f"✓ Background doc generation completed: {task_id}")
        _force_refresh['needed'] = True

    except Exception as e:
        logger.error(f"Error in background doc generation: {e}")
        import traceback
        logger.error(traceback.format_exc())

        # Mark as failed
        if task_id in _background_doc_tasks:
            _background_doc_tasks[task_id]['status'] = 'failed'
            _background_doc_tasks[task_id]['phase'] = 'error'
            _background_doc_tasks[task_id]['message'] = str(e)
            _background_doc_tasks[task_id]['end_time'] = datetime.now()

        _force_refresh['needed'] = True

    finally:
        # Remove from generating dict
        _doc_generating.pop(database.id, None)


def sync_to_bookstack(database: Database, user, server: Server, team: Team):
    """Sync database documentation to BookStack - shows selection dialog first"""
    import logging
    from ..services.bookstack_service import get_bookstack_service
    from ..models.documentation import Documentation

    logger = logging.getLogger(__name__)
    logger.info(f"sync_to_bookstack called for database: {database.name}")

    # Check if BookStack is configured for this server
    db = get_db()
    try:
        from ..models.bookstack_config import BookstackConfig
        bs_config = db.query(BookstackConfig).filter(
            BookstackConfig.server_id == server.id,
            BookstackConfig.is_active == True
        ).first()

        if not bs_config or not bs_config.is_configured:
            ui.notify(
                f'BookStack nicht konfiguriert für Server {server.name}\n'
                f'Bitte konfigurieren Sie BookStack im Admin-Panel.',
                type='warning',
                timeout=5000
            )
            return

        # Get latest documentation (optional - will be shown in dialog)
        doc = db.query(Documentation).filter(
            Documentation.database_id == database.id
        ).order_by(Documentation.generated_at.desc()).first()

        # Check what content is available
        from ..utils.path_resolver import get_database_path
        db_path = get_database_path(server, team, database.name)

        has_docs = doc and doc.content
        has_scripts = False
        has_erd = False

        if db_path and db_path.exists():
            scripts_file = db_path / 'SCRIPTS.md'
            erd_file = db_path / 'erd.svg'
            has_scripts = scripts_file.exists()
            has_erd = erd_file.exists()

        # Check if at least one content type is available
        if not any([has_docs, has_scripts, has_erd]):
            ui.notify(
                f'Keine Inhalte zum Übertragen verfügbar für {database.name}\n'
                f'Bitte generieren Sie zuerst Dokumentation mit "GEN DOKU" und führen Sie einen Sync durch.',
                type='warning',
                timeout=5000
            )
            return

        # Show selection dialog
        logger.info(f"Opening BookStack selection dialog with: docs={has_docs}, scripts={has_scripts}, erd={has_erd}")
        with ui.dialog() as dialog, ui.card().classes('w-full').style('max-width: 500px;'):
            with ui.row().classes('w-full items-center justify-between p-4 bg-primary text-white'):
                ui.label(f'BookStack-Übertragung: {database.name}').classes('text-h6 font-bold')
                close_btn = ui.button(icon='close', on_click=dialog.close).props('flat color=white round')

            # Selection container (will be hidden during sync)
            selection_container = ui.column().classes('w-full p-6 gap-4')
            with selection_container:
                ui.label('Wählen Sie die zu übertragenden Inhalte:').classes('text-subtitle1 font-bold')

                # Checkboxes for content selection (all checked by default)
                docs_checkbox = ui.checkbox('Dokumentation (APPLICATION_DOCS.md)', value=has_docs).props('disable' if not has_docs else '')
                if not has_docs:
                    ui.label('Keine Dokumentation vorhanden').classes('text-xs text-grey-6 ml-8 -mt-2')

                scripts_checkbox = ui.checkbox('Scripts (SCRIPTS.md)', value=has_scripts).props('disable' if not has_scripts else '')
                if not has_scripts:
                    ui.label('Keine Scripts vorhanden').classes('text-xs text-grey-6 ml-8 -mt-2')

                erd_checkbox = ui.checkbox('ERD-Diagramm (erd.svg)', value=has_erd).props('disable' if not has_erd else '')
                if not has_erd:
                    ui.label('Kein ERD vorhanden').classes('text-xs text-grey-6 ml-8 -mt-2')

                ui.separator()

                # Info about BookStack destination
                with ui.row().classes('items-center gap-2'):
                    ui.icon('info', size='sm', color='blue')
                    ui.label(f'Ziel: {bs_config.default_shelf_name}').classes('text-sm text-grey-7')

                # Buttons
                button_row = ui.row().classes('w-full justify-end gap-2 mt-4')
                with button_row:
                    ui.button('Abbrechen', on_click=dialog.close).props('flat')

                    def start_sync():
                        # Get selected options
                        sync_docs = docs_checkbox.value
                        sync_scripts = scripts_checkbox.value
                        sync_erd = erd_checkbox.value

                        # Check if at least one option is selected
                        if not any([sync_docs, sync_scripts, sync_erd]):
                            # Show error in dialog
                            with selection_container:
                                with ui.row().classes('items-center gap-2 p-2 bg-orange-50 rounded'):
                                    ui.icon('warning', color='orange')
                                    ui.label('Bitte wählen Sie mindestens einen Inhalt aus').classes('text-sm')
                            return

                        # Hide selection, show progress
                        selection_container.style('display: none;')
                        close_btn.style('display: none;')

                        # Show progress container
                        progress_container.style('display: block;')

                        # Perform the sync with selected options (async)
                        _perform_bookstack_sync_in_dialog(
                            database, server, team, doc,
                            sync_docs, sync_scripts, sync_erd,
                            db_path, bs_config,
                            progress_container, dialog
                        )

                    ui.button('Übertragen', icon='cloud_upload', on_click=start_sync).props('color=primary')

            # Progress container (initially hidden)
            progress_container = ui.column().classes('w-full p-6 gap-4 items-center').style('display: none;')
            with progress_container:
                ui.spinner(size='lg', color='primary')
                status_label = ui.label('Übertrage zu BookStack...').classes('text-h6')

        dialog.open()

    finally:
        db.close()


def _perform_bookstack_sync_in_dialog(database, server, team, doc, sync_docs, sync_scripts, sync_erd, db_path, bs_config, progress_container, dialog):
    """Perform BookStack sync with progress updates in dialog"""
    import logging
    import threading
    from ..services.bookstack_service import get_bookstack_service

    logger = logging.getLogger(__name__)

    def sync_thread():
        """Run sync in background thread"""
        try:
            # Read selected content
            docs_content = doc.content if sync_docs and doc else None
            scripts_content = None
            erd_content = None

            try:
                if sync_scripts and db_path:
                    scripts_file = db_path / 'SCRIPTS.md'
                    if scripts_file.exists():
                        with open(scripts_file, 'r', encoding='utf-8') as f:
                            scripts_content = f.read()
                        logger.info(f"✓ Read SCRIPTS.md for BookStack sync")

                if sync_erd and db_path:
                    erd_file = db_path / 'erd.svg'
                    if erd_file.exists():
                        with open(erd_file, 'r', encoding='utf-8') as f:
                            erd_content = f.read()
                        logger.info(f"✓ Read erd.svg for BookStack sync")

            except Exception as e:
                logger.error(f"Error reading content: {e}")
                # Show error in dialog
                progress_container.clear()
                with progress_container:
                    ui.icon('error', size='64px', color='red')
                    ui.label('Fehler beim Lesen der Dateien').classes('text-h6 text-negative')
                    ui.label(str(e)).classes('text-sm text-grey-7')
                    ui.button('Schließen', on_click=dialog.close).props('color=primary')
                return

            # Build info about what will be synced
            sync_items = []
            if sync_docs:
                sync_items.append('Dokumentation')
            if sync_scripts:
                sync_items.append('Scripts')
            if sync_erd:
                sync_items.append('ERD')

            # Sync to BookStack
            bookstack_service = get_bookstack_service()
            success, result = bookstack_service.sync_database_to_bookstack(
                database,
                server,
                docs_content,
                scripts_content,
                erd_content
            )

            # Update dialog with result
            progress_container.clear()
            with progress_container:
                if success:
                    # Success message
                    ui.icon('check_circle', size='64px', color='green')
                    ui.label('Erfolgreich übertragen!').classes('text-h5 text-positive font-bold')

                    pages_count = len(sync_items)
                    pages_info = ' + '.join(sync_items)

                    ui.label(f'{database.name} → BookStack').classes('text-subtitle1')
                    ui.label(f'Inhalte: {pages_info}').classes('text-sm text-grey-7')
                    ui.label(f'{pages_count} {"Seite" if pages_count == 1 else "Seiten"} erstellt').classes('text-sm text-grey-7')

                    # Show BookStack link if available
                    if result and result.startswith('http'):
                        ui.link('In BookStack öffnen', result, new_tab=True).classes('text-primary')

                    logger.info(f"✓ Synced {database.name} to BookStack: {result}")

                    # Trigger refresh to update card
                    _force_refresh['needed'] = True
                else:
                    # Error message
                    ui.icon('error', size='64px', color='red')
                    ui.label('Übertragung fehlgeschlagen').classes('text-h6 text-negative')
                    ui.label(str(result)).classes('text-sm text-grey-7')
                    logger.error(f"BookStack sync failed: {result}")

                # Close button
                ui.button('Schließen', icon='close', on_click=dialog.close).props('color=primary')

        except Exception as e:
            logger.error(f"Error in sync thread: {e}")
            import traceback
            logger.error(traceback.format_exc())

            # Show error in dialog
            progress_container.clear()
            with progress_container:
                ui.icon('error', size='64px', color='red')
                ui.label('Unerwarteter Fehler').classes('text-h6 text-negative')
                ui.label(str(e)).classes('text-sm text-grey-7')
                ui.button('Schließen', on_click=dialog.close).props('color=primary')

    # Start sync in background thread
    thread = threading.Thread(target=sync_thread, daemon=True)
    thread.start()


