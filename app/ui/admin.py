"""
Admin panel for Ninox2Git
"""
from nicegui import ui
from datetime import datetime
from ..database import get_db
from ..models.user import User
from ..models.server import Server
from ..models.team import Team
from ..models.database import Database
from ..models.audit_log import AuditLog
from ..auth import (
    register_user, activate_user, deactivate_user, create_audit_log,
    UserExistsError
)
from .components import (
    NavHeader, Card, FormField, Toast, ConfirmDialog,
    DataTable, StatusBadge, format_datetime, PRIMARY_COLOR,
    WARNING_COLOR, ERROR_COLOR, SUCCESS_COLOR
)


def render(user):
    """
    Render the admin panel page

    Args:
        user: Current user object (must be admin)
    """
    ui.colors(primary=PRIMARY_COLOR)

    # Navigation header
    NavHeader(user, 'admin').render()

    # Main content
    with ui.column().classes('w-full p-6 gap-6').style('max-width: 1400px; margin: 0 auto;'):
        ui.label('Admin Panel').classes('text-h4 font-bold mb-4')

        # Admin tabs
        with ui.tabs().classes('w-full') as tabs:
            overview_tab = ui.tab('Overview', icon='dashboard')
            users_tab = ui.tab('Users', icon='people')
            audit_tab = ui.tab('Audit Logs', icon='receipt_long')
            stats_tab = ui.tab('Statistics', icon='analytics')

        with ui.tab_panels(tabs, value=overview_tab).classes('w-full'):
            # Overview panel
            with ui.tab_panel(overview_tab):
                render_overview(user)

            # Users panel
            with ui.tab_panel(users_tab):
                render_users_management(user)

            # Audit logs panel
            with ui.tab_panel(audit_tab):
                render_audit_logs(user)

            # Statistics panel
            with ui.tab_panel(stats_tab):
                render_statistics(user)


def render_overview(user):
    """Render admin overview"""
    db = get_db()
    try:
        # Get counts
        total_users = db.query(User).count()
        active_users = db.query(User).filter(User.is_active == True).count()
        total_servers = db.query(Server).count()
        active_servers = db.query(Server).filter(Server.is_active == True).count()
        total_teams = db.query(Team).count()
        total_databases = db.query(Database).count()

        # Recent activity
        recent_logs = db.query(AuditLog).order_by(
            AuditLog.created_at.desc()
        ).limit(10).all()

    finally:
        db.close()

    with ui.column().classes('w-full gap-6'):
        # System statistics
        ui.label('System Overview').classes('text-h5 font-bold')

        with ui.row().classes('w-full gap-4'):
            render_stat_card('Total Users', str(total_users), 'people', PRIMARY_COLOR)
            render_stat_card('Active Users', str(active_users), 'check_circle', SUCCESS_COLOR)
            render_stat_card('Total Servers', str(total_servers), 'storage', PRIMARY_COLOR)
            render_stat_card('Active Servers', str(active_servers), 'check_circle', SUCCESS_COLOR)

        with ui.row().classes('w-full gap-4'):
            render_stat_card('Teams', str(total_teams), 'group', PRIMARY_COLOR)
            render_stat_card('Databases', str(total_databases), 'folder', PRIMARY_COLOR)

        # Recent activity
        with Card(title='Recent Activity', icon='history'):
            if not recent_logs:
                ui.label('No recent activity.').classes('text-grey-7')
            else:
                with ui.column().classes('w-full gap-2'):
                    for log in recent_logs:
                        with ui.card().classes('w-full p-3').style('background-color: #f5f5f5;'):
                            with ui.row().classes('w-full items-center justify-between'):
                                with ui.column().classes('gap-1'):
                                    ui.label(log.action.replace('_', ' ').title()).classes(
                                        'font-bold'
                                    )
                                    ui.label(log.details or 'No details').classes(
                                        'text-caption text-grey-7'
                                    )
                                    ui.label(f'By: {log.user.username}').classes(
                                        'text-caption text-grey-7'
                                    )
                                ui.label(format_datetime(log.created_at)).classes(
                                    'text-caption text-grey-7'
                                )


def render_stat_card(title, value, icon, color):
    """Render a statistics card"""
    with ui.card().classes('flex-1 p-4').style(f'border-left: 4px solid {color};'):
        with ui.row().classes('items-center justify-between w-full'):
            with ui.column().classes('gap-1'):
                ui.label(title).classes('text-caption text-grey-7')
                ui.label(value).classes('text-h5 font-bold')
            ui.icon(icon, size='lg').style(f'color: {color}; opacity: 0.6;')


def render_users_management(user):
    """Render users management section"""
    users_container = ui.column().classes('w-full gap-4')

    with ui.column().classes('w-full gap-4'):
        # Header with add button
        with ui.row().classes('w-full items-center justify-between'):
            ui.label('User Management').classes('text-h5 font-bold')
            ui.button(
                'Add User',
                icon='person_add',
                on_click=lambda: show_add_user_dialog(user, users_container)
            ).props('color=primary')

        # Users table
        with users_container:
            load_users_table(user, users_container)


def load_users_table(admin_user, container):
    """Load and display users table"""
    container.clear()

    db = get_db()
    try:
        users = db.query(User).order_by(User.created_at.desc()).all()

        with container:
            with ui.card().classes('w-full p-4'):
                if not users:
                    ui.label('No users found.').classes('text-grey-7')
                else:
                    for user in users:
                        render_user_row(admin_user, user, container)

    finally:
        db.close()


def render_user_row(admin_user, user, container):
    """Render a user row"""
    with ui.card().classes('w-full p-3 mb-2').style('background-color: #f9f9f9;'):
        with ui.row().classes('w-full items-center justify-between'):
            # User info
            with ui.column().classes('flex-1 gap-1'):
                with ui.row().classes('items-center gap-2'):
                    ui.icon('person', size='md').classes('text-primary')
                    ui.label(user.username).classes('text-h6 font-bold')
                    StatusBadge.render(
                        'Active' if user.is_active else 'Inactive',
                        user.is_active
                    )
                    if user.is_admin:
                        ui.badge('Admin', color='orange')

                ui.label(f'Email: {user.email}').classes('text-grey-7')
                if user.full_name:
                    ui.label(f'Name: {user.full_name}').classes('text-grey-7')
                ui.label(f'Last Login: {format_datetime(user.last_login)}').classes('text-grey-7')

            # Actions
            with ui.row().classes('gap-2'):
                # Don't allow disabling own account
                if user.id != admin_user.id:
                    if user.is_active:
                        ui.button(
                            'Deactivate',
                            icon='block',
                            on_click=lambda u=user: handle_deactivate_user(
                                admin_user, u, container
                            )
                        ).props('flat dense color=warning')
                    else:
                        ui.button(
                            'Activate',
                            icon='check_circle',
                            on_click=lambda u=user: handle_activate_user(
                                admin_user, u, container
                            )
                        ).props('flat dense color=positive')

                    ui.button(
                        'Delete',
                        icon='delete',
                        on_click=lambda u=user: confirm_delete_user(admin_user, u, container)
                    ).props('flat dense color=negative')
                else:
                    ui.label('(You)').classes('text-caption text-grey-7')


def show_add_user_dialog(admin_user, container):
    """Show dialog to add a new user"""
    with ui.dialog() as dialog, ui.card().classes('w-full p-6').style('min-width: 500px;'):
        ui.label('Add New User').classes('text-h5 font-bold mb-4')

        username_input = FormField.text(
            label='Username',
            placeholder='username',
            required=True
        )

        email_input = FormField.text(
            label='Email',
            placeholder='user@example.com',
            required=True
        )

        full_name_input = FormField.text(
            label='Full Name',
            placeholder='Full Name (Optional)'
        )

        password_input = FormField.password(
            label='Password',
            placeholder='Password',
            required=True
        )

        is_admin_checkbox = FormField.checkbox(
            label='Admin User',
            value=False
        )

        error_label = ui.label('').classes('text-negative mt-2')
        error_label.visible = False

        async def handle_save():
            """Handle user creation"""
            username = username_input.value.strip()
            email = email_input.value.strip()
            full_name = full_name_input.value.strip() or None
            password = password_input.value
            is_admin = is_admin_checkbox.value

            if not username or not email or not password:
                error_label.text = 'Please fill in all required fields'
                error_label.visible = True
                return

            try:
                db = get_db()
                new_user = register_user(
                    db=db,
                    username=username,
                    email=email,
                    password=password,
                    full_name=full_name,
                    is_admin=is_admin
                )

                # Create audit log
                create_audit_log(
                    db=db,
                    user_id=admin_user.id,
                    action='user_created_by_admin',
                    resource_type='user',
                    resource_id=new_user.id,
                    details=f'Admin created user: {username}'
                )

                db.close()

                Toast.success(f'User "{username}" created successfully!')
                dialog.close()

                # Reload users
                load_users_table(admin_user, container)

            except UserExistsError as e:
                error_label.text = str(e)
                error_label.visible = True
            except ValueError as e:
                error_label.text = str(e)
                error_label.visible = True
            except Exception as e:
                error_label.text = f'Error creating user: {str(e)}'
                error_label.visible = True

        with ui.row().classes('w-full justify-end gap-2 mt-4'):
            ui.button('Cancel', on_click=dialog.close).props('flat')
            ui.button('Create User', on_click=handle_save, color='primary')

    dialog.open()


def handle_activate_user(admin_user, user, container):
    """Activate a user"""
    try:
        db = get_db()
        activate_user(db, user.id, admin_user.id)
        db.close()

        Toast.success(f'User "{user.username}" activated successfully!')

        # Reload users
        load_users_table(admin_user, container)

    except Exception as e:
        Toast.error(f'Error activating user: {str(e)}')


def handle_deactivate_user(admin_user, user, container):
    """Deactivate a user"""
    try:
        db = get_db()
        deactivate_user(db, user.id, admin_user.id)
        db.close()

        Toast.success(f'User "{user.username}" deactivated successfully!')

        # Reload users
        load_users_table(admin_user, container)

    except Exception as e:
        Toast.error(f'Error deactivating user: {str(e)}')


def confirm_delete_user(admin_user, user, container):
    """Confirm and delete a user"""
    def handle_delete():
        try:
            db = get_db()

            # Create audit log before deletion
            create_audit_log(
                db=db,
                user_id=admin_user.id,
                action='user_deleted',
                resource_type='user',
                resource_id=user.id,
                details=f'Deleted user: {user.username}'
            )

            # Delete user (cascades to servers, teams, etc.)
            db.query(User).filter(User.id == user.id).delete()
            db.commit()
            db.close()

            Toast.success(f'User "{user.username}" deleted successfully!')

            # Reload users
            load_users_table(admin_user, container)

        except Exception as e:
            Toast.error(f'Error deleting user: {str(e)}')

    ConfirmDialog.show(
        title='Delete User',
        message=f'Are you sure you want to delete user "{user.username}"? This will also delete all their servers, teams, and data.',
        on_confirm=handle_delete,
        confirm_text='Delete',
        danger=True
    )


def render_audit_logs(user):
    """Render audit logs section"""
    with ui.column().classes('w-full gap-4'):
        ui.label('Audit Logs').classes('text-h5 font-bold')

        # Filters
        with ui.row().classes('w-full gap-4 mb-4'):
            action_filter = ui.select(
                label='Action',
                options=['All'] + [
                    'login', 'logout', 'user_created', 'user_deleted',
                    'server_created', 'server_updated', 'server_deleted',
                    'team_synced', 'database_synced'
                ],
                value='All'
            ).classes('flex-1')

            user_filter = ui.input(
                label='Username',
                placeholder='Filter by username'
            ).classes('flex-1')

        logs_container = ui.column().classes('w-full gap-2')

        def load_logs():
            """Load and display audit logs"""
            logs_container.clear()

            db = get_db()
            try:
                query = db.query(AuditLog)

                # Apply filters
                if action_filter.value != 'All':
                    query = query.filter(AuditLog.action == action_filter.value)

                if user_filter.value:
                    query = query.join(User).filter(
                        User.username.ilike(f'%{user_filter.value}%')
                    )

                logs = query.order_by(AuditLog.created_at.desc()).limit(100).all()

                with logs_container:
                    if not logs:
                        ui.label('No audit logs found.').classes('text-grey-7')
                    else:
                        for log in logs:
                            with ui.card().classes('w-full p-3').style(
                                'background-color: #f9f9f9;'
                            ):
                                with ui.row().classes('w-full items-start justify-between'):
                                    with ui.column().classes('flex-1 gap-1'):
                                        ui.label(
                                            log.action.replace('_', ' ').title()
                                        ).classes('font-bold')
                                        ui.label(log.details or 'No details').classes(
                                            'text-grey-7'
                                        )
                                        ui.label(f'User: {log.user.username}').classes(
                                            'text-caption text-grey-7'
                                        )
                                        if log.ip_address:
                                            ui.label(f'IP: {log.ip_address}').classes(
                                                'text-caption text-grey-7'
                                            )
                                    with ui.column().classes('items-end gap-1'):
                                        ui.label(format_datetime(log.created_at)).classes(
                                            'text-caption text-grey-7'
                                        )
                                        if log.resource_type:
                                            ui.badge(log.resource_type, color='info')

            finally:
                db.close()

        # Load initial logs
        load_logs()

        # Reload on filter change
        action_filter.on('update:model-value', lambda: load_logs())
        user_filter.on('keyup.enter', lambda: load_logs())

        ui.button('Refresh', icon='refresh', on_click=load_logs).props('flat')


def render_statistics(user):
    """Render statistics section"""
    db = get_db()
    try:
        # User statistics
        total_users = db.query(User).count()
        active_users = db.query(User).filter(User.is_active == True).count()
        admin_users = db.query(User).filter(User.is_admin == True).count()

        # Server statistics
        total_servers = db.query(Server).count()
        active_servers = db.query(Server).filter(Server.is_active == True).count()
        servers_with_github = db.query(Server).filter(
            Server.github_token_encrypted.isnot(None)
        ).count()

        # Team and database statistics
        total_teams = db.query(Team).count()
        active_teams = db.query(Team).filter(Team.is_active == True).count()
        total_databases = db.query(Database).count()
        excluded_databases = db.query(Database).filter(
            Database.is_excluded == True
        ).count()

        # Activity statistics
        total_logins = db.query(AuditLog).filter(AuditLog.action == 'login').count()
        total_syncs = db.query(AuditLog).filter(
            AuditLog.action == 'database_synced'
        ).count()

    finally:
        db.close()

    with ui.column().classes('w-full gap-6'):
        # User statistics
        with Card(title='User Statistics', icon='people'):
            with ui.column().classes('w-full gap-3'):
                ui.label(f'Total Users: {total_users}').classes('text-h6')
                ui.label(f'Active Users: {active_users}').classes('text-grey-7')
                ui.label(f'Admin Users: {admin_users}').classes('text-grey-7')
                ui.label(f'Inactive Users: {total_users - active_users}').classes('text-grey-7')

        # Server statistics
        with Card(title='Server Statistics', icon='storage'):
            with ui.column().classes('w-full gap-3'):
                ui.label(f'Total Servers: {total_servers}').classes('text-h6')
                ui.label(f'Active Servers: {active_servers}').classes('text-grey-7')
                ui.label(f'Servers with GitHub: {servers_with_github}').classes('text-grey-7')

        # Team and database statistics
        with Card(title='Team & Database Statistics', icon='folder'):
            with ui.column().classes('w-full gap-3'):
                ui.label(f'Total Teams: {total_teams}').classes('text-h6')
                ui.label(f'Active Teams: {active_teams}').classes('text-grey-7')
                ui.label(f'Total Databases: {total_databases}').classes('text-grey-7')
                ui.label(f'Excluded Databases: {excluded_databases}').classes('text-grey-7')
                ui.label(
                    f'Synced Databases: {total_databases - excluded_databases}'
                ).classes('text-grey-7')

        # Activity statistics
        with Card(title='Activity Statistics', icon='analytics'):
            with ui.column().classes('w-full gap-3'):
                ui.label(f'Total Logins: {total_logins}').classes('text-h6')
                ui.label(f'Total Syncs: {total_syncs}').classes('text-grey-7')
