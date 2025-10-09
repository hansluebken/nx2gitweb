"""
Dashboard page for Ninox2Git
"""
from nicegui import ui
from datetime import datetime
from ..database import get_db
from ..models.server import Server
from ..models.team import Team
from .components import (
    NavHeader, Card, StatsCard, Toast, EmptyState,
    format_datetime, PRIMARY_COLOR, SUCCESS_COLOR, INFO_COLOR
)


def render(user):
    """
    Render the dashboard page

    Args:
        user: Current user object
    """
    ui.colors(primary=PRIMARY_COLOR)

    # Navigation header
    NavHeader(user, 'dashboard').render()

    # Main content
    with ui.column().classes('w-full p-6 gap-6').style('max-width: 1400px; margin: 0 auto;'):
        # Welcome section
        with ui.row().classes('w-full items-center justify-between'):
            with ui.column().classes('gap-1'):
                ui.label(f'Welcome back, {user.full_name or user.username}!').classes(
                    'text-h4 font-bold'
                )
                ui.label(f'Last login: {format_datetime(user.last_login)}').classes('text-grey-7')

        # Statistics cards
        render_stats(user)

        # Quick actions
        with ui.row().classes('w-full gap-4'):
            with ui.column().classes('flex-1 gap-4'):
                render_quick_actions(user)

            with ui.column().classes('flex-1 gap-4'):
                render_recent_activity(user)


def render_stats(user):
    """Render statistics cards"""
    db = get_db()

    try:
        # Count servers
        if user.is_admin:
            servers_count = db.query(Server).count()
        else:
            servers_count = db.query(Server).filter(Server.user_id == user.id).count()

        # Count active servers
        if user.is_admin:
            active_servers = db.query(Server).filter(Server.is_active == True).count()
        else:
            active_servers = db.query(Server).filter(
                Server.user_id == user.id,
                Server.is_active == True
            ).count()

        # Count teams
        team_query = db.query(Team)
        if not user.is_admin:
            team_query = team_query.join(Server).filter(Server.user_id == user.id)
        teams_count = team_query.count()

        # Get last sync time
        last_sync_query = db.query(Team).filter(Team.last_sync.isnot(None))
        if not user.is_admin:
            last_sync_query = last_sync_query.join(Server).filter(Server.user_id == user.id)
        last_sync_team = last_sync_query.order_by(Team.last_sync.desc()).first()
        last_sync = format_datetime(last_sync_team.last_sync) if last_sync_team else 'Never'

    finally:
        db.close()

    # Display stats
    with ui.row().classes('w-full gap-4'):
        StatsCard.render(
            'Total Servers',
            str(servers_count),
            'storage',
            PRIMARY_COLOR
        )
        StatsCard.render(
            'Active Servers',
            str(active_servers),
            'check_circle',
            SUCCESS_COLOR
        )
        StatsCard.render(
            'Teams',
            str(teams_count),
            'group',
            INFO_COLOR
        )
        StatsCard.render(
            'Last Sync',
            last_sync,
            'sync',
            PRIMARY_COLOR
        )


def render_quick_actions(user):
    """Render quick actions section"""
    with Card(title='Quick Actions', icon='flash_on'):
        with ui.column().classes('w-full gap-3'):
            # Add server button
            with ui.button(
                'Add New Server',
                icon='add',
                on_click=lambda: ui.navigate.to('/servers')
            ).classes('w-full').props('align=left'):
                pass

            # View servers button
            with ui.button(
                'Manage Servers',
                icon='storage',
                on_click=lambda: ui.navigate.to('/servers')
            ).classes('w-full').props('align=left color=secondary'):
                pass

            # Sync teams button
            with ui.button(
                'Sync Teams',
                icon='group',
                on_click=lambda: ui.navigate.to('/teams')
            ).classes('w-full').props('align=left color=secondary'):
                pass

            # Run sync button
            with ui.button(
                'Run Synchronization',
                icon='sync',
                on_click=lambda: ui.navigate.to('/sync')
            ).classes('w-full').props('align=left color=primary'):
                pass

            # Admin panel (if admin)
            if user.is_admin:
                ui.separator()
                with ui.button(
                    'Admin Panel',
                    icon='admin_panel_settings',
                    on_click=lambda: ui.navigate.to('/admin')
                ).classes('w-full').props('align=left color=warning'):
                    pass


def render_recent_activity(user):
    """Render recent activity section"""
    db = get_db()

    try:
        # Get recent synced teams
        recent_teams_query = db.query(Team).filter(Team.last_sync.isnot(None))
        if not user.is_admin:
            recent_teams_query = recent_teams_query.join(Server).filter(
                Server.user_id == user.id
            )
        recent_teams = recent_teams_query.order_by(Team.last_sync.desc()).limit(5).all()

    finally:
        db.close()

    with Card(title='Recent Activity', icon='history'):
        if not recent_teams:
            EmptyState.render(
                icon='history',
                title='No Activity',
                message='No synchronization activity yet. Start by adding a server.',
                action_label='Add Server',
                on_action=lambda: ui.navigate.to('/servers')
            )
        else:
            with ui.column().classes('w-full gap-2'):
                for team in recent_teams:
                    with ui.card().classes('w-full p-3').style('background-color: #f5f5f5;'):
                        with ui.row().classes('w-full items-center justify-between'):
                            with ui.column().classes('gap-1'):
                                ui.label(team.name).classes('font-bold')
                                ui.label(f'Team ID: {team.team_id}').classes('text-caption text-grey-7')
                            with ui.column().classes('gap-1 items-end'):
                                with ui.row().classes('items-center gap-1'):
                                    ui.icon('sync', size='sm').classes('text-positive')
                                    ui.label('Synced').classes('text-caption text-positive')
                                ui.label(format_datetime(team.last_sync)).classes(
                                    'text-caption text-grey-7'
                                )


def render_getting_started(user):
    """Render getting started guide for new users"""
    with Card(title='Getting Started', icon='info'):
        with ui.column().classes('w-full gap-3'):
            with ui.expansion('1. Add a Ninox Server', icon='storage').classes('w-full'):
                ui.label(
                    'First, add a Ninox server by providing the server URL and API key. '
                    'You can find your API key in your Ninox account settings.'
                ).classes('p-4')
                ui.button(
                    'Go to Servers',
                    icon='arrow_forward',
                    on_click=lambda: ui.navigate.to('/servers')
                ).classes('ml-4 mb-4')

            with ui.expansion('2. Sync Teams', icon='group').classes('w-full'):
                ui.label(
                    'After adding a server, sync your teams to see all available teams '
                    'and databases from your Ninox account.'
                ).classes('p-4')
                ui.button(
                    'Go to Teams',
                    icon='arrow_forward',
                    on_click=lambda: ui.navigate.to('/teams')
                ).classes('ml-4 mb-4')

            with ui.expansion('3. Configure Synchronization', icon='sync').classes('w-full'):
                ui.label(
                    'Select which databases to sync and configure GitHub settings. '
                    'You can run manual syncs or schedule automatic synchronization.'
                ).classes('p-4')
                ui.button(
                    'Go to Sync',
                    icon='arrow_forward',
                    on_click=lambda: ui.navigate.to('/sync')
                ).classes('ml-4 mb-4')
