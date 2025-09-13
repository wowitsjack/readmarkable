"""
Logging system for readmarkable.

This module provides a custom logger with colored output,
multiple log levels, file logging, and GUI log handler interfaces.
"""

import sys
import logging
import logging.handlers
from pathlib import Path
from typing import Optional, Dict, Any, Callable, List, TextIO
from datetime import datetime
from enum import Enum


class LogLevel(Enum):
    """Custom log levels for readmarkable."""
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    HIGHLIGHT = 35  # Custom level between WARNING and ERROR


class ColorCodes:
    """ANSI color codes for console output."""
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    PURPLE = '\033[0;35m'
    NC = '\033[0m'  # No Color
    
    @classmethod
    def strip_colors(cls, text: str) -> str:
        """Remove ANSI color codes from text."""
        import re
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', text)


class ColoredFormatter(logging.Formatter):
    """Custom formatter that adds colors to log messages."""
    
    def __init__(self, colored: bool = True, show_timestamp: bool = True):
        """
        Initialize colored formatter.
        
        Args:
            colored: Whether to include ANSI color codes
            show_timestamp: Whether to include timestamps in format
        """
        self.colored = colored
        self.show_timestamp = show_timestamp
        
        # Format patterns
        if show_timestamp:
            self.formats = {
                LogLevel.DEBUG.value: "[DEBUG] %(message)s",
                LogLevel.INFO.value: "[INFO] %(message)s", 
                LogLevel.WARNING.value: "[WARNING] %(message)s",
                LogLevel.ERROR.value: "[ERROR] %(message)s",
                LogLevel.HIGHLIGHT.value: "[SYNC] %(message)s",
                logging.INFO: "[%(asctime)s] %(message)s"  # Default for log() function
            }
        else:
            self.formats = {
                LogLevel.DEBUG.value: "[DEBUG] %(message)s",
                LogLevel.INFO.value: "[INFO] %(message)s",
                LogLevel.WARNING.value: "[WARNING] %(message)s", 
                LogLevel.ERROR.value: "[ERROR] %(message)s",
                LogLevel.HIGHLIGHT.value: "[SYNC] %(message)s",
                logging.INFO: "%(message)s"
            }
        
        # Color mappings
        self.colors = {
            LogLevel.DEBUG.value: ColorCodes.NC,
            LogLevel.INFO.value: ColorCodes.BLUE,
            LogLevel.WARNING.value: ColorCodes.YELLOW,
            LogLevel.ERROR.value: ColorCodes.RED,
            LogLevel.HIGHLIGHT.value: ColorCodes.PURPLE,
            logging.INFO: ColorCodes.GREEN  # Default for log() function
        }
        
        super().__init__()
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record with appropriate colors and style."""
        # Choose format pattern
        log_format = self.formats.get(record.levelno, "[%(levelname)s] %(message)s")
        
        # Set timestamp format
        if self.show_timestamp and record.levelno == logging.INFO:
            self.datefmt = '%Y-%m-%d %H:%M:%S'
        
        formatter = logging.Formatter(log_format, self.datefmt)
        formatted_message = formatter.format(record)
        
        # Add colors if enabled
        if self.colored and sys.stdout.isatty():
            color = self.colors.get(record.levelno, ColorCodes.NC)
            formatted_message = f"{color}{formatted_message}{ColorCodes.NC}"
        
        return formatted_message


class GUILogHandler(logging.Handler):
    """Log handler that can send messages to GUI components."""
    
    def __init__(self, callback: Optional[Callable[[str, int], None]] = None):
        """
        Initialize GUI log handler.
        
        Args:
            callback: Function to call with (message, level) for each log entry
        """
        super().__init__()
        self.callback = callback
        self.log_entries: List[Dict[str, Any]] = []
    
    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record to GUI."""
        try:
            msg = self.format(record)
            
            # Store log entry
            self.log_entries.append({
                'timestamp': datetime.fromtimestamp(record.created),
                'level': record.levelno,
                'level_name': record.levelname,
                'message': msg,
                'raw_message': record.getMessage()
            })
            
            # Call GUI callback if available
            if self.callback:
                self.callback(msg, record.levelno)
                
        except Exception:
            self.handleError(record)
    
    def get_recent_logs(self, count: int = 100) -> List[Dict[str, Any]]:
        """Get recent log entries."""
        return self.log_entries[-count:]
    
    def clear_logs(self) -> None:
        """Clear stored log entries."""
        self.log_entries.clear()


class ReadmarkableLogger:
    """
    Custom logger for readmarkable application.
    
    Provides logging functions for markdown synchronization operations:
    - log() - Main logging with timestamp
    - error() - Error messages
    - warn() - Warning messages  
    - info() - Info messages
    - highlight() - Sync/highlight messages
    """
    
    def __init__(self, name: str = "readmarkable", 
                 colored: bool = True,
                 log_file: Optional[Path] = None):
        """
        Initialize readmarkable logger.
        
        Args:
            name: Logger name
            colored: Whether to use colored output
            log_file: Optional file to log to
        """
        self.name = name
        self.colored = colored
        self.log_file = log_file
        
        # Create logger instance
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        
        # Clear any existing handlers
        self.logger.handlers.clear()
        
        # Add console handler
        self._setup_console_handler()
        
        # Add file handler if specified
        if log_file:
            self._setup_file_handler(log_file)
        
        # Add custom log level
        logging.addLevelName(LogLevel.HIGHLIGHT.value, "HIGHLIGHT")
        
        # GUI handler for log output to interface
        self.gui_handler: Optional[GUILogHandler] = None
    
    def _setup_console_handler(self) -> None:
        """Setup console logging handler."""
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)
        console_formatter = ColoredFormatter(colored=self.colored, show_timestamp=True)
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)
    
    def _setup_file_handler(self, log_file: Path) -> None:
        """Setup file logging handler."""
        try:
            # Ensure log directory exists
            log_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Create rotating file handler
            file_handler = logging.handlers.RotatingFileHandler(
                log_file, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8'
            )
            file_handler.setLevel(logging.DEBUG)
            
            # File logs should not have colors
            file_formatter = ColoredFormatter(colored=False, show_timestamp=True)
            file_handler.setFormatter(file_formatter)
            
            self.logger.addHandler(file_handler)
            
        except Exception as e:
            # If file logging fails, log to console
            self.error(f"Failed to setup file logging: {e}")
    
    def add_gui_handler(self, callback: Callable[[str, int], None]) -> GUILogHandler:
        """
        Add a GUI log handler.
        
        Args:
            callback: Function to call with (message, level) for each log entry
            
        Returns:
            GUILogHandler instance
        """
        if self.gui_handler:
            self.logger.removeHandler(self.gui_handler)
        
        self.gui_handler = GUILogHandler(callback)
        self.gui_handler.setLevel(logging.DEBUG)
        gui_formatter = ColoredFormatter(colored=False, show_timestamp=True)
        self.gui_handler.setFormatter(gui_formatter)
        
        self.logger.addHandler(self.gui_handler)
        return self.gui_handler
    
    def set_level(self, level: LogLevel) -> None:
        """Set logging level."""
        self.logger.setLevel(level.value)
    
    def set_colored(self, colored: bool) -> None:
        """Enable or disable colored output."""
        self.colored = colored
        
        # Update console handler formatter
        for handler in self.logger.handlers:
            if isinstance(handler, logging.StreamHandler) and handler.stream == sys.stdout:
                handler.setFormatter(ColoredFormatter(colored=colored, show_timestamp=True))
    
    # Main logging functions
    
    def log(self, message: str) -> None:
        """
        Main log function with timestamp.
        
        Args:
            message: Message to log
        """
        self.logger.info(message)
    
    def error(self, message: str) -> None:
        """
        Error logging function.
        
        Args:
            message: Error message to log
        """
        self.logger.log(LogLevel.ERROR.value, message)
    
    def warn(self, message: str) -> None:
        """
        Warning logging function.
        
        Args:
            message: Warning message to log
        """
        self.logger.log(LogLevel.WARNING.value, message)
    
    def warning(self, message: str) -> None:
        """
        Warning logging function (alias for warn()).
        
        Args:
            message: Warning message to log
        """
        self.warn(message)
    
    def info(self, message: str) -> None:
        """
        Info logging function.
        
        Args:
            message: Info message to log
        """
        self.logger.log(LogLevel.INFO.value, message)
    
    def highlight(self, message: str) -> None:
        """
        Highlight/sync logging function.
        
        Args:
            message: Highlight message to log
        """
        self.logger.log(LogLevel.HIGHLIGHT.value, message)
    
    def debug(self, message: str) -> None:
        """
        Debug logging function.
        
        Args:
            message: Debug message to log
        """
        self.logger.debug(message)
    
    # Convenience methods for formatted output
    
    def log_separator(self, char: str = "=", length: int = 70) -> None:
        """Log a separator line."""
        self.highlight(char * length)
    
    def log_header(self, title: str, char: str = "=") -> None:
        """Log a header with title."""
        self.log_separator(char)
        centered_title = f" {title} ".center(70, char)
        self.highlight(centered_title)
        self.log_separator(char)
    
    def log_sync_status(self, operation: str, status: str, details: str = "") -> None:
        """Log sync operation status."""
        status_msg = f"Sync {operation}: {status}"
        if details:
            status_msg += f" - {details}"
        self.highlight(status_msg)
    
    def log_progress(self, current: int, total: int, message: str = "") -> None:
        """Log progress information."""
        percentage = (current / total * 100) if total > 0 else 0
        progress_msg = f"Progress: {current}/{total} ({percentage:.1f}%)"
        if message:
            progress_msg += f" - {message}"
        self.info(progress_msg)
    
    def log_dict(self, data: Dict[str, Any], title: str = "Information") -> None:
        """Log dictionary data in a formatted way."""
        self.info(f"{title}:")
        for key, value in data.items():
            self.info(f"  {key}: {value}")
    
    # Context manager support for section logging
    
    def section(self, title: str, char: str = "-"):
        """Context manager for logging sections."""
        return LogSection(self, title, char)


class LogSection:
    """Context manager for logging sections with headers and footers."""
    
    def __init__(self, logger: ReadmarkableLogger, title: str, char: str = "-"):
        self.logger = logger
        self.title = title
        self.char = char
        self.start_time = None
    
    def __enter__(self):
        self.start_time = datetime.now()
        self.logger.log_header(self.title, self.char)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time:
            duration = datetime.now() - self.start_time
            self.logger.info(f"Section '{self.title}' completed in {duration.total_seconds():.2f} seconds")
        self.logger.log_separator(self.char)


# Global logger instance
_global_logger: Optional[ReadmarkableLogger] = None


def get_logger() -> ReadmarkableLogger:
    """
    Get the global logger instance.
    
    Returns:
        Global ReadmarkableLogger instance
        
    Raises:
        RuntimeError: If logger hasn't been initialized
    """
    global _global_logger
    if _global_logger is None:
        raise RuntimeError("Logger not initialized. Call setup_logging() first.")
    return _global_logger


def setup_logging(name: str = "readmarkable",
                 colored: bool = True,
                 log_file: Optional[Path] = None,
                 level: LogLevel = LogLevel.INFO) -> ReadmarkableLogger:
    """
    Setup and configure global logging.
    
    Args:
        name: Logger name
        colored: Whether to use colored output
        log_file: Optional file to log to
        level: Logging level
        
    Returns:
        Configured ReadmarkableLogger instance
    """
    global _global_logger
    
    _global_logger = ReadmarkableLogger(name=name, colored=colored, log_file=log_file)
    _global_logger.set_level(level)
    
    return _global_logger


def configure_from_config(config: Any) -> ReadmarkableLogger:
    """
    Configure logging from application config.
    
    Args:
        config: Application configuration object
        
    Returns:
        Configured logger
    """
    colored = getattr(config.ui, 'colored_output', True) if hasattr(config, 'ui') else True
    log_level = LogLevel.DEBUG if getattr(config, 'debug_mode', False) else LogLevel.INFO
    
    log_file = None
    if hasattr(config, 'get_logs_directory'):
        log_file = config.get_logs_directory() / 'readmarkable.log'
    
    return setup_logging(
        colored=colored,
        log_file=log_file,
        level=log_level
    )


# Convenience functions for direct use

def log(message: str) -> None:
    """Log with timestamp."""
    get_logger().log(message)


def error(message: str) -> None:
    """Log error message."""
    get_logger().error(message)


def warn(message: str) -> None:
    """Log warning message."""
    get_logger().warn(message)


def info(message: str) -> None:
    """Log info message."""
    get_logger().info(message)


def highlight(message: str) -> None:
    """Log highlight message."""
    get_logger().highlight(message)


def debug(message: str) -> None:
    """Log debug message."""
    get_logger().debug(message)