"""Help command for QuipBot."""

from .. import commands

class HelpCommand(commands.Command):
    @property
    def name(self):
        """Command name."""
        return "help"

    @property
    def help(self):
        """Command help."""
        return "Show available commands. Usage: help [command]"

    @property
    def usage(self):
        """Command usage."""
        return "[command]"

    def execute(self, nick, channel, args):
        """Execute the help command."""
        if args:
            # Help for specific command
            command = args[0].lower()
            if command in self.bot.handler.commands:
                cmd = self.bot.handler.commands[command]
                return f"{self.bot.config['cmd_prefix']}{cmd.usage} - {cmd.help}"
            else:
                # Silently ignore unknown commands
                return None
        
        # List all available commands
        available_commands = []
        for cmd_name, cmd in sorted(self.bot.handler.commands.items()):
            if cmd_name == 'help':  # Skip help command initially
                continue
            available_commands.append(f"{cmd_name}")
        
        # Only add help command if user has access to other commands
        if available_commands:
            available_commands.append(f"help")
            return f"Available commands: {', '.join(sorted(available_commands))} - For details, use: {self.bot.config['cmd_prefix']}help <command>"
        else:
            self.bot.logger.debug(f"User {nick} has no available commands")
            return None