"""
Sync state model for readmarkable.

This module contains classes for tracking markdown synchronization progress,
file states, and sync operations between local and remote directories.
"""

import os
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Set, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class FileStatus(Enum):
    """File synchronization status."""
    UNKNOWN = "unknown"
    UP_TO_DATE = "up_to_date"
    MODIFIED_LOCAL = "modified_local"
    MODIFIED_REMOTE = "modified_remote"
    NEW_LOCAL = "new_local"
    NEW_REMOTE = "new_remote"
    DELETED_LOCAL = "deleted_local"
    DELETED_REMOTE = "deleted_remote"
    CONFLICT = "conflict"
    ERROR = "error"


class SyncOperation(Enum):
    """Types of sync operations."""
    UPLOAD = "upload"
    DOWNLOAD = "download"
    DELETE_LOCAL = "delete_local"
    DELETE_REMOTE = "delete_remote"
    CONVERT_PDF = "convert_pdf"
    SKIP = "skip"


@dataclass
class FileInfo:
    """Information about a file in the sync process."""
    path: str
    size: int
    modified_time: datetime
    checksum: Optional[str] = None
    is_markdown: bool = False
    
    def calculate_checksum(self, file_path: Path) -> str:
        """Calculate MD5 checksum of the file."""
        if not file_path.exists():
            return ""
        
        hash_md5 = hashlib.md5()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            self.checksum = hash_md5.hexdigest()
        except Exception:
            self.checksum = ""
        
        return self.checksum


@dataclass
class SyncItem:
    """A single item to be synchronized."""
    local_path: Optional[str] = None
    remote_path: Optional[str] = None
    local_info: Optional[FileInfo] = None
    remote_info: Optional[FileInfo] = None
    status: FileStatus = FileStatus.UNKNOWN
    operation: SyncOperation = SyncOperation.SKIP
    error_message: Optional[str] = None
    
    @property
    def relative_path(self) -> str:
        """Get the relative path for this sync item."""
        if self.local_path:
            return self.local_path
        elif self.remote_path:
            return self.remote_path
        return "unknown"
    
    @property
    def is_markdown_file(self) -> bool:
        """Check if this is a markdown file."""
        if self.local_info:
            return self.local_info.is_markdown
        elif self.remote_info:
            return self.remote_info.is_markdown
        return False
    
    def needs_sync(self) -> bool:
        """Check if this item needs synchronization."""
        return self.status not in [FileStatus.UP_TO_DATE, FileStatus.ERROR]


@dataclass
class SyncProgress:
    """Progress information for sync operations."""
    total_items: int = 0
    processed_items: int = 0
    current_item: Optional[str] = None
    bytes_total: int = 0
    bytes_processed: int = 0
    start_time: Optional[datetime] = None
    
    @property
    def percentage(self) -> float:
        """Get progress as percentage."""
        if self.total_items > 0:
            return (self.processed_items / self.total_items) * 100.0
        return 0.0
    
    @property
    def bytes_percentage(self) -> float:
        """Get bytes progress as percentage."""
        if self.bytes_total > 0:
            return (self.bytes_processed / self.bytes_total) * 100.0
        return 0.0
    
    @property
    def elapsed_time(self) -> float:
        """Get elapsed time in seconds."""
        if self.start_time:
            return (datetime.now() - self.start_time).total_seconds()
        return 0.0
    
    @property
    def estimated_remaining(self) -> Optional[float]:
        """Get estimated remaining time in seconds."""
        if self.processed_items > 0 and self.total_items > self.processed_items:
            elapsed = self.elapsed_time
            rate = self.processed_items / elapsed if elapsed > 0 else 0
            if rate > 0:
                remaining_items = self.total_items - self.processed_items
                return remaining_items / rate
        return None


class SyncState:
    """
    Manages the state of markdown synchronization operations.
    
    Tracks file states, sync progress, and provides methods for
    analyzing differences between local and remote directories.
    """
    
    def __init__(self, local_dir: Path, remote_dir: str):
        """
        Initialize sync state.
        
        Args:
            local_dir: Local directory to sync
            remote_dir: Remote directory path on device
        """
        self.local_dir = local_dir
        self.remote_dir = remote_dir
        
        # Sync items and state
        self.sync_items: Dict[str, SyncItem] = {}
        self.progress = SyncProgress()
        
        # File tracking
        self.local_files: Dict[str, FileInfo] = {}
        self.remote_files: Dict[str, FileInfo] = {}
        
        # Sync settings
        self.markdown_extensions = {".md", ".markdown", ".mdown", ".mkd", ".txt"}
        self.ignore_patterns = {".*", "__pycache__", "*.pyc", ".git"}
        
        # State tracking
        self.last_scan_time: Optional[datetime] = None
        self.is_scanning = False
        self.is_syncing = False
    
    def should_ignore_file(self, file_path: str) -> bool:
        """
        Check if a file should be ignored based on ignore patterns.
        
        Args:
            file_path: File path to check
            
        Returns:
            True if file should be ignored
        """
        file_name = os.path.basename(file_path)
        
        for pattern in self.ignore_patterns:
            if pattern.startswith("*"):
                if file_name.endswith(pattern[1:]):
                    return True
            elif pattern.startswith("."):
                if file_name.startswith(pattern):
                    return True
            elif pattern == file_name:
                return True
        
        return False
    
    def is_markdown_file(self, file_path: str) -> bool:
        """
        Check if a file is a markdown file.
        
        Args:
            file_path: File path to check
            
        Returns:
            True if file is markdown
        """
        return Path(file_path).suffix.lower() in self.markdown_extensions
    
    def scan_local_directory(self) -> None:
        """Scan local directory for files."""
        self.local_files.clear()
        
        if not self.local_dir.exists():
            return
        
        for file_path in self.local_dir.rglob("*"):
            if file_path.is_file():
                relative_path = str(file_path.relative_to(self.local_dir))
                
                if self.should_ignore_file(relative_path):
                    continue
                
                try:
                    stat = file_path.stat()
                    file_info = FileInfo(
                        path=relative_path,
                        size=stat.st_size,
                        modified_time=datetime.fromtimestamp(stat.st_mtime),
                        is_markdown=self.is_markdown_file(relative_path)
                    )
                    file_info.calculate_checksum(file_path)
                    self.local_files[relative_path] = file_info
                except Exception:
                    # Skip files that can't be read
                    continue
    
    def update_remote_files(self, remote_files: Dict[str, Dict[str, Any]]) -> None:
        """
        Update remote files information.
        
        Args:
            remote_files: Dictionary of remote file information
        """
        self.remote_files.clear()
        
        for relative_path, file_data in remote_files.items():
            if self.should_ignore_file(relative_path):
                continue
            
            try:
                file_info = FileInfo(
                    path=relative_path,
                    size=file_data.get("size", 0),
                    modified_time=datetime.fromtimestamp(file_data.get("mtime", 0)),
                    checksum=file_data.get("checksum", ""),
                    is_markdown=self.is_markdown_file(relative_path)
                )
                self.remote_files[relative_path] = file_info
            except Exception:
                # Skip invalid file data
                continue
    
    def analyze_differences(self) -> None:
        """Analyze differences between local and remote files."""
        self.sync_items.clear()
        
        # Get all unique file paths
        all_paths = set(self.local_files.keys()) | set(self.remote_files.keys())
        
        for relative_path in all_paths:
            local_info = self.local_files.get(relative_path)
            remote_info = self.remote_files.get(relative_path)
            
            sync_item = SyncItem(
                local_path=relative_path if local_info else None,
                remote_path=relative_path if remote_info else None,
                local_info=local_info,
                remote_info=remote_info
            )
            
            # Determine file status and required operation
            sync_item.status, sync_item.operation = self._determine_sync_action(
                local_info, remote_info
            )
            
            self.sync_items[relative_path] = sync_item
        
        # Update progress information
        self.progress.total_items = len([item for item in self.sync_items.values() if item.needs_sync()])
        self.progress.processed_items = 0
        self.progress.bytes_total = sum(
            (item.local_info.size if item.local_info else item.remote_info.size if item.remote_info else 0)
            for item in self.sync_items.values()
            if item.needs_sync()
        )
        self.progress.bytes_processed = 0
    
    def _determine_sync_action(self, local_info: Optional[FileInfo], 
                             remote_info: Optional[FileInfo]) -> tuple[FileStatus, SyncOperation]:
        """
        Determine the required sync action for a file.
        
        Args:
            local_info: Local file information
            remote_info: Remote file information
            
        Returns:
            Tuple of (status, operation)
        """
        if local_info and remote_info:
            # File exists in both locations
            if local_info.checksum == remote_info.checksum:
                return FileStatus.UP_TO_DATE, SyncOperation.SKIP
            elif local_info.modified_time > remote_info.modified_time:
                return FileStatus.MODIFIED_LOCAL, SyncOperation.UPLOAD
            elif remote_info.modified_time > local_info.modified_time:
                return FileStatus.MODIFIED_REMOTE, SyncOperation.DOWNLOAD
            else:
                # Same modification time but different checksums - conflict
                return FileStatus.CONFLICT, SyncOperation.SKIP
        
        elif local_info and not remote_info:
            # File only exists locally
            return FileStatus.NEW_LOCAL, SyncOperation.UPLOAD
        
        elif remote_info and not local_info:
            # File only exists remotely
            return FileStatus.NEW_REMOTE, SyncOperation.DOWNLOAD
        
        else:
            # Should not happen
            return FileStatus.UNKNOWN, SyncOperation.SKIP
    
    def get_sync_summary(self) -> Dict[str, int]:
        """
        Get a summary of sync operations.
        
        Returns:
            Dictionary with count of each operation type
        """
        summary = {
            "up_to_date": 0,
            "upload": 0,
            "download": 0,
            "conflicts": 0,
            "errors": 0,
            "total_files": len(self.sync_items)
        }
        
        for item in self.sync_items.values():
            if item.status == FileStatus.UP_TO_DATE:
                summary["up_to_date"] += 1
            elif item.operation == SyncOperation.UPLOAD:
                summary["upload"] += 1
            elif item.operation == SyncOperation.DOWNLOAD:
                summary["download"] += 1
            elif item.status == FileStatus.CONFLICT:
                summary["conflicts"] += 1
            elif item.status == FileStatus.ERROR:
                summary["errors"] += 1
        
        return summary
    
    def get_items_by_operation(self, operation: SyncOperation) -> List[SyncItem]:
        """
        Get sync items filtered by operation type.
        
        Args:
            operation: Operation type to filter by
            
        Returns:
            List of sync items with the specified operation
        """
        return [item for item in self.sync_items.values() if item.operation == operation]
    
    def mark_item_completed(self, relative_path: str, success: bool = True, 
                          error_message: Optional[str] = None) -> None:
        """
        Mark a sync item as completed.
        
        Args:
            relative_path: Path of the item
            success: Whether the operation was successful
            error_message: Error message if operation failed
        """
        if relative_path in self.sync_items:
            item = self.sync_items[relative_path]
            
            if success:
                item.status = FileStatus.UP_TO_DATE
                item.operation = SyncOperation.SKIP
                self.progress.processed_items += 1
                
                # Update bytes processed
                if item.local_info:
                    self.progress.bytes_processed += item.local_info.size
                elif item.remote_info:
                    self.progress.bytes_processed += item.remote_info.size
            else:
                item.status = FileStatus.ERROR
                item.error_message = error_message
    
    def start_sync(self) -> None:
        """Start a sync operation."""
        self.is_syncing = True
        self.progress.start_time = datetime.now()
        self.progress.processed_items = 0
        self.progress.bytes_processed = 0
    
    def finish_sync(self) -> None:
        """Finish a sync operation."""
        self.is_syncing = False
        self.last_scan_time = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert sync state to dictionary.
        
        Returns:
            Dictionary representation of sync state
        """
        return {
            "local_dir": str(self.local_dir),
            "remote_dir": self.remote_dir,
            "last_scan_time": self.last_scan_time.isoformat() if self.last_scan_time else None,
            "is_scanning": self.is_scanning,
            "is_syncing": self.is_syncing,
            "progress": {
                "total_items": self.progress.total_items,
                "processed_items": self.progress.processed_items,
                "percentage": self.progress.percentage,
                "bytes_total": self.progress.bytes_total,
                "bytes_processed": self.progress.bytes_processed,
                "bytes_percentage": self.progress.bytes_percentage,
                "elapsed_time": self.progress.elapsed_time,
                "estimated_remaining": self.progress.estimated_remaining
            },
            "summary": self.get_sync_summary()
        }