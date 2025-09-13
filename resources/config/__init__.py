"""
Configuration module for readmarkable.

Provides application configuration management and settings.
"""

from .settings import AppConfig, init_config, get_config

__all__ = ['AppConfig', 'init_config', 'get_config']