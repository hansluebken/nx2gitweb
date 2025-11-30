"""
Reusable UI components for Ninox2Git web application
"""
from typing import Optional, Callable, List, Dict, Any
from nicegui import ui
from datetime import datetime


# Color scheme
PRIMARY_COLOR = '#1976D2'
SECONDARY_COLOR = '#424242'
SUCCESS_COLOR = '#4CAF50'
WARNING_COLOR = '#FF9800'
ERROR_COLOR = '#F44336'
INFO_COLOR = '#2196F3'


class NavHeader:
    """Navigation header component"""

    def __init__(self, user, current_page: str = ''):
        """
        Create navigation header

        Args:
            user: Current user object
            current_page: Current page identifier
        """
        self.user = user
        self.current_page = current_page

    def render(self):
        """Render the navigation header"""
        with ui.header().classes('items-center justify-between').style(
            f'background-color: {PRIMARY_COLOR}; padding: 1rem 2rem;'
        ):
            with ui.row().classes('items-center gap-2'):
                ui.label('Ninox2Git').classes('text-h5 font-bold')
                if self.user.is_admin:
                    ui.badge('Admin', color='orange').classes('ml-2')

            with ui.row().classes('items-center gap-4'):
                # Dashboard (kein Dropdown)
                self._nav_link('Dashboard', '/dashboard', 'dashboard')
                
                # Ninox Dropdown
                self._nav_dropdown('Ninox', 'cloud', [
                    ('Servers', '/servers', 'storage'),
                    ('Teams', '/teams', 'group'),
                    ('Sync', '/sync', 'sync'),
                ], ['servers', 'teams', 'sync'])
                
                # Entwicklung Dropdown
                self._nav_dropdown('Entwicklung', 'code', [
                    ('Code', '/code-viewer', 'code'),
                    ('JSON', '/json-viewer', 'data_object'),
                    ('Änderungen', '/changes', 'history'),
                ], ['code-viewer', 'json-viewer', 'changes'])
                
                # Einstellungen Dropdown (mit Cronjobs und Admin)
                settings_items = [
                    ('Cronjobs', '/cronjobs', 'schedule'),
                ]
                settings_pages = ['cronjobs']
                
                if self.user.is_admin:
                    settings_items.append(('Admin', '/admin', 'admin_panel_settings'))
                    settings_pages.append('admin')
                
                self._nav_dropdown('', 'settings', settings_items, settings_pages, icon_only=True)

                # User menu
                with ui.button(icon='account_circle', color='white').props('flat'):
                    with ui.menu():
                        ui.menu_item(
                            f'{self.user.full_name or self.user.username}',
                            on_click=lambda: None
                        ).props('disable')
                        ui.separator()
                        ui.menu_item('Profil', on_click=lambda: ui.navigate.to('/profile'))
                        ui.menu_item('Abmelden', on_click=lambda: ui.navigate.to('/logout'))

    def _nav_link(self, label: str, path: str, icon: str):
        """Create a navigation link"""
        is_active = self.current_page == label.lower()
        btn = ui.button(
            label,
            icon=icon,
            on_click=lambda: ui.navigate.to(path)
        ).props('flat')

        if is_active:
            btn.classes('bg-white bg-opacity-20')
        else:
            btn.classes('text-white')
    
    def _nav_dropdown(self, label: str, icon: str, items: list, active_pages: list, icon_only: bool = False):
        """Create a navigation dropdown menu"""
        # Check if any sub-item is active
        is_active = self.current_page in active_pages
        
        # Create button with dropdown - no color prop, use classes for styling
        if icon_only:
            btn = ui.button(icon=icon).props('flat')
        else:
            btn = ui.button(label, icon=icon).props('flat')
        
        if is_active:
            btn.classes('text-white bg-white bg-opacity-20')
        else:
            btn.classes('text-white')
        
        with btn:
            with ui.menu().classes('bg-white'):
                for item_label, item_path, item_icon in items:
                    item_active = self.current_page == item_path.strip('/').replace('-', '-')
                    # Check various formats of current_page
                    page_id = item_path.strip('/').replace('-viewer', '').replace('-', '')
                    is_item_active = (
                        self.current_page == item_path.strip('/') or
                        self.current_page == page_id or
                        self.current_page == item_label.lower()
                    )
                    
                    with ui.menu_item(on_click=lambda p=item_path: ui.navigate.to(p)):
                        with ui.row().classes('items-center gap-2'):
                            ui.icon(item_icon, size='sm').classes(
                                'text-primary' if is_item_active else 'text-grey-7'
                            )
                            ui.label(item_label).classes(
                                'font-bold' if is_item_active else ''
                            )


class Card:
    """Card component for displaying content"""

    def __init__(self, title: Optional[str] = None, icon: Optional[str] = None):
        """
        Create a card

        Args:
            title: Card title
            icon: Material icon name
        """
        self.title = title
        self.icon = icon
        self.container = None

    def __enter__(self):
        """Context manager entry"""
        self.container = ui.card().classes('w-full p-4')
        self.container.__enter__()

        if self.title or self.icon:
            with ui.row().classes('items-center gap-2 mb-4'):
                if self.icon:
                    ui.icon(self.icon, size='md').classes('text-primary')
                if self.title:
                    ui.label(self.title).classes('text-h6 font-bold')

        return self

    def __exit__(self, *args):
        """Context manager exit"""
        if self.container:
            self.container.__exit__(*args)


class StatsCard:
    """Statistics card component"""

    @staticmethod
    def render(title: str, value: str, icon: str, color: str = PRIMARY_COLOR):
        """
        Render a statistics card

        Args:
            title: Card title
            value: Value to display
            icon: Material icon name
            color: Card color
        """
        with ui.card().classes('p-4').style(f'border-left: 4px solid {color};'):
            with ui.row().classes('items-center justify-between w-full'):
                with ui.column().classes('gap-1'):
                    ui.label(title).classes('text-caption text-grey-7')
                    ui.label(value).classes('text-h5 font-bold')
                ui.icon(icon, size='lg').style(f'color: {color}; opacity: 0.6;')


class ConfirmDialog:
    """Confirmation dialog component"""

    @staticmethod
    def show(
        title: str,
        message: str,
        on_confirm: Callable,
        confirm_text: str = 'Confirm',
        cancel_text: str = 'Cancel',
        danger: bool = False
    ):
        """
        Show confirmation dialog

        Args:
            title: Dialog title
            message: Dialog message
            on_confirm: Callback function when confirmed
            confirm_text: Confirm button text
            cancel_text: Cancel button text
            danger: Whether this is a dangerous action
        """
        with ui.dialog() as dialog, ui.card().classes('p-4'):
            with ui.row().classes('items-center gap-2 mb-4'):
                icon_name = 'warning' if danger else 'help'
                icon_color = ERROR_COLOR if danger else WARNING_COLOR
                ui.icon(icon_name, size='lg').style(f'color: {icon_color};')
                ui.label(title).classes('text-h6 font-bold')

            ui.label(message).classes('mb-4')

            with ui.row().classes('gap-2 justify-end w-full'):
                ui.button(cancel_text, on_click=dialog.close).props('flat')
                btn_color = 'negative' if danger else 'primary'
                ui.button(
                    confirm_text,
                    on_click=lambda: (on_confirm(), dialog.close()),
                    color=btn_color
                )

        dialog.open()


class LoadingSpinner:
    """Loading spinner component"""

    def __init__(self, message: str = 'Loading...'):
        """
        Create loading spinner

        Args:
            message: Loading message
        """
        self.message = message
        self.container = None

    def __enter__(self):
        """Context manager entry"""
        self.container = ui.column().classes('items-center justify-center gap-4 p-8')
        self.container.__enter__()
        ui.spinner(size='lg', color='primary')
        ui.label(self.message).classes('text-grey-7')
        return self

    def __exit__(self, *args):
        """Context manager exit"""
        if self.container:
            self.container.__exit__(*args)


class DataTable:
    """Data table component"""

    @staticmethod
    def render(
        columns: List[Dict[str, Any]],
        rows: List[Dict[str, Any]],
        row_key: str = 'id',
        on_row_click: Optional[Callable] = None
    ):
        """
        Render a data table

        Args:
            columns: List of column definitions
            rows: List of row data
            row_key: Key field for rows
            on_row_click: Callback when row is clicked

        Returns:
            ui.table object
        """
        table = ui.table(
            columns=columns,
            rows=rows,
            row_key=row_key
        ).classes('w-full')

        if on_row_click:
            table.on('row-click', on_row_click)

        return table


class FormField:
    """Form field wrapper component"""

    @staticmethod
    def text(
        label: str,
        placeholder: str = '',
        value: str = '',
        required: bool = False,
        validation: Optional[Dict[str, str]] = None
    ):
        """
        Create text input field

        Args:
            label: Field label
            placeholder: Placeholder text
            value: Initial value
            required: Whether field is required
            validation: Validation rules

        Returns:
            ui.input object
        """
        input_field = ui.input(
            label=label,
            placeholder=placeholder,
            value=value
        ).classes('w-full')

        if required:
            input_field.props('required')

        if validation:
            input_field.validation = validation

        return input_field

    @staticmethod
    def password(
        label: str,
        placeholder: str = '',
        required: bool = False
    ):
        """
        Create password input field

        Args:
            label: Field label
            placeholder: Placeholder text
            required: Whether field is required

        Returns:
            ui.input object
        """
        input_field = ui.input(
            label=label,
            placeholder=placeholder,
            password=True,
            password_toggle_button=True
        ).classes('w-full')

        if required:
            input_field.props('required')

        return input_field

    @staticmethod
    def textarea(
        label: str,
        placeholder: str = '',
        value: str = '',
        rows: int = 3
    ):
        """
        Create textarea field

        Args:
            label: Field label
            placeholder: Placeholder text
            value: Initial value
            rows: Number of rows

        Returns:
            ui.textarea object
        """
        return ui.textarea(
            label=label,
            placeholder=placeholder,
            value=value
        ).classes('w-full').props(f'rows="{rows}"')

    @staticmethod
    def select(
        label: str,
        options: List[Any],
        value: Optional[Any] = None,
        required: bool = False
    ):
        """
        Create select field

        Args:
            label: Field label
            options: List of options
            value: Initial value
            required: Whether field is required

        Returns:
            ui.select object
        """
        select_field = ui.select(
            label=label,
            options=options,
            value=value
        ).classes('w-full')

        if required:
            select_field.props('required')

        return select_field

    @staticmethod
    def checkbox(label: str, value: bool = False):
        """
        Create checkbox field

        Args:
            label: Field label
            value: Initial value

        Returns:
            ui.checkbox object
        """
        return ui.checkbox(label, value=value)


class Toast:
    """Toast notification helpers"""

    @staticmethod
    def success(message: str):
        """Show success toast"""
        ui.notify(message, type='positive', position='top-right')

    @staticmethod
    def error(message: str):
        """Show error toast"""
        ui.notify(message, type='negative', position='top-right')

    @staticmethod
    def warning(message: str):
        """Show warning toast"""
        ui.notify(message, type='warning', position='top-right')

    @staticmethod
    def info(message: str):
        """Show info toast"""
        ui.notify(message, type='info', position='top-right')


class EmptyState:
    """Empty state component"""

    @staticmethod
    def render(
        icon: str,
        title: str,
        message: str,
        action_label: Optional[str] = None,
        on_action: Optional[Callable] = None
    ):
        """
        Render empty state

        Args:
            icon: Material icon name
            title: Title text
            message: Message text
            action_label: Action button label
            on_action: Action button callback
        """
        with ui.column().classes('items-center justify-center gap-4 p-8 text-center'):
            ui.icon(icon, size='xl').classes('text-grey-5')
            ui.label(title).classes('text-h6 font-bold text-grey-7')
            ui.label(message).classes('text-grey-6')

            if action_label and on_action:
                ui.button(action_label, on_click=on_action, color='primary')


class Badge:
    """Badge component"""

    @staticmethod
    def render(label: str, color: str = 'primary', icon: Optional[str] = None):
        """
        Render a badge

        Args:
            label: Badge label
            color: Badge color
            icon: Optional icon

        Returns:
            ui.badge object
        """
        badge = ui.badge(label, color=color)

        if icon:
            with badge:
                ui.icon(icon, size='sm')

        return badge


class StatusBadge:
    """Status badge component"""

    @staticmethod
    def render(status: str, active: bool = True):
        """
        Render a status badge

        Args:
            status: Status text
            active: Whether status is active/positive

        Returns:
            ui.badge object
        """
        color = SUCCESS_COLOR if active else 'grey'
        icon = 'check_circle' if active else 'cancel'

        with ui.row().classes('items-center gap-1'):
            ui.icon(icon, size='sm').style(f'color: {color};')
            ui.label(status).classes('text-caption').style(f'color: {color};')


def format_datetime(dt: Optional[datetime]) -> str:
    """
    Format datetime for display

    Args:
        dt: Datetime object

    Returns:
        Formatted string
    """
    if not dt:
        return 'Never'

    now = datetime.utcnow()
    diff = now - dt

    if diff.days > 7:
        return dt.strftime('%Y-%m-%d %H:%M')
    elif diff.days > 0:
        return f'{diff.days} days ago'
    elif diff.seconds > 3600:
        hours = diff.seconds // 3600
        return f'{hours} hours ago'
    elif diff.seconds > 60:
        minutes = diff.seconds // 60
        return f'{minutes} minutes ago'
    else:
        return 'Just now'


def truncate_text(text: str, max_length: int = 50) -> str:
    """
    Truncate text with ellipsis

    Args:
        text: Text to truncate
        max_length: Maximum length

    Returns:
        Truncated text
    """
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + '...'
