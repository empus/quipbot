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
        # Get user info for permission checking
        user_info = self.bot.users.get(nick, {})
        userhost = user_info.get('host')
        channel_info = self.bot.channel_users.get(channel, {}).get(nick, {})
        
        if args:
            # Help for specific command
            command = args[0].lower()
            if command in self.bot.handler.commands:
                cmd = self.bot.handler.commands[command]
                # Get command config
                cmd_config = self.bot.get_channel_command_config(channel, command)
                # Check if user has permission to use this command
                if self._check_command_permission(nick, userhost, channel_info, cmd_config):
                    return (f"{self.bot.config['cmd_prefix']}{cmd.usage} - {cmd.help}", False)  # (message, add_to_history)
                else:
                    return (f"You don't have permission to use the '{command}' command.", False)
            else:
                # Silently ignore unknown commands
                return None
        
        # List all available commands
        available_commands = []
        for cmd_name, cmd in sorted(self.bot.handler.commands.items()):
            if cmd_name == 'help':  # Skip help command initially
                continue
            # Get command config
            cmd_config = self.bot.get_channel_command_config(channel, cmd_name)
            # Only include commands the user has permission to use
            if self._check_command_permission(nick, userhost, channel_info, cmd_config):
                available_commands.append(f"{cmd_name}")
        
        # Only add help command if user has access to other commands
        if available_commands:
            available_commands.append(f"help")
            return (f"Available commands: {', '.join(sorted(available_commands))} - For details, use: {self.bot.config['cmd_prefix']}help <command>", False)
        else:
            self.bot.logger.debug(f"User {nick} ({userhost}) in {channel} has no available commands")
            return None

    def _check_command_permission(self, nick, userhost, channel_info, cmd_config):
        """Check if a user has permission to use a command.
        
        Args:
            nick: User's nickname
            userhost: User's userhost
            channel_info: User's channel info dict
            cmd_config: Command configuration dict
            
        Returns:
            bool: True if user has permission, False otherwise
        """
        # Get required permission level - default to 'admin' if command not configured
        # Special case for help command which defaults to 'any'
        if not cmd_config:
            required = 'any' if self.name == 'help' else 'admin'
        else:
            required = cmd_config.get('requires', 'any').lower()
        
        # Check if user is admin (admins can use any command)
        if userhost and self.bot.permissions.is_admin(nick, userhost):
            return True
            
        # Check if nick matches an admin nick exactly (for cases where we don't have userhost)
        if nick in self.bot.config.get('admins', []):
            return True
            
        # Handle different permission levels
        if required == 'admin':
            return False
            
        elif required == 'op':
            return channel_info.get('op', False)
            
        elif required == 'voice':
            return channel_info.get('voice', False) or channel_info.get('op', False)
            
        # 'any' permission level always returns True
        return True 