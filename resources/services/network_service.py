"""
Network service for readMarkable.

This module provides SSH/SCP operations with paramiko, connection management,
remote command execution, and file transfer with progress tracking for markdown sync operations.
"""

import os
import logging
import threading
import time
from pathlib import Path
from typing import Optional, Callable, Dict, Any, List, Union, Tuple
from dataclasses import dataclass
from enum import Enum
import paramiko
from paramiko import SSHClient, SFTPClient
from paramiko.ssh_exception import (
    SSHException, 
    AuthenticationException, 
    NoValidConnectionsError,
    BadHostKeyException
)
import socket
from concurrent.futures import ThreadPoolExecutor, Future


class ConnectionStatus(Enum):
    """SSH connection status."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    AUTHENTICATION_FAILED = "auth_failed"
    HOST_KEY_ERROR = "host_key_error"
    TIMEOUT = "timeout"
    NETWORK_ERROR = "network_error"
    ERROR = "error"


class CommandResult:
    """Result of SSH command execution."""
    
    def __init__(self, command: str, exit_code: int, stdout: str, stderr: str, 
                 execution_time: float = 0.0):
        self.command = command
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.execution_time = execution_time
        
    @property
    def success(self) -> bool:
        """Check if command executed successfully."""
        return self.exit_code == 0
    
    @property
    def output(self) -> str:
        """Get combined stdout/stderr output."""
        return f"{self.stdout}\n{self.stderr}".strip()
    
    def __str__(self) -> str:
        return f"Command: {self.command}\nExit Code: {self.exit_code}\nOutput: {self.output}"


@dataclass
class TransferProgress:
    """Progress information for file transfers."""
    filename: str
    bytes_transferred: int
    total_bytes: int
    start_time: float
    is_upload: bool = True
    
    @property
    def progress_percentage(self) -> float:
        """Get transfer progress as percentage."""
        if self.total_bytes > 0:
            return (self.bytes_transferred / self.total_bytes) * 100.0
        return 0.0
    
    @property
    def speed_bytes_per_second(self) -> float:
        """Get transfer speed in bytes per second."""
        elapsed = time.time() - self.start_time
        if elapsed > 0:
            return self.bytes_transferred / elapsed
        return 0.0
    
    @property
    def eta_seconds(self) -> Optional[float]:
        """Get estimated time to completion."""
        speed = self.speed_bytes_per_second
        if speed > 0:
            remaining = self.total_bytes - self.bytes_transferred
            return remaining / speed
        return None


class NetworkService:
    """
    Network service for SSH/SCP operations with reMarkable device.
    
    Provides secure SSH connections, remote command execution, and file transfers
    with progress tracking for markdown synchronization operations.
    """
    
    def __init__(self, connection_timeout: int = 10, 
                 max_retries: int = 3,
                 retry_delay: int = 2,
                 keepalive_interval: int = 30):
        """
        Initialize network service.
        
        Args:
            connection_timeout: SSH connection timeout in seconds
            max_retries: Maximum connection retry attempts
            retry_delay: Delay between retry attempts in seconds
            keepalive_interval: SSH keepalive interval in seconds
        """
        self.connection_timeout = connection_timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.keepalive_interval = keepalive_interval
        
        # Connection state
        self.ssh_client: Optional[SSHClient] = None
        self.sftp_client: Optional[SFTPClient] = None
        self.connection_status = ConnectionStatus.DISCONNECTED
        self.last_error: Optional[str] = None
        
        # Connection details
        self.hostname: Optional[str] = None
        self.username: str = "root"  # reMarkable always uses root
        self.password: Optional[str] = None
        self.port: int = 22
        
        # Progress callbacks
        self.command_output_callback: Optional[Callable[[str], None]] = None
        self.transfer_progress_callback: Optional[Callable[[TransferProgress], None]] = None
        
        # Thread management
        self.executor = ThreadPoolExecutor(max_workers=4)
        self._connection_lock = threading.Lock()
        
        self._logger = logging.getLogger(__name__)
    
    def set_connection_details(self, hostname: str, password: str, 
                             username: str = "root", port: int = 22) -> None:
        """
        Set connection details for SSH operations.
        
        Args:
            hostname: Device IP address or hostname
            password: SSH password
            username: SSH username (default: root)
            port: SSH port (default: 22)
        """
        self.hostname = hostname
        self.password = password
        self.username = username
        self.port = port
        
        # Reset connection if details changed
        if self.is_connected():
            self._logger.info("Connection details changed, disconnecting...")
            self.disconnect()
    
    def set_transfer_progress_callback(self, callback: Callable[[TransferProgress], None]) -> None:
        """Set callback for file transfer progress."""
        self.transfer_progress_callback = callback
    
    def is_connected(self) -> bool:
        """Check if SSH connection is active."""
        return (self.connection_status == ConnectionStatus.CONNECTED and 
                self.ssh_client is not None and 
                self.ssh_client.get_transport() is not None and
                self.ssh_client.get_transport().is_active())
    
    def connect(self, force_reconnect: bool = False) -> bool:
        """
        Establish SSH connection to the device.
        
        Args:
            force_reconnect: Force reconnection even if already connected
            
        Returns:
            True if connection successful, False otherwise
        """
        with self._connection_lock:
            if self.is_connected() and not force_reconnect:
                return True
            
            if not self.hostname or not self.password:
                self.last_error = "Hostname and password are required"
                self.connection_status = ConnectionStatus.ERROR
                return False
            
            self._logger.info(f"Connecting to {self.hostname}:{self.port} as {self.username}")
            
            # Disconnect existing connection
            if self.ssh_client:
                self.disconnect()
            
            # Clear any existing host keys for this hostname
            known_hosts_path = os.path.expanduser('~/.ssh/known_hosts')
            if os.path.exists(known_hosts_path):
                try:
                    with open(known_hosts_path, 'r') as f:
                        lines = f.readlines()
                    
                    filtered_lines = []
                    for line in lines:
                        if not line.startswith(self.hostname + ' ') and not line.startswith(self.hostname + ','):
                            filtered_lines.append(line)
                    
                    if len(filtered_lines) < len(lines):
                        with open(known_hosts_path, 'w') as f:
                            f.writelines(filtered_lines)
                        self._logger.debug(f"Cleared conflicting host key entries for {self.hostname}")
                except Exception as e:
                    self._logger.debug(f"Could not clear host key entries: {e}")
            
            # Attempt connection with retries
            for attempt in range(self.max_retries):
                self.connection_status = ConnectionStatus.CONNECTING
                
                try:
                    self.ssh_client = SSHClient()
                    self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                    
                    self.ssh_client.connect(
                        hostname=self.hostname,
                        port=self.port,
                        username=self.username,
                        password=self.password,
                        timeout=self.connection_timeout,
                        banner_timeout=self.connection_timeout,
                        auth_timeout=self.connection_timeout,
                        look_for_keys=False,
                        allow_agent=False
                    )
                    
                    # Set keepalive
                    transport = self.ssh_client.get_transport()
                    if transport:
                        transport.set_keepalive(self.keepalive_interval)
                    
                    # Create SFTP client
                    self.sftp_client = self.ssh_client.open_sftp()
                    
                    self.connection_status = ConnectionStatus.CONNECTED
                    self.last_error = None
                    self._logger.info(f"Successfully connected to {self.hostname}")
                    
                    return True
                    
                except AuthenticationException as e:
                    self.last_error = f"Authentication failed: {e}"
                    self.connection_status = ConnectionStatus.AUTHENTICATION_FAILED
                    self._logger.error(self.last_error)
                    break
                    
                except BadHostKeyException as e:
                    self.last_error = f"Host key verification failed: {e}"
                    self.connection_status = ConnectionStatus.HOST_KEY_ERROR
                    self._logger.error(self.last_error)
                    break
                    
                except (NoValidConnectionsError, socket.timeout, socket.error) as e:
                    self.last_error = f"Network connection failed: {e}"
                    self.connection_status = ConnectionStatus.NETWORK_ERROR
                    
                    if attempt < self.max_retries - 1:
                        self._logger.warning(f"Connection attempt {attempt + 1} failed: {e}")
                        self._logger.info(f"Retrying in {self.retry_delay} seconds...")
                        time.sleep(self.retry_delay)
                    else:
                        self._logger.error(f"All connection attempts failed: {e}")
                        
                except Exception as e:
                    self.last_error = f"Unexpected error: {e}"
                    self.connection_status = ConnectionStatus.ERROR
                    self._logger.error(f"Unexpected connection error: {e}")
                    break
            
            # Clean up on failure
            if self.ssh_client:
                self.disconnect()
            
            return False
    
    def disconnect(self) -> None:
        """Close SSH and SFTP connections."""
        with self._connection_lock:
            if self.sftp_client:
                try:
                    self.sftp_client.close()
                except Exception:
                    pass
                self.sftp_client = None
            
            if self.ssh_client:
                try:
                    self.ssh_client.close()
                except Exception:
                    pass
                self.ssh_client = None
            
            self.connection_status = ConnectionStatus.DISCONNECTED
            self._logger.debug("SSH connection closed")
    
    def execute_command(self, command: str, timeout: Optional[int] = None) -> CommandResult:
        """
        Execute a command on the remote device.
        
        Args:
            command: Command to execute
            timeout: Command timeout in seconds
            
        Returns:
            CommandResult with execution details
        """
        if not self.is_connected():
            if not self.connect():
                return CommandResult(
                    command=command,
                    exit_code=-1,
                    stdout="",
                    stderr=f"Not connected to device: {self.last_error}",
                    execution_time=0.0
                )
        
        self._logger.debug(f"Executing command: {command}")
        start_time = time.time()
        
        try:
            if timeout is None:
                stdin, stdout, stderr = self.ssh_client.exec_command(command)
            else:
                stdin, stdout, stderr = self.ssh_client.exec_command(command, timeout=timeout)
            
            stdout_text = stdout.read().decode('utf-8', errors='replace')
            stderr_text = stderr.read().decode('utf-8', errors='replace')
            exit_code = stdout.channel.recv_exit_status()
            
            execution_time = time.time() - start_time
            
            result = CommandResult(
                command=command,
                exit_code=exit_code,
                stdout=stdout_text,
                stderr=stderr_text,
                execution_time=execution_time
            )
            
            if result.success:
                self._logger.debug(f"Command completed successfully in {execution_time:.2f}s")
            else:
                self._logger.warning(f"Command failed with exit code {exit_code}: {stderr_text}")
            
            return result
            
        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = f"Command execution failed: {e}"
            self._logger.error(error_msg)
            return CommandResult(command, -1, "", error_msg, execution_time)
    
    def upload_file(self, local_path: Union[str, Path], remote_path: str, create_dirs: bool = True) -> bool:
        """
        Upload a file to the remote device.
        
        Args:
            local_path: Local file path
            remote_path: Remote file path
            create_dirs: Whether to create remote directories
            
        Returns:
            True if upload successful
        """
        if not self.is_connected():
            if not self.connect():
                self._logger.error("Cannot upload file: not connected")
                return False
        
        local_path = Path(local_path)
        if not local_path.exists():
            self._logger.error(f"Local file does not exist: {local_path}")
            return False
        
        try:
            # Create remote directories if needed
            if create_dirs:
                remote_dir = str(Path(remote_path).parent)
                if remote_dir != "/":
                    self.execute_command(f"mkdir -p '{remote_dir}'")
            
            # Get file size for progress tracking
            file_size = local_path.stat().st_size
            start_time = time.time()
            
            def progress_callback(bytes_transferred: int, total_bytes: int) -> None:
                if self.transfer_progress_callback:
                    progress = TransferProgress(
                        filename=local_path.name,
                        bytes_transferred=bytes_transferred,
                        total_bytes=total_bytes,
                        start_time=start_time,
                        is_upload=True
                    )
                    self.transfer_progress_callback(progress)
            
            self._logger.info(f"Uploading {local_path} to {remote_path}")
            
            # Use SFTP for file transfer
            self.sftp_client.put(
                str(local_path), 
                remote_path, 
                callback=progress_callback
            )
            
            elapsed = time.time() - start_time
            speed = file_size / elapsed if elapsed > 0 else 0
            self._logger.info(f"Upload completed: {file_size} bytes in {elapsed:.2f}s ({speed:.0f} B/s)")
            
            return True
            
        except Exception as e:
            self._logger.error(f"Upload failed: {e}")
            return False
    
    def download_file(self, remote_path: str, local_path: Union[str, Path], create_dirs: bool = True) -> bool:
        """
        Download a file from the remote device.
        
        Args:
            remote_path: Remote file path
            local_path: Local file path
            create_dirs: Whether to create local directories
            
        Returns:
            True if download successful
        """
        if not self.is_connected():
            if not self.connect():
                self._logger.error("Cannot download file: not connected")
                return False
        
        local_path = Path(local_path)
        
        try:
            # Create local directories if needed
            if create_dirs:
                local_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Get remote file size for progress tracking
            try:
                file_attrs = self.sftp_client.stat(remote_path)
                file_size = file_attrs.st_size
            except Exception:
                file_size = 0
            
            start_time = time.time()
            
            def progress_callback(bytes_transferred: int, total_bytes: int) -> None:
                if self.transfer_progress_callback:
                    progress = TransferProgress(
                        filename=Path(remote_path).name,
                        bytes_transferred=bytes_transferred,
                        total_bytes=total_bytes or file_size,
                        start_time=start_time,
                        is_upload=False
                    )
                    self.transfer_progress_callback(progress)
            
            self._logger.info(f"Downloading {remote_path} to {local_path}")
            
            # Use SFTP for file transfer
            self.sftp_client.get(
                remote_path,
                str(local_path),
                callback=progress_callback
            )
            
            elapsed = time.time() - start_time
            actual_size = local_path.stat().st_size if local_path.exists() else 0
            speed = actual_size / elapsed if elapsed > 0 else 0
            self._logger.info(f"Download completed: {actual_size} bytes in {elapsed:.2f}s ({speed:.0f} B/s)")
            
            return True
            
        except Exception as e:
            self._logger.error(f"Download failed: {e}")
            return False
    
    def file_exists(self, remote_path: str) -> bool:
        """Check if a file exists on the remote device."""
        if not self.is_connected():
            return False
        
        try:
            self.sftp_client.stat(remote_path)
            return True
        except FileNotFoundError:
            return False
        except Exception:
            return False
    
    def list_directory(self, remote_path: str) -> List[str]:
        """List files in a remote directory."""
        if not self.is_connected():
            return []
        
        try:
            return self.sftp_client.listdir(remote_path)
        except Exception as e:
            self._logger.error(f"Failed to list directory {remote_path}: {e}")
            return []
    
    def get_connection_status(self) -> Dict[str, Any]:
        """Get current connection status information."""
        return {
            "status": self.connection_status.value,
            "hostname": self.hostname,
            "port": self.port,
            "username": self.username,
            "connected": self.is_connected(),
            "last_error": self.last_error
        }
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with cleanup."""
        self.disconnect()
        self.executor.shutdown(wait=True)


# Global network service instance
_global_network_service: Optional[NetworkService] = None


def get_network_service() -> NetworkService:
    """
    Get the global network service instance.
    
    Returns:
        Global NetworkService instance
        
    Raises:
        RuntimeError: If network service hasn't been initialized
    """
    global _global_network_service
    if _global_network_service is None:
        raise RuntimeError("Network service not initialized. Call init_network_service() first.")
    return _global_network_service


def init_network_service(**kwargs) -> NetworkService:
    """
    Initialize the global network service.
    
    Args:
        **kwargs: NetworkService initialization arguments
        
    Returns:
        Initialized NetworkService instance
    """
    global _global_network_service
    
    _global_network_service = NetworkService(**kwargs)
    return _global_network_service