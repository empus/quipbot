"""Rehash command for QuipBot - reloads configuration file only."""

from . import Command
import yaml

class RehashCommand(Command):
    @property
    def name(self):
        return "rehash"

    @property
    def help(self):
        prefix = self.bot.config.get('cmd_prefix', '!')
        return f"Reload the bot configuration file only. Usage: {prefix}rehash"

    def execute(self, nick, channel, args):
        """Execute the rehash command."""
        try:
            # Reload configuration
            with open(self.bot.config_file, 'r') as f:
                new_config = yaml.safe_load(f)
                
            # Update configuration
            self.bot.update_config(new_config)
            
            self.bot.logger.info(f"Successfully reloaded configuration from {self.bot.config_file}")
            return "Configuration reloaded successfully."
            
        except Exception as e:
            self.bot.logger.error(f"Error reloading config: {e}")
            return "Failed to reload configuration." 