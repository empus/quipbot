"""Help command for QuipBot."""

from . import Command

class HelpCommand(Command):
    @property
    def name(self):
        return "help"

    @property
    def help(self):
        prefix = self.bot.config.get('cmd_prefix', '!')
        return f"Show available commands and their usage. Usage: {prefix}help [command]"

    def execute(self, nick, channel, args):
        """Execute the help command."""
        prefix = self.bot.config.get('cmd_prefix', '!')
        if not args:
            # List all available commands
            commands = [cmd for cmd in self.bot.handler.commands.values()]
            command_list = ", ".join(f"{prefix}{cmd.name}" for cmd in commands)
            return f"Available commands: {command_list}"
        
        # Show help for specific command
        command_name = args[0].lower()
        command = self.bot.handler.commands.get(command_name)
        if command:
            return command.help
        return f"Unknown command: {command_name}" 