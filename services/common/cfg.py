"""Configuration management module."""

import os
import yaml
from typing import Any, Dict
from pathlib import Path
from dotenv import load_dotenv


class Config:
    """Central configuration manager."""
    
    def __init__(self, config_path: str = None):
        """Initialize configuration from YAML and environment variables."""
        # Load environment variables
        load_dotenv()
        
        # Default config path
        if config_path is None:
            config_path = Path(__file__).parent.parent.parent / "configs" / "config.yaml"
        
        # Load YAML config
        with open(config_path, 'r') as f:
            self._config = yaml.safe_load(f)
        
        # Substitute environment variables
        self._config = self._substitute_env_vars(self._config)
    
    def _substitute_env_vars(self, obj: Any) -> Any:
        """Recursively substitute environment variables in config."""
        if isinstance(obj, dict):
            return {key: self._substitute_env_vars(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self._substitute_env_vars(item) for item in obj]
        elif isinstance(obj, str) and obj.startswith("${") and obj.endswith("}"):
            # Format: ${VAR_NAME} or ${VAR_NAME:-default}
            var_expr = obj[2:-1]
            if ":-" in var_expr:
                var_name, default = var_expr.split(":-", 1)
                env_value = os.getenv(var_name, default)
            else:
                var_name = var_expr
                env_value = os.getenv(var_name)
            if env_value is not None:
                # Try to convert to appropriate type
                if env_value.isdigit():
                    return int(env_value)
                elif env_value.replace('.', '', 1).isdigit():
                    return float(env_value)
                elif env_value.lower() in ('true', 'false'):
                    return env_value.lower() == 'true'
                return env_value
            return obj
        return obj
    
    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Get configuration value using dot notation.
        
        Example: config.get('database.host')
        """
        keys = key_path.split('.')
        value = self._config
        
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        
        return value
    
    def __getitem__(self, key: str) -> Any:
        """Get config section."""
        return self._config[key]
    
    def __contains__(self, key: str) -> bool:
        """Check if config section exists."""
        return key in self._config
    
    def to_dict(self) -> Dict:
        """Return full configuration as dictionary."""
        return self._config.copy()


# Global config instance
_config_instance = None


def get_config(config_path: str = None) -> Config:
    """Get or create global config instance."""
    global _config_instance
    if _config_instance is None:
        _config_instance = Config(config_path)
    return _config_instance

