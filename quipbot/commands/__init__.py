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
        # Only set logger if bot is provided (not None)
        self.logger = bot.logger if bot is not None else logging.getLogger('QuipBot')

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

    def get_prefix(self, channel=None):
        """Get channel-specific command prefix.
        
        Args:
            channel: Optional channel name. If None, uses global default.
            
        Returns:
            str: The command prefix for the channel
        """
        return self.bot.get_channel_config(channel, 'cmd_prefix', '!')

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
                        # Get command name from class property without instantiating
                        cmd_name = obj.name.fget(None)  # Call the property getter directly with None
                        commands[cmd_name] = obj
                        logger.debug(f"Found command: {cmd_name}")
                    except Exception as e:
                        logger.error(f"Error getting command name for {name}: {e}", exc_info=True)
                    
        except Exception as e:
            logger.error(f"Error loading command module {file.name}: {e}", exc_info=True)
            
    return commands

# Export only the essential components
__all__ = ['Command', 'load_commands'] 