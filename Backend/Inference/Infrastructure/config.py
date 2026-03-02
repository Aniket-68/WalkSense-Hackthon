# utils/config_loader.py

import json
import os

class Config:
    """
    Centralized configuration loader for WalkSense
    Reads from config.json and provides access to settings.
    """
    
    _config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")
    _data = {}

    @classmethod
    def load(cls):
        """Load configuration from file"""
        if not os.path.exists(cls._config_path):
            from loguru import logger
            logger.debug(f"Configuration file {cls._config_path} not found. Using defaults.")
            return

        from loguru import logger
        try:
            with open(cls._config_path, "r") as f:
                cls._data = json.load(f)
            logger.debug("Configuration loaded from config.json")
        except Exception as e:
            logger.error(f"Config Error: {e}")

    # Inference root directory (parent of Infrastructure/)
    _inference_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    @classmethod
    def get(cls, key_path, default=None):
        """
        Get a configuration value using a dot-separated path (e.g. 'vlm.url')
        """
        if not cls._data:
            cls.load()
            
        keys = key_path.split(".")
        val = cls._data
        
        try:
            for key in keys:
                val = val[key]
            return val
        except (KeyError, TypeError):
            return default

    @classmethod
    def resolve_path(cls, relative_path: str) -> str:
        """
        Resolve a relative path from config.json to an absolute path
        anchored at the Inference/ directory.
        """
        if os.path.isabs(relative_path):
            return relative_path
        return os.path.join(cls._inference_root, relative_path)

# Initialize on import
Config.load()
