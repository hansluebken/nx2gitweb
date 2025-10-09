"""
SMTP Configuration page for Admin Panel
Manage SMTP server settings and test email functionality
"""
from nicegui import ui
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import asyncio
from ..database import get_db
from ..models.smtp_config import SmtpConfig
from ..utils.encryption import get_encryption_manager
from ..auth import create_audit_log
from .components import (
    NavHeader, Card, FormField, Toast, ConfirmDialog,
    EmptyState, StatusBadge, format_datetime, PRIMARY_COLOR, SUCCESS_COLOR, WARNING_COLOR
)


def render(user):
    """
    Render the SMTP configuration page

    Args:
        user: Current user object (must be admin)
    """
    if not user.is_admin:
        ui.navigate.to('/dashboard')
        return

    ui.colors(primary=PRIMARY_COLOR)

    # Navigation header
    NavHeader(user, 'smtp').render()

    # Main content
    with ui.column().classes('w-full p-6 gap-6').style('max-width: 1400px; margin: 0 auto;'):
        ui.label('SMTP Configuration').classes('text-h4 font-bold mb-4')

        # Add new SMTP server button
        with ui.row().classes('w-full justify-end mb-4'):
            ui.button(
                'Add SMTP Server',
                icon='add',
                on_click=lambda: show_add_smtp_dialog(user, smtp_container)
            ).props('color=primary')

        # SMTP servers list container
        smtp_container = ui.column().classes('w-full gap-4')
        load_smtp_configs(user, smtp_container)


def load_smtp_configs(user, container):
    """Load and display SMTP configurations"""
    container.clear()

    db = get_db()
    try:
        configs = db.query(SmtpConfig).order_by(SmtpConfig.is_active.desc(), SmtpConfig.created_at.desc()).all()

        if not configs:
            with container:
                EmptyState.render(
                    icon='email',
                    title='No SMTP Servers Configured',
                    message='Add your first SMTP server to enable email functionality.',
                )
        else:
            with container:
                for config in configs:
                    render_smtp_card(user, config, container)

    finally:
        db.close()


def render_smtp_card(user, config, container):
    """Render a single SMTP configuration card"""
    with ui.card().classes('w-full p-4'):
        with ui.row().classes('w-full items-start justify-between'):
            # SMTP info
            with ui.column().classes('flex-1 gap-2'):
                with ui.row().classes('items-center gap-2'):
                    ui.icon('email', size='md').classes('text-primary')
                    ui.label(config.name).classes('text-h6 font-bold')
                    if config.is_active:
                        StatusBadge.render('Active', True)
                    else:
                        StatusBadge.render('Inactive', False)
                    if config.is_tested:
                        ui.icon('check_circle', size='sm').classes('text-positive').props('title="Tested successfully"')

                with ui.row().classes('gap-4 text-grey-7'):
                    ui.label(f'Server: {config.host}:{config.port}')
                    ui.label(f'Username: {config.username}')
                    ui.label(f'From: {config.from_email}')

                with ui.row().classes('gap-4 text-caption text-grey-7'):
                    ui.label(f'TLS: {"Yes" if config.use_tls else "No"}')
                    ui.label(f'SSL: {"Yes" if config.use_ssl else "No"}')

                if config.last_test_date:
                    with ui.row().classes('gap-2 items-center'):
                        # Make datetime timezone-naive if it has timezone info
                        test_date = config.last_test_date
                        if hasattr(test_date, 'tzinfo') and test_date.tzinfo is not None:
                            test_date = test_date.replace(tzinfo=None)
                        ui.label(f'Last tested: {format_datetime(test_date)}').classes('text-caption text-grey-7')
                        if config.last_test_result:
                            if 'success' in config.last_test_result.lower():
                                ui.icon('check', size='xs').classes('text-positive')
                            else:
                                ui.icon('error', size='xs').classes('text-negative').props(f'title="{config.last_test_result}"')

            # Actions
            with ui.column().classes('gap-2'):
                ui.button(
                    'Test',
                    icon='send',
                    on_click=lambda c=config: test_smtp_config(user, c, container)
                ).props('flat dense color=primary')

                ui.button(
                    'Edit',
                    icon='edit',
                    on_click=lambda c=config: show_edit_smtp_dialog(user, c, container)
                ).props('flat dense')

                if not config.is_active:
                    ui.button(
                        'Set Active',
                        icon='check',
                        on_click=lambda c=config: set_active_smtp(user, c, container)
                    ).props('flat dense color=positive')

                ui.button(
                    'Delete',
                    icon='delete',
                    on_click=lambda c=config: confirm_delete_smtp(user, c, container)
                ).props('flat dense color=negative')


def show_add_smtp_dialog(user, container=None):
    """Show dialog to add a new SMTP configuration"""
    with ui.dialog() as dialog, ui.card().classes('w-full p-6').style('min-width: 600px;'):
        ui.label('Add SMTP Server').classes('text-h5 font-bold mb-4')

        # Form inputs
        name_input = FormField.text(
            label='Configuration Name',
            placeholder='e.g. "Gmail" or "Company Mail"',
            required=True
        )

        host_input = FormField.text(
            label='SMTP Host',
            placeholder='e.g. smtp.gmail.com',
            required=True
        )

        port_input = ui.number(
            label='Port',
            value=587,
            min=1,
            max=65535
        ).classes('w-full')

        username_input = FormField.text(
            label='Username/Email',
            placeholder='your-email@gmail.com',
            required=True
        )

        password_input = FormField.password(
            label='Password/App Password',
            placeholder='For Gmail, use App Password',
            required=True
        )

        from_email_input = FormField.text(
            label='From Email',
            placeholder='noreply@yourdomain.com',
            required=True
        )

        from_name_input = FormField.text(
            label='From Name',
            value='Ninox2Git',
            required=True
        )

        # Security options
        with ui.row().classes('gap-4'):
            use_tls = ui.checkbox('Use TLS', value=True)
            use_ssl = ui.checkbox('Use SSL', value=False)

        ui.label('Note: For most servers (Gmail, Outlook), use TLS on port 587').classes('text-caption text-grey-7')

        error_label = ui.label('').classes('text-negative mt-2')
        error_label.visible = False

        def handle_save():
            """Save new SMTP configuration"""
            name = name_input.value.strip()
            host = host_input.value.strip()
            port = int(port_input.value)
            username = username_input.value.strip()
            password = password_input.value.strip()
            from_email = from_email_input.value.strip()
            from_name = from_name_input.value.strip()

            if not all([name, host, username, password, from_email, from_name]):
                error_label.text = 'Please fill in all required fields'
                error_label.visible = True
                return

            try:
                db = get_db()

                # Check if name already exists
                existing = db.query(SmtpConfig).filter(SmtpConfig.name == name).first()
                if existing:
                    error_label.text = 'A configuration with this name already exists'
                    error_label.visible = True
                    return

                # Encrypt password
                encryption = get_encryption_manager()
                password_encrypted = encryption.encrypt(password)

                # Create new config (first config will be active by default)
                is_first = db.query(SmtpConfig).count() == 0

                config = SmtpConfig(
                    name=name,
                    host=host,
                    port=port,
                    username=username,
                    password_encrypted=password_encrypted,
                    from_email=from_email,
                    from_name=from_name,
                    use_tls=use_tls.value,
                    use_ssl=use_ssl.value,
                    is_active=is_first,  # First config is automatically active
                    is_tested=False
                )

                db.add(config)
                db.commit()

                # Create audit log
                create_audit_log(
                    db=db,
                    user_id=user.id,
                    action='smtp_config_created',
                    resource_type='smtp_config',
                    resource_id=config.id,
                    details=f'Created SMTP config: {name}',
                    auto_commit=True
                )

                db.close()

                Toast.success(f'SMTP configuration "{name}" created successfully!')
                dialog.close()

                # Reload the SMTP configs list
                load_smtp_configs(user, container)

            except Exception as e:
                error_label.text = f'Error creating configuration: {str(e)}'
                error_label.visible = True

        with ui.row().classes('w-full justify-end gap-2 mt-4'):
            ui.button('Cancel', on_click=dialog.close).props('flat')
            ui.button('Save', on_click=handle_save, color='primary')

    dialog.open()


def show_edit_smtp_dialog(user, config, container):
    """Show dialog to edit SMTP configuration"""
    with ui.dialog() as dialog, ui.card().classes('w-full p-6').style('min-width: 600px;'):
        ui.label('Edit SMTP Server').classes('text-h5 font-bold mb-4')

        # Decrypt current password
        encryption = get_encryption_manager()

        # Form inputs
        name_input = FormField.text(
            label='Configuration Name',
            value=config.name,
            required=True
        )

        host_input = FormField.text(
            label='SMTP Host',
            value=config.host,
            required=True
        )

        port_input = ui.number(
            label='Port',
            value=config.port,
            min=1,
            max=65535
        ).classes('w-full')

        username_input = FormField.text(
            label='Username/Email',
            value=config.username,
            required=True
        )

        password_input = FormField.password(
            label='Password/App Password (leave empty to keep current)',
            placeholder='Enter new password or leave empty',
            required=False
        )

        from_email_input = FormField.text(
            label='From Email',
            value=config.from_email,
            required=True
        )

        from_name_input = FormField.text(
            label='From Name',
            value=config.from_name,
            required=True
        )

        # Security options
        with ui.row().classes('gap-4'):
            use_tls = ui.checkbox('Use TLS', value=config.use_tls)
            use_ssl = ui.checkbox('Use SSL', value=config.use_ssl)

        error_label = ui.label('').classes('text-negative mt-2')
        error_label.visible = False

        def handle_save():
            """Update SMTP configuration"""
            name = name_input.value.strip()
            host = host_input.value.strip()
            port = int(port_input.value)
            username = username_input.value.strip()
            password = password_input.value.strip()
            from_email = from_email_input.value.strip()
            from_name = from_name_input.value.strip()

            if not all([name, host, username, from_email, from_name]):
                error_label.text = 'Please fill in all required fields'
                error_label.visible = True
                return

            try:
                db = get_db()

                # Check if name already exists (for another config)
                existing = db.query(SmtpConfig).filter(
                    SmtpConfig.name == name,
                    SmtpConfig.id != config.id
                ).first()
                if existing:
                    error_label.text = 'A configuration with this name already exists'
                    error_label.visible = True
                    return

                # Update config
                config_obj = db.query(SmtpConfig).filter(SmtpConfig.id == config.id).first()
                config_obj.name = name
                config_obj.host = host
                config_obj.port = port
                config_obj.username = username

                # Only update password if provided
                if password:
                    config_obj.password_encrypted = encryption.encrypt(password)
                    config_obj.is_tested = False  # Reset test status when password changes

                config_obj.from_email = from_email
                config_obj.from_name = from_name
                config_obj.use_tls = use_tls.value
                config_obj.use_ssl = use_ssl.value

                db.commit()

                # Create audit log
                create_audit_log(
                    db=db,
                    user_id=user.id,
                    action='smtp_config_updated',
                    resource_type='smtp_config',
                    resource_id=config.id,
                    details=f'Updated SMTP config: {name}',
                    auto_commit=True
                )

                db.close()

                Toast.success(f'SMTP configuration "{name}" updated successfully!')
                dialog.close()
                load_smtp_configs(user, container)

            except Exception as e:
                error_label.text = f'Error updating configuration: {str(e)}'
                error_label.visible = True

        with ui.row().classes('w-full justify-end gap-2 mt-4'):
            ui.button('Cancel', on_click=dialog.close).props('flat')
            ui.button('Save Changes', on_click=handle_save, color='primary')

    dialog.open()


def test_smtp_config(user, config, container):
    """Test SMTP configuration by sending a test email"""

    # Create test dialog
    with ui.dialog() as dialog, ui.card().classes('w-full p-6').style('min-width: 500px;'):
        ui.label(f'Test SMTP: {config.name}').classes('text-h5 font-bold mb-4')

        test_email_input = FormField.text(
            label='Send test email to:',
            value=user.email,
            placeholder='test@example.com',
            required=True
        )

        with ui.row().classes('items-center gap-2 mt-4'):
            spinner = ui.spinner(size='sm')
            status_label = ui.label('Ready to send test email')
        spinner.visible = False

        error_label = ui.label('').classes('text-negative mt-2')
        error_label.visible = False

        success_label = ui.label('').classes('text-positive mt-2')
        success_label.visible = False

        async def send_test_email():
            """Send test email"""
            test_email = test_email_input.value.strip()

            if not test_email:
                error_label.text = 'Please enter an email address'
                error_label.visible = True
                return

            spinner.visible = True
            status_label.text = 'Sending test email...'
            error_label.visible = False
            success_label.visible = False

            try:
                # Decrypt password
                encryption = get_encryption_manager()
                password = encryption.decrypt(config.password_encrypted)

                # Create message
                msg = MIMEMultipart('alternative')
                msg['Subject'] = 'Ninox2Git SMTP Test Email'
                msg['From'] = f'{config.from_name} <{config.from_email}>'
                msg['To'] = test_email

                # Email body
                html = f"""
                <html>
                <body style="font-family: Arial, sans-serif; padding: 20px;">
                    <h2>SMTP Configuration Test Successful!</h2>
                    <p>This is a test email from your Ninox2Git application.</p>
                    <hr>
                    <p><strong>Configuration Details:</strong></p>
                    <ul>
                        <li>Config Name: {config.name}</li>
                        <li>SMTP Server: {config.host}:{config.port}</li>
                        <li>From: {config.from_email}</li>
                        <li>Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</li>
                    </ul>
                    <hr>
                    <p style="color: #666; font-size: 12px;">
                        This is an automated test email. If you received this, your SMTP configuration is working correctly.
                    </p>
                </body>
                </html>
                """

                part = MIMEText(html, 'html')
                msg.attach(part)

                # Connect and send
                if config.use_ssl:
                    server = smtplib.SMTP_SSL(config.host, config.port)
                else:
                    server = smtplib.SMTP(config.host, config.port)
                    if config.use_tls:
                        server.starttls()

                server.login(config.username, password)
                server.send_message(msg)
                server.quit()

                # Update test status in database
                db = get_db()
                config_obj = db.query(SmtpConfig).filter(SmtpConfig.id == config.id).first()
                config_obj.is_tested = True
                config_obj.last_test_date = datetime.utcnow()
                config_obj.last_test_result = f'Success: Test email sent to {test_email}'
                db.commit()

                # Create audit log
                create_audit_log(
                    db=db,
                    user_id=user.id,
                    action='smtp_config_tested',
                    resource_type='smtp_config',
                    resource_id=config.id,
                    details=f'SMTP test successful for: {config.name}',
                    auto_commit=True
                )

                db.close()

                spinner.visible = False
                status_label.text = 'Test completed!'
                success_label.text = f'✓ Test email sent successfully to {test_email}'
                success_label.visible = True

                # Reload configs after 2 seconds
                await asyncio.sleep(2)
                dialog.close()
                load_smtp_configs(user, container)

            except Exception as e:
                # Update test status with error
                db = get_db()
                config_obj = db.query(SmtpConfig).filter(SmtpConfig.id == config.id).first()
                config_obj.last_test_date = datetime.utcnow()
                config_obj.last_test_result = f'Error: {str(e)}'[:500]
                db.commit()
                db.close()

                spinner.visible = False
                status_label.text = 'Test failed!'
                error_label.text = f'Error: {str(e)}'
                error_label.visible = True

        with ui.row().classes('w-full justify-end gap-2 mt-4'):
            ui.button('Cancel', on_click=dialog.close).props('flat')
            ui.button(
                'Send Test Email',
                on_click=lambda: asyncio.create_task(send_test_email()),
                color='primary'
            )

    dialog.open()


def set_active_smtp(user, config, container):
    """Set an SMTP configuration as active"""
    try:
        db = get_db()

        # Deactivate all configs
        db.query(SmtpConfig).update({SmtpConfig.is_active: False})

        # Activate selected config
        config_obj = db.query(SmtpConfig).filter(SmtpConfig.id == config.id).first()
        config_obj.is_active = True

        db.commit()

        # Create audit log
        create_audit_log(
            db=db,
            user_id=user.id,
            action='smtp_config_activated',
            resource_type='smtp_config',
            resource_id=config.id,
            details=f'Activated SMTP config: {config.name}',
            auto_commit=True
        )

        db.close()

        Toast.success(f'SMTP configuration "{config.name}" is now active!')
        load_smtp_configs(user, container)

    except Exception as e:
        Toast.error(f'Error activating configuration: {str(e)}')


def confirm_delete_smtp(user, config, container):
    """Confirm and delete SMTP configuration"""
    def handle_delete():
        try:
            db = get_db()

            # Create audit log before deletion
            create_audit_log(
                db=db,
                user_id=user.id,
                action='smtp_config_deleted',
                resource_type='smtp_config',
                resource_id=config.id,
                details=f'Deleted SMTP config: {config.name}',
                auto_commit=True
            )

            # Delete config
            db.query(SmtpConfig).filter(SmtpConfig.id == config.id).delete()
            db.commit()
            db.close()

            Toast.success(f'SMTP configuration "{config.name}" deleted successfully!')
            load_smtp_configs(user, container)

        except Exception as e:
            Toast.error(f'Error deleting configuration: {str(e)}')

    ConfirmDialog.show(
        title='Delete SMTP Configuration',
        message=f'Are you sure you want to delete "{config.name}"? This action cannot be undone.',
        on_confirm=handle_delete,
        confirm_text='Delete',
        danger=True
    )