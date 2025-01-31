"""Configuration management for QuipBot."""

import yaml
from pathlib import Path

def load_config(config_path="config.yaml"):
    """Load configuration from YAML file."""
    try:
        with open(config_path, 'r') as config_file:
            config = yaml.safe_load(config_file)
        return config
    except Exception as e:
        raise Exception(f"Failed to load configuration: {e}")

def save_config(config, config_path="config.yaml"):
    """Save configuration to YAML file."""
    try:
        with open(config_path, 'w') as config_file:
            yaml.dump(config, config_file, default_flow_style=False)
    except Exception as e:
        raise Exception(f"Failed to save configuration: {e}") 