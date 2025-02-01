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
        return self._name
        
    @property
    def help(self):
        """Command help text."""
        return self._help
        
    @property
    def usage(self):
        """Command usage text."""
        return self._usage
        
    def execute(self, nick, channel, args):
        """Execute the sleep command."""
        if not args:
            return f"Usage: {self.bot.config['cmd_prefix']}{self.usage}"

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
            self.bot.logger.info(f"Bot put to sleep in {channel} for {minutes} minutes by {nick}")
            return f"Going to sleep for {minutes} minutes. Wake me with {self.bot.config['cmd_prefix']}wake"

        except ValueError:
            return "Sleep time must be a number" 