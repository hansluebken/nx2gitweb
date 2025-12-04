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
from ..models.cronjob import Cronjob, CronjobType, IntervalUnit
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

        # Server and team selector
        selector_container = ui.column().classes('w-full')
        cronjobs_container = ui.column().classes('w-full gap-4 mt-4')

        with selector_container:
            render_selectors(user, cronjobs_container)


def render_selectors(user, cronjobs_container):
    """Render server and team selectors"""
    db = get_db()
    try:
        # Get user's servers
        if user.is_admin:
            servers = db.query(Server).filter(Server.is_active == True).all()
        else:
            servers = db.query(Server).filter(
                Server.user_id == user.id,
                Server.is_active == True
            ).all()

        if not servers:
            with cronjobs_container:
                cronjobs_container.clear()
                EmptyState.render(
                    icon='storage',
                    title='No Active Servers',
                    message='You need to add an active server first.',
                    action_label='Add Server',
                    on_action=lambda: ui.navigate.to('/servers')
                )
            return

        server_options = {server.name: server for server in servers}

        button_container = ui.row().classes('w-full items-center gap-4')

        with button_container:
            server_select = ui.select(
                label='Select Server',
                options=list(server_options.keys()),
                value=list(server_options.keys())[0] if server_options else None
            ).classes('flex-1')

            team_select = ui.select(
                label='Select Team',
                options=[],
                value=None
            ).classes('flex-1')

        # Container for add button (created dynamically)
        add_button_container = ui.row().classes('w-full justify-end mt-2')

        # Update teams when server changes
        def on_server_change(e):
            if e.value:
                event_db = get_db()
                try:
                    server = server_options[e.value]
                    teams = event_db.query(Team).filter(
                        Team.server_id == server.id,
                        Team.is_active == True
                    ).all()
                    team_options = {team.name: team for team in teams}
                    team_select.options = list(team_options.keys())
                    team_select.value = list(team_options.keys())[0] if team_options else None
                    team_select.team_options = team_options

                    if team_select.value:
                        # Clear and recreate add button
                        add_button_container.clear()
                        with add_button_container:
                            ui.button(
                                'Add Cronjob',
                                icon='add',
                                on_click=lambda: show_add_cronjob_dialog(
                                    user, server, team_options[team_select.value], cronjobs_container
                                )
                            ).props('color=primary')
                        load_cronjobs(user, team_options[team_select.value], cronjobs_container)
                finally:
                    event_db.close()

        # Update cronjobs when team changes
        def on_team_change(e):
            team_name = team_select.value
            if team_name and server_select.value and hasattr(team_select, 'team_options'):
                server = server_options[server_select.value]
                team = team_select.team_options[team_name]

                # Clear and recreate add button
                add_button_container.clear()
                with add_button_container:
                    ui.button(
                        'Add Cronjob',
                        icon='add',
                        on_click=lambda: show_add_cronjob_dialog(user, server, team, cronjobs_container)
                    ).props('color=primary')

                load_cronjobs(user, team, cronjobs_container)

        server_select.on('update:model-value', on_server_change)
        team_select.on('update:model-value', on_team_change)

        # Load initial
        if server_select.value:
            on_server_change(type('Event', (), {'value': server_select.value})())

    finally:
        db.close()


def load_cronjobs(user, team, container):
    """Load and display cronjobs for a team"""
    container.clear()

    db = get_db()
    try:
        cronjobs = db.query(Cronjob).filter(
            Cronjob.team_id == team.id
        ).order_by(Cronjob.created_at.desc()).all()

        if not cronjobs:
            with container:
                EmptyState.render(
                    icon='schedule',
                    title='No Scheduled Jobs',
                    message='No cronjobs configured for this team yet. Add your first scheduled sync job!',
                )
        else:
            with container:
                for cronjob in cronjobs:
                    render_cronjob_card(user, team, cronjob, container)

    finally:
        db.close()


def render_cronjob_card(user, team, cronjob, container):
    """Render a cronjob card"""
    with ui.card().classes('w-full p-4'):
        with ui.row().classes('w-full items-start justify-between'):
            # Cronjob info
            with ui.column().classes('flex-1 gap-2'):
                with ui.row().classes('items-center gap-2'):
                    ui.icon('schedule', size='md').classes('text-primary')
                    ui.label(cronjob.name).classes('text-h6 font-bold')
                    StatusBadge.render(
                        'Active' if cronjob.is_active else 'Inactive',
                        cronjob.is_active
                    )

                ui.label(f'Schedule: {cronjob.get_schedule_description()}').classes('text-grey-7')

                if cronjob.description:
                    ui.label(cronjob.description).classes('text-grey-7')

                with ui.row().classes('gap-4'):
                    if cronjob.last_run:
                        ui.label(f'Last Run: {format_datetime(cronjob.last_run)}').classes('text-caption text-grey-7')
                    if cronjob.next_run:
                        ui.label(f'Next Run: {format_datetime(cronjob.next_run)}').classes('text-caption text-grey-7')

                if cronjob.last_status:
                    status_color = SUCCESS_COLOR if cronjob.last_status == 'success' else 'red'
                    ui.label(f'Last Status: {cronjob.last_status}').style(f'color: {status_color};').classes('text-caption font-bold')

                ui.label(f'Total Runs: {cronjob.run_count}').classes('text-caption text-grey-7')

            # Actions
            with ui.column().classes('gap-2'):
                ui.button(
                    'Run Now',
                    icon='play_arrow',
                    on_click=lambda j=cronjob: run_cronjob_now(user, team, j, container)
                ).props('flat dense color=primary')

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


def show_add_cronjob_dialog(user, server, team, container):
    """Show dialog to add a new cronjob"""
    import logging
    logger = logging.getLogger(__name__)
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
                load_cronjobs(user, team, container)

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

        # Get team for reload
        team = db.query(Team).filter(Team.id == cronjob.team_id).first()
        db.close()

        status_text = 'activated' if is_active else 'deactivated'
        Toast.success(f'Cronjob "{cronjob.name}" {status_text} successfully!')

        load_cronjobs(user, team, container)

    except Exception as e:
        Toast.error(f'Error updating cronjob: {str(e)}')


def confirm_delete_cronjob(user, cronjob, container):
    """Confirm and delete a cronjob"""
    def handle_delete():
        try:
            db = get_db()

            # Get team before deleting
            team = db.query(Team).filter(Team.id == cronjob.team_id).first()
            team_id = team.id

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

            # Reload team
            team = db.query(Team).filter(Team.id == team_id).first()
            db.close()

            Toast.success(f'Cronjob "{cronjob.name}" deleted successfully!')
            load_cronjobs(user, team, container)

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
    """Manually execute a cronjob now"""
    import logging
    logger = logging.getLogger(__name__)

    # Get database count first
    db = get_db()
    databases = db.query(Database).filter(
        Database.team_id == cronjob.team_id,
        Database.is_excluded == False
    ).all()
    total_dbs = len(databases)
    db.close()

    # Create status dialog
    with ui.dialog() as status_dialog, ui.card().classes('w-full p-6').style('min-width: 500px;'):
        ui.label(f'Running: {cronjob.name}').classes('text-h5 font-bold mb-4')

        with ui.row().classes('items-center gap-2 mb-4'):
            ui.spinner(size='lg')
            status_label = ui.label(f'Initializing sync for {total_dbs} databases...')

        progress_label = ui.label('').classes('text-grey-7')
        error_label = ui.label('').classes('text-negative')
        error_label.visible = False

        # Add close button (initially disabled)
        close_button = ui.button('Close', on_click=status_dialog.close).props('flat')
        close_button.enabled = False

    status_dialog.open()

    # Shared state for status updates
    job_state = {
        'running': True,
        'status': 'initializing',
        'progress': '',
        'error': None
    }

    async def execute_in_background():
        """Execute cronjob in background without blocking UI"""
        try:
            from ..services.cronjob_scheduler import get_scheduler
            scheduler = get_scheduler()

            logger.info(f"=== Manual execution started: {cronjob.name} ({total_dbs} databases) ===")

            job_state['status'] = 'running'
            job_state['progress'] = f'Initializing sync for {total_dbs} databases...'

            # Define progress callback
            def update_progress(status, message):
                job_state['progress'] = message

            # Execute the job asynchronously with progress callback
            await scheduler.execute_job(cronjob, progress_callback=update_progress)

            job_state['status'] = 'completed'
            job_state['progress'] = f'✓ Successfully synced {total_dbs} databases'
            logger.info(f"✓ Cronjob {cronjob.name} executed successfully")

        except Exception as e:
            job_state['status'] = 'error'
            job_state['error'] = str(e)
            logger.error(f"✗ Error executing cronjob {cronjob.name}: {e}")
            import traceback
            logger.error(traceback.format_exc())
        finally:
            job_state['running'] = False

    # Update UI based on job state
    def update_status():
        if job_state['status'] == 'running':
            status_label.text = 'Processing...'
            if job_state['progress']:
                progress_label.text = job_state['progress']
        elif job_state['status'] == 'completed':
            status_label.text = 'Completed!'
            status_label.classes(add='text-positive', remove='text-grey-7')
            progress_label.text = job_state['progress']
            progress_label.classes(add='text-positive')
            # Reload the cronjobs list
            load_cronjobs(user, team, container)
            close_button.enabled = True
            # Auto-close after 3 seconds
            ui.timer(3.0, lambda: status_dialog.close(), once=True)
        elif job_state['status'] == 'error':
            status_label.text = 'Error occurred!'
            status_label.classes(add='text-negative', remove='text-grey-7')
            error_label.text = f"Error: {job_state['error']}"
            error_label.visible = True
            close_button.enabled = True

        # Stop timer when job is done
        if not job_state['running']:
            status_timer.active = False

    # Create timer to update status
    status_timer = ui.timer(0.5, update_status)

    # Start the background task using asyncio
    asyncio.create_task(execute_in_background())


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
