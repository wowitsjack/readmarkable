"""
Drag-and-drop file pusher GUI for ReMarkable.

Modern, user-friendly interface with drag-and-drop support,
file manager, and proper theming.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinterdnd2 import TkinterDnD, DND_FILES
from pathlib import Path
import threading
import os
from typing import Optional, List, Dict, Any
from datetime import datetime

from config.settings import get_config
from utils.logger import get_logger
from services.network_service import get_network_service
from services.markdown_service import get_markdown_service
from services.remarkable_service import get_remarkable_service
from models.device import Device


class DragDropZone(tk.Frame):
    """Drag and drop zone for file uploads."""
    
    def __init__(self, parent, callback):
        super().__init__(parent)
        self.callback = callback
        self.configure(bg='#2b2b2b', highlightthickness=2, highlightbackground='#444444')
        
        # Track drag state
        self.is_dragging = False
        
        # Create drop zone
        self.drop_frame = tk.Frame(self, bg='#3c3c3c', relief=tk.SUNKEN, bd=2)
        self.drop_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Drop zone label with icon
        self.drop_label = tk.Label(
            self.drop_frame,
            text="[ FILES ]\n\nDrag & Drop Files Here\n\nor click to browse",
            font=('Arial', 14),
            fg='#888888',
            bg='#3c3c3c',
            cursor='hand2'
        )
        self.drop_label.pack(expand=True)
        
        # Bind click to browse (only on label, not frame to avoid double events)
        self.drop_label.bind('<ButtonRelease-1>', self._browse_files)
        
        # Setup drag and drop with proper state tracking
        try:
            self.drop_frame.drop_target_register(DND_FILES)
            self.drop_frame.dnd_bind('<<Drop>>', self._on_drop)
            self.drop_frame.dnd_bind('<<DragEnter>>', self._on_drag_enter)
            self.drop_frame.dnd_bind('<<DragLeave>>', self._on_drag_leave)
        except Exception as e:
            print(f"Warning: Drag and drop setup failed: {e}")
    
    def _on_drop(self, event):
        """Handle file drop."""
        self.is_dragging = False
        files = self.tk.splitlist(event.data)
        self.drop_frame.configure(bg='#3c3c3c')
        self.drop_label.configure(bg='#3c3c3c')
        if self.callback:
            self.callback(files)
    
    def _on_drag_enter(self, event):
        """Handle drag enter."""
        if not self.is_dragging:
            self.is_dragging = True
            self.drop_frame.configure(bg='#4a4a4a')
            self.drop_label.configure(bg='#4a4a4a')
    
    def _on_drag_leave(self, event):
        """Handle drag leave."""
        self.is_dragging = False
        self.drop_frame.configure(bg='#3c3c3c')
        self.drop_label.configure(bg='#3c3c3c')
    
    def _browse_files(self, event=None):
        """Open file browser."""
        # Only open dialog if not dragging
        if not self.is_dragging:
            files = filedialog.askopenfilenames(
                title="Select files to upload",
                filetypes=[
                    ("Supported files", "*.md *.markdown *.pdf *.epub"),
                    ("Markdown files", "*.md *.markdown"),
                    ("PDF files", "*.pdf"),
                    ("EPUB files", "*.epub"),
                    ("All files", "*.*")
                ]
            )
            if files and self.callback:
                self.callback(list(files))


class FileManagerPanel(tk.Frame):
    """File manager panel with queue management and device file browser."""
    
    def __init__(self, parent, upload_callback, remove_callback):
        super().__init__(parent)
        self.upload_callback = upload_callback
        self.remove_callback = remove_callback
        self.configure(bg='#2b2b2b')
        
        # Create notebook for tabs
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        # Configure notebook style for dark theme
        style = ttk.Style()
        style.configure('TNotebook', background='#2b2b2b')
        style.configure('TNotebook.Tab', background='#3c3c3c', foreground='#ffffff', padding=[10, 5])
        style.map('TNotebook.Tab',
                  background=[('selected', '#5c5c5c')],
                  foreground=[('selected', '#ffffff')])
        
        # Upload Queue tab
        self.queue_frame = tk.Frame(self.notebook, bg='#2b2b2b')
        self.notebook.add(self.queue_frame, text='Upload Queue')
        
        # Title
        title = tk.Label(
            self.queue_frame,
            text="Files to Upload",
            font=('Arial', 12, 'bold'),
            fg='#ffffff',
            bg='#2b2b2b'
        )
        title.pack(pady=(10, 5))
        
        # File list with scrollbar
        list_frame = tk.Frame(self.queue_frame, bg='#2b2b2b')
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10)
        
        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.file_listbox = tk.Listbox(
            list_frame,
            bg='#3c3c3c',
            fg='#ffffff',
            selectbackground='#5c5c5c',
            selectforeground='#ffffff',
            font=('Arial', 10),
            yscrollcommand=scrollbar.set
        )
        self.file_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.file_listbox.yview)
        
        # Buttons
        button_frame = tk.Frame(self.queue_frame, bg='#2b2b2b')
        button_frame.pack(fill=tk.X, padx=10, pady=10)
        
        self.upload_btn = tk.Button(
            button_frame,
            text="Upload Selected",
            command=self._upload_selected,
            bg='#4CAF50',
            fg='white',
            font=('Arial', 10, 'bold'),
            cursor='hand2'
        )
        self.upload_btn.pack(side=tk.LEFT, padx=2)
        
        self.upload_all_btn = tk.Button(
            button_frame,
            text="Upload All",
            command=self._upload_all,
            bg='#2196F3',
            fg='white',
            font=('Arial', 10, 'bold'),
            cursor='hand2'
        )
        self.upload_all_btn.pack(side=tk.LEFT, padx=2)
        
        self.remove_btn = tk.Button(
            button_frame,
            text="Remove",
            command=self._remove_selected,
            bg='#f44336',
            fg='white',
            font=('Arial', 10, 'bold'),
            cursor='hand2'
        )
        self.remove_btn.pack(side=tk.LEFT, padx=2)
        
        self.clear_btn = tk.Button(
            button_frame,
            text="Clear All",
            command=self._clear_all,
            bg='#666666',
            fg='white',
            font=('Arial', 10, 'bold'),
            cursor='hand2'
        )
        self.clear_btn.pack(side=tk.LEFT, padx=2)
        
        # File tracking
        self.files = []
        
        # Device Files tab
        self.device_frame = tk.Frame(self.notebook, bg='#2b2b2b')
        self.notebook.add(self.device_frame, text='Device Files')
        
        # Device files title
        device_title = tk.Label(
            self.device_frame,
            text="Files on ReMarkable",
            font=('Arial', 12, 'bold'),
            fg='#ffffff',
            bg='#2b2b2b'
        )
        device_title.pack(pady=(10, 5))
        
        # Device files list with scrollbar
        device_list_frame = tk.Frame(self.device_frame, bg='#2b2b2b')
        device_list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        
        device_scrollbar = tk.Scrollbar(device_list_frame)
        device_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.device_listbox = tk.Listbox(
            device_list_frame,
            bg='#3c3c3c',
            fg='#ffffff',
            selectbackground='#5c5c5c',
            selectforeground='#ffffff',
            font=('Arial', 10),
            yscrollcommand=device_scrollbar.set
        )
        self.device_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        device_scrollbar.config(command=self.device_listbox.yview)
        
        # Refresh button for device files
        refresh_btn = tk.Button(
            self.device_frame,
            text="Refresh Device Files",
            command=self._refresh_device_files,
            bg='#2196F3',
            fg='white',
            font=('Arial', 10, 'bold'),
            cursor='hand2'
        )
        refresh_btn.pack(pady=(0, 10))
        
        self.device_files = []
    
    def add_files(self, file_paths: List[str]):
        """Add files to the queue."""
        for path in file_paths:
            if path not in self.files:
                self.files.append(path)
                filename = os.path.basename(path)
                self.file_listbox.insert(tk.END, filename)
    
    def _upload_selected(self):
        """Upload selected files."""
        selection = self.file_listbox.curselection()
        if selection:
            files_to_upload = [self.files[i] for i in selection]
            if self.upload_callback:
                self.upload_callback(files_to_upload)
    
    def _upload_all(self):
        """Upload all files."""
        if self.files and self.upload_callback:
            self.upload_callback(self.files.copy())
    
    def _remove_selected(self):
        """Remove selected files from queue."""
        selection = self.file_listbox.curselection()
        if selection:
            # Remove in reverse order to maintain indices
            for index in reversed(selection):
                self.file_listbox.delete(index)
                del self.files[index]
            if self.remove_callback:
                self.remove_callback()
    
    def _clear_all(self):
        """Clear all files from queue."""
        self.file_listbox.delete(0, tk.END)
        self.files.clear()
        if self.remove_callback:
            self.remove_callback()
    
    def clear_uploaded(self, uploaded_files: List[str]):
        """Remove uploaded files from the queue."""
        for file_path in uploaded_files:
            if file_path in self.files:
                index = self.files.index(file_path)
                self.files.remove(file_path)
                self.file_listbox.delete(index)
    
    def _refresh_device_files(self):
        """Refresh the list of files on the device."""
        try:
            remarkable_service = get_remarkable_service()
            documents = remarkable_service.list_all_documents()
            
            self.device_listbox.delete(0, tk.END)
            self.device_files = []
            
            for doc in documents:
                title = doc.get('title', 'Unknown')
                file_type = doc.get('file_type', 'unknown')
                display_text = f"{title} ({file_type})"
                self.device_listbox.insert(tk.END, display_text)
                self.device_files.append(doc)
            
            if not documents:
                self.device_listbox.insert(tk.END, "No documents found on device")
        except Exception as e:
            self.device_listbox.delete(0, tk.END)
            self.device_listbox.insert(tk.END, f"Error: {str(e)}")
    
    def refresh_after_upload(self):
        """Refresh device files after successful upload."""
        self._refresh_device_files()


class StatusPanel(tk.Frame):
    """Status and progress panel."""
    
    def __init__(self, parent):
        super().__init__(parent)
        self.configure(bg='#1e1e1e')
        
        # Connection status
        self.connection_frame = tk.Frame(self, bg='#1e1e1e')
        self.connection_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.connection_label = tk.Label(
            self.connection_frame,
            text="Device: Not Connected",
            font=('Arial', 10),
            fg='#ff6666',
            bg='#1e1e1e'
        )
        self.connection_label.pack(side=tk.LEFT)
        
        # Progress bar
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(
            self,
            variable=self.progress_var,
            maximum=100,
            style='custom.Horizontal.TProgressbar'
        )
        self.progress_bar.pack(fill=tk.X, padx=10, pady=5)
        
        # Status text
        self.status_text = tk.Text(
            self,
            height=8,
            bg='#2b2b2b',
            fg='#ffffff',
            font=('Consolas', 9),
            wrap=tk.WORD
        )
        self.status_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Configure text tags for colors
        self.status_text.tag_configure('success', foreground='#4CAF50')
        self.status_text.tag_configure('error', foreground='#f44336')
        self.status_text.tag_configure('warning', foreground='#FF9800')
        self.status_text.tag_configure('info', foreground='#2196F3')
    
    def set_connected(self, device_name: str):
        """Update connection status to connected."""
        self.connection_label.configure(
            text=f"Device: {device_name}",
            fg='#4CAF50'
        )
    
    def set_disconnected(self):
        """Update connection status to disconnected."""
        self.connection_label.configure(
            text="Device: Not Connected",
            fg='#ff6666'
        )
    
    def update_progress(self, value: float):
        """Update progress bar."""
        self.progress_var.set(value)
    
    def add_status(self, message: str, level: str = 'info'):
        """Add status message."""
        timestamp = datetime.now().strftime('%H:%M:%S')
        self.status_text.insert(tk.END, f"[{timestamp}] {message}\n", level)
        self.status_text.see(tk.END)


class ReMarkableFilePusher(TkinterDnD.Tk):
    """Main application window for ReMarkable file pusher."""
    
    def __init__(self):
        super().__init__()
        
        self.title("ReMarkable File Pusher")
        self.geometry("900x600")
        self.configure(bg='#1e1e1e')
        
        # Initialize services
        self.logger = get_logger()
        self.config = get_config()
        self.device = None
        self.remarkable_service = get_remarkable_service()
        self.markdown_service = get_markdown_service()
        
        # Configure styles
        self._configure_styles()
        
        # Create UI
        self._create_ui()
        
        # Auto-connect if configured
        self._auto_connect()
    
    def _configure_styles(self):
        """Configure ttk styles for dark theme."""
        style = ttk.Style()
        style.theme_use('clam')
        
        # Configure progress bar
        style.configure(
            'custom.Horizontal.TProgressbar',
            background='#4CAF50',
            troughcolor='#3c3c3c',
            bordercolor='#2b2b2b',
            lightcolor='#4CAF50',
            darkcolor='#4CAF50'
        )
    
    def _create_ui(self):
        """Create the user interface."""
        # Top bar with connection
        top_bar = tk.Frame(self, bg='#2b2b2b', height=50)
        top_bar.pack(fill=tk.X)
        top_bar.pack_propagate(False)
        
        # Device connection
        conn_frame = tk.Frame(top_bar, bg='#2b2b2b')
        conn_frame.pack(side=tk.LEFT, padx=10, pady=10)
        
        tk.Label(
            conn_frame,
            text="IP:",
            fg='#ffffff',
            bg='#2b2b2b',
            font=('Arial', 10)
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        self.ip_entry = tk.Entry(
            conn_frame,
            bg='#3c3c3c',
            fg='#ffffff',
            insertbackground='#ffffff',
            font=('Arial', 10)
        )
        self.ip_entry.insert(0, "10.11.99.1")
        self.ip_entry.pack(side=tk.LEFT, padx=(0, 10))
        
        tk.Label(
            conn_frame,
            text="Password:",
            fg='#ffffff',
            bg='#2b2b2b',
            font=('Arial', 10)
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        self.password_entry = tk.Entry(
            conn_frame,
            bg='#3c3c3c',
            fg='#ffffff',
            insertbackground='#ffffff',
            show='*',
            font=('Arial', 10)
        )
        self.password_entry.pack(side=tk.LEFT, padx=(0, 10))
        
        self.connect_btn = tk.Button(
            conn_frame,
            text="Connect",
            command=self._connect_device,
            bg='#4CAF50',
            fg='white',
            font=('Arial', 10, 'bold'),
            cursor='hand2'
        )
        self.connect_btn.pack(side=tk.LEFT)
        
        # Main content area
        main_frame = tk.Frame(self, bg='#1e1e1e')
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Left side - Drag & Drop (smaller)
        left_frame = tk.Frame(main_frame, bg='#1e1e1e', width=300)
        left_frame.pack(side=tk.LEFT, fill=tk.Y)
        left_frame.pack_propagate(False)
        
        tk.Label(
            left_frame,
            text="DRAG & DROP",
            font=('Arial', 12, 'bold'),
            fg='#ffffff',
            bg='#1e1e1e'
        ).pack(pady=(10, 0))
        
        self.drop_zone = DragDropZone(left_frame, self._handle_dropped_files)
        self.drop_zone.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Right side - File Manager (bigger)
        right_frame = tk.Frame(main_frame, bg='#2b2b2b')
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        self.file_manager = FileManagerPanel(
            right_frame,
            self._upload_files,
            self._on_files_removed
        )
        self.file_manager.pack(fill=tk.BOTH, expand=True)
        
        # Bottom - Status Panel
        self.status_panel = StatusPanel(self)
        self.status_panel.pack(fill=tk.X)
    
    def _auto_connect(self):
        """Auto-connect to device if configured."""
        # Check if we have saved IP and password
        if hasattr(self.config, 'device') and hasattr(self.config.device, 'ip_address'):
            if self.config.device.ip_address:
                self.ip_entry.delete(0, tk.END)
                self.ip_entry.insert(0, self.config.device.ip_address)
            
            if self.config.device.ssh_password:
                self.password_entry.delete(0, tk.END)
                self.password_entry.insert(0, self.config.device.ssh_password)
        else:
            # If no saved config, try to read from SSH script
            try:
                ssh_script_path = Path.home() / 'Documents' / 'playaround' / 'SSH_INTO_REMARKABLE.sh'
                if not ssh_script_path.exists():
                    ssh_script_path = Path.cwd().parent / 'SSH_INTO_REMARKABLE.sh'
                
                if ssh_script_path.exists():
                    with open(ssh_script_path, 'r') as f:
                        content = f.read()
                        # Extract password from script
                        if 'dyovaamsE' in content:
                            self.password_entry.delete(0, tk.END)
                            self.password_entry.insert(0, 'dyovaamsE')
            except Exception:
                pass
    
    def _connect_device(self):
        """Connect to ReMarkable device."""
        ip = self.ip_entry.get().strip()
        password = self.password_entry.get().strip()
        
        if not ip or not password:
            messagebox.showerror("Error", "Please enter IP and password")
            return
        
        self.connect_btn.configure(state='disabled', text='Connecting...')
        
        def connect_worker():
            try:
                # Initialize network service
                network_service = get_network_service()
                network_service.set_connection_details(hostname=ip, password=password)
                
                if network_service.connect():
                    self.device = Device(ip, password)
                    self.after(0, lambda: self._on_connected(ip))
                else:
                    self.after(0, lambda: self._on_connection_failed("Connection failed"))
            except Exception as e:
                self.after(0, lambda: self._on_connection_failed(str(e)))
        
        threading.Thread(target=connect_worker, daemon=True).start()
    
    def _on_connected(self, ip: str):
        """Handle successful connection."""
        self.status_panel.set_connected(ip)
        self.status_panel.add_status(f"Connected to {ip}", 'success')
        self.connect_btn.configure(state='normal', text='Connected', bg='#666666')
        
        # Save connection details for next time
        try:
            if hasattr(self.config, 'update_device_info'):
                self.config.update_device_info(ip, self.password_entry.get())
            else:
                # Create config if it doesn't exist
                from pathlib import Path
                import json
                config_dir = Path.home() / '.config' / 'readmarkable'
                config_dir.mkdir(parents=True, exist_ok=True)
                config_file = config_dir / 'config.json'
                
                config_data = {}
                if config_file.exists():
                    with open(config_file, 'r') as f:
                        config_data = json.load(f)
                
                if 'device' not in config_data:
                    config_data['device'] = {}
                
                config_data['device']['ip_address'] = ip
                config_data['device']['ssh_password'] = self.password_entry.get()
                
                with open(config_file, 'w') as f:
                    json.dump(config_data, f, indent=2)
        except Exception as e:
            self.logger.debug(f"Could not save config: {e}")
        
        # Refresh device files after connection
        self.file_manager._refresh_device_files()
    
    def _on_connection_failed(self, error: str):
        """Handle connection failure."""
        self.status_panel.add_status(f"Connection failed: {error}", 'error')
        self.connect_btn.configure(state='normal', text='Connect')
        messagebox.showerror("Connection Error", error)
    
    def _handle_dropped_files(self, files: List[str]):
        """Handle dropped files."""
        self.file_manager.add_files(files)
        self.status_panel.add_status(f"Added {len(files)} file(s) to queue", 'info')
    
    def _upload_files(self, files: List[str]):
        """Upload files to ReMarkable."""
        if not self.device:
            messagebox.showerror("Error", "Please connect to device first")
            return
        
        # Show immediate feedback
        self.status_panel.add_status(f"Starting upload of {len(files)} file(s)...", 'info')
        self.status_panel.update_progress(0)
        
        def upload_worker():
            uploaded = []
            total = len(files)
            
            for i, file_path in enumerate(files):
                file_path = Path(file_path)
                filename = file_path.name
                
                # Update progress for each file
                progress = ((i + 0.5) / total) * 100
                self.status_panel.update_progress(progress)
                self.status_panel.add_status(f"Processing {filename}...", 'info')
                
                try:
                    # Handle different file types
                    if file_path.suffix.lower() in ['.md', '.markdown']:
                        # Convert to PDF first
                        self.status_panel.add_status(f"Converting {filename} to PDF...", 'info')
                        output_dir = Path.home() / '.cache' / 'readmarkable'
                        output_dir.mkdir(parents=True, exist_ok=True)
                        
                        pdf_path = self.markdown_service.process_markdown_file(
                            file_path,
                            output_dir
                        )
                        
                        if pdf_path:
                            self.status_panel.add_status(f"Uploading PDF to ReMarkable...", 'info')
                            title = file_path.stem
                            uuid = self.remarkable_service.add_with_metadata_if_new(pdf_path, title)
                            if uuid:
                                self.status_panel.add_status(f"[OK] Successfully uploaded {filename} as PDF", 'success')
                                uploaded.append(file_path)
                            else:
                                self.status_panel.add_status(f"[FAIL] Failed to upload {filename}", 'error')
                            
                            # Clean up temp PDF
                            pdf_path.unlink(missing_ok=True)
                        else:
                            self.status_panel.add_status(f"[FAIL] Failed to convert {filename} to PDF", 'error')
                    
                    elif file_path.suffix.lower() == '.pdf':
                        title = file_path.stem
                        uuid = self.remarkable_service.add_with_metadata_if_new(file_path, title)
                        if uuid:
                            self.status_panel.add_status(f"[OK] Uploaded {filename}", 'success')
                            uploaded.append(file_path)
                        else:
                            self.status_panel.add_status(f"[FAIL] Failed to upload {filename}", 'error')
                    
                    elif file_path.suffix.lower() == '.epub':
                        title = file_path.stem
                        uuid = self.remarkable_service.add_epub_with_metadata(file_path, title)
                        if uuid:
                            self.status_panel.add_status(f"[OK] Uploaded {filename}", 'success')
                            uploaded.append(file_path)
                        else:
                            self.status_panel.add_status(f"[FAIL] Failed to upload {filename}", 'error')
                    
                    else:
                        self.status_panel.add_status(f"[WARN] Unsupported file type: {filename}", 'warning')
                
                except Exception as e:
                    self.status_panel.add_status(f"[ERROR] Error uploading {filename}: {e}", 'error')
            
            # Clear uploaded files from queue
            self.after(0, lambda: self.file_manager.clear_uploaded([str(f) for f in uploaded]))
            
            # Refresh device files list after successful upload
            if uploaded:
                self.after(0, lambda: self.file_manager.refresh_after_upload())
            
            self.status_panel.update_progress(100)
            self.status_panel.add_status(f"Upload complete: {len(uploaded)}/{total} files", 'success')
            
            # Show completion message
            if uploaded:
                self.after(0, lambda: messagebox.showinfo("Upload Complete", f"Successfully uploaded {len(uploaded)} of {total} files"))
            elif total > 0:
                self.after(0, lambda: messagebox.showwarning("Upload Failed", "No files were uploaded successfully"))
            
            # Reset progress after delay
            self.after(2000, lambda: self.status_panel.update_progress(0))
        
        threading.Thread(target=upload_worker, daemon=True).start()
    
    def _on_files_removed(self):
        """Handle files removed from queue."""
        self.status_panel.add_status("Files removed from queue", 'info')


def main():
    """Run the application."""
    app = ReMarkableFilePusher()
    app.mainloop()


if __name__ == "__main__":
    main()