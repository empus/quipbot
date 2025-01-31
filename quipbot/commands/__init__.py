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