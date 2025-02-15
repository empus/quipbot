"""Command system for QuipBot."""

from abc import ABC, abstractmethod
import os
import importlib
import inspect
import logging
from typing import Dict, Type
from pathlib import Path

logger = logging.getLogger('QuipBot')

class Command(ABC):
    def __init__(self, bot):
        """Initialize command with bot instance."""
        self.bot = bot

    @abstractmethod
    def execute(self, nick, channel, args):
        """Execute the command."""
        pass

    @property
    @abstractmethod
    def name(self):
        """Command name."""
        pass

    @property
    @abstractmethod
    def help(self):
        """Command help text."""
        pass

    @property
    def usage(self):
        """Command usage text."""
        return self.name

def load_commands() -> Dict[str, Type[Command]]:
    """Dynamically load all command classes.
    
    Returns:
        Dict mapping command names to command classes
    """
    commands = {}
    commands_dir = Path(__file__).parent
    
    # Load each .py file in the commands directory
    for file in commands_dir.glob('*.py'):
        if file.name == '__init__.py':
            continue
            
        try:
            # Import the module dynamically
            module_name = f"quipbot.commands.{file.stem}"
            module = importlib.import_module(module_name)
            
            # Find Command subclasses in the module
            for name, obj in inspect.getmembers(module, inspect.isclass):
                # Check if class is a Command subclass by checking its bases
                is_command = False
                for base in obj.__mro__[1:]:  # Skip the class itself
                    if base.__name__ == 'Command' and base.__module__ == 'quipbot.commands':
                        is_command = True
                        break
                
                if (is_command and 
                    obj.__module__ == module.__name__):  # Only get commands defined in this module
                    
                    try:
                        # Create temporary instance to get command name
                        cmd_instance = obj(None)
                        cmd_name = cmd_instance.name
                        commands[cmd_name] = obj
                    except Exception as e:
                        logger.error(f"Error initializing command {name}: {e}", exc_info=True)
                    
        except Exception as e:
            logger.error(f"Error loading command module {file.name}: {e}", exc_info=True)
            
    return commands

# Export only the essential components
__all__ = ['Command', 'load_commands'] 