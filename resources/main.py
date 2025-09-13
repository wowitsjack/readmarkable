"""
Main entry point for readMarkable GUI application.

This module initializes the configuration, logging, and launches the main GUI
for markdown synchronization with reMarkable devices.
"""

import sys
import os
import argparse
from pathlib import Path
from typing import Optional

# Add the project root to the Python path
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Import application modules
from config.settings import init_config, get_config, AppConfig
from utils.logger import setup_logging, get_logger
from services.network_service import init_network_service
from models.device import Device


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="readMarkable - Markdown sync for reMarkable devices",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                    # Launch GUI
  python main.py --debug           # Launch with debug logging
  python main.py --config custom.json  # Use custom config file
        """
    )
    
    parser.add_argument(
        "--config",
        type=str,
        help="Path to configuration file"
    )
    
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )
    
    parser.add_argument(
        "--no-gui",
        action="store_true",
        help="Run without GUI (command line mode - future feature)"
    )
    
    parser.add_argument(
        "--classic",
        action="store_true",
        help="Use classic GUI interface instead of drag-and-drop"
    )
    
    parser.add_argument(
        "--device-ip",
        type=str,
        help="reMarkable device IP address"
    )
    
    parser.add_argument(
        "--device-password",
        type=str,
        help="reMarkable device SSH password"
    )
    
    parser.add_argument(
        "--sync-dir",
        type=str,
        help="Local directory to sync markdown files from"
    )
    
    parser.add_argument(
        "--version",
        action="version",
        version="readMarkable 1.2.0"
    )
    
    return parser.parse_args()


def setup_application(args: argparse.Namespace) -> AppConfig:
    """
    Setup application configuration and logging.
    
    Args:
        args: Parsed command line arguments
        
    Returns:
        Initialized application configuration
    """
    # Initialize configuration
    try:
        config = init_config(args.config)
    except Exception as e:
        print(f"Error loading configuration: {e}")
        print("Using default configuration")
        config = AppConfig()
    
    # Override config with command line arguments
    if args.debug:
        config.debug_mode = True
        config.log_level = config.log_level.__class__.DEBUG
    
    if args.device_ip:
        config.device.ip_address = args.device_ip
    
    if args.device_password:
        config.device.ssh_password = args.device_password
    
    if args.sync_dir:
        config.sync.local_sync_dir = args.sync_dir
    
    # Setup logging
    log_file = config.get_logs_directory() / "readMarkable.log"
    setup_logging(
        colored=True,
        log_file=log_file,
        level=config.log_level
    )
    
    logger = get_logger()
    logger.log("Starting readMarkable application")
    logger.info(f"Configuration loaded from: {config.get_config_file_path()}")
    logger.info(f"Log file: {log_file}")
    
    if config.debug_mode:
        logger.debug("Debug mode enabled")
    
    return config


def initialize_services(config: AppConfig) -> None:
    """
    Initialize application services.
    
    Args:
        config: Application configuration
    """
    logger = get_logger()
    
    # Initialize network service
    try:
        init_network_service(
            connection_timeout=config.network.connection_timeout,
            max_retries=config.network.max_connection_attempts,
            retry_delay=config.network.retry_delay,
            keepalive_interval=config.network.keepalive_interval
        )
        logger.info("Network service initialized")
    except Exception as e:
        logger.error(f"Failed to initialize network service: {e}")
        raise


def launch_gui(config: AppConfig, use_classic: bool = False) -> int:
    """
    Launch the GUI application.
    
    Args:
        config: Application configuration
        use_classic: Not used anymore - kept for compatibility
        
    Returns:
        Exit code
    """
    logger = get_logger()
    
    try:
        # Launch the enhanced Kivy GUI
        try:
            from gui.kivy_app import main as run_kivy_app
            
            logger.info("Launching Kivy GUI interface")
            run_kivy_app()
            logger.info("Kivy GUI application closed")
            return 0
            
        except ImportError as e:
            logger.error(f"Kivy GUI not available: {e}")
            logger.error("Please install GUI dependencies: pip install kivy kivymd plyer")
            return 1
        
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
        return 0
    except Exception as e:
        logger.error(f"GUI application error: {e}")
        return 1


def run_cli_mode(config: AppConfig) -> int:
    """
    Run in command line mode (future feature).
    
    Args:
        config: Application configuration
        
    Returns:
        Exit code
    """
    logger = get_logger()
    logger.error("Command line mode not yet implemented")
    logger.info("Please run without --no-gui flag to use the GUI")
    return 1


def main() -> int:
    """
    Main application entry point.
    
    Returns:
        Exit code
    """
    try:
        # Parse command line arguments
        args = parse_arguments()
        
        # Setup application
        config = setup_application(args)
        
        # Initialize services
        initialize_services(config)
        
        # Launch appropriate interface
        if args.no_gui:
            return run_cli_mode(config)
        else:
            return launch_gui(config, use_classic=args.classic)
            
    except KeyboardInterrupt:
        print("\nApplication interrupted by user")
        return 0
    except Exception as e:
        print(f"Fatal error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())