"""
Device model and data structures for readmarkable.

This module contains the Device class representing reMarkable tablet state,
connection info, and validation methods for markdown synchronization.
"""

import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from ipaddress import IPv4Address, AddressValueError


class DeviceType(Enum):
    """Supported reMarkable device types with their architecture mappings."""
    RM1 = ("rM1", "armv6l", "reMarkable 1")
    RM2 = ("rM2", "armv7l", "reMarkable 2") 
    RMPP = ("rMPP", "aarch64", "reMarkable Paper Pro")
    
    def __init__(self, short_name: str, architecture: str, display_name: str):
        self.short_name = short_name
        self.architecture = architecture
        self.display_name = display_name
    
    @classmethod
    def from_architecture(cls, arch: str) -> Optional['DeviceType']:
        """Get device type from architecture string."""
        arch_mapping = {
            "armv6l": cls.RM1,
            "armv7l": cls.RM2,
            "armhf": cls.RM2,  # Alternative name for rM2
            "aarch64": cls.RMPP,
            "arm64": cls.RMPP   # Alternative name for rMPP
        }
        return arch_mapping.get(arch.lower())
    
    @classmethod
    def from_short_name(cls, name: str) -> Optional['DeviceType']:
        """Get device type from short name (rM1, rM2, rMPP)."""
        name_mapping = {
            "rm1": cls.RM1,
            "rm2": cls.RM2,
            "rmpp": cls.RMPP
        }
        return name_mapping.get(name.lower())


class ConnectionStatus(Enum):
    """Device connection status."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    AUTHENTICATION_FAILED = "auth_failed"
    TIMEOUT = "timeout"
    ERROR = "error"


class SyncStatus(Enum):
    """Synchronization status."""
    IDLE = "idle"
    SYNCING = "syncing"
    WATCHING = "watching"
    ERROR = "error"
    COMPLETED = "completed"


@dataclass
class DeviceInfo:
    """Device system information."""
    hostname: Optional[str] = None
    kernel_version: Optional[str] = None
    remarkable_version: Optional[str] = None
    uptime: Optional[str] = None
    free_space: Optional[int] = None  # bytes
    total_space: Optional[int] = None  # bytes
    
    def get_free_space_mb(self) -> Optional[float]:
        """Get free space in MB."""
        return self.free_space / (1024 * 1024) if self.free_space else None
    
    def get_total_space_mb(self) -> Optional[float]:
        """Get total space in MB."""
        return self.total_space / (1024 * 1024) if self.total_space else None


@dataclass
class NetworkInfo:
    """Device network configuration."""
    usb_ip: Optional[str] = None
    wifi_ip: Optional[str] = None
    wifi_enabled: bool = False
    ethernet_enabled: bool = False
    
    def get_primary_ip(self) -> Optional[str]:
        """Get the primary IP address (USB preferred)."""
        return self.usb_ip or self.wifi_ip
    
    def has_connectivity(self) -> bool:
        """Check if device has any network connectivity."""
        return bool(self.usb_ip or self.wifi_ip)


@dataclass
class SyncInfo:
    """Information about synchronization state."""
    last_sync: Optional[datetime] = None
    files_synced: int = 0
    files_pending: int = 0
    sync_errors: int = 0
    bytes_synced: int = 0
    
    sync_directory: Optional[str] = None
    markdown_files_count: int = 0
    pdf_files_count: int = 0
    
    def get_sync_progress(self) -> float:
        """Get sync progress as percentage."""
        total_files = self.files_synced + self.files_pending
        if total_files > 0:
            return (self.files_synced / total_files) * 100.0
        return 0.0


class Device:
    """
    Represents a reMarkable device with connection and sync state management.
    
    This class encapsulates all device-related functionality including
    connection management, device detection, and synchronization status.
    """
    
    def __init__(self, ip_address: Optional[str] = None, 
                 ssh_password: Optional[str] = None,
                 device_type: Optional[DeviceType] = None):
        """
        Initialize a Device instance.
        
        Args:
            ip_address: Device IP address
            ssh_password: SSH password for authentication
            device_type: Device type (will be auto-detected if None)
        """
        self.ip_address = ip_address
        self.ssh_password = ssh_password
        self.device_type = device_type
        
        # State information
        self.connection_status = ConnectionStatus.DISCONNECTED
        self.sync_status = SyncStatus.IDLE
        self.last_connection_attempt: Optional[datetime] = None
        self.last_error: Optional[str] = None
        
        # Device information (populated on connection)
        self.device_info: Optional[DeviceInfo] = None
        self.network_info: Optional[NetworkInfo] = None
        self.sync_info: Optional[SyncInfo] = None
        
        # Connection settings
        self.connection_timeout = 10
        self.max_retries = 3
        self.ssh_port = 22
        
        self._logger = logging.getLogger(__name__)
    
    def __str__(self) -> str:
        """String representation of the device."""
        device_type_str = self.device_type.display_name if self.device_type else "Unknown"
        status_str = self.connection_status.value.replace('_', ' ').title()
        return f"{device_type_str} at {self.ip_address or 'Unknown IP'} ({status_str})"
    
    def __repr__(self) -> str:
        """Developer representation of the device."""
        return (f"Device(ip_address='{self.ip_address}', "
                f"device_type={self.device_type}, "
                f"status={self.connection_status})")
    
    def is_configured(self) -> bool:
        """Check if device has minimum required configuration."""
        return bool(self.ip_address and self.ssh_password)
    
    def is_connected(self) -> bool:
        """Check if device is currently connected."""
        return self.connection_status == ConnectionStatus.CONNECTED
    
    def validate_ip_address(self) -> bool:
        """
        Validate the IP address format.
        
        Returns:
            True if IP address is valid, False otherwise
        """
        if not self.ip_address:
            return False
        
        try:
            IPv4Address(self.ip_address)
            return True
        except AddressValueError:
            return False
    
    def validate_ssh_password(self) -> bool:
        """
        Validate SSH password format.
        
        Returns:
            True if password appears valid, False otherwise
        """
        if not self.ssh_password:
            return False
        
        # Basic validation - password should be non-empty and reasonable length
        return 1 <= len(self.ssh_password) <= 256
    
    def update_connection_info(self, ip_address: Optional[str] = None,
                             ssh_password: Optional[str] = None) -> None:
        """
        Update device connection information.
        
        Args:
            ip_address: New IP address
            ssh_password: New SSH password
        """
        if ip_address is not None:
            self.ip_address = ip_address
            self.connection_status = ConnectionStatus.DISCONNECTED
            
        if ssh_password is not None:
            self.ssh_password = ssh_password
            self.connection_status = ConnectionStatus.DISCONNECTED
    
    def test_connection(self) -> bool:
        """
        Test SSH connection to the device.
        
        Returns:
            True if connection successful, False otherwise
        """
        if not self.is_configured():
            self.connection_status = ConnectionStatus.ERROR
            self.last_error = "Device not configured (missing IP or password)"
            return False
        
        if not self.validate_ip_address():
            self.connection_status = ConnectionStatus.ERROR
            self.last_error = "Invalid IP address format"
            return False
        
        self.connection_status = ConnectionStatus.CONNECTING
        self.last_connection_attempt = datetime.now()
        
        try:
            # Import network service here to avoid circular imports
            from services.network_service import get_network_service
            
            network_service = get_network_service()
            network_service.set_connection_details(
                hostname=self.ip_address,
                password=self.ssh_password
            )
            
            success = network_service.connect()
            
            if success:
                self.connection_status = ConnectionStatus.CONNECTED
                self.last_error = None
                self._logger.info(f"Successfully connected to device at {self.ip_address}")
                
                # Try to detect device type
                self.detect_device_type()
                
                return True
            else:
                self.connection_status = ConnectionStatus.AUTHENTICATION_FAILED
                self.last_error = network_service.last_error or "Connection test failed"
                self._logger.error(f"Connection test failed: {self.last_error}")
                return False
                
        except Exception as e:
            self._logger.error(f"Connection test failed: {e}")
            self.connection_status = ConnectionStatus.ERROR
            self.last_error = str(e)
            return False
    
    def detect_device_type(self) -> Optional[DeviceType]:
        """
        Detect device type by querying architecture.
        
        Returns:
            Detected device type or None if detection failed
        """
        if not self.is_connected():
            self._logger.warning("Cannot detect device type: not connected")
            return None
        
        try:
            # Import network service here to avoid circular imports
            from services.network_service import get_network_service
            
            network_service = get_network_service()
            
            # Get device architecture
            arch_result = network_service.execute_command("uname -m")
            if arch_result.success:
                arch = arch_result.stdout.strip()
                self.device_type = DeviceType.from_architecture(arch)
                if self.device_type:
                    self._logger.info(f"Detected device type: {self.device_type.display_name}")
                else:
                    self._logger.warning(f"Unknown architecture: {arch}")
            
            return self.device_type
            
        except Exception as e:
            self._logger.error(f"Failed to detect device type: {e}")
            self.last_error = str(e)
            return None
    
    def get_status_summary(self) -> Dict[str, Any]:
        """
        Get a comprehensive status summary.
        
        Returns:
            Dictionary containing device status information
        """
        return {
            "device_type": self.device_type.display_name if self.device_type else "Unknown",
            "ip_address": self.ip_address,
            "connection_status": self.connection_status.value,
            "sync_status": self.sync_status.value,
            "last_connection_attempt": self.last_connection_attempt.isoformat() if self.last_connection_attempt else None,
            "last_error": self.last_error,
            "is_configured": self.is_configured(),
            "is_connected": self.is_connected(),
            "has_network": self.network_info.has_connectivity() if self.network_info else False,
            "sync_progress": self.sync_info.get_sync_progress() if self.sync_info else 0.0
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert device to dictionary representation.
        
        Returns:
            Dictionary representation of the device
        """
        return {
            "ip_address": self.ip_address,
            "device_type": self.device_type.short_name if self.device_type else None,
            "connection_status": self.connection_status.value,
            "sync_status": self.sync_status.value,
            "last_connection_attempt": self.last_connection_attempt.isoformat() if self.last_connection_attempt else None,
            "last_error": self.last_error,
            "device_info": {
                "hostname": self.device_info.hostname if self.device_info else None,
                "kernel_version": self.device_info.kernel_version if self.device_info else None,
                "remarkable_version": self.device_info.remarkable_version if self.device_info else None,
                "free_space_mb": self.device_info.get_free_space_mb() if self.device_info else None,
                "total_space_mb": self.device_info.get_total_space_mb() if self.device_info else None
            },
            "network_info": {
                "primary_ip": self.network_info.get_primary_ip() if self.network_info else None,
                "wifi_enabled": self.network_info.wifi_enabled if self.network_info else False,
                "ethernet_enabled": self.network_info.ethernet_enabled if self.network_info else False
            },
            "sync_info": {
                "last_sync": self.sync_info.last_sync.isoformat() if self.sync_info and self.sync_info.last_sync else None,
                "files_synced": self.sync_info.files_synced if self.sync_info else 0,
                "files_pending": self.sync_info.files_pending if self.sync_info else 0,
                "sync_progress": self.sync_info.get_sync_progress() if self.sync_info else 0.0
            }
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Device':
        """
        Create Device instance from dictionary.
        
        Args:
            data: Dictionary representation of device
            
        Returns:
            Device instance
        """
        device_type = None
        if data.get("device_type"):
            device_type = DeviceType.from_short_name(data["device_type"])
        
        device = cls(
            ip_address=data.get("ip_address"),
            device_type=device_type
        )
        
        # Restore connection status
        if connection_status := data.get("connection_status"):
            try:
                device.connection_status = ConnectionStatus(connection_status)
            except ValueError:
                pass
        
        # Restore sync status
        if sync_status := data.get("sync_status"):
            try:
                device.sync_status = SyncStatus(sync_status)
            except ValueError:
                pass
        
        # Restore timestamps and errors
        if last_attempt := data.get("last_connection_attempt"):
            try:
                device.last_connection_attempt = datetime.fromisoformat(last_attempt)
            except ValueError:
                pass
                
        device.last_error = data.get("last_error")
        
        return device


# Utility functions for device management

def get_default_device_ip() -> str:
    """Get the default reMarkable device IP address."""
    return "10.11.99.1"


def is_valid_remarkable_ip(ip_address: str) -> bool:
    """
    Check if an IP address is likely a reMarkable device.
    
    Args:
        ip_address: IP address to validate
        
    Returns:
        True if IP appears to be a reMarkable device
    """
    if not ip_address:
        return False
    
    try:
        ip = IPv4Address(ip_address)
        
        # Common reMarkable IP ranges
        remarkable_networks = [
            "10.11.99.0/24",    # USB ethernet
            "192.168.0.0/16",   # Common WiFi networks
            "172.16.0.0/12",    # Private networks
            "10.0.0.0/8"        # Private networks
        ]
        
        # Check if IP is in any of the common ranges
        for network in remarkable_networks:
            try:
                from ipaddress import ip_network
                if ip in ip_network(network):
                    return True
            except ValueError:
                continue
        
        return False
        
    except AddressValueError:
        return False


def detect_local_remarkable_devices() -> List[str]:
    """
    Attempt to detect reMarkable devices on the local network.
    
    Returns:
        List of potential reMarkable IP addresses
    """
    # This would implement network scanning to find reMarkable devices
    # For now, return common IP addresses
    return ["10.11.99.1"]  # USB ethernet default