"""
Configuration management system for readMarkable.

This module handles application settings, user preferences, default values,
and configuration file loading/saving for markdown synchronization operations.
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Union, List
from dataclasses import dataclass, asdict, field
from enum import Enum


class LogLevel(Enum):
    """Available log levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass
class NetworkConfig:
    """Network and connection configuration."""
    default_ip: str = "10.11.99.1"
    connection_timeout: int = 10
    ssh_port: int = 22
    max_connection_attempts: int = 3
    retry_delay: int = 2
    keepalive_interval: int = 30


@dataclass
class SyncConfig:
    """Markdown synchronization configuration."""
    local_sync_dir: str = "sync"
    remote_sync_dir: str = "/home/root/readMarkable_sync"
    watch_for_changes: bool = True
    auto_sync_interval: int = 30  # seconds
    sync_on_startup: bool = True
    
    # File patterns
    markdown_extensions: List[str] = field(default_factory=lambda: [".md", ".markdown", ".txt"])
    ignore_patterns: List[str] = field(default_factory=lambda: [".*", "__pycache__", "*.pyc", ".git"])
    
    # Conversion settings
    convert_to_pdf: bool = True
    pdf_output_dir: str = "pdf_output"
    preserve_structure: bool = True
    
    # Backup settings
    create_backups: bool = True
    backup_dir: str = "backups"
    max_backups: int = 10


@dataclass
class ConversionConfig:
    """Document conversion settings."""
    pdf_engine: str = "weasyprint"  # "weasyprint" or "reportlab"
    pdf_page_size: str = "A4"
    pdf_margin: int = 20  # mm
    
    # Font settings
    font_family: str = "Liberation Serif"
    font_size: int = 12
    line_height: float = 1.5
    
    # Markdown extensions
    enable_tables: bool = True
    enable_code_blocks: bool = True
    enable_math: bool = False  # LaTeX math support
    enable_footnotes: bool = True


@dataclass
class WatchConfig:
    """File watching configuration."""
    enabled: bool = True
    recursive: bool = True
    debounce_delay: float = 1.0  # seconds to wait before processing changes
    ignore_temp_files: bool = True
    watch_subdirectories: bool = True


@dataclass
class PathConfig:
    """File and directory path configuration."""
    config_dir: str = "config"
    logs_dir: str = "logs"
    temp_dir: str = "temp"
    
    # Device paths
    device_home: str = "/home/root"
    device_documents: str = "/home/root/.local/share/remarkable/xochitl"


@dataclass
class DeviceConfig:
    """Device-specific configuration."""
    ip_address: Optional[str] = None
    ssh_password: Optional[str] = None
    
    # Auto-detection settings
    auto_detect_device: bool = True
    validate_connection: bool = True
    
    # Device preferences
    preferred_connection_type: str = "usb"  # "usb" or "wifi"


@dataclass
class UIConfig:
    """User interface configuration."""
    theme: str = "light"  # "light" or "dark"
    window_width: int = 1000
    window_height: int = 700
    show_progress_details: bool = True
    
    # Notifications
    show_notifications: bool = True
    notification_level: str = "info"  # "error", "warning", "info", "all"
    
    # GUI behavior
    minimize_to_tray: bool = True
    start_minimized: bool = False
    confirm_on_exit: bool = True


@dataclass
class AppConfig:
    """Main application configuration container."""
    
    # Core configuration sections
    network: NetworkConfig = field(default_factory=NetworkConfig)
    sync: SyncConfig = field(default_factory=SyncConfig)
    conversion: ConversionConfig = field(default_factory=ConversionConfig)
    watch: WatchConfig = field(default_factory=WatchConfig)
    paths: PathConfig = field(default_factory=PathConfig)
    device: DeviceConfig = field(default_factory=DeviceConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    
    # Application metadata
    version: str = "1.0.0"
    app_name: str = "readMarkable"
    config_version: str = "1.0"
    
    # Runtime settings
    debug_mode: bool = False
    log_level: LogLevel = LogLevel.INFO
    
    def __post_init__(self):
        """Post-initialization processing."""
        self._load_environment_variables()
        self._validate_config()
    
    def _load_environment_variables(self) -> None:
        """Load configuration from environment variables."""
        # Device connection from environment
        if env_ip := os.getenv("REMARKABLE_IP"):
            self.device.ip_address = env_ip
            
        if env_password := os.getenv("REMARKABLE_PASSWORD"):
            self.device.ssh_password = env_password
        
        # Application settings from environment  
        if env_debug := os.getenv("READMARKABLE_DEBUG"):
            self.debug_mode = env_debug.lower() in ("true", "1", "yes", "on")
            
        if env_log_level := os.getenv("READMARKABLE_LOG_LEVEL"):
            try:
                self.log_level = LogLevel(env_log_level.upper())
            except ValueError:
                logging.warning(f"Invalid log level in environment: {env_log_level}")
        
        # Sync settings from environment
        if env_sync_dir := os.getenv("READMARKABLE_SYNC_DIR"):
            self.sync.local_sync_dir = env_sync_dir
            
        if env_auto_sync := os.getenv("READMARKABLE_AUTO_SYNC"):
            self.sync.watch_for_changes = env_auto_sync.lower() in ("true", "1", "yes", "on")
    
    def _validate_config(self) -> None:
        """Validate configuration values."""
        # Validate network timeouts
        if self.network.connection_timeout <= 0:
            raise ValueError("Connection timeout must be positive")
            
        if self.network.max_connection_attempts <= 0:
            raise ValueError("Max connection attempts must be positive")
        
        # Validate sync settings
        if self.sync.auto_sync_interval <= 0:
            raise ValueError("Auto sync interval must be positive")
        
        # Validate paths
        if not self.sync.local_sync_dir:
            raise ValueError("Local sync directory cannot be empty")
    
    def get_config_dir(self) -> Path:
        """Get the application configuration directory."""
        if os.name == 'nt':  # Windows
            config_base = Path(os.environ.get('APPDATA', '~')).expanduser()
        else:  # Unix-like
            config_base = Path(os.environ.get('XDG_CONFIG_HOME', '~/.config')).expanduser()
        
        return config_base / 'readMarkable'
    
    def get_config_file_path(self) -> Path:
        """Get the path to the configuration file."""
        return self.get_config_dir() / 'config.json'
    
    def get_sync_directory(self) -> Path:
        """Get the local sync directory path, creating it if necessary."""
        sync_path = Path(self.sync.local_sync_dir)
        if not sync_path.is_absolute():
            sync_path = Path.cwd() / sync_path
        sync_path.mkdir(parents=True, exist_ok=True)
        return sync_path
    
    def get_backup_directory(self) -> Path:
        """Get the backup directory path, creating it if necessary."""
        backup_path = Path(self.sync.backup_dir)
        if not backup_path.is_absolute():
            backup_path = self.get_config_dir() / backup_path
        backup_path.mkdir(parents=True, exist_ok=True)
        return backup_path
    
    def get_logs_directory(self) -> Path:
        """Get the logs directory path, creating it if necessary."""
        logs_path = Path(self.paths.logs_dir)
        if not logs_path.is_absolute():
            logs_path = self.get_config_dir() / logs_path
        logs_path.mkdir(parents=True, exist_ok=True)
        return logs_path
    
    def save_to_file(self, file_path: Optional[Union[str, Path]] = None) -> None:
        """
        Save configuration to a JSON file.
        
        Args:
            file_path: Path to save the config file. If None, uses default location.
            
        Raises:
            IOError: If the file cannot be written
            ValueError: If the configuration is invalid
        """
        if file_path is None:
            file_path = self.get_config_file_path()
        else:
            file_path = Path(file_path)
        
        try:
            # Convert to dictionary, handling enums
            config_dict = self._to_serializable_dict()
            
            # Ensure parent directory exists
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(config_dict, f, indent=2, ensure_ascii=False)
                
            logging.info(f"Configuration saved to {file_path}")
            
        except Exception as e:
            raise IOError(f"Failed to save configuration to {file_path}: {e}")
    
    def _to_serializable_dict(self) -> Dict[str, Any]:
        """Convert configuration to a JSON-serializable dictionary."""
        config_dict = asdict(self)
        
        # Convert enums to their values
        if config_dict.get('log_level'):
            config_dict['log_level'] = config_dict['log_level'].value
            
        return config_dict
    
    @classmethod
    def load_from_file(cls, file_path: Optional[Union[str, Path]] = None) -> 'AppConfig':
        """
        Load configuration from a JSON file.
        
        Args:
            file_path: Path to load the config file from. If None, uses default location.
            
        Returns:
            AppConfig instance loaded from file
            
        Raises:
            FileNotFoundError: If the config file doesn't exist
            ValueError: If the config file is invalid
        """
        if file_path is None:
            file_path = cls._get_default_config_path()
        else:
            file_path = Path(file_path)
            
        if not file_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {file_path}")
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                config_dict = json.load(f)
            
            return cls._from_dict(config_dict)
            
        except Exception as e:
            raise ValueError(f"Failed to load configuration from {file_path}: {e}")
    
    @classmethod
    def _get_default_config_path(cls) -> Path:
        """Get the default configuration file path."""
        temp_config = cls()
        return temp_config.get_config_file_path()
    
    @classmethod
    def _from_dict(cls, config_dict: Dict[str, Any]) -> 'AppConfig':
        """Create AppConfig instance from dictionary."""
        # Handle enum conversions
        if log_level_str := config_dict.get('log_level'):
            try:
                config_dict['log_level'] = LogLevel(log_level_str)
            except ValueError:
                logging.warning(f"Invalid log level in config: {log_level_str}")
                config_dict['log_level'] = LogLevel.INFO
        
        # Create nested configurations
        network_config = NetworkConfig(**config_dict.get('network', {}))
        sync_config = SyncConfig(**config_dict.get('sync', {}))
        conversion_config = ConversionConfig(**config_dict.get('conversion', {}))
        watch_config = WatchConfig(**config_dict.get('watch', {}))
        paths_config = PathConfig(**config_dict.get('paths', {}))
        device_config = DeviceConfig(**config_dict.get('device', {}))
        ui_config = UIConfig(**config_dict.get('ui', {}))
        
        # Create main config
        return cls(
            network=network_config,
            sync=sync_config,
            conversion=conversion_config,
            watch=watch_config,
            paths=paths_config,
            device=device_config,
            ui=ui_config,
            version=config_dict.get('version', '1.0.0'),
            app_name=config_dict.get('app_name', 'readMarkable'),
            config_version=config_dict.get('config_version', '1.0'),
            debug_mode=config_dict.get('debug_mode', False),
            log_level=config_dict.get('log_level', LogLevel.INFO)
        )
    
    def update_device_info(self, ip_address: Optional[str] = None,
                          ssh_password: Optional[str] = None) -> None:
        """
        Update device configuration information.
        
        Args:
            ip_address: Device IP address
            ssh_password: SSH password
        """
        if ip_address is not None:
            self.device.ip_address = ip_address
            
        if ssh_password is not None:
            self.device.ssh_password = ssh_password
    
    def is_valid_device_config(self) -> bool:
        """Check if device configuration is valid for connection."""
        return (
            self.device.ip_address is not None and 
            self.device.ssh_password is not None
        )
    
    def reset_to_defaults(self) -> None:
        """Reset all configuration to default values."""
        default_config = AppConfig()
        
        self.network = default_config.network
        self.sync = default_config.sync
        self.conversion = default_config.conversion
        self.watch = default_config.watch
        self.paths = default_config.paths
        self.device = DeviceConfig()  # Keep device info separate
        self.ui = default_config.ui
        self.debug_mode = default_config.debug_mode
        self.log_level = default_config.log_level


# Global configuration instance
_global_config: Optional[AppConfig] = None


def get_config() -> AppConfig:
    """
    Get the global configuration instance.
    
    Returns:
        Global AppConfig instance
        
    Raises:
        RuntimeError: If configuration hasn't been initialized
    """
    global _global_config
    if _global_config is None:
        raise RuntimeError("Configuration not initialized. Call init_config() first.")
    return _global_config


def init_config(config_file: Optional[Union[str, Path]] = None) -> AppConfig:
    """
    Initialize the global configuration.
    
    Args:
        config_file: Optional path to config file. If None, uses default or creates new.
        
    Returns:
        Initialized AppConfig instance
    """
    global _global_config
    
    try:
        if config_file:
            _global_config = AppConfig.load_from_file(config_file)
        else:
            # Try to load from default location
            try:
                _global_config = AppConfig.load_from_file()
            except FileNotFoundError:
                # Create new config with defaults
                _global_config = AppConfig()
                logging.info("Created new configuration with default values")
    except Exception as e:
        logging.warning(f"Failed to load configuration: {e}. Using defaults.")
        _global_config = AppConfig()
    
    return _global_config


def save_config() -> None:
    """Save the current global configuration to file."""
    config = get_config()
    config.save_to_file()