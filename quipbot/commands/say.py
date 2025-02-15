"""Say command for QuipBot."""

from . import Command

class SayCommand(Command):
    @property
    def name(self):
        return "say"

    @property
    def help(self):
        # Get prefix from channel if available, otherwise use global
        prefix = self.bot.get_channel_config(self.bot.channel if hasattr(self.bot, 'channel') else None, 'cmd_prefix', '!')
        return f"Make the bot say something. Usage: {prefix}say <message>"

    def execute(self, nick, channel, args):
        """Execute the say command."""
        if not args:
            prefix = self.bot.get_channel_config(channel, 'cmd_prefix', '!')
            return f"Usage: {prefix}say <message>"
            
        message = " ".join(args)
        return message 