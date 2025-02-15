"""Reload command for QuipBot - reloads both configuration and code modules."""

from . import Command
from ..utils.reloader import ModuleReloader
import yaml

class ReloadCommand(Command):
    @property
    def name(self):
        return "reload"

    @property
    def help(self):
        # Get prefix from channel if available, otherwise use global
        prefix = self.bot.get_channel_config(self.bot.channel if hasattr(self.bot, 'channel') else None, 'cmd_prefix', '!')
        return f"Reload both configuration and code modules. Usage: {prefix}reload"

    def execute(self, nick, channel, args):
        """Execute reload command."""
        try:
            # Preserve current state
            self.bot.logger.info("Preserving current state...")
            self.bot.reloader.preserve_state(self.bot)
            preserved_state = self.bot.reloader.preserved_state
            
            # Reload configuration first
            self.bot.logger.info("Reloading configuration...")
            if not self.bot.reload_config():
                return "Failed to reload configuration. Check logs for details."
            
            # Then reload code modules
            self.bot.logger.info("Reloading code modules...")
            if not self.bot.reloader.reload_modules(self.bot):
                return "Failed to reload code modules. Check logs for details."
            
            # Finally restore state
            self.bot.logger.info("Restoring preserved state...")
            if not self.bot.reloader.restore_state(self.bot, preserved_state):
                return "Failed to restore bot state after reload. Check logs for details."
            
            return "Successfully reloaded configuration and code modules"
            
        except Exception as e:
            self.bot.logger.error(f"Error during reload: {e}", exc_info=True)
            return f"Error during reload: {e}" 