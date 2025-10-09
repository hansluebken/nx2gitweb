"""
Server management page for Ninox2Git
"""
from nicegui import ui
from ..database import get_db
from ..models.server import Server
from ..auth import create_audit_log
from ..utils.encryption import get_encryption_manager
from ..api.ninox_client import NinoxClient
from .components import (
    NavHeader, Card, FormField, Toast, ConfirmDialog,
    EmptyState, StatusBadge, PRIMARY_COLOR, SUCCESS_COLOR
)


def render(user):
    """
    Render the servers management page

    Args:
        user: Current user object
    """
    ui.colors(primary=PRIMARY_COLOR)

    # Navigation header
    NavHeader(user, 'servers').render()

    # Main content
    with ui.column().classes('w-full p-6 gap-6').style('max-width: 1400px; margin: 0 auto;'):
        # Header with add button
        with ui.row().classes('w-full items-center justify-between mb-4'):
            ui.label('Servers').classes('text-h4 font-bold')
            ui.button(
                'Add Server',
                icon='add',
                on_click=lambda: show_add_server_dialog(user)
            ).props('color=primary')

        # Server list container
        servers_container = ui.column().classes('w-full gap-4')

        # Load and display servers
        with servers_container:
            load_servers(user, servers_container)


def load_servers(user, container):
    """Load and display servers"""
    container.clear()

    db = get_db()
    try:
        # Query servers
        if user.is_admin:
            servers = db.query(Server).order_by(Server.created_at.desc()).all()
        else:
            servers = db.query(Server).filter(
                Server.user_id == user.id
            ).order_by(Server.created_at.desc()).all()

        if not servers:
            with container:
                EmptyState.render(
                    icon='storage',
                    title='No Servers',
                    message='You have not added any Ninox servers yet. Add your first server to get started.',
                    action_label='Add Server',
                    on_action=lambda: show_add_server_dialog(user)
                )
        else:
            with container:
                for server in servers:
                    render_server_card(user, server, container)

    finally:
        db.close()


def render_server_card(user, server, container):
    """Render a server card"""
    with ui.card().classes('w-full p-4'):
        with ui.row().classes('w-full items-start justify-between'):
            # Server info
            with ui.column().classes('flex-1 gap-2'):
                with ui.row().classes('items-center gap-2'):
                    ui.icon('storage', size='md').classes('text-primary')
                    ui.label(server.name).classes('text-h6 font-bold')
                    StatusBadge.render(
                        'Active' if server.is_active else 'Inactive',
                        server.is_active
                    )
                    if user.is_admin and server.user_id != user.id:
                        ui.badge('Shared', color='info')

                ui.label(f'URL: {server.url}').classes('text-grey-7')

                if server.custom_name:
                    ui.label(f'Custom Name: {server.custom_name}').classes('text-grey-7')

                # Show GitHub config from user if available
                if user.github_organization:
                    with ui.row().classes('items-center gap-2'):
                        ui.icon('github', size='sm').classes('text-grey-7')
                        ui.label(
                            f'GitHub: {user.github_organization}/{user.github_default_repo or "ninox-backup"}'
                        ).classes('text-grey-7')

            # Actions
            with ui.column().classes('gap-2'):
                ui.button(
                    'Test',
                    icon='cell_tower',
                    on_click=lambda s=server: test_server_connection(s)
                ).props('flat dense color=primary')

                ui.button(
                    'Edit',
                    icon='edit',
                    on_click=lambda s=server: show_edit_server_dialog(user, s, container)
                ).props('flat dense')

                ui.button(
                    'Delete',
                    icon='delete',
                    on_click=lambda s=server: confirm_delete_server(user, s, container)
                ).props('flat dense color=negative')


def show_add_server_dialog(user):
    """Show dialog to add a new server"""
    with ui.dialog() as dialog, ui.card().classes('w-full p-6').style('min-width: 600px;'):
        ui.label('Add New Server').classes('text-h5 font-bold mb-4')

        name_input = FormField.text(
            label='Server Name',
            placeholder='My Ninox Server',
            required=True
        )

        url_input = FormField.text(
            label='Server URL',
            placeholder='https://nx.nf1.eu',
            required=True
        )

        api_key_input = FormField.password(
            label='API Key',
            placeholder='Your Ninox API Key',
            required=True
        )

        custom_name_input = FormField.text(
            label='Custom Name (Optional)',
            placeholder='Optional custom identifier'
        )

        error_label = ui.label('').classes('text-negative mt-2')
        error_label.visible = False

        async def handle_save():
            """Handle server creation"""
            name = name_input.value.strip()
            url = url_input.value.strip()
            api_key = api_key_input.value.strip()
            custom_name = custom_name_input.value.strip() or None

            if not name or not url or not api_key:
                error_label.text = 'Please fill in all required fields'
                error_label.visible = True
                return

            try:
                # Encrypt sensitive data
                encryption = get_encryption_manager()
                api_key_encrypted = encryption.encrypt(api_key)

                # Create server
                db = get_db()
                server = Server(
                    user_id=user.id,
                    name=name,
                    url=url,
                    api_key_encrypted=api_key_encrypted,
                    custom_name=custom_name,
                    is_active=True
                )
                db.add(server)
                db.commit()

                # Create audit log
                create_audit_log(
                    db=db,
                    user_id=user.id,
                    action='server_created',
                    resource_type='server',
                    resource_id=server.id,
                    details=f'Created server: {name}'
                )

                db.close()

                Toast.success(f'Server "{name}" added successfully!')
                dialog.close()

                # Reload page to show new server
                ui.navigate.to('/servers')

            except Exception as e:
                error_label.text = f'Error adding server: {str(e)}'
                error_label.visible = True

        with ui.row().classes('w-full justify-end gap-2 mt-4'):
            ui.button('Cancel', on_click=dialog.close).props('flat')
            ui.button('Add Server', on_click=handle_save, color='primary')

    dialog.open()


def show_edit_server_dialog(user, server, container):
    """Show dialog to edit a server"""
    # Decrypt sensitive data
    encryption = get_encryption_manager()
    api_key = encryption.decrypt(server.api_key_encrypted)

    with ui.dialog() as dialog, ui.card().classes('w-full p-6').style('min-width: 600px;'):
        ui.label('Edit Server').classes('text-h5 font-bold mb-4')

        name_input = FormField.text(
            label='Server Name',
            value=server.name,
            required=True
        )

        url_input = FormField.text(
            label='Server URL',
            value=server.url,
            required=True
        )

        api_key_input = FormField.password(
            label='API Key',
            required=True
        )
        api_key_input.value = api_key

        custom_name_input = FormField.text(
            label='Custom Name (Optional)',
            value=server.custom_name or ''
        )

        is_active_checkbox = FormField.checkbox(
            label='Active',
            value=server.is_active
        )

        error_label = ui.label('').classes('text-negative mt-2')
        error_label.visible = False

        async def handle_save():
            """Handle server update"""
            name = name_input.value.strip()
            url = url_input.value.strip()
            api_key_new = api_key_input.value.strip()
            custom_name = custom_name_input.value.strip() or None
            is_active = is_active_checkbox.value

            if not name or not url or not api_key_new:
                error_label.text = 'Please fill in all required fields'
                error_label.visible = True
                return

            try:
                # Encrypt sensitive data
                encryption = get_encryption_manager()
                api_key_encrypted = encryption.encrypt(api_key_new)

                # Update server
                db = get_db()
                db_server = db.query(Server).filter(Server.id == server.id).first()
                db_server.name = name
                db_server.url = url
                db_server.api_key_encrypted = api_key_encrypted
                db_server.custom_name = custom_name
                db_server.is_active = is_active
                db.commit()

                # Create audit log
                create_audit_log(
                    db=db,
                    user_id=user.id,
                    action='server_updated',
                    resource_type='server',
                    resource_id=server.id,
                    details=f'Updated server: {name}'
                )

                db.close()

                Toast.success(f'Server "{name}" updated successfully!')
                dialog.close()

                # Reload servers
                load_servers(user, container)

            except Exception as e:
                error_label.text = f'Error updating server: {str(e)}'
                error_label.visible = True

        with ui.row().classes('w-full justify-end gap-2 mt-4'):
            ui.button('Cancel', on_click=dialog.close).props('flat')
            ui.button('Save Changes', on_click=handle_save, color='primary')

    dialog.open()


def confirm_delete_server(user, server, container):
    """Confirm and delete a server"""
    def handle_delete():
        try:
            db = get_db()

            # Create audit log before deletion
            create_audit_log(
                db=db,
                user_id=user.id,
                action='server_deleted',
                resource_type='server',
                resource_id=server.id,
                details=f'Deleted server: {server.name}'
            )

            # Delete server (cascades to teams and databases)
            db.query(Server).filter(Server.id == server.id).delete()
            db.commit()
            db.close()

            Toast.success(f'Server "{server.name}" deleted successfully!')

            # Reload servers
            load_servers(user, container)

        except Exception as e:
            Toast.error(f'Error deleting server: {str(e)}')

    ConfirmDialog.show(
        title='Delete Server',
        message=f'Are you sure you want to delete "{server.name}"? This will also delete all associated teams and databases.',
        on_confirm=handle_delete,
        confirm_text='Delete',
        danger=True
    )


def test_server_connection(server):
    """Test connection to Ninox server"""
    try:
        # Decrypt API key
        encryption = get_encryption_manager()
        api_key = encryption.decrypt(server.api_key_encrypted)

        # Create client and test connection
        client = NinoxClient(server.url, api_key)
        if client.test_connection():
            Toast.success(f'Connection to "{server.name}" successful!')
        else:
            Toast.error(f'Failed to connect to "{server.name}"')

    except Exception as e:
        Toast.error(f'Connection error: {str(e)}')
