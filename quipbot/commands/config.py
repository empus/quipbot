"""Configuration inspection command for QuipBot."""

import pprint
from .. import commands

class ConfigCommand(commands.Command):
    @property
    def name(self):
        """Command name."""
        return "config"

    @property
    def help(self):
        """Command help."""
        return "Print a configuration variable value to the log. Usage: config <variable>"

    @property
    def usage(self):
        """Command usage."""
        return "<variable>"

    def execute(self, nick, channel, args):
        """Execute the config command."""
        if not args:
            return f"Usage: {self.bot.config['cmd_prefix']}{self.usage}"

        var_name = args[0]
        
        # Try to get the variable from config
        try:
            # Split on dots for nested access
            parts = var_name.split('.')
            value = self.bot.config
            for part in parts:
                value = value[part]
                
            # Pretty print the value to log
            pp = pprint.PrettyPrinter(indent=2)
            formatted_value = pp.pformat(value)
            self.bot.logger.info(f"Config variable {var_name} value:\n{formatted_value}")
            
            return f"Printed config {var_name} value to log"
            
        except (KeyError, TypeError):
            return f"Error: Config variable '{var_name}' not found" 