"""
Kivy-based GUI for ReMarkable file uploader.
Clean, modern interface without the bugs of tkinter.
"""

import os
import sys
import threading
from pathlib import Path
from typing import List, Optional
import asyncio

# Configure Kivy before importing
from kivy.config import Config
Config.set('input', 'mouse', 'mouse,multitouch_on_demand')
Config.set('graphics', 'multisamples', '0')

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.uix.progressbar import ProgressBar
from kivy.uix.popup import Popup
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.core.window import Window
from kivymd.app import MDApp
from kivymd.uix.screen import MDScreen
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDRaisedButton, MDIconButton
from kivymd.uix.textfield import MDTextField
from kivymd.uix.label import MDLabel
from kivymd.uix.card import MDCard
from kivymd.uix.list import MDList, OneLineListItem, TwoLineListItem
from kivymd.uix.scrollview import MDScrollView
from kivymd.uix.progressbar import MDProgressBar
from kivymd.uix.dialog import MDDialog
from kivymd.uix.floatlayout import MDFloatLayout
from kivymd.theming import ThemableBehavior
from kivymd.uix.selectioncontrol import MDCheckbox
from kivymd.uix.menu import MDDropdownMenu
from plyer import filechooser

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from services.remarkable_service import ReMarkableService
from services.markdown_service import MarkdownService
from services.network_service import NetworkService
from config.settings import get_config, save_config


class StatusMessage:
    """Status message container."""
    def __init__(self, text: str, level: str = 'info'):
        self.text = text
        self.level = level  # 'info', 'success', 'error', 'warning'


class EnhancedListItem(TwoLineListItem):
    """Enhanced list item with right-click support and checkboxes."""
    
    def __init__(self, app_instance, item_type, item_data, **kwargs):
        super().__init__(**kwargs)
        self.app_instance = app_instance
        self.item_type = item_type  # 'upload' or 'device'
        self.item_data = item_data
        self.selected = False
        
        # Add checkbox as an icon on the right side instead of overlapping
        self.checkbox = MDCheckbox(
            size_hint=(None, None),
            size=(dp(30), dp(30)),
            pos_hint={'center_y': 0.5, 'right': 1},
            on_active=self.on_checkbox_active
        )
        
        # Use the built-in right area for the checkbox
        self.add_widget(self.checkbox)
    
    def on_checkbox_active(self, checkbox, value):
        """Handle checkbox state change."""
        self.selected = value
        # Update app's selection tracking
        if self.item_type == 'device':
            if value:
                if self.item_data not in self.app_instance.selected_device_files:
                    self.app_instance.selected_device_files.append(self.item_data)
            else:
                if self.item_data in self.app_instance.selected_device_files:
                    self.app_instance.selected_device_files.remove(self.item_data)
        else:  # upload queue
            if value:
                if self.item_data not in self.app_instance.selected_upload_files:
                    self.app_instance.selected_upload_files.append(self.item_data)
            else:
                if self.item_data in self.app_instance.selected_upload_files:
                    self.app_instance.selected_upload_files.remove(self.item_data)
        
    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            if touch.button == 'right':
                self.show_context_menu(touch.pos)
                return True
        return super().on_touch_down(touch)
    
    def show_context_menu(self, pos):
        """Show context menu for this item."""
        if self.item_type == 'upload':
            menu_items = [
                {
                    "text": "Remove from Queue",
                    "on_release": lambda: self.remove_from_queue()
                },
                {
                    "text": "View File Info",
                    "on_release": lambda: self.show_file_info()
                },
                {
                    "text": "Open File Location",
                    "on_release": lambda: self.open_file_location()
                }
            ]
        else:  # device file
            menu_items = [
                {
                    "text": "View Document Info",
                    "on_release": lambda: self.show_document_info()
                },
                {
                    "text": "Rename Document",
                    "on_release": lambda: self.rename_document()
                },
                {
                    "text": "Delete from Device",
                    "on_release": lambda: self.delete_from_device()
                },
                {
                    "text": "Download File",
                    "on_release": lambda: self.download_file()
                }
            ]
        
        # Create simple popup without animations
        content = BoxLayout(orientation='vertical', spacing=5, padding=10)
        
        # Add menu buttons
        for item in menu_items:
            btn = Button(
                text=item['text'],
                size_hint_y=None,
                height=40,
                on_release=lambda x, action=item['on_release']: self._execute_menu_action(popup, action)
            )
            content.add_widget(btn)
        
        # Create popup without animations
        popup = Popup(
            title='Actions',
            content=content,
            size_hint=(None, None),
            size=(200, len(menu_items) * 50 + 60),
            auto_dismiss=True,
            title_size='16sp'
        )
        
        # Position popup at cursor location
        popup.pos = (pos[0] - 100, pos[1] - popup.height // 2)
        
        # Store popup reference for menu action callbacks
        self.menu = popup
        popup.open()
    
    def _execute_menu_action(self, popup, action):
        """Execute menu action and dismiss popup."""
        popup.dismiss()
        action()
    
    def remove_from_queue(self):
        """Remove file from upload queue."""
        self.app_instance.remove_from_queue(self.item_data)
    
    def show_file_info(self):
        """Show file information dialog."""
        from pathlib import Path
        import os
        import datetime
        
        file_path = Path(self.item_data)
        if file_path.exists():
            stat = file_path.stat()
            size_mb = stat.st_size / (1024 * 1024)
            mod_time = datetime.datetime.fromtimestamp(stat.st_mtime)
            
            info_text = f"""File: {file_path.name}
Path: {file_path.parent}
Size: {size_mb:.2f} MB
Type: {file_path.suffix.upper()[1:]} file
Modified: {mod_time.strftime('%Y-%m-%d %H:%M:%S')}"""
        else:
            info_text = f"File not found: {file_path}"
        
        dialog = MDDialog(
            title="File Information",
            text=info_text,
            buttons=[
                MDRaisedButton(
                    text="OK",
                    on_release=lambda x: dialog.dismiss()
                )
            ]
        )
        dialog.open()
    
    def open_file_location(self):
        """Open file location in system file manager."""
        import subprocess
        import platform
        from pathlib import Path
        
        file_path = Path(self.item_data)
        folder_path = file_path.parent
        
        try:
            system = platform.system()
            if system == "Windows":
                subprocess.run(f'explorer /select,"{file_path}"', shell=True)
            elif system == "Darwin":  # macOS
                subprocess.run(["open", "-R", str(file_path)])
            else:  # Linux
                subprocess.run(["xdg-open", str(folder_path)])
                
            self.app_instance.update_status(f"Opened location: {folder_path}", "info")
        except Exception as e:
            self.app_instance.update_status(f"Failed to open location: {e}", "error")
    
    def show_document_info(self):
        """Show document information dialog."""
        doc = self.item_data
        info_text = f"""Title: {doc.get('title', 'Unknown')}
UUID: {doc.get('uuid', 'Unknown')}
Type: {doc.get('file_type', 'Unknown').upper()}
Last Modified: {doc.get('last_modified', 'Unknown')}
Size: {doc.get('size', 'Unknown')}"""
        
        dialog = MDDialog(
            title="Document Information",
            text=info_text,
            buttons=[
                MDRaisedButton(
                    text="OK",
                    on_release=lambda x: dialog.dismiss()
                )
            ]
        )
        dialog.open()
    
    def rename_document(self):
        """Rename document on device."""
        from kivymd.uix.textfield import MDTextField
        from kivymd.uix.boxlayout import MDBoxLayout
        
        doc = self.item_data
        current_title = doc.get('title', 'Unknown')
        
        # Create rename dialog
        content = MDBoxLayout(orientation='vertical', spacing=dp(10), size_hint_y=None, height=dp(80))
        
        text_field = MDTextField(
            hint_text="New document name",
            text=current_title,
            multiline=False
        )
        content.add_widget(text_field)
        
        dialog = MDDialog(
            title="Rename Document",
            type="custom",
            content_cls=content,
            buttons=[
                MDRaisedButton(
                    text="CANCEL",
                    on_release=lambda x: dialog.dismiss()
                ),
                MDRaisedButton(
                    text="RENAME",
                    on_release=lambda x: self._perform_rename(dialog, text_field.text, doc)
                )
            ]
        )
        dialog.open()
    
    def _perform_rename(self, dialog, new_title, doc):
        """Perform the actual rename operation."""
        dialog.dismiss()
        
        if not new_title.strip():
            self.app_instance.update_status("Document name cannot be empty", "error")
            return
        
        try:
            # Get the UUID and rename using the service
            uuid = doc.get('uuid')
            if uuid and self.app_instance.remarkable_service:
                self.app_instance.update_status(f"Renaming '{doc.get('title')}' to '{new_title.strip()}'...", "info")
                
                # Use the actual rename function
                if self.app_instance.remarkable_service.rename_document(uuid, new_title.strip()):
                    # Update the local document data
                    doc['title'] = new_title.strip()
                    
                    # Refresh the device files list
                    self.app_instance.refresh_device_files()
                    self.app_instance.update_status(f"Document renamed to '{new_title.strip()}'", "success")
                else:
                    self.app_instance.update_status("Failed to rename document on device", "error")
            else:
                self.app_instance.update_status("Cannot rename: document UUID missing or not connected", "error")
                
        except Exception as e:
            self.app_instance.update_status(f"Failed to rename document: {e}", "error")
    
    def delete_from_device(self):
        """Delete document from device."""
        doc = self.item_data
        title = doc.get('title', 'Unknown Document')
        
        # Create confirmation dialog
        dialog = MDDialog(
            title="Delete Document",
            text=f"Are you sure you want to delete '{title}' from your ReMarkable device? This action cannot be undone.",
            buttons=[
                MDRaisedButton(
                    text="CANCEL",
                    on_release=lambda x: dialog.dismiss()
                ),
                MDRaisedButton(
                    text="DELETE",
                    theme_icon_color="Custom",
                    icon_color=(1, 0, 0, 1),
                    on_release=lambda x: self._perform_delete(dialog, doc)
                )
            ]
        )
        dialog.open()
    
    def _perform_delete(self, dialog, doc):
        """Perform the actual delete operation."""
        dialog.dismiss()
        
        try:
            uuid = doc.get('uuid')
            title = doc.get('title', 'Unknown Document')
            
            if uuid and self.app_instance.remarkable_service:
                self.app_instance.update_status(f"Deleting '{title}'...", "info")
                
                # Use the actual delete function
                if self.app_instance.remarkable_service.delete_document(uuid):
                    # Remove from local list
                    self.app_instance.device_files = [d for d in self.app_instance.device_files if d.get('uuid') != uuid]
                    self.app_instance.update_device_files_list()
                    self.app_instance.update_status(f"Document '{title}' deleted successfully", "success")
                else:
                    self.app_instance.update_status(f"Failed to delete '{title}' from device", "error")
            else:
                self.app_instance.update_status("Cannot delete: document UUID missing or not connected", "error")
                
        except Exception as e:
            self.app_instance.update_status(f"Failed to delete document: {e}", "error")
    
    def download_file(self):
        """Download file from device."""
        doc = self.item_data
        title = doc.get('title', 'Unknown Document')
        file_type = doc.get('file_type', 'pdf')
        uuid = doc.get('uuid')
        
        try:
            from pathlib import Path
            
            if not uuid or not self.app_instance.remarkable_service:
                self.app_instance.update_status("Cannot download: document UUID missing or not connected", "error")
                return
            
            # Choose download location
            downloads_dir = Path.home() / "Downloads"
            downloads_dir.mkdir(exist_ok=True)
            
            # Create filename
            safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).rstrip()
            filename = f"{safe_title}.{file_type}"
            download_path = downloads_dir / filename
            
            # Make sure filename is unique
            counter = 1
            while download_path.exists():
                name_part = f"{safe_title}_{counter}"
                filename = f"{name_part}.{file_type}"
                download_path = downloads_dir / filename
                counter += 1
            
            self.app_instance.update_status(f"Downloading '{title}' to {download_path}...", "info")
            
            # Use the actual download function
            if self.app_instance.remarkable_service.download_document(uuid, download_path):
                self.app_instance.update_status(f"Document downloaded to {download_path}", "success")
            else:
                self.app_instance.update_status(f"Failed to download '{title}' from device", "error")
            
        except Exception as e:
            self.app_instance.update_status(f"Failed to download document: {e}", "error")


class ReMarkableUploaderApp(MDApp):
    """Main Kivy application for ReMarkable file uploader."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.title = "ReMarkable File Uploader"
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "Orange"
        
        # Services
        self.remarkable_service = None
        self.markdown_service = None
        self.network_service = None
        self.device = None
        
        # UI components
        self.ip_field = None
        self.password_field = None
        self.connect_button = None
        self.status_label = None
        self.progress_bar = None
        self.upload_list = None
        self.device_files_list = None
        self.tabs = None
        
        # State
        self.upload_queue = []
        self.device_files = []
        self.is_connected = False
        
        # Selection tracking
        self.selected_device_files = []
        self.selected_upload_files = []
        
        # Load app config (renamed to avoid conflict with Kivy's config)
        try:
            self.app_config = get_config()
        except:
            from config.settings import AppConfig
            self.app_config = AppConfig()
    
    def build(self):
        """Build the main UI."""
        # Set window size
        Window.size = (1200, 800)
        
        # Main screen
        screen = MDScreen()
        
        # Main layout
        main_layout = MDBoxLayout(orientation='vertical', spacing=dp(10), padding=dp(10))
        
        # Connection panel
        connection_card = self.create_connection_panel()
        main_layout.add_widget(connection_card)
        
        # Status panel
        status_card = self.create_status_panel()
        main_layout.add_widget(status_card)
        
        # Unified file manager
        file_manager = self.create_unified_file_manager()
        main_layout.add_widget(file_manager)
        
        screen.add_widget(main_layout)
        
        # Initialize services
        self.initialize_services()
        
        # Auto-connect if credentials are saved
        Clock.schedule_once(self.auto_connect, 1)
        
        return screen
    
    def create_connection_panel(self):
        """Create the connection panel."""
        card = MDCard(
            size_hint_y=None,
            height=dp(120),
            elevation=3,
            padding=dp(15),
            spacing=dp(10)
        )
        
        layout = MDBoxLayout(orientation='vertical', spacing=dp(10))
        
        # Title
        title = MDLabel(
            text="ReMarkable Connection",
            theme_text_color="Primary",
            font_style="H6",
            size_hint_y=None,
            height=dp(30)
        )
        layout.add_widget(title)
        
        # Connection fields
        fields_layout = MDBoxLayout(orientation='horizontal', spacing=dp(10))
        
        # IP field
        self.ip_field = MDTextField(
            hint_text="IP Address",
            text=self.app_config.device.ip_address or "10.11.99.1",
            size_hint_x=0.3
        )
        fields_layout.add_widget(self.ip_field)
        
        # Password field
        self.password_field = MDTextField(
            hint_text="SSH Password",
            text=self.app_config.device.ssh_password or "",
            password=True,
            size_hint_x=0.4
        )
        fields_layout.add_widget(self.password_field)
        
        # Connect button
        self.connect_button = MDRaisedButton(
            text="CONNECT",
            size_hint_x=0.3,
            on_release=self.toggle_connection
        )
        fields_layout.add_widget(self.connect_button)
        
        layout.add_widget(fields_layout)
        card.add_widget(layout)
        
        return card
    
    def create_status_panel(self):
        """Create the status panel."""
        card = MDCard(
            size_hint_y=None,
            height=dp(80),
            elevation=3,
            padding=dp(15)
        )
        
        layout = MDBoxLayout(orientation='vertical', spacing=dp(10))
        
        # Status label
        self.status_label = MDLabel(
            text="Ready to connect...",
            theme_text_color="Secondary",
            size_hint_y=None,
            height=dp(30)
        )
        layout.add_widget(self.status_label)
        
        # Progress bar
        self.progress_bar = MDProgressBar(
            value=0,
            size_hint_y=None,
            height=dp(20)
        )
        layout.add_widget(self.progress_bar)
        
        card.add_widget(layout)
        return card
    
    def create_unified_file_manager(self):
        """Create the unified file manager interface."""
        card = MDCard(elevation=3, padding=dp(15))
        layout = MDBoxLayout(orientation='vertical', spacing=dp(10))
        
        # Title
        title = MDLabel(
            text="File Manager",
            theme_text_color="Primary",
            font_style="H6",
            size_hint_y=None,
            height=dp(30)
        )
        layout.add_widget(title)
        
        # Action buttons
        actions_layout = MDBoxLayout(
            orientation='horizontal',
            spacing=dp(10),
            size_hint_y=None,
            height=dp(50)
        )
        
        # Local files section
        local_btn = MDRaisedButton(
            text="ADD LOCAL FILES",
            size_hint_x=0.15,
            on_release=self.select_files
        )
        actions_layout.add_widget(local_btn)
        
        upload_btn = MDRaisedButton(
            text="UPLOAD SELECTED",
            size_hint_x=0.15,
            on_release=self.upload_selected_files,
            md_bg_color=self.theme_cls.primary_color
        )
        actions_layout.add_widget(upload_btn)
        
        refresh_btn = MDRaisedButton(
            text="REFRESH DEVICE",
            size_hint_x=0.15,
            on_release=self.refresh_device_files
        )
        actions_layout.add_widget(refresh_btn)
        
        clear_btn = MDRaisedButton(
            text="CLEAR QUEUE",
            size_hint_x=0.15,
            on_release=self.clear_upload_queue
        )
        actions_layout.add_widget(clear_btn)
        
        # Batch operations
        select_all_btn = MDRaisedButton(
            text="SELECT ALL",
            size_hint_x=0.15,
            on_release=self.select_all_files
        )
        actions_layout.add_widget(select_all_btn)
        
        batch_delete_btn = MDRaisedButton(
            text="BATCH DELETE",
            size_hint_x=0.15,
            md_bg_color=[0.8, 0.2, 0.2, 1],  # Red color
            on_release=self.batch_delete_selected
        )
        actions_layout.add_widget(batch_delete_btn)
        
        # Spacer
        actions_layout.add_widget(MDLabel(size_hint_x=0.1))
        
        layout.add_widget(actions_layout)
        
        # File lists container
        files_layout = MDBoxLayout(orientation='horizontal', spacing=dp(10))
        
        # Upload queue (left side)
        queue_card = MDCard(elevation=2, padding=dp(10))
        queue_layout = MDBoxLayout(orientation='vertical', spacing=dp(5))
        
        queue_title = MDLabel(
            text="Upload Queue",
            theme_text_color="Primary",
            font_style="Subtitle1",
            size_hint_y=None,
            height=dp(30)
        )
        queue_layout.add_widget(queue_title)
        
        queue_scroll = MDScrollView()
        self.upload_list = MDList()
        queue_scroll.add_widget(self.upload_list)
        queue_layout.add_widget(queue_scroll)
        
        queue_card.add_widget(queue_layout)
        files_layout.add_widget(queue_card)
        
        # Device files (right side)
        device_card = MDCard(elevation=2, padding=dp(10))
        device_layout = MDBoxLayout(orientation='vertical', spacing=dp(5))
        
        device_title = MDLabel(
            text="Device Files",
            theme_text_color="Primary", 
            font_style="Subtitle1",
            size_hint_y=None,
            height=dp(30)
        )
        device_layout.add_widget(device_title)
        
        device_scroll = MDScrollView()
        self.device_files_list = MDList()
        device_scroll.add_widget(self.device_files_list)
        device_layout.add_widget(device_scroll)
        
        device_card.add_widget(device_layout)
        files_layout.add_widget(device_card)
        
        layout.add_widget(files_layout)
        card.add_widget(layout)
        
        return card
    
    def initialize_services(self):
        """Initialize the backend services."""
        try:
            self.network_service = NetworkService()
            self.markdown_service = MarkdownService()
            self.update_status("Services initialized", "success")
        except Exception as e:
            self.update_status(f"Service initialization failed: {e}", "error")
    
    def auto_connect(self, dt):
        """Auto-connect if credentials are available."""
        if (self.app_config.device.ip_address and 
            self.app_config.device.ssh_password and 
            not self.is_connected):
            self.toggle_connection()
    
    def toggle_connection(self, *args):
        """Toggle connection to ReMarkable device."""
        if self.is_connected:
            self.disconnect()
        else:
            self.connect()
    
    def connect(self):
        """Connect to ReMarkable device."""
        ip = self.ip_field.text.strip()
        password = self.password_field.text.strip()
        
        if not ip or not password:
            self.show_error("Please enter both IP address and password")
            return
        
        # Update button state
        self.connect_button.text = "CONNECTING..."
        self.connect_button.disabled = True
        self.update_status("Connecting to ReMarkable...", "info")
        
        # Connect in background thread
        threading.Thread(target=self._connect_worker, args=(ip, password), daemon=True).start()
    
    def _connect_worker(self, ip, password):
        """Background worker for connection."""
        try:
            # Initialize network service
            from services.network_service import init_network_service, get_network_service
            network_service = init_network_service(
                connection_timeout=10,
                max_retries=3,
                retry_delay=2,
                keepalive_interval=30
            )
            
            # Set connection details
            network_service.set_connection_details(ip, password)
            
            # Test connection
            if not network_service.connect():
                raise Exception(f"Failed to connect: {network_service.last_error}")
            
            # Get ReMarkable service instance
            from services.remarkable_service import get_remarkable_service
            self.remarkable_service = get_remarkable_service()
            
            # Test connection by listing documents
            documents = self.remarkable_service.list_all_documents()
            
            # Update UI on main thread
            Clock.schedule_once(lambda dt: self._connection_success(documents), 0)
            
            # Save credentials
            self.app_config.device.ip_address = ip
            self.app_config.device.ssh_password = password
            save_config()
            
        except Exception as e:
            # Update UI on main thread
            error_msg = str(e)
            Clock.schedule_once(lambda dt: self._connection_failed(error_msg), 0)
    
    def _connection_success(self, documents):
        """Handle successful connection."""
        self.is_connected = True
        self.connect_button.text = "DISCONNECT"
        self.connect_button.disabled = False
        self.connect_button.md_bg_color = self.theme_cls.accent_color
        
        self.device_files = documents
        self.update_status(f"Connected! Found {len(documents)} documents on device", "success")
        self.update_device_files_list()
    
    def _connection_failed(self, error):
        """Handle connection failure."""
        self.is_connected = False
        self.connect_button.text = "CONNECT"
        self.connect_button.disabled = False
        self.connect_button.md_bg_color = self.theme_cls.primary_color
        self.update_status(f"Connection failed: {error}", "error")
        
        # Clear any existing device files
        self.device_files = []
        self.update_device_files_list()
    
    def disconnect(self):
        """Disconnect from ReMarkable device."""
        self.is_connected = False
        self.remarkable_service = None
        self.connect_button.text = "CONNECT"
        self.connect_button.md_bg_color = self.theme_cls.primary_color
        self.update_status("Disconnected", "info")
        self.device_files = []
        self.update_device_files_list()
    
    def select_files(self, *args):
        """Open file chooser to select files."""
        try:
            # Use plyer's filechooser for native file browser
            filechooser.open_file(
                title="Select Files to Upload",
                filters=[
                    ("Supported Files", "*.md;*.markdown;*.pdf;*.epub"),
                    ("Markdown Files", "*.md;*.markdown"),
                    ("PDF Files", "*.pdf"),
                    ("EPUB Files", "*.epub"),
                    ("All Files", "*.*")
                ],
                multiple=True,
                on_selection=self._on_files_selected
            )
            self.update_status("Opening file browser...", "info")
            
        except Exception as e:
            self.update_status(f"Failed to open file browser: {e}", "error")
            # Fallback to simple file discovery
            self._fallback_file_selection()
    
    def _on_files_selected(self, selected_files):
        """Handle files selected from file browser."""
        if not selected_files:
            self.update_status("No files selected", "info")
            return
        
        added_count = 0
        for file_path in selected_files:
            file_path = Path(file_path)
            
            # Check if file type is supported
            if file_path.suffix.lower() not in ['.md', '.markdown', '.pdf', '.epub']:
                self.update_status(f"Skipping unsupported file: {file_path.name}", "warning")
                continue
            
            # Check if already in queue
            if str(file_path) not in self.upload_queue:
                self.upload_queue.append(str(file_path))
                added_count += 1
            else:
                self.update_status(f"File already in queue: {file_path.name}", "warning")
        
        if added_count > 0:
            self.update_upload_list()
            self.update_status(f"Added {added_count} file(s) to upload queue", "success")
        else:
            self.update_status("No new files added to queue", "info")
    
    def _fallback_file_selection(self):
        """Fallback file selection when plyer fails."""
        try:
            from pathlib import Path
            
            # Look for files in common locations
            search_dirs = [
                Path.home() / "Documents",
                Path.home() / "Desktop", 
                Path.home() / "Downloads",
                Path.home() / "Documents" / "playaround"
            ]
            
            found_files = []
            for search_dir in search_dirs:
                if search_dir.exists():
                    for ext in ['*.md', '*.markdown', '*.pdf', '*.epub']:
                        found_files.extend(search_dir.glob(ext))
            
            if found_files:
                # Create selection dialog
                from kivymd.uix.list import OneLineListItem
                
                content = MDBoxLayout(orientation='vertical', spacing=dp(5))
                scroll = MDScrollView()
                file_list = MDList()
                
                for file_path in found_files[:20]:  # Limit to first 20 files
                    item = OneLineListItem(
                        text=f"{file_path.name} ({file_path.parent.name})",
                        on_release=lambda x, fp=file_path: self._add_file_from_fallback(fp, dialog)
                    )
                    file_list.add_widget(item)
                
                scroll.add_widget(file_list)
                content.add_widget(scroll)
                
                dialog = MDDialog(
                    title="Select Files",
                    type="custom",
                    content_cls=content,
                    buttons=[
                        MDRaisedButton(
                            text="CANCEL",
                            on_release=lambda x: dialog.dismiss()
                        )
                    ]
                )
                dialog.open()
            else:
                self.update_status("No supported files found in common locations", "warning")
                
        except Exception as e:
            self.update_status(f"Fallback file selection failed: {e}", "error")
    
    def _add_file_from_fallback(self, file_path, dialog):
        """Add file from fallback selection."""
        dialog.dismiss()
        if str(file_path) not in self.upload_queue:
            self.upload_queue.append(str(file_path))
            self.update_upload_list()
            self.update_status(f"Added {file_path.name} to upload queue", "success")
        else:
            self.update_status(f"File already in queue: {file_path.name}", "warning")
    
    def clear_upload_queue(self, *args):
        """Clear the upload queue."""
        self.upload_queue.clear()
        self.selected_upload_files.clear()
        self.update_upload_list()
        self.update_status("Upload queue cleared", "info")
    
    def upload_selected_files(self, *args):
        """Upload selected files in the queue."""
        if not self.is_connected:
            self.show_error("Please connect to device first")
            return
        
        if not self.upload_queue:
            self.show_error("No files in upload queue")
            return
        
        # Start upload in background
        threading.Thread(target=self._upload_worker, daemon=True).start()
    
    def upload_all_files(self, *args):
        """Upload all files in the queue."""
        self.upload_selected_files(*args)
    
    def _upload_worker(self):
        """Background worker for file uploads."""
        total_files = len(self.upload_queue)
        uploaded_files = []
        
        Clock.schedule_once(lambda dt: self.update_status(f"Starting upload of {total_files} file(s)...", "info"), 0)
        
        for i, file_path in enumerate(self.upload_queue):
            try:
                # Update progress
                progress = (i / total_files) * 100
                Clock.schedule_once(lambda dt, p=progress: setattr(self.progress_bar, 'value', p), 0)
                
                file_path = Path(file_path)
                filename = file_path.name
                
                self.update_status(f"Processing {filename}...", "info")
                
                # Handle different file types
                if file_path.suffix.lower() in ['.md', '.markdown']:
                    # Convert to PDF first
                    self.update_status(f"Converting {filename} to PDF...", "info")
                    
                    output_dir = Path.home() / '.cache' / 'readMarkable'
                    output_dir.mkdir(parents=True, exist_ok=True)
                    
                    pdf_path = self.markdown_service.process_markdown_file(file_path, output_dir)
                    
                    if pdf_path:
                        Clock.schedule_once(lambda dt: self.update_status("Uploading PDF to ReMarkable...", "info"), 0)
                        title = file_path.stem
                        uuid = self.remarkable_service.add_with_metadata_if_new(pdf_path, title)
                        
                        if uuid:
                            uploaded_files.append(file_path)
                            Clock.schedule_once(lambda dt: self.update_status(f"Successfully uploaded {filename} as PDF", "success"), 0)
                        else:
                            Clock.schedule_once(lambda dt: self.update_status(f"Failed to upload {filename}", "error"), 0)
                        
                        # Clean up temp PDF
                        pdf_path.unlink(missing_ok=True)
                    else:
                        Clock.schedule_once(lambda dt: self.update_status(f"Failed to convert {filename} to PDF", "error"), 0)
                
                elif file_path.suffix.lower() == '.pdf':
                    # Direct PDF upload
                    title = file_path.stem
                    uuid = self.remarkable_service.add_with_metadata_if_new(file_path, title)
                    
                    if uuid:
                        uploaded_files.append(file_path)
                        Clock.schedule_once(lambda dt: self.update_status(f"Successfully uploaded {filename}", "success"), 0)
                    else:
                        Clock.schedule_once(lambda dt: self.update_status(f"Failed to upload {filename}", "error"), 0)
                
                elif file_path.suffix.lower() == '.epub':
                    # EPUB upload
                    title = file_path.stem
                    uuid = self.remarkable_service.add_epub_with_metadata(file_path, title)
                    
                    if uuid:
                        uploaded_files.append(file_path)
                        Clock.schedule_once(lambda dt: self.update_status(f"Successfully uploaded {filename}", "success"), 0)
                    else:
                        Clock.schedule_once(lambda dt: self.update_status(f"Failed to upload {filename}", "error"), 0)
            
            except Exception as error:
                Clock.schedule_once(lambda dt: self.update_status(f"Error uploading {filename}: {str(error)}", "error"), 0)
        
        # Upload complete
        Clock.schedule_once(lambda dt: setattr(self.progress_bar, 'value', 100), 0)
        Clock.schedule_once(lambda dt: self.update_status(f"Upload complete: {len(uploaded_files)}/{total_files} files", "success"), 0)
        
        # Clear uploaded files from queue
        for file_path in uploaded_files:
            if file_path in self.upload_queue:
                self.upload_queue.remove(file_path)
        
        Clock.schedule_once(lambda dt: self.update_upload_list(), 0)
        Clock.schedule_once(lambda dt: self.refresh_device_files(), 0)
        
        # Reset progress after delay
        Clock.schedule_once(lambda dt: setattr(self.progress_bar, 'value', 0), 3)
    
    def refresh_device_files(self, *args):
        """Refresh the device files list."""
        if not self.is_connected:
            return
        
        threading.Thread(target=self._refresh_device_files_worker, daemon=True).start()
    
    def _refresh_device_files_worker(self):
        """Background worker to refresh device files."""
        try:
            documents = self.remarkable_service.list_all_documents()
            self.device_files = documents
            Clock.schedule_once(lambda dt: self.update_device_files_list(), 0)
            Clock.schedule_once(lambda dt: self.update_status(f"Found {len(documents)} documents on device", "info"), 0)
        except Exception as e:
            Clock.schedule_once(lambda dt: self.update_status(f"Failed to refresh device files: {e}", "error"), 0)
    
    def update_upload_list(self):
        """Update the upload queue list display."""
        self.upload_list.clear_widgets()
        
        for file_path in self.upload_queue:
            file_path_obj = Path(file_path)
            
            item = EnhancedListItem(
                app_instance=self,
                item_type='upload',
                item_data=file_path,
                text=file_path_obj.name,
                secondary_text=str(file_path_obj.parent)
            )
            
            self.upload_list.add_widget(item)
    
    def update_device_files_list(self):
        """Update the device files list display."""
        self.device_files_list.clear_widgets()
        
        # Clear selections when refreshing
        self.selected_device_files.clear()
        
        if not self.device_files:
            no_files_item = OneLineListItem(text="No documents found on device")
            self.device_files_list.add_widget(no_files_item)
            return
        
        for doc in self.device_files:
            title = doc.get('title', 'Unknown Document')
            file_type = doc.get('file_type', 'unknown')
            uuid = doc.get('uuid', 'no-uuid')
            
            # Create a more informative display with right-click support and checkboxes
            item = EnhancedListItem(
                app_instance=self,
                item_type='device',
                item_data=doc,
                text=f"{title} ({file_type.upper()})",
                secondary_text=f"UUID: {uuid[:8]}...{uuid[-8:]}" if len(uuid) > 16 else f"UUID: {uuid}"
            )
            
            self.device_files_list.add_widget(item)
    
    def remove_from_queue(self, file_path):
        """Remove a file from the upload queue."""
        if file_path in self.upload_queue:
            self.upload_queue.remove(file_path)
            self.update_upload_list()
            self.update_status(f"Removed {Path(file_path).name} from queue", "info")
    
    def update_status(self, message, level="info"):
        """Update the status message."""
        if level == "error":
            color = [1, 0.2, 0.2, 1]  # Red
        elif level == "success":
            color = [0.2, 0.8, 0.2, 1]  # Green
        elif level == "warning":
            color = [1, 0.8, 0.2, 1]  # Orange
        else:
            color = [0.7, 0.7, 0.7, 1]  # Gray
        
        self.status_label.text = message
        self.status_label.text_color = color
    
    def show_error(self, message):
        """Show an error dialog."""
        dialog = MDDialog(
            title="Error",
            text=message,
            buttons=[
                MDRaisedButton(
                    text="OK",
                    on_release=lambda x: dialog.dismiss()
                )
            ]
        )
        dialog.open()
    
    def select_all_files(self, *args):
        """Select or deselect all files in device list."""
        if not self.device_files:
            return
        
        # Check if all files are currently selected
        all_selected = len(self.selected_device_files) == len(self.device_files)
        
        # Toggle selection state
        if all_selected:
            # Deselect all
            self.selected_device_files.clear()
            for child in self.device_files_list.children:
                if hasattr(child, 'checkbox'):
                    child.checkbox.active = False
            self.update_status("Deselected all files", "info")
        else:
            # Select all
            self.selected_device_files = self.device_files.copy()
            for child in self.device_files_list.children:
                if hasattr(child, 'checkbox'):
                    child.checkbox.active = True
            self.update_status(f"Selected {len(self.device_files)} files", "info")
    
    def batch_delete_selected(self, *args):
        """Delete all selected device files."""
        if not self.selected_device_files:
            self.show_error("No files selected for deletion")
            return
        
        if not self.is_connected:
            self.show_error("Please connect to device first")
            return
        
        # Create confirmation dialog
        count = len(self.selected_device_files)
        file_list = "\n".join([doc.get('title', 'Unknown') for doc in self.selected_device_files[:5]])
        if count > 5:
            file_list += f"\n... and {count - 5} more files"
        
        dialog = MDDialog(
            title=f"Delete {count} Documents",
            text=f"Are you sure you want to delete these {count} documents from your ReMarkable device?\n\n{file_list}\n\nThis action cannot be undone.",
            buttons=[
                MDRaisedButton(
                    text="CANCEL",
                    on_release=lambda x: dialog.dismiss()
                ),
                MDRaisedButton(
                    text=f"DELETE {count} FILES",
                    theme_icon_color="Custom",
                    icon_color=(1, 0, 0, 1),
                    md_bg_color=[0.8, 0.2, 0.2, 1],
                    on_release=lambda x: self._perform_batch_delete(dialog)
                )
            ]
        )
        dialog.open()
    
    def _perform_batch_delete(self, dialog):
        """Perform the actual batch delete operation."""
        dialog.dismiss()
        
        # Start batch delete in background
        threading.Thread(target=self._batch_delete_worker, daemon=True).start()
    
    def _batch_delete_worker(self):
        """Background worker for batch delete."""
        total_files = len(self.selected_device_files)
        deleted_files = []
        
        Clock.schedule_once(lambda dt: self.update_status(f"Starting batch delete of {total_files} file(s)...", "info"), 0)
        
        for i, doc in enumerate(self.selected_device_files):
            try:
                # Update progress
                progress = (i / total_files) * 100
                Clock.schedule_once(lambda dt, p=progress: setattr(self.progress_bar, 'value', p), 0)
                
                uuid = doc.get('uuid')
                title = doc.get('title', 'Unknown Document')
                
                Clock.schedule_once(lambda dt, t=title: self.update_status(f"Deleting '{t}'...", "info"), 0)
                
                if uuid and self.remarkable_service:
                    if self.remarkable_service.delete_document(uuid):
                        deleted_files.append(doc)
                        Clock.schedule_once(lambda dt, t=title: self.update_status(f"Deleted '{t}'", "success"), 0)
                    else:
                        Clock.schedule_once(lambda dt, t=title: self.update_status(f"Failed to delete '{t}'", "error"), 0)
                else:
                    Clock.schedule_once(lambda dt, t=title: self.update_status(f"Cannot delete '{t}': missing UUID", "error"), 0)
                    
            except Exception as e:
                Clock.schedule_once(lambda dt, t=title, err=str(e): self.update_status(f"Error deleting '{t}': {err}", "error"), 0)
        
        # Batch delete complete
        Clock.schedule_once(lambda dt: setattr(self.progress_bar, 'value', 100), 0)
        Clock.schedule_once(lambda dt: self.update_status(f"Batch delete complete: {len(deleted_files)}/{total_files} files deleted", "success"), 0)
        
        # Remove deleted files from local lists
        for doc in deleted_files:
            if doc in self.device_files:
                self.device_files.remove(doc)
            if doc in self.selected_device_files:
                self.selected_device_files.remove(doc)
        
        # Update UI
        Clock.schedule_once(lambda dt: self.update_device_files_list(), 0)
        
        # Reset progress after delay
        Clock.schedule_once(lambda dt: setattr(self.progress_bar, 'value', 0), 3)


def main():
    """Run the Kivy application."""
    ReMarkableUploaderApp().run()


if __name__ == "__main__":
    main()