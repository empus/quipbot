"""Variable inspection command for QuipBot."""

import pprint
from .. import commands

class VarCommand(commands.Command):
    @property
    def name(self):
        """Command name."""
        return "var"

    @property
    def help(self):
        """Command help."""
        return "Print a bot variable value to the log. Usage: var <variable> - Available: chat_history, users, channel_users, last_chat_times, last_bot_times, conversation_timers, sleep_until"

    @property
    def usage(self):
        """Command usage."""
        return "<variable>"

    def execute(self, nick, channel, args):
        """Execute the var command."""
        if not args:
            return f"Usage: {self.bot.config['cmd_prefix']}{self.usage}"

        original_name = args[0]  # Keep original name for messages
        var_name = original_name.lower()  # Lowercase for lookup
        
        # Define available variables
        variables = {
            'chat_history': lambda: self.bot.ai_client.chat_history,
            'users': lambda: self.bot.users,
            'channel_users': lambda: self.bot.channel_users,
            'last_chat_times': lambda: self.bot.last_chat_times,
            'last_bot_times': lambda: self.bot.last_bot_times,
            'conversation_timers': lambda: self.bot.conversation_timers,
            'sleep_until': lambda: self.bot.sleep_until
        }
        
        if var_name not in variables:
            return f"Error: Variable '{original_name}' not found. Available variables: {', '.join(sorted(variables.keys()))}"
            
        try:
            # Get the variable value using the lambda
            value = variables[var_name]()
            
            # Pretty print the value to log
            pp = pprint.PrettyPrinter(indent=2)
            formatted_value = pp.pformat(value)
            self.bot.logger.info(f"Variable {original_name} value:\n{formatted_value}")
            
            return f"Printed var {original_name} value to log"
            
        except Exception as e:
            return f"Error accessing variable '{original_name}': {str(e)}" 