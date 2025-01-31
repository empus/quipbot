"""Say command for QuipBot."""

from . import Command

class SayCommand(Command):
    @property
    def name(self):
        return "say"

    @property
    def help(self):
        prefix = self.bot.config.get('cmd_prefix', '!')
        return f"Make the bot say something. Usage: {prefix}say <message>"

    def execute(self, nick, channel, args):
        """Execute the say command."""
        if not args:
            prefix = self.bot.config.get('cmd_prefix', '!')
            return f"Usage: {prefix}say <message>"
            
        message = " ".join(args)
        return message 