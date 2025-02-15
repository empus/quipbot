"""Sleep command for QuipBot."""

from . import Command
import time

class SleepCommand(Command):
    def __init__(self, bot):
        """Initialize sleep command."""
        super().__init__(bot)
        self._name = "sleep"
        self._help = "Put the bot to sleep for a specified number of minutes"
        self._usage = "sleep <minutes>"
        
    @property
    def name(self):
        """Command name."""
        return "sleep"
        
    @property
    def help(self):
        """Command help text."""
        prefix = self.get_prefix()
        return f"Make the bot sleep for a specified time. Usage: {prefix}sleep <minutes>"
        
    @property
    def usage(self):
        """Command usage text."""
        return self._usage
        
    def execute(self, nick, channel, args):
        """Execute the sleep command."""
        if not args:
            prefix = self.get_prefix(channel)
            return f"Usage: {prefix}sleep <minutes>"

        try:
            minutes = int(args[0])
            if minutes <= 0:
                return "Sleep time must be positive"

            # Get sleep_max from config (channel-specific or global)
            sleep_max = self.bot.get_channel_config(channel, 'sleep_max', 60)
            
            if minutes > sleep_max:
                return f"Sleep time cannot exceed {sleep_max} minutes"

            channel_lower = channel.lower()
            self.bot.sleep_until[channel_lower] = time.time() + (minutes * 60)
            self.logger.info(f"Bot put to sleep in {channel} for {minutes} minutes by {nick}")
            prefix = self.get_prefix(channel)
            return f"Going to sleep for {minutes} minutes. Wake me with {prefix}wake"

        except ValueError:
            return "Sleep time must be a number" 