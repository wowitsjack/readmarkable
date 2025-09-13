"""
File service for readmarkable.

This module handles file operations including markdown file discovery,
file watching, backup management, and file system utilities.
"""

import os
import shutil
from pathlib import Path
from typing import List, Dict, Optional, Callable, Any
from datetime import datetime
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from utils.logger import get_logger
from models.sync_state import SyncState


class FileChangeHandler(FileSystemEventHandler):
    """Handler for file system change events."""
    
    def __init__(self, callback: Optional[Callable[[str, str], None]] = None):
        """
        Initialize file change handler.
        
        Args:
            callback: Function to call when files change (event_type, file_path)
        """
        super().__init__()
        self.callback = callback
        self._logger = get_logger()
    
    def on_modified(self, event):
        if not event.is_directory and self.callback:
            self.callback("modified", event.src_path)
    
    def on_created(self, event):
        if not event.is_directory and self.callback:
            self.callback("created", event.src_path)
    
    def on_deleted(self, event):
        if not event.is_directory and self.callback:
            self.callback("deleted", event.src_path)


class FileService:
    """
    Service for file operations and monitoring.
    
    Handles markdown file discovery, file watching, backup operations,
    and file system utilities for the sync process.
    """
    
    def __init__(self):
        """Initialize file service."""
        self._logger = get_logger()
        self.observer: Optional[Observer] = None
        self.is_watching = False
        
        # File watching settings
        self.watch_callback: Optional[Callable[[str, str], None]] = None
        self.debounce_delay = 1.0  # seconds
        
        # Markdown extensions
        self.markdown_extensions = {".md", ".markdown", ".mdown", ".mkd", ".txt"}
    
    def start_watching(self, directory: Path, callback: Callable[[str, str], None],
                      recursive: bool = True) -> bool:
        """
        Start watching a directory for file changes.
        
        Args:
            directory: Directory to watch
            callback: Function to call on file changes
            recursive: Whether to watch subdirectories
            
        Returns:
            True if watching started successfully
        """
        if self.is_watching:
            self.stop_watching()
        
        try:
            self.watch_callback = callback
            self.observer = Observer()
            
            handler = FileChangeHandler(callback)
            self.observer.schedule(handler, str(directory), recursive=recursive)
            
            self.observer.start()
            self.is_watching = True
            
            self._logger.info(f"Started watching directory: {directory}")
            return True
            
        except Exception as e:
            self._logger.error(f"Failed to start watching: {e}")
            return False
    
    def stop_watching(self) -> None:
        """Stop watching for file changes."""
        if self.observer and self.is_watching:
            self.observer.stop()
            self.observer.join()
            self.observer = None
            self.is_watching = False
            self._logger.info("Stopped file watching")
    
    def discover_markdown_files(self, directory: Path) -> List[Path]:
        """
        Discover all markdown files in a directory.
        
        Args:
            directory: Directory to search
            
        Returns:
            List of markdown file paths
        """
        markdown_files = []
        
        if not directory.exists():
            return markdown_files
        
        for file_path in directory.rglob("*"):
            if file_path.is_file() and file_path.suffix.lower() in self.markdown_extensions:
                markdown_files.append(file_path)
        
        return markdown_files
    
    def create_backup(self, file_path: Path, backup_dir: Path) -> Optional[Path]:
        """
        Create a backup of a file.
        
        Args:
            file_path: File to backup
            backup_dir: Directory to store backup
            
        Returns:
            Path to backup file if successful
        """
        try:
            backup_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"{file_path.stem}_{timestamp}{file_path.suffix}"
            backup_path = backup_dir / backup_name
            
            shutil.copy2(file_path, backup_path)
            self._logger.info(f"Created backup: {backup_path}")
            return backup_path
            
        except Exception as e:
            self._logger.error(f"Failed to create backup: {e}")
            return None
    
    def cleanup_old_backups(self, backup_dir: Path, max_backups: int = 10) -> None:
        """
        Clean up old backup files.
        
        Args:
            backup_dir: Directory containing backups
            max_backups: Maximum number of backups to keep
        """
        try:
            if not backup_dir.exists():
                return
            
            backup_files = list(backup_dir.glob("*"))
            backup_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            
            if len(backup_files) > max_backups:
                for old_backup in backup_files[max_backups:]:
                    old_backup.unlink()
                    self._logger.info(f"Removed old backup: {old_backup}")
                    
        except Exception as e:
            self._logger.error(f"Failed to cleanup backups: {e}")


# Global file service instance
_global_file_service: Optional[FileService] = None


def get_file_service() -> FileService:
    """
    Get the global file service instance.
    
    Returns:
        Global FileService instance
    """
    global _global_file_service
    if _global_file_service is None:
        _global_file_service = FileService()
    return _global_file_service