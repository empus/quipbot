"""Help command for QuipBot."""

from . import Command

class HelpCommand(Command):
    @property
    def name(self):
        """Command name."""
        return "help"

    @property
    def help(self):
        """Command help."""
        prefix = self.bot.get_channel_config(None, 'cmd_prefix', '!')
        return f"Display help for commands. Usage: {prefix}help [command]"

    @property
    def usage(self):
        """Command usage."""
        return "[command]"

    def _format_command_help(self, cmd, channel):
        """Format help text for a single command."""
        prefix = self.bot.get_channel_config(channel, 'cmd_prefix', '!')
        return f"{prefix}{cmd.usage} - {cmd.help}"

    def execute(self, nick, channel, args):
        """Execute help command."""
        try:
            # Get channel-specific prefix
            prefix = self.bot.get_channel_config(channel, 'cmd_prefix', '!')
            
            if args:
                command_name = args[0].lower()
                command = self.bot.handler.commands.get(command_name)
                if command:
                    return self._format_command_help(command, channel)
                else:
                    return f"Unknown command: {command_name}"
            else:
                # Get list of available commands for this user
                available_commands = []
                for cmd_name, cmd in self.bot.handler.commands.items():
                    # Get command config
                    cmd_config = self.bot.get_channel_command_config(channel, cmd_name)
                    # Check if user has permission to use this command
                    if self.bot.handler._check_command_permissions(nick, channel, cmd_config):
                        available_commands.append(cmd_name)
                
                return f"Available commands: {', '.join(sorted(available_commands))} - For details, use: {prefix}help <command>"
                
        except Exception as e:
            self.bot.logger.error(f"Error in help command: {e}", exc_info=True)
            return f"Error retrieving help: {e}"