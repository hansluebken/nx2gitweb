"""
Cronjob management page for Ninox2Git
"""
from nicegui import ui
from datetime import datetime, timedelta
import asyncio
from ..database import get_db
from ..models.server import Server
from ..models.team import Team
from ..models.database import Database
from ..models.cronjob import Cronjob, CronjobType, IntervalUnit, SyncType
from ..models.user import User
from ..auth import create_audit_log
from .components import (
    NavHeader, Card, FormField, Toast, ConfirmDialog,
    EmptyState, StatusBadge, format_datetime, PRIMARY_COLOR, SUCCESS_COLOR, WARNING_COLOR
)


def render(user):
    """
    Render the cronjobs management page

    Args:
        user: Current user object
    """
    ui.colors(primary=PRIMARY_COLOR)

    # Navigation header
    NavHeader(user, 'cronjobs').render()

    # Main content
    with ui.column().classes('w-full p-6 gap-6').style('max-width: 1400px; margin: 0 auto;'):
        ui.label('Scheduled Sync Jobs').classes('text-h4 font-bold mb-4')
        
        # Ninox Docs Sync Section (global, not team-specific)
        with ui.card().classes('w-full p-4 mb-4'):
            with ui.row().classes('w-full items-center justify-between'):
                with ui.row().classes('items-center gap-2'):
                    ui.icon('menu_book', size='md').classes('text-primary')
                    ui.label('Ninox Documentation Sync').classes('text-h6 font-bold')
                
                ui.button(
                    'Add Docs Sync Job',
                    icon='add',
                    on_click=lambda: show_add_docs_sync_dialog(user)
                ).props('color=primary')
            
            ui.label('Automatically sync Ninox documentation (functions, API, printing) to GitHub').classes('text-grey-7 mt-2')
            
            # Container for docs sync jobs
            docs_jobs_container = ui.column().classes('w-full gap-2 mt-4')
            load_docs_sync_jobs(user, docs_jobs_container)
        
        ui.separator().classes('my-4')
        
        # Database Sync Section
        ui.label('Database Sync Jobs').classes('text-h6 font-bold')

        # Filter and selector container
        filter_container = ui.column().classes('w-full')
        cronjobs_container = ui.column().classes('w-full gap-4 mt-4')

        with filter_container:
            render_database_sync_section(user, cronjobs_container)


def render_database_sync_section(user, cronjobs_container):
    """Render database sync jobs section with filters"""
    db = get_db()
    try:
        # Get user's servers for the filter dropdowns
        if user.is_admin:
            servers = db.query(Server).filter(Server.is_active == True).all()
        else:
            servers = db.query(Server).filter(
                Server.user_id == user.id,
                Server.is_active == True
            ).all()

        # Store server info as dict (id -> name mapping) to use after db.close()
        server_options = {server.name: server.id for server in servers}
        user_server_ids = [s.id for s in servers]
        
    finally:
        db.close()
    
    # Store state for team filter
    filter_state = {
        'team_id_map': {}  # team_name -> team_id
    }

    # Filter row
    with ui.row().classes('w-full items-center gap-4 flex-wrap'):
        # Status filter
        status_select = ui.select(
            label='Status',
            options=['All', 'Active', 'Inactive'],
            value='All'
        ).classes('w-32')
        
        # Server filter (optional) - empty means show all
        server_select = ui.select(
            label='Filter by Server',
            options=['All Servers'] + list(server_options.keys()),
            value='All Servers',
            clearable=True
        ).classes('flex-1').style('min-width: 150px;')

        # Team filter (optional, depends on server) - empty means show all
        team_select = ui.select(
            label='Filter by Team',
            options=['All Teams'],
            value='All Teams',
            clearable=True
        ).classes('flex-1').style('min-width: 150px;')
        
        # Add button
        ui.button(
            'Add Cronjob',
            icon='add',
            on_click=lambda: show_add_cronjob_dialog_with_selection(user, cronjobs_container)
        ).props('color=primary')

    def load_all_jobs():
        """Load jobs based on current filters"""
        status_filter = status_select.value
        server_filter = server_select.value
        team_filter = team_select.value
        
        # Build query
        query_db = get_db()
        try:
            # Filter by sync_type = DATABASE (team-based syncs)
            query = query_db.query(Cronjob).filter(
                Cronjob.sync_type == SyncType.DATABASE
            )
            
            # Status filter
            if status_filter == 'Active':
                query = query.filter(Cronjob.is_active == True)
            elif status_filter == 'Inactive':
                query = query.filter(Cronjob.is_active == False)
            
            # Server filter (optional)
            if server_filter and server_filter != 'All Servers' and server_filter in server_options:
                server_id = server_options[server_filter]
                # Get team IDs for this server
                teams = query_db.query(Team).filter(Team.server_id == server_id).all()
                team_ids = [t.id for t in teams]
                if team_ids:
                    query = query.filter(Cronjob.team_id.in_(team_ids))
                else:
                    # No teams for this server = no results
                    query = query.filter(Cronjob.id == -1)
                
                # Further filter by team if selected
                if team_filter and team_filter != 'All Teams' and team_filter in filter_state['team_id_map']:
                    query = query.filter(Cronjob.team_id == filter_state['team_id_map'][team_filter])
            
            # For non-admin users, only show jobs for their servers' teams
            if not user.is_admin and user_server_ids:
                user_teams = query_db.query(Team).filter(Team.server_id.in_(user_server_ids)).all()
                user_team_ids = [t.id for t in user_teams]
                if user_team_ids:
                    query = query.filter(Cronjob.team_id.in_(user_team_ids))
                else:
                    query = query.filter(Cronjob.id == -1)
            
            jobs = query.order_by(Cronjob.created_at.desc()).all()
            
            # Get team and server info for display
            job_infos = []
            for job in jobs:
                team = query_db.query(Team).filter(Team.id == job.team_id).first()
                server = query_db.query(Server).filter(Server.id == team.server_id).first() if team else None
                job_infos.append({
                    'job': job,
                    'team': team,
                    'server': server
                })
            
        finally:
            query_db.close()
        
        # Render jobs
        cronjobs_container.clear()
        with cronjobs_container:
            if not job_infos:
                EmptyState.render(
                    icon='schedule',
                    title='No Jobs Found',
                    message='No database sync jobs match your filters. Create a new job with "Add Cronjob".',
                )
            else:
                ui.label(f'{len(job_infos)} job(s) found').classes('text-caption text-grey-7 mb-2')
                for info in job_infos:
                    render_cronjob_card_with_info(user, info['job'], info['team'], info['server'], cronjobs_container)
    
    def on_server_change(e=None):
        """Update team options when server changes"""
        selected = server_select.value
        if not selected or selected == 'All Servers':
            team_select.options = ['All Teams']
            team_select.value = 'All Teams'
            filter_state['team_id_map'] = {}
        elif selected in server_options:
            server_id = server_options[selected]
            query_db = get_db()
            try:
                teams = query_db.query(Team).filter(
                    Team.server_id == server_id,
                    Team.is_active == True
                ).all()
                filter_state['team_id_map'] = {t.name: t.id for t in teams}
                team_select.options = ['All Teams'] + list(filter_state['team_id_map'].keys())
                team_select.value = 'All Teams'
            finally:
                query_db.close()
        team_select.update()
        load_all_jobs()
    
    def on_filter_change(e=None):
        """Reload jobs when any filter changes"""
        load_all_jobs()
    
    # Register event handlers
    status_select.on('update:model-value', on_filter_change)
    server_select.on('update:model-value', on_server_change)
    team_select.on('update:model-value', on_filter_change)
    
    # Load initial jobs (show ALL jobs by default)
    load_all_jobs()


def show_add_cronjob_dialog_with_selection(user, container):
    """Show dialog to add a new cronjob with server/team selection"""
    
    # Load servers fresh from DB
    db = get_db()
    try:
        if user.is_admin:
            servers = db.query(Server).filter(Server.is_active == True).all()
        else:
            servers = db.query(Server).filter(
                Server.user_id == user.id,
                Server.is_active == True
            ).all()
        
        # Store as dict: name -> id
        server_options = {s.name: s.id for s in servers}
        server_names = list(server_options.keys())
    finally:
        db.close()
    
    if not server_names:
        Toast.error('No active servers available. Please add a server first.')
        return
    
    with ui.dialog() as dialog, ui.card().classes('w-full p-6').style('min-width: 600px;'):
        ui.label('Add Database Sync Job').classes('text-h5 font-bold mb-4')
        
        # Server selection
        server_select = ui.select(
            label='Server',
            options=server_names,
            value=server_names[0] if server_names else None
        ).classes('w-full')
        
        # Team selection (populated based on server)
        team_select = ui.select(
            label='Team',
            options=[],
            value=None
        ).classes('w-full')
        
        # Job name
        name_input = FormField.text(
            label='Job Name',
            value='',
            required=True
        )
        
        # Schedule type
        ui.label('Schedule Type').classes('font-bold mt-4')
        schedule_type = ui.toggle(
            ['Interval', 'Daily at specific time'],
            value='Daily at specific time'
        ).classes('w-full')
        
        # Interval options
        interval_container = ui.row().classes('w-full gap-2 mt-2')
        with interval_container:
            interval_value = ui.number(label='Every', value=1, min=1).classes('w-24')
            interval_unit = ui.select(
                label='Unit',
                options=['hours', 'days', 'weeks'],
                value='days'
            ).classes('flex-1')
        interval_container.visible = False
        
        # Daily time option
        time_container = ui.row().classes('w-full mt-2')
        with time_container:
            time_input = ui.input(label='Time (HH:MM)', value='22:00').classes('w-full')
        
        def on_schedule_change(e):
            interval_container.visible = schedule_type.value == 'Interval'
            time_container.visible = schedule_type.value == 'Daily at specific time'
        
        schedule_type.on('update:model-value', on_schedule_change)
        
        error_label = ui.label('').classes('text-negative mt-2')
        error_label.visible = False
        
        # Team ID map
        team_id_map = {}
        
        def update_teams():
            nonlocal team_id_map
            if server_select.value and server_select.value in server_options:
                server_id = server_options[server_select.value]
                query_db = get_db()
                try:
                    teams = query_db.query(Team).filter(
                        Team.server_id == server_id,
                        Team.is_active == True
                    ).all()
                    team_id_map = {t.name: t.id for t in teams}
                    team_select.options = list(team_id_map.keys())
                    team_select.value = list(team_id_map.keys())[0] if team_id_map else None
                finally:
                    query_db.close()
                team_select.update()
        
        server_select.on('update:model-value', lambda e: update_teams())
        update_teams()  # Initial load
        
        def handle_save():
            if not team_select.value or team_select.value not in team_id_map:
                error_label.text = 'Please select a team'
                error_label.visible = True
                return
            
            name = name_input.value.strip() if name_input.value else ''
            if not name:
                error_label.text = 'Please enter a job name'
                error_label.visible = True
                return
            
            team_id = team_id_map[team_select.value]
            
            # Create job
            query_db = get_db()
            try:
                if schedule_type.value == 'Interval':
                    job = Cronjob(
                        name=name,
                        team_id=team_id,
                        sync_type=SyncType.DATABASE,
                        job_type=CronjobType.INTERVAL,
                        interval_value=int(interval_value.value),
                        interval_unit=IntervalUnit(interval_unit.value),
                        next_run=calculate_next_run_interval(int(interval_value.value), interval_unit.value),
                        is_active=True
                    )
                else:
                    daily_time = time_input.value.strip()
                    try:
                        hour, minute = map(int, daily_time.split(':'))
                        if not (0 <= hour <= 23 and 0 <= minute <= 59):
                            raise ValueError()
                    except:
                        error_label.text = 'Invalid time format (HH:MM)'
                        error_label.visible = True
                        return
                    
                    job = Cronjob(
                        name=name,
                        team_id=team_id,
                        sync_type=SyncType.DATABASE,
                        job_type=CronjobType.DAILY_TIME,
                        daily_time=daily_time,
                        next_run=calculate_next_run_daily(daily_time),
                        is_active=True
                    )
                
                query_db.add(job)
                query_db.commit()
                
                create_audit_log(
                    db=query_db,
                    user_id=user.id,
                    action='cronjob_created',
                    resource_type='cronjob',
                    resource_id=job.id,
                    details=f'Created cronjob: {name}',
                    auto_commit=True
                )
            finally:
                query_db.close()
            
            dialog.close()
            Toast.success(f'Cronjob "{name}" created!')
            ui.navigate.to('/cronjobs')  # Refresh page
        
        with ui.row().classes('w-full justify-end gap-2 mt-4'):
            ui.button('Cancel', on_click=dialog.close).props('flat')
            ui.button('Create', on_click=handle_save).props('color=primary')
    
    dialog.open()


def render_cronjob_card_with_info(user, cronjob, team, server, container):
    """Render a cronjob card with team/server info"""
    from ..services.background_sync import get_sync_manager
    
    # Check if bulk sync is active for this team
    sync_manager = get_sync_manager()
    is_syncing = sync_manager.is_bulk_sync_active(cronjob.team_id) if cronjob.team_id else False
    completed, total = sync_manager.get_bulk_sync_progress() if is_syncing else (0, 0)
    
    with ui.card().classes('w-full p-4'):
        with ui.row().classes('w-full items-start justify-between'):
            # Cronjob info
            with ui.column().classes('flex-1 gap-2'):
                with ui.row().classes('items-center gap-2'):
                    # Show spinner if syncing
                    if is_syncing:
                        ui.spinner(size='sm', color='primary')
                    else:
                        ui.icon('schedule', size='md').classes('text-primary')
                    ui.label(cronjob.name).classes('text-h6 font-bold')
                    StatusBadge.render(
                        'Active' if cronjob.is_active else 'Inactive',
                        cronjob.is_active
                    )
                
                # Server/Team info
                with ui.row().classes('items-center gap-2'):
                    if server:
                        ui.chip(server.name, icon='dns').props('dense outline color=grey')
                    if team:
                        ui.chip(team.name, icon='group').props('dense outline color=primary')

                ui.label(f'Schedule: {cronjob.get_schedule_description()}').classes('text-grey-7')

                # Show sync progress if syncing
                if is_syncing:
                    with ui.row().classes('items-center gap-2'):
                        ui.label(f'Syncing: {completed}/{total} databases').classes('text-caption text-primary font-bold')
                else:
                    with ui.row().classes('gap-4'):
                        if cronjob.last_run:
                            ui.label(f'Last Run: {format_datetime(cronjob.last_run)}').classes('text-caption text-grey-7')
                        if cronjob.next_run:
                            ui.label(f'Next Run: {format_datetime(cronjob.next_run)}').classes('text-caption text-grey-7')

                    if cronjob.last_status:
                        status_color = SUCCESS_COLOR if cronjob.last_status == 'success' else ('orange' if cronjob.last_status == 'partial' else 'red')
                        ui.label(f'Last Status: {cronjob.last_status}').style(f'color: {status_color};').classes('text-caption font-bold')

                ui.label(f'Total Runs: {cronjob.run_count}').classes('text-caption text-grey-7')

            # Actions
            with ui.column().classes('gap-2'):
                # Disable Run Now if syncing
                ui.button(
                    'Syncing...' if is_syncing else 'Run Now',
                    icon='sync' if is_syncing else 'play_arrow',
                    on_click=lambda j=cronjob, t=team: run_cronjob_now(user, t, j, container)
                ).props(f'flat dense color=primary {"loading disabled" if is_syncing else ""}')

                ui.button(
                    'Edit',
                    icon='edit',
                    on_click=lambda j=cronjob, t=team: show_edit_cronjob_dialog(user, t, j, container)
                ).props('flat dense')

                if cronjob.is_active:
                    ui.button(
                        'Deactivate',
                        icon='pause',
                        on_click=lambda j=cronjob: toggle_cronjob_status(user, j, False, container)
                    ).props('flat dense color=warning')
                else:
                    ui.button(
                        'Activate',
                        icon='play_arrow',
                        on_click=lambda j=cronjob: toggle_cronjob_status(user, j, True, container)
                    ).props('flat dense color=positive')

                ui.button(
                    'Delete',
                    icon='delete',
                    on_click=lambda j=cronjob: confirm_delete_cronjob(user, j, container)
                ).props('flat dense color=negative')


def load_cronjobs(user, team, container):
    """
    Load and display cronjobs for a team with auto-refresh when syncing.
    Uses @ui.refreshable pattern like the sync page.
    """
    from ..services.background_sync import get_sync_manager
    import logging
    
    logger = logging.getLogger(__name__)
    
    container.clear()
    
    # Handle both Team objects and team_id integers
    team_id = team.id if hasattr(team, 'id') else team
    
    # Store timer reference
    refresh_timer_holder = {'timer': None}
    
    @ui.refreshable
    def cronjob_list():
        """Refreshable cronjob list - call cronjob_list.refresh() to update"""
        sync_manager = get_sync_manager()
        bulk_sync_active = sync_manager.is_bulk_sync_active(team_id)
        completed, total = sync_manager.get_bulk_sync_progress() if bulk_sync_active else (0, 0)
        
        db = get_db()
        try:
            # Reload team from DB
            team_obj = db.query(Team).filter(Team.id == team_id).first()
            if not team_obj:
                EmptyState.render(
                    icon='error',
                    title='Team not found',
                    message='The selected team could not be found.',
                )
                return
                
            cronjobs = db.query(Cronjob).filter(
                Cronjob.team_id == team_id
            ).order_by(Cronjob.created_at.desc()).all()

            if not cronjobs:
                EmptyState.render(
                    icon='schedule',
                    title='No Scheduled Jobs',
                    message='No cronjobs configured for this team yet. Add your first scheduled sync job!',
                )
            else:
                for cronjob in cronjobs:
                    render_cronjob_card(user, team_obj, cronjob, container, bulk_sync_active, completed, total)
        finally:
            db.close()
    
    def check_and_refresh():
        """Timer callback - check if still syncing and refresh"""
        sync_manager = get_sync_manager()
        bulk_active = sync_manager.is_bulk_sync_active(team_id)
        
        if bulk_active:
            # Still syncing - refresh the UI
            completed, total = sync_manager.get_bulk_sync_progress()
            logger.info(f"Cronjob auto-refresh: {completed}/{total}, bulk={bulk_active}")
            cronjob_list.refresh()
        else:
            # Done - stop timer and do final refresh
            logger.info("Cronjob sync complete - stopping timer")
            if refresh_timer_holder['timer']:
                refresh_timer_holder['timer'].cancel()
                refresh_timer_holder['timer'] = None
            cronjob_list.refresh()
    
    # Render initial cronjob list
    with container:
        cronjob_list()
        
        # Setup auto-refresh timer (always, will self-cancel when not needed)
        refresh_timer_holder['timer'] = ui.timer(2.0, check_and_refresh)


def render_cronjob_card(user, team, cronjob, container, bulk_sync_active=False, completed=0, total=0):
    """Render a cronjob card with sync status indicator"""
    # Use passed-in sync status (from refreshable parent)
    is_syncing = bulk_sync_active
    
    with ui.card().classes('w-full p-4'):
        with ui.row().classes('w-full items-start justify-between'):
            # Cronjob info
            with ui.column().classes('flex-1 gap-2'):
                with ui.row().classes('items-center gap-2'):
                    # Show spinner if syncing, otherwise schedule icon
                    if is_syncing:
                        ui.spinner(size='sm', color='primary')
                    else:
                        ui.icon('schedule', size='md').classes('text-primary')
                    ui.label(cronjob.name).classes('text-h6 font-bold')
                    StatusBadge.render(
                        'Active' if cronjob.is_active else 'Inactive',
                        cronjob.is_active
                    )

                ui.label(f'Schedule: {cronjob.get_schedule_description()}').classes('text-grey-7')

                if cronjob.description:
                    ui.label(cronjob.description).classes('text-grey-7')

                # Show sync progress if syncing
                if is_syncing:
                    with ui.row().classes('items-center gap-2'):
                        ui.label(f'Syncing: {completed}/{total} databases').classes('text-caption text-primary font-bold')
                        ui.button(
                            'View Progress',
                            icon='open_in_new',
                            on_click=lambda t=team: ui.navigate.to(f'/sync?team={t.id}')
                        ).props('flat dense size=sm color=primary')
                else:
                    with ui.row().classes('gap-4'):
                        if cronjob.last_run:
                            ui.label(f'Last Run: {format_datetime(cronjob.last_run)}').classes('text-caption text-grey-7')
                        if cronjob.next_run:
                            ui.label(f'Next Run: {format_datetime(cronjob.next_run)}').classes('text-caption text-grey-7')

                    if cronjob.last_status:
                        status_color = SUCCESS_COLOR if cronjob.last_status == 'success' else ('orange' if cronjob.last_status == 'partial' else 'red')
                        ui.label(f'Last Status: {cronjob.last_status}').style(f'color: {status_color};').classes('text-caption font-bold')

                ui.label(f'Total Runs: {cronjob.run_count}').classes('text-caption text-grey-7')

            # Actions
            with ui.column().classes('gap-2'):
                # Disable Run Now if already syncing
                run_btn = ui.button(
                    'Syncing...' if is_syncing else 'Run Now',
                    icon='sync' if is_syncing else 'play_arrow',
                    on_click=lambda j=cronjob: run_cronjob_now(user, team, j, container)
                ).props(f'flat dense color=primary {"loading disabled" if is_syncing else ""}')

                ui.button(
                    'Edit',
                    icon='edit',
                    on_click=lambda j=cronjob: show_edit_cronjob_dialog(user, team, j, container)
                ).props('flat dense')

                if cronjob.is_active:
                    ui.button(
                        'Deactivate',
                        icon='pause',
                        on_click=lambda j=cronjob: toggle_cronjob_status(user, j, False, container)
                    ).props('flat dense color=warning')
                else:
                    ui.button(
                        'Activate',
                        icon='play_arrow',
                        on_click=lambda j=cronjob: toggle_cronjob_status(user, j, True, container)
                    ).props('flat dense color=positive')

                ui.button(
                    'Delete',
                    icon='delete',
                    on_click=lambda j=cronjob: confirm_delete_cronjob(user, j, container)
                ).props('flat dense color=negative')


def show_add_cronjob_dialog(user, server, team_id, container):
    """Show dialog to add a new cronjob"""
    import logging
    logger = logging.getLogger(__name__)
    
    # Load team from DB
    db = get_db()
    team = db.query(Team).filter(Team.id == team_id).first()
    db.close()
    
    if not team:
        Toast.error('Team not found')
        return
        
    logger.info(f"=== SHOW ADD CRONJOB DIALOG === Team: {team.name}, Team ID: {team.id}")

    with ui.dialog() as dialog, ui.card().classes('w-full p-6').style('min-width: 600px;'):
        ui.label('Add Scheduled Sync Job').classes('text-h5 font-bold mb-4')

        name_input = FormField.text(
            label='Job Name',
            placeholder='e.g. "Daily Backup" or "Weekly Sync"',
            required=True
        )

        description_input = FormField.text(
            label='Description (Optional)',
            placeholder='Describe what this job does'
        )

        # Job type selector with clear labels
        job_type_options = {
            'Interval (Every X hours/days/weeks)': 'interval',
            'Daily at specific time': 'daily_time'
        }
        job_type_select = ui.select(
            label='Schedule Type',
            options=list(job_type_options.keys()),
            value=list(job_type_options.keys())[0]
        ).classes('w-full')

        # Interval settings (shown when type = interval)
        interval_container = ui.column().classes('w-full gap-4')

        with interval_container:
            with ui.row().classes('w-full gap-4'):
                interval_value_input = ui.number(
                    label='Interval Value',
                    value=5,
                    min=5,
                    max=100,
                    step=5
                ).classes('flex-1')

                interval_unit_select = ui.select(
                    label='Unit',
                    options=['minutes', 'hours', 'days', 'weeks'],
                    value='minutes'
                ).classes('flex-1')

            ui.label('Note: For minutes, value must be a multiple of 5 (5, 10, 15, ...)').classes('text-caption text-grey-7')

        # Daily time settings (shown when type = daily_time)
        daily_time_container = ui.column().classes('w-full gap-4')
        daily_time_container.visible = False

        with daily_time_container:
            time_input = ui.input(
                label='Time (HH:MM)',
                placeholder='14:30'
            ).classes('w-full')

        # Toggle visibility based on job type
        def on_job_type_change():
            selected_type = job_type_options[job_type_select.value]
            if selected_type == 'interval':
                interval_container.visible = True
                daily_time_container.visible = False
            else:
                interval_container.visible = False
                daily_time_container.visible = True

        job_type_select.on('update:model-value', lambda: on_job_type_change())

        error_label = ui.label('').classes('text-negative mt-2')
        error_label.visible = False

        def handle_save():
            """Handle cronjob creation"""
            import logging
            logger = logging.getLogger(__name__)
            logger.info("=== HANDLE_SAVE CRONJOB CALLED ===")

            name = name_input.value.strip()
            description = description_input.value.strip() or None
            # Get actual value from the options dict
            job_type = job_type_options[job_type_select.value]

            logger.info(f"Name: {name}, Type: {job_type}, Selected: {job_type_select.value}")

            if not name:
                error_label.text = 'Please enter a job name'
                error_label.visible = True
                return

            # Validate based on type
            if job_type == 'interval':
                interval_value = int(interval_value_input.value)
                interval_unit = interval_unit_select.value

                # Validate minutes must be multiple of 5
                if interval_unit == 'minutes':
                    if interval_value < 5 or interval_value % 5 != 0:
                        error_label.text = 'Minute intervals must be multiples of 5 (5, 10, 15, 20, ...)'
                        error_label.visible = True
                        return
                elif interval_value < 1:
                    error_label.text = 'Interval value must be at least 1'
                    error_label.visible = True
                    return

                try:
                    db = get_db()

                    # Calculate next run
                    next_run = calculate_next_run_interval(interval_value, interval_unit)

                    cronjob = Cronjob(
                        team_id=team.id,
                        name=name,
                        description=description,
                        job_type=CronjobType.INTERVAL,
                        interval_value=interval_value,
                        interval_unit=IntervalUnit[interval_unit.upper()],
                        daily_time=None,
                        is_active=True,
                        next_run=next_run,
                        run_count=0
                    )

                    db.add(cronjob)
                    db.commit()

                    # Create audit log
                    create_audit_log(
                        db=db,
                        user_id=user.id,
                        action='cronjob_created',
                        resource_type='cronjob',
                        resource_id=cronjob.id,
                        details=f'Created cronjob: {name} for team {team.name}',
                        auto_commit=True
                    )

                    db.close()

                    Toast.success(f'Cronjob "{name}" created successfully!')
                    dialog.close()
                    load_cronjobs(user, team, container)

                except Exception as e:
                    error_label.text = f'Error creating cronjob: {str(e)}'
                    error_label.visible = True

            else:  # daily_time
                daily_time = time_input.value.strip()

                # Validate time format
                import re
                if not re.match(r'^\d{1,2}:\d{2}$', daily_time):
                    error_label.text = 'Time must be in HH:MM format (e.g. 14:30)'
                    error_label.visible = True
                    return

                try:
                    db = get_db()

                    # Calculate next run
                    next_run = calculate_next_run_daily(daily_time)

                    cronjob = Cronjob(
                        team_id=team.id,
                        name=name,
                        description=description,
                        job_type=CronjobType.DAILY_TIME,
                        interval_value=None,
                        interval_unit=None,
                        daily_time=daily_time,
                        is_active=True,
                        next_run=next_run,
                        run_count=0
                    )

                    db.add(cronjob)
                    db.commit()

                    # Create audit log
                    create_audit_log(
                        db=db,
                        user_id=user.id,
                        action='cronjob_created',
                        resource_type='cronjob',
                        resource_id=cronjob.id,
                        details=f'Created daily cronjob: {name} for team {team.name}',
                        auto_commit=True
                    )

                    db.close()

                    Toast.success(f'Cronjob "{name}" created successfully!')
                    dialog.close()
                    load_cronjobs(user, team, container)

                except Exception as e:
                    error_label.text = f'Error creating cronjob: {str(e)}'
                    error_label.visible = True

        with ui.row().classes('w-full justify-end gap-2 mt-4'):
            ui.button('Cancel', on_click=dialog.close).props('flat')
            ui.button('Create Cronjob', on_click=handle_save, color='primary')

    dialog.open()


def show_edit_cronjob_dialog(user, team, cronjob, container):
    """Show dialog to edit a cronjob"""
    with ui.dialog() as dialog, ui.card().classes('w-full p-6').style('min-width: 600px;'):
        ui.label('Edit Scheduled Sync Job').classes('text-h5 font-bold mb-4')

        name_input = FormField.text(
            label='Job Name',
            value=cronjob.name,
            required=True
        )

        description_input = FormField.text(
            label='Description (Optional)',
            value=cronjob.description or ''
        )

        # Show current configuration (read-only display)
        with ui.card().classes('w-full p-4 bg-grey-1'):
            ui.label('Current Schedule:').classes('font-bold mb-2')
            ui.label(cronjob.get_schedule_description()).classes('text-grey-7')
            ui.label('(To change schedule, delete and create a new job)').classes('text-caption text-grey-7')

        error_label = ui.label('').classes('text-negative mt-2')
        error_label.visible = False

        def handle_save_edit():
            """Handle cronjob update"""
            name = name_input.value.strip()
            description = description_input.value.strip() or None

            if not name:
                error_label.text = 'Please enter a job name'
                error_label.visible = True
                return

            try:
                db = get_db()
                job_obj = db.query(Cronjob).filter(Cronjob.id == cronjob.id).first()
                job_obj.name = name
                job_obj.description = description
                db.commit()

                # Create audit log
                create_audit_log(
                    db=db,
                    user_id=user.id,
                    action='cronjob_updated',
                    resource_type='cronjob',
                    resource_id=cronjob.id,
                    details=f'Updated cronjob: {name}',
                    auto_commit=True
                )

                db.close()

                Toast.success(f'Cronjob "{name}" updated successfully!')
                dialog.close()
                # Refresh page to reload the job list
                ui.navigate.to('/cronjobs')

            except Exception as e:
                error_label.text = f'Error updating cronjob: {str(e)}'
                error_label.visible = True

        with ui.row().classes('w-full justify-end gap-2 mt-4'):
            ui.button('Cancel', on_click=dialog.close).props('flat')
            ui.button('Save Changes', on_click=handle_save_edit, color='primary')

    dialog.open()


def toggle_cronjob_status(user, cronjob, is_active, container):
    """Toggle cronjob active status"""
    try:
        db = get_db()
        job_obj = db.query(Cronjob).filter(Cronjob.id == cronjob.id).first()
        job_obj.is_active = is_active

        # Recalculate next_run if activating
        if is_active:
            if job_obj.job_type == CronjobType.INTERVAL:
                job_obj.next_run = calculate_next_run_interval(
                    job_obj.interval_value,
                    job_obj.interval_unit.value
                )
            else:
                job_obj.next_run = calculate_next_run_daily(job_obj.daily_time)
        else:
            job_obj.next_run = None

        db.commit()

        # Create audit log
        action = 'cronjob_activated' if is_active else 'cronjob_deactivated'
        create_audit_log(
            db=db,
            user_id=user.id,
            action=action,
            resource_type='cronjob',
            resource_id=cronjob.id,
            details=f'{"Activated" if is_active else "Deactivated"} cronjob: {cronjob.name}',
            auto_commit=True
        )
        db.close()

        status_text = 'activated' if is_active else 'deactivated'
        Toast.success(f'Cronjob "{cronjob.name}" {status_text} successfully!')

        # Refresh page to reload the job list
        ui.navigate.to('/cronjobs')

    except Exception as e:
        Toast.error(f'Error updating cronjob: {str(e)}')


def confirm_delete_cronjob(user, cronjob, container):
    """Confirm and delete a cronjob"""
    def handle_delete():
        try:
            db = get_db()

            # Create audit log before deletion
            create_audit_log(
                db=db,
                user_id=user.id,
                action='cronjob_deleted',
                resource_type='cronjob',
                resource_id=cronjob.id,
                details=f'Deleted cronjob: {cronjob.name}',
                auto_commit=True
            )

            # Delete cronjob
            db.query(Cronjob).filter(Cronjob.id == cronjob.id).delete()
            db.commit()
            db.close()

            Toast.success(f'Cronjob "{cronjob.name}" deleted successfully!')
            # Refresh page to reload the job list
            ui.navigate.to('/cronjobs')

        except Exception as e:
            Toast.error(f'Error deleting cronjob: {str(e)}')

    ConfirmDialog.show(
        title='Delete Cronjob',
        message=f'Are you sure you want to delete cronjob "{cronjob.name}"?',
        on_confirm=handle_delete,
        confirm_text='Delete',
        danger=True
    )


def run_cronjob_now(user, team, cronjob, container):
    """
    Manually execute a cronjob now using BackgroundSyncManager.
    Works exactly like "Sync All" in the sync UI - no modal, just toast notifications.
    """
    import logging
    from ..services.background_sync import get_sync_manager
    from ..models.server import Server
    
    logger = logging.getLogger(__name__)

    # Get sync manager
    sync_manager = get_sync_manager()
    
    # Check if bulk sync is already running for this team
    if sync_manager.is_bulk_sync_active(cronjob.team_id):
        Toast.warning('Bulk sync already in progress for this team')
        return

    # Get databases, server, team fresh from DB
    db = get_db()
    try:
        team_obj = db.query(Team).filter(Team.id == cronjob.team_id).first()
        if not team_obj:
            Toast.error('Team not found')
            return
            
        server = db.query(Server).filter(Server.id == team_obj.server_id).first()
        if not server:
            Toast.error('Server not found')
            return

        databases = db.query(Database).filter(
            Database.team_id == cronjob.team_id,
            Database.is_excluded == False
        ).all()
        
        total_count = len(databases)
        
        if total_count == 0:
            Toast.warning('No databases to sync (all are excluded)')
            return

        # Start bulk sync mode
        sync_manager.start_bulk_sync(team_obj.id, total_count)
        
        # Start background syncs for all databases
        started_count = 0
        skipped_count = 0
        
        for database in databases:
            if sync_manager.is_syncing(database.id):
                skipped_count += 1
                logger.info(f"Skipping {database.name} - already syncing")
            else:
                started = sync_manager.start_sync(user, server, team_obj, database)
                if started:
                    started_count += 1
                    logger.info(f"Started background sync for {database.name}")
                else:
                    skipped_count += 1
        
        # Show result (same as Sync All)
        if started_count > 0:
            Toast.info(f'Started bulk sync for {started_count} databases - runs in background')
        
        if skipped_count > 0:
            Toast.warning(f'{skipped_count} databases already syncing')
        
        # If no syncs started, end bulk sync mode
        if started_count == 0:
            sync_manager.end_bulk_sync()
        
        # Update cronjob record - only update last_run, NOT status
        # Status will be updated when background sync completes
        job_obj = db.query(Cronjob).filter(Cronjob.id == cronjob.id).first()
        if job_obj:
            job_obj.last_run = datetime.utcnow()
            # Don't change last_status here - sync runs in background
            # Don't increment run_count - that's for scheduled runs only
            db.commit()
            
            # Create audit log
            create_audit_log(
                db=db,
                user_id=user.id,
                action='cronjob_manual_run',
                resource_type='cronjob',
                resource_id=cronjob.id,
                details=f'Manual run: {cronjob.name} - {started_count} syncs started',
                auto_commit=True
            )
        
        # Store team_id before closing db
        reload_team_id = team_obj.id
        
    finally:
        db.close()
    
    # Reload cronjobs list to show spinners (use team_id, not detached object)
    load_cronjobs(user, reload_team_id, container)


def calculate_next_run_interval(interval_value, interval_unit):
    """Calculate next run time for interval-based cronjob"""
    now = datetime.utcnow()

    if interval_unit == 'minutes' or interval_unit == IntervalUnit.MINUTES.value:
        return now + timedelta(minutes=interval_value)
    elif interval_unit == 'hours' or interval_unit == IntervalUnit.HOURS.value:
        return now + timedelta(hours=interval_value)
    elif interval_unit == 'days' or interval_unit == IntervalUnit.DAYS.value:
        return now + timedelta(days=interval_value)
    elif interval_unit == 'weeks' or interval_unit == IntervalUnit.WEEKS.value:
        return now + timedelta(weeks=interval_value)
    else:
        return now + timedelta(days=1)


def calculate_next_run_daily(daily_time):
    """Calculate next run time for daily cronjob at specific time"""
    now = datetime.utcnow()
    hour, minute = map(int, daily_time.split(':'))

    # Today at specified time
    next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

    # If time has passed today, schedule for tomorrow
    if next_run <= now:
        next_run += timedelta(days=1)

    return next_run


# ============================================================================
# Ninox Docs Sync Jobs
# ============================================================================

def load_docs_sync_jobs(user, container):
    """Load and display Ninox docs sync jobs with auto-refresh"""
    from ..services.background_sync import get_sync_manager
    import logging
    
    logger = logging.getLogger(__name__)
    container.clear()
    
    # Check if docs sync is running
    sync_manager = get_sync_manager()
    is_syncing = sync_manager.is_docs_sync_active()
    progress = sync_manager.get_docs_sync_progress() if is_syncing else None
    
    db = get_db()
    try:
        # Get docs sync jobs for this user
        jobs = db.query(Cronjob).filter(
            Cronjob.user_id == user.id,
            Cronjob.sync_type == SyncType.NINOX_DOCS
        ).order_by(Cronjob.created_at.desc()).all()
        
        if not jobs:
            with container:
                ui.label('No docs sync jobs configured yet.').classes('text-grey-7 text-sm')
        else:
            with container:
                for job in jobs:
                    render_docs_sync_card(user, job, container, is_syncing, progress)
    finally:
        db.close()
    
    # Auto-refresh while syncing
    if is_syncing:
        def check_and_refresh():
            if sync_manager.is_docs_sync_active():
                load_docs_sync_jobs(user, container)
            else:
                # Done - final refresh and stop timer
                load_docs_sync_jobs(user, container)
                refresh_timer.active = False
                logger.info("Docs sync complete - stopping refresh timer")
        
        refresh_timer = ui.timer(1.0, check_and_refresh)


def render_docs_sync_card(user, cronjob, container, is_syncing=False, progress=None):
    """Render a docs sync job card with sync status"""
    # Check if THIS job is the one syncing
    job_is_syncing = is_syncing and progress and progress.job_id == cronjob.id
    
    with ui.card().classes('w-full p-3 bg-grey-1'):
        with ui.row().classes('w-full items-center justify-between'):
            with ui.row().classes('items-center gap-2'):
                # Show spinner if this job is syncing
                if job_is_syncing:
                    ui.spinner(size='sm', color='primary')
                else:
                    ui.icon('menu_book', size='sm').classes('text-primary')
                ui.label(cronjob.name).classes('font-bold')
                StatusBadge.render(
                    'Active' if cronjob.is_active else 'Inactive',
                    cronjob.is_active
                )
            
            with ui.row().classes('gap-1'):
                # Disable Run Now if syncing
                ui.button(
                    icon='sync' if job_is_syncing else 'play_arrow',
                    on_click=lambda j=cronjob: run_docs_sync_now(user, j, container)
                ).props(f'flat dense color=primary {"loading disabled" if is_syncing else ""}').tooltip('Syncing...' if job_is_syncing else 'Run Now')
                
                if cronjob.is_active:
                    ui.button(
                        icon='pause',
                        on_click=lambda j=cronjob: toggle_docs_sync_status(user, j, False, container)
                    ).props('flat dense color=warning').tooltip('Deactivate')
                else:
                    ui.button(
                        icon='play_arrow',
                        on_click=lambda j=cronjob: toggle_docs_sync_status(user, j, True, container)
                    ).props('flat dense color=positive').tooltip('Activate')
                
                ui.button(
                    icon='delete',
                    on_click=lambda j=cronjob: confirm_delete_docs_sync(user, j, container)
                ).props('flat dense color=negative').tooltip('Delete')
        
        # Show sync progress if this job is syncing
        if job_is_syncing and progress:
            with ui.row().classes('items-center gap-2 mt-2'):
                phase_text = {
                    'init': 'Starting...',
                    'scraping': f'Downloading: {progress.current}/{progress.total}',
                    'creating': f'Creating files: {progress.current}/3',
                    'uploading': 'Uploading to GitHub...'
                }.get(progress.phase, progress.message)
                ui.label(phase_text).classes('text-caption text-primary font-bold')
        else:
            with ui.row().classes('gap-4 mt-2'):
                ui.label(f'Schedule: {cronjob.get_schedule_description()}').classes('text-caption text-grey-7')
                if cronjob.last_run:
                    ui.label(f'Last: {format_datetime(cronjob.last_run)}').classes('text-caption text-grey-7')
                if cronjob.next_run:
                    ui.label(f'Next: {format_datetime(cronjob.next_run)}').classes('text-caption text-grey-7')
                if cronjob.last_status:
                    status_color = SUCCESS_COLOR if cronjob.last_status == 'success' else 'red'
                    ui.label(f'Status: {cronjob.last_status}').style(f'color: {status_color};').classes('text-caption font-bold')


def show_add_docs_sync_dialog(user):
    """Show dialog to add a new docs sync job"""
    with ui.dialog() as dialog, ui.card().classes('w-full p-6').style('min-width: 500px;'):
        ui.label('Add Ninox Docs Sync Job').classes('text-h5 font-bold mb-4')
        
        ui.label('Automatically download Ninox documentation and upload to GitHub.').classes('text-grey-7 mb-4')
        
        name_input = FormField.text(
            label='Job Name',
            value='Ninox Docs Sync',
            required=True
        )
        
        # Schedule - daily at specific time
        ui.label('Schedule').classes('font-bold mt-4')
        time_input = ui.input(
            label='Daily at (HH:MM)',
            value='13:00'
        ).classes('w-full')
        
        error_label = ui.label('').classes('text-negative mt-2')
        error_label.visible = False
        
        def handle_save():
            name = name_input.value.strip() if name_input.value else ''
            daily_time = time_input.value.strip() if time_input.value else ''
            
            if not name:
                error_label.text = 'Please enter a job name'
                error_label.visible = True
                return
            
            # Validate time format
            try:
                hour, minute = map(int, daily_time.split(':'))
                if not (0 <= hour <= 23 and 0 <= minute <= 59):
                    raise ValueError()
            except:
                error_label.text = 'Invalid time format. Use HH:MM (e.g., 13:00)'
                error_label.visible = True
                return
            
            # Create cronjob
            db = get_db()
            try:
                cronjob = Cronjob(
                    name=name,
                    description='Sync Ninox documentation to GitHub',
                    user_id=user.id,
                    team_id=None,  # Not team-specific
                    sync_type=SyncType.NINOX_DOCS,
                    job_type=CronjobType.DAILY_TIME,
                    daily_time=daily_time,
                    next_run=calculate_next_run_daily(daily_time),
                    is_active=True
                )
                db.add(cronjob)
                db.commit()
                
                create_audit_log(
                    db=db,
                    user_id=user.id,
                    action='cronjob_created',
                    resource_type='cronjob',
                    resource_id=cronjob.id,
                    details=f'Created docs sync job: {name}',
                    auto_commit=True
                )
            finally:
                db.close()
            
            dialog.close()
            Toast.success(f'Docs sync job "{name}" created!')
            ui.navigate.to('/cronjobs')  # Refresh page
        
        with ui.row().classes('w-full justify-end gap-2 mt-4'):
            ui.button('Cancel', on_click=dialog.close).props('flat')
            ui.button('Create Job', on_click=handle_save).props('color=primary')
    
    dialog.open()


def run_docs_sync_now(user, cronjob, container):
    """
    Manually run a docs sync job using BackgroundSyncManager.
    Works like Database Sync - runs in background with spinner in card.
    """
    from ..services.background_sync import get_sync_manager
    
    sync_manager = get_sync_manager()
    
    # Check if already running
    if sync_manager.is_docs_sync_active():
        Toast.warning('Docs sync already in progress')
        return
    
    # Start background sync
    started = sync_manager.start_docs_sync(user.id, cronjob.id)
    
    if started:
        Toast.info('Started docs sync - runs in background')
        # Reload to show spinner
        load_docs_sync_jobs(user, container)
    else:
        Toast.warning('Could not start docs sync')


def toggle_docs_sync_status(user, cronjob, is_active, container):
    """Toggle docs sync job active status"""
    db = get_db()
    try:
        job = db.query(Cronjob).filter(Cronjob.id == cronjob.id).first()
        job.is_active = is_active
        db.commit()
        
        create_audit_log(
            db=db,
            user_id=user.id,
            action='cronjob_updated',
            resource_type='cronjob',
            resource_id=cronjob.id,
            details=f'{"Activated" if is_active else "Deactivated"} docs sync job: {cronjob.name}',
            auto_commit=True
        )
    finally:
        db.close()
    
    Toast.success(f'Job {"activated" if is_active else "deactivated"}!')
    load_docs_sync_jobs(user, container)


def confirm_delete_docs_sync(user, cronjob, container):
    """Confirm and delete a docs sync job"""
    def handle_delete():
        db = get_db()
        try:
            job = db.query(Cronjob).filter(Cronjob.id == cronjob.id).first()
            if job:
                db.delete(job)
                db.commit()
                
                create_audit_log(
                    db=db,
                    user_id=user.id,
                    action='cronjob_deleted',
                    resource_type='cronjob',
                    resource_id=cronjob.id,
                    details=f'Deleted docs sync job: {cronjob.name}',
                    auto_commit=True
                )
        finally:
            db.close()
        
        Toast.success('Job deleted!')
        load_docs_sync_jobs(user, container)
    
    ConfirmDialog.show(
        title='Delete Docs Sync Job',
        message=f'Are you sure you want to delete "{cronjob.name}"?',
        on_confirm=handle_delete,
        confirm_text='Delete',
        danger=True
    )
