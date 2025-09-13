"""
Input validation utilities for readmarkable.

This module provides validation functions for IP addresses, passwords,
file paths, network connectivity, and markdown sync operations.
"""

import re
import os
import socket
import subprocess
import logging
from pathlib import Path
from typing import Union, Optional, List, Tuple, Dict, Any
from ipaddress import IPv4Address, AddressValueError
from urllib.parse import urlparse


class ValidationError(Exception):
    """Custom exception for validation errors."""
    pass


class ValidationResult:
    """Result of a validation operation."""
    
    def __init__(self, is_valid: bool, message: str = "", details: Optional[Dict[str, Any]] = None):
        self.is_valid = is_valid
        self.message = message
        self.details = details or {}
    
    def __bool__(self) -> bool:
        return self.is_valid
    
    def __str__(self) -> str:
        return f"ValidationResult(valid={self.is_valid}, message='{self.message}')"


class Validator:
    """
    Comprehensive validator class for readmarkable.
    
    Provides validation methods for various input types including
    IP addresses, passwords, file paths, markdown files, and network connectivity.
    """
    
    def __init__(self):
        self._logger = logging.getLogger(__name__)
        
        # Regex patterns
        self.ip_pattern = re.compile(r'^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$')
        self.hostname_pattern = re.compile(r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$')
        
        # Common reMarkable IP ranges
        self.remarkable_networks = [
            "10.11.99.0/24",    # USB ethernet default
            "192.168.0.0/16",   # Common WiFi networks
            "172.16.0.0/12",    # Private networks
            "10.0.0.0/8"        # Private networks
        ]
        
        # Markdown file extensions
        self.markdown_extensions = [".md", ".markdown", ".mdown", ".mkd", ".txt"]
    
    def validate_ip_address(self, ip_address: str, allow_hostnames: bool = False) -> ValidationResult:
        """
        Validate IP address format and optionally resolve hostnames.
        
        Args:
            ip_address: IP address or hostname to validate
            allow_hostnames: Whether to allow and resolve hostnames
            
        Returns:
            ValidationResult with validation status and details
        """
        if not ip_address or not isinstance(ip_address, str):
            return ValidationResult(False, "IP address cannot be empty")
        
        ip_address = ip_address.strip()
        
        # Check basic format with regex
        if self.ip_pattern.match(ip_address):
            try:
                # Validate with ipaddress module
                ip_obj = IPv4Address(ip_address)
                
                # Additional checks for reMarkable devices
                is_remarkable_range = self._is_remarkable_ip_range(ip_address)
                is_private = ip_obj.is_private
                
                details = {
                    "ip_object": ip_obj,
                    "is_private": is_private,
                    "is_remarkable_range": is_remarkable_range,
                    "ip_type": "ipv4"
                }
                
                if ip_obj.is_loopback:
                    return ValidationResult(False, "Loopback addresses are not valid for reMarkable devices", details)
                
                if ip_obj.is_multicast:
                    return ValidationResult(False, "Multicast addresses are not valid for reMarkable devices", details)
                
                return ValidationResult(True, "Valid IP address", details)
                
            except AddressValueError as e:
                return ValidationResult(False, f"Invalid IP address format: {e}")
        
        # If not a valid IP, check if it's a hostname (if allowed)
        if allow_hostnames:
            if self.hostname_pattern.match(ip_address):
                try:
                    # Try to resolve hostname
                    resolved_ip = socket.gethostbyname(ip_address)
                    recursive_result = self.validate_ip_address(resolved_ip, allow_hostnames=False)
                    
                    if recursive_result.is_valid:
                        details = recursive_result.details.copy()
                        details.update({
                            "original_hostname": ip_address,
                            "resolved_ip": resolved_ip,
                            "ip_type": "hostname"
                        })
                        return ValidationResult(True, f"Valid hostname resolves to {resolved_ip}", details)
                    else:
                        return ValidationResult(False, f"Hostname resolves to invalid IP: {recursive_result.message}")
                        
                except socket.gaierror as e:
                    return ValidationResult(False, f"Cannot resolve hostname: {e}")
            else:
                return ValidationResult(False, "Invalid hostname format")
        
        return ValidationResult(False, "Invalid IP address format. Expected format: xxx.xxx.xxx.xxx")
    
    def _is_remarkable_ip_range(self, ip_address: str) -> bool:
        """Check if IP address is in a typical reMarkable device range."""
        try:
            ip = IPv4Address(ip_address)
            from ipaddress import ip_network
            
            for network_str in self.remarkable_networks:
                network = ip_network(network_str)
                if ip in network:
                    return True
            return False
        except (AddressValueError, ValueError):
            return False
    
    def validate_ssh_password(self, password: str, min_length: int = 1, max_length: int = 256) -> ValidationResult:
        """
        Validate SSH password.
        
        Args:
            password: Password to validate
            min_length: Minimum password length
            max_length: Maximum password length
            
        Returns:
            ValidationResult with validation status
        """
        if not password:
            return ValidationResult(False, "Password cannot be empty")
        
        if not isinstance(password, str):
            return ValidationResult(False, "Password must be a string")
        
        if len(password) < min_length:
            return ValidationResult(False, f"Password too short (minimum {min_length} characters)")
        
        if len(password) > max_length:
            return ValidationResult(False, f"Password too long (maximum {max_length} characters)")
        
        # Check for problematic characters that might cause SSH issues
        problematic_chars = ['\n', '\r', '\0']
        for char in problematic_chars:
            if char in password:
                return ValidationResult(False, f"Password contains invalid character: {repr(char)}")
        
        # Basic strength indicators
        details = {
            "length": len(password),
            "has_uppercase": any(c.isupper() for c in password),
            "has_lowercase": any(c.islower() for c in password),
            "has_digits": any(c.isdigit() for c in password),
            "has_special": any(not c.isalnum() for c in password)
        }
        
        return ValidationResult(True, "Valid password", details)
    
    def validate_file_path(self, file_path: Union[str, Path], 
                          must_exist: bool = False,
                          must_be_file: bool = False,
                          must_be_dir: bool = False,
                          must_be_readable: bool = False,
                          must_be_writable: bool = False) -> ValidationResult:
        """
        Validate file path and check various conditions.
        
        Args:
            file_path: Path to validate
            must_exist: Whether the path must exist
            must_be_file: Whether the path must be a file
            must_be_dir: Whether the path must be a directory
            must_be_readable: Whether the path must be readable
            must_be_writable: Whether the path must be writable
            
        Returns:
            ValidationResult with validation status and path details
        """
        if not file_path:
            return ValidationResult(False, "File path cannot be empty")
        
        try:
            path_obj = Path(file_path)
            
            # Basic path validation
            if not path_obj.is_absolute() and '..' in str(path_obj):
                # Allow relative paths but warn about potential security issues with ..
                self._logger.warning(f"Path contains '..' which may be a security risk: {file_path}")
            
            # Check existence
            exists = path_obj.exists()
            if must_exist and not exists:
                return ValidationResult(False, f"Path does not exist: {file_path}")
            
            details = {
                "path_object": path_obj,
                "exists": exists,
                "is_absolute": path_obj.is_absolute(),
                "parent_exists": path_obj.parent.exists() if path_obj.parent != path_obj else True
            }
            
            if exists:
                is_file = path_obj.is_file()
                is_dir = path_obj.is_dir()
                
                details.update({
                    "is_file": is_file,
                    "is_dir": is_dir,
                    "is_symlink": path_obj.is_symlink(),
                    "size_bytes": path_obj.stat().st_size if is_file else None
                })
                
                # Type checks
                if must_be_file and not is_file:
                    return ValidationResult(False, f"Path is not a file: {file_path}")
                
                if must_be_dir and not is_dir:
                    return ValidationResult(False, f"Path is not a directory: {file_path}")
                
                # Permission checks
                if must_be_readable and not os.access(path_obj, os.R_OK):
                    return ValidationResult(False, f"Path is not readable: {file_path}")
                
                if must_be_writable and not os.access(path_obj, os.W_OK):
                    return ValidationResult(False, f"Path is not writable: {file_path}")
                
                details.update({
                    "readable": os.access(path_obj, os.R_OK),
                    "writable": os.access(path_obj, os.W_OK),
                    "executable": os.access(path_obj, os.X_OK)
                })
            
            return ValidationResult(True, "Valid file path", details)
            
        except Exception as e:
            return ValidationResult(False, f"Invalid file path: {e}")
    
    def validate_markdown_file(self, file_path: Union[str, Path]) -> ValidationResult:
        """
        Validate if a file is a valid markdown file.
        
        Args:
            file_path: Path to the markdown file
            
        Returns:
            ValidationResult with markdown validation status
        """
        path_result = self.validate_file_path(file_path, must_exist=True, must_be_file=True, must_be_readable=True)
        if not path_result.is_valid:
            return path_result
        
        path_obj = Path(file_path)
        
        # Check file extension
        if path_obj.suffix.lower() not in self.markdown_extensions:
            return ValidationResult(
                False, 
                f"File extension '{path_obj.suffix}' is not a recognized markdown extension. "
                f"Expected one of: {', '.join(self.markdown_extensions)}"
            )
        
        # Try to read and validate basic markdown content
        try:
            content = path_obj.read_text(encoding='utf-8', errors='ignore')
            
            # Basic markdown validation
            is_likely_markdown = any([
                content.startswith('#'),  # Headers
                '# ' in content,          # Headers with space
                '## ' in content,         # Subheaders
                '**' in content,          # Bold text
                '*' in content and not content.count('*') < 2,  # Italic or emphasis
                '[' in content and '](' in content,  # Links
                '```' in content,         # Code blocks
                content.strip() == '' or len(content.strip()) > 0  # Empty or has content
            ])
            
            details = {
                "file_size": len(content),
                "line_count": content.count('\n') + 1 if content else 0,
                "extension": path_obj.suffix.lower(),
                "is_likely_markdown": is_likely_markdown,
                "encoding": "utf-8"
            }
            
            return ValidationResult(True, "Valid markdown file", details)
            
        except Exception as e:
            return ValidationResult(False, f"Cannot read markdown file: {e}")
    
    def validate_sync_directory(self, dir_path: Union[str, Path]) -> ValidationResult:
        """
        Validate if a directory is suitable for markdown synchronization.
        
        Args:
            dir_path: Path to the sync directory
            
        Returns:
            ValidationResult with directory validation status
        """
        dir_result = self.validate_file_path(
            dir_path, 
            must_exist=False,  # Directory might not exist yet
            must_be_dir=True if Path(dir_path).exists() else False,
            must_be_readable=True if Path(dir_path).exists() else False,
            must_be_writable=True if Path(dir_path).exists() else False
        )
        
        if not dir_result.is_valid and Path(dir_path).exists():
            return dir_result
        
        path_obj = Path(dir_path)
        
        try:
            # If directory doesn't exist, check if we can create it
            if not path_obj.exists():
                # Check if parent directory is writable
                parent = path_obj.parent
                if not parent.exists():
                    return ValidationResult(False, f"Parent directory does not exist: {parent}")
                if not os.access(parent, os.W_OK):
                    return ValidationResult(False, f"Cannot create directory - parent not writable: {parent}")
            
            # Count markdown files if directory exists
            markdown_count = 0
            if path_obj.exists():
                for ext in self.markdown_extensions:
                    markdown_count += len(list(path_obj.glob(f"**/*{ext}")))
            
            details = {
                "can_create": not path_obj.exists() and os.access(path_obj.parent, os.W_OK),
                "markdown_files_count": markdown_count,
                "is_empty": markdown_count == 0 if path_obj.exists() else True
            }
            
            return ValidationResult(True, "Valid sync directory", details)
            
        except Exception as e:
            return ValidationResult(False, f"Error validating sync directory: {e}")
    
    def check_network_connectivity(self, host: str, port: int = 22, timeout: int = 5) -> ValidationResult:
        """
        Check network connectivity to a host and port.
        
        Args:
            host: Hostname or IP address
            port: Port number (default: 22 for SSH)
            timeout: Connection timeout in seconds
            
        Returns:
            ValidationResult with connectivity status
        """
        try:
            # First validate the host as an IP or hostname
            ip_result = self.validate_ip_address(host, allow_hostnames=True)
            if not ip_result.is_valid:
                return ValidationResult(False, f"Invalid host: {ip_result.message}")
            
            # Attempt socket connection
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            
            try:
                result = sock.connect_ex((host, port))
                sock.close()
                
                if result == 0:
                    details = {
                        "host": host,
                        "port": port,
                        "timeout": timeout,
                        "connection_successful": True
                    }
                    return ValidationResult(True, f"Successfully connected to {host}:{port}", details)
                else:
                    details = {
                        "host": host,
                        "port": port,
                        "timeout": timeout,
                        "connection_successful": False,
                        "error_code": result
                    }
                    return ValidationResult(False, f"Cannot connect to {host}:{port} (error {result})", details)
                    
            except socket.timeout:
                return ValidationResult(False, f"Connection to {host}:{port} timed out after {timeout} seconds")
            except Exception as e:
                return ValidationResult(False, f"Connection error: {e}")
                
        except Exception as e:
            return ValidationResult(False, f"Network connectivity check failed: {e}")
    
    def check_ssh_requirements(self) -> ValidationResult:
        """
        Check if SSH client requirements are met.
        
        Returns:
            ValidationResult with SSH requirements status
        """
        # Check for paramiko (primary SSH client)
        paramiko_available = False
        try:
            import paramiko
            paramiko_available = True
        except ImportError:
            pass
        
        if paramiko_available:
            details = {
                "paramiko_available": True,
                "primary_client": "paramiko",
                "all_requirements_met": True
            }
            return ValidationResult(True, "SSH support available via paramiko", details)
        
        # Check for system SSH as fallback
        ssh_available = False
        try:
            result = subprocess.run(['ssh', '-V'], capture_output=True, text=True, timeout=5)
            ssh_available = result.returncode == 0 or 'OpenSSH' in result.stderr
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        
        if ssh_available:
            details = {
                "paramiko_available": False,
                "openssh_available": True,
                "primary_client": "openssh",
                "all_requirements_met": True,
                "warning": "Using system SSH - paramiko recommended for better integration"
            }
            return ValidationResult(True, "SSH support available via system SSH", details)
        
        return ValidationResult(
            False,
            "No SSH client available. Please install paramiko: pip install paramiko",
            {"paramiko_available": False, "openssh_available": False, "all_requirements_met": False}
        )
    
    def sanitize_filename(self, filename: str, replacement: str = "_") -> str:
        """
        Sanitize filename by removing/replacing problematic characters.
        
        Args:
            filename: Original filename
            replacement: Character to replace problematic characters with
            
        Returns:
            Sanitized filename
        """
        if not filename:
            return "unnamed"
        
        # Remove problematic characters
        problematic_chars = r'[<>:"/\\|?*\x00-\x1f]'
        sanitized = re.sub(problematic_chars, replacement, filename)
        
        # Remove leading/trailing dots and spaces
        sanitized = sanitized.strip('. ')
        
        # Ensure not empty
        if not sanitized:
            sanitized = "unnamed"
        
        # Limit length
        if len(sanitized) > 255:
            sanitized = sanitized[:255]
        
        return sanitized


# Global validator instance
_global_validator: Optional[Validator] = None


def get_validator() -> Validator:
    """
    Get the global validator instance.
    
    Returns:
        Global Validator instance
    """
    global _global_validator
    if _global_validator is None:
        _global_validator = Validator()
    return _global_validator


# Convenience functions for common validations

def validate_ip(ip_address: str) -> ValidationResult:
    """Validate IP address (convenience function)."""
    return get_validator().validate_ip_address(ip_address)


def validate_password(password: str) -> ValidationResult:
    """Validate password (convenience function)."""
    return get_validator().validate_ssh_password(password)


def validate_path(file_path: Union[str, Path], **kwargs) -> ValidationResult:
    """Validate file path (convenience function)."""
    return get_validator().validate_file_path(file_path, **kwargs)


def validate_markdown(file_path: Union[str, Path]) -> ValidationResult:
    """Validate markdown file (convenience function)."""
    return get_validator().validate_markdown_file(file_path)


def validate_sync_dir(dir_path: Union[str, Path]) -> ValidationResult:
    """Validate sync directory (convenience function)."""
    return get_validator().validate_sync_directory(dir_path)


def check_connectivity(host: str, port: int = 22) -> ValidationResult:
    """Check network connectivity (convenience function)."""
    return get_validator().check_network_connectivity(host, port)


def check_ssh_available() -> ValidationResult:
    """Check SSH requirements (convenience function)."""
    return get_validator().check_ssh_requirements()