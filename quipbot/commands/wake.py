"""Wake command for QuipBot."""

from . import Command

class WakeCommand(Command):
    def __init__(self, bot):
        """Initialize wake command."""
        super().__init__(bot)
        self._name = "wake"
        self._help = "Wake the bot from sleep mode"
        self._usage = "wake"
        
    @property
    def name(self):
        """Command name."""
        return "wake"
        
    @property
    def help(self):
        """Command help text."""
        return self._help
        
    @property
    def usage(self):
        """Command usage text."""
        return self._usage
        
    def execute(self, nick, channel, args):
        """Execute the wake command."""
        channel_lower = channel.lower()
        if channel_lower in self.bot.sleep_until:
            del self.bot.sleep_until[channel_lower]
            self.bot.logger.info(f"Bot woken up in {channel} by {nick}")
            return "I'm awake! Ready to chat again."
        else:
            return "I wasn't sleeping!" 