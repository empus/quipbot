"""Command system for QuipBot."""

from abc import ABC, abstractmethod

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

# Import all commands
from .boot import BootCommand
from .help import HelpCommand
from .kick import KickCommand
from .reload import ReloadCommand
from .say import SayCommand
from .sleep import SleepCommand
from .topic import TopicCommand
from .wake import WakeCommand

# Export all commands
__all__ = [
    'Command',
    'BootCommand',
    'HelpCommand',
    'KickCommand',
    'ReloadCommand',
    'SayCommand',
    'SleepCommand',
    'TopicCommand',
    'WakeCommand',
] 