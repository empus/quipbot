"""Reload command for QuipBot."""

from . import Command

class ReloadCommand(Command):
    @property
    def name(self):
        return "reload"

    @property
    def help(self):
        prefix = self.bot.config.get('cmd_prefix', '!')
        return f"Reload the bot configuration. Usage: {prefix}reload"

    def execute(self, nick, channel, args):
        """Execute the reload command."""
        if self.bot.reload_config():
            return "Configuration reloaded successfully."
        return "Failed to reload configuration." 