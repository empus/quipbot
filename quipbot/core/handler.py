"""Message handler for QuipBot."""

import logging
import re
from pathlib import Path
import pkgutil
import importlib
from .. import commands
import time

class MessageHandler:
    def __init__(self, bot):
        """Initialize message handler."""
        self.bot = bot
        self.logger = self.bot.logger
        self.commands = {}
        self._load_commands()

    def _load_commands(self):
        """Load all command modules."""
        commands_path = Path(__file__).parent.parent / 'commands'
        self.logger.debug(f"Loading commands from: {commands_path}")
        
        for _, name, _ in pkgutil.iter_modules([str(commands_path)]):
            if name != '__init__':
                try:
                    self.logger.debug(f"Attempting to load command module: {name}")
                    module = importlib.import_module(f'..commands.{name}', package=__package__)
                    
                    # Find the command class (should be the only class that inherits from Command)
                    command_class_found = False
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if isinstance(attr, type) and issubclass(attr, commands.Command) and attr != commands.Command:
                            cmd = attr(self.bot)
                            self.commands[cmd.name] = cmd
                            command_class_found = True
                            self.logger.debug(f"Loaded command: {cmd.name}")
                            
                    if not command_class_found:
                        self.logger.warning(f"No command class found in module: {name}")
                        
                except Exception as e:
                    self.logger.error(f"Failed to load command {name}: {e}")
                    
        self.logger.info(f"Loaded commands: {', '.join(sorted(self.commands.keys()))}")

    def handle_line(self, line):
        """Handle a line from the IRC server."""
        self.logger.debug(f"<<< {line}")

        if line.startswith('PING'):
            self.bot.send_raw(f"PONG {line[5:]}")
            return

        if ' ' not in line:
            return

        # Parse IRC message
        if line[0] == ':':
            prefix, command, *params = line[1:].split(' ', 2)
            nick, userhost = self._parse_prefix(prefix)
            
            # Store/update user info when we see them
            if nick and userhost and nick != self.bot.nick:
                if nick not in self.bot.users:
                    self.bot.users[nick] = {'host': userhost}
                elif not self.bot.users[nick].get('host'):
                    self.bot.users[nick]['host'] = userhost
        else:
            prefix = ''
            nick = ''
            userhost = ''
            command, *params = line.split(' ', 1)

        params = ' '.join(params).lstrip(':')

        # Handle numeric responses
        if command.isdigit():
            numeric_handler = getattr(self, f'handle_{command}', None)
            if numeric_handler:
                self.logger.debug(f"Handling numeric {command} with handler")
                numeric_handler(nick, userhost, params)
            else:
                self.bot.handle_numeric(command, params)
            return

        # Handle different commands
        if command == "CAP":
            self.bot.handle_cap(params)
            return
        elif command == "AUTHENTICATE":
            self.bot.handle_authenticate(params)
            return

        handler = getattr(self, f'handle_{command.lower()}', None)
        if handler:
            handler(nick, userhost, params)

    def handle_privmsg(self, nick, userhost, params):
        """Handle PRIVMSG command."""
        if ' :' not in params:
            return

        target, message = params.split(' :', 1)
        
        # Handle channel messages
        if target.startswith('#'):
            # Skip if we're not in the channel
            if not self.bot.is_in_channel(target):
                return
                
            # Process the message through the bot's handler
            self.bot.handle_channel_message(nick, userhost, target, message)
            
        else:
            # Handle private messages
            self.bot.handle_private_message(nick, userhost, message)

    def handle_join(self, nick, userhost, params):
        """Handle JOIN command."""
        channel = params.lstrip(':')
        if nick.lower() == self.bot.current_nick.lower():
            self.logger.debug(f"Bot joining {channel}")
            # Clear and rebuild channel users list
            self.bot.channel_users[channel] = {}
            # Add ourselves to the channel user list with current nickname
            self.bot.channel_users[channel][self.bot.current_nick] = {
                'op': False,
                'voice': False,
                'account': None,
                'host': None
            }
            self.logger.info(f"Joined channel: {channel} (as {self.bot.current_nick})")
            
            # Initialize timers for this channel
            self.bot.last_chat_times[channel] = time.time()
            self.bot.last_action_times[channel] = time.time()
            
            # Server will automatically send NAMES list after JOIN
            # handle_366 (end of NAMES) will trigger the WHO request
            
            # Generate and send entrance message if enabled
            if self.bot.config.get('ai_entrance', False):
                self.logger.debug(f"Generating entrance message for {channel}")
                entrance_prompt = self.bot.config.get('ai_prompt_entrance', 'Generate a channel entrance message')
                entrance_msg = self.bot.ai_client.get_response(
                    entrance_prompt,
                    self.bot.current_nick,
                    channel=channel,
                    add_to_history=True
                )
                if entrance_msg:
                    self.bot.send_channel_message(channel, entrance_msg)
                else:
                    self.logger.debug(f"Failed to generate entrance message for {channel}")
        else:
            self.logger.debug(f"User {nick} joining {channel}")
            if channel in self.bot.channel_users:
                self.bot.channel_users[channel][nick] = {
                    'op': False,
                    'voice': False,
                    'account': None,
                    'host': userhost
                }
                # Request WHOX info just for this user
                # %tnuhiraf gives us: channel, nick, user, host, ip, realname, account, flags
                self.bot.send_raw(f"WHO {nick} %tnuhiraf")
                self.logger.debug(f"Added {nick} to {channel} users: {', '.join(sorted(self.bot.channel_users[channel].keys()))}")
        
        # Track user info
        if nick not in self.bot.users:
            self.bot.users[nick] = {'host': userhost}
        elif not self.bot.users[nick].get('host'):
            self.bot.users[nick]['host'] = userhost

    def handle_part(self, nick, userhost, params):
        """Handle PART command."""
        channel = params.split()[0]
        if nick.lower() == self.bot.current_nick.lower():
            if channel in self.bot.channel_users:
                del self.bot.channel_users[channel]
                self.logger.info(f"Left channel: {channel}")
        else:
            if channel in self.bot.channel_users and nick in self.bot.channel_users[channel]:
                del self.bot.channel_users[channel][nick]
                self.logger.debug(f"User {nick} left {channel}")

    def handle_quit(self, nick, userhost, params):
        """Handle QUIT command."""
        # Remove user from all channels they were in
        for channel, users in self.bot.channel_users.items():
            if nick in users:
                del users[nick]
                self.logger.debug(f"Removed quit user {nick} from {channel}")
        
        # Remove from global users list
        if nick in self.bot.users:
            del self.bot.users[nick]
            self.logger.debug(f"User {nick} quit")

    def handle_nick(self, nick, userhost, params):
        """Handle NICK command."""
        new_nick = params.lstrip(':')
        
        # Update user in all channels they're in
        for channel, users in self.bot.channel_users.items():
            if nick in users:
                # Preserve user data when changing nick
                users[new_nick] = users.pop(nick)
                self.logger.debug(f"Updated nick {nick} to {new_nick} in {channel}")
        
        # Update global users list
        if nick in self.bot.users:
            self.bot.users[new_nick] = self.bot.users.pop(nick)
            self.logger.debug(f"User {nick} changed nick to {new_nick}")

    def handle_mode(self, nick, userhost, params):
        """Handle MODE command."""
        parts = params.split()
        if len(parts) < 2:
            return
            
        channel = parts[0]
        if channel not in self.bot.channel_users:
            return

        modes = parts[1]
        mode_params = parts[2:]
        adding = True
        param_index = 0

        for mode in modes:
            if mode == '+':
                adding = True
            elif mode == '-':
                adding = False
            elif mode in 'ov':  # op and voice modes
                if param_index < len(mode_params):
                    target = mode_params[param_index]
                    if target in self.bot.channel_users[channel]:
                        if mode == 'o':
                            self.bot.channel_users[channel][target]['op'] = adding
                            self.logger.debug(f"User {target} {'given' if adding else 'removed from'} op in {channel}")
                        elif mode == 'v':
                            self.bot.channel_users[channel][target]['voice'] = adding
                            self.logger.debug(f"User {target} {'given' if adding else 'removed from'} voice in {channel}")
                    param_index += 1

    def handle_353(self, nick, userhost, params):
        """Handle NAMES list (353 response)."""
        parts = params.split(" :", 1)
        if len(parts) > 1:
            channel = parts[0].split()[-1]
            nicks = parts[1].split()
            self.logger.debug(f"Processing NAMES response for {channel} with {len(nicks)} users: {', '.join(nicks)}")
            
            if channel not in self.bot.channel_users:
                self.bot.channel_users[channel] = {}
                self.logger.debug(f"Initializing user list for {channel}")
            
            for n in nicks:
                prefix = ''
                while n and n[0] in '@+%~&!':
                    prefix += n[0]
                    n = n[1:]
                if n:  # Only add if we have a nickname after stripping prefixes
                    self.bot.channel_users[channel][n] = {
                        'op': '@' in prefix,
                        'voice': '+' in prefix,
                        'account': None,
                        'host': None
                    }
                    self.logger.debug(f"NAMES: Added user {n} to {channel} with prefix '{prefix}', data: {self.bot.channel_users[channel][n]}")
            
            self.logger.debug(f"NAMES complete - Users in {channel}: {', '.join(sorted(self.bot.channel_users[channel].keys()))}")

    def handle_366(self, nick, userhost, params):
        """Handle end of NAMES list."""
        # Format: <botnick> <channel> :End of /NAMES list.
        # Example: "Quip2 #qtest :End of /NAMES list."
        try:
            # Split on space, channel is the second parameter
            parts = params.split()
            if len(parts) >= 2:
                channel = parts[1]  # Channel is the second parameter
                self.logger.debug(f"End of NAMES for {channel} - Raw params: {params}")
                self.logger.debug(f"Sending WHO request to get full user info")
                # Send WHO request with WHOX format to get complete user info
                # %tnuhiraf gives us: channel, nick, user, host, ip, realname, account, flags
                self.bot.send_raw(f"WHO {channel} %tnuhiraf")
                self.logger.debug(f"Current users before WHO: {', '.join(sorted(self.bot.channel_users.get(channel, {}).keys()))}")
        except Exception as e:
            self.logger.error(f"Error processing end of NAMES: {e} - Raw params: {params}")
            return

    def handle_352(self, nick, userhost, params):
        """Handle WHO response (numeric 352)."""
        # WHO response format: <channel> <user> <host> <server> <nick> <H|G>[*][@|+] :<hopcount> <real_name>
        parts = params.split()
        if len(parts) >= 8:
            channel = parts[0]
            ident = parts[1]
            host = parts[2]
            nick = parts[4]
            status = parts[5]
            
            if channel in self.bot.channel_users:
                # Update or create user entry
                if nick not in self.bot.channel_users[channel]:
                    self.logger.debug(f"WHO: Creating new entry for {nick} in {channel}")
                    self.bot.channel_users[channel][nick] = {}
                
                # Update user info
                old_data = self.bot.channel_users[channel][nick].copy() if nick in self.bot.channel_users[channel] else {}
                self.bot.channel_users[channel][nick].update({
                    'op': '@' in status,
                    'voice': '+' in status,
                    'host': f"{ident}@{host}",
                    'account': None  # Will be updated by 354 response if account is logged in
                })
                
                self.logger.debug(f"WHO: Updated {nick} in {channel} - Old data: {old_data}, New data: {self.bot.channel_users[channel][nick]}")
                self.logger.debug(f"WHO response - Current users in {channel}: {', '.join(sorted(self.bot.channel_users[channel].keys()))}")

    def handle_354(self, nick, userhost, params):
        """Handle WHOX response (numeric 354) for account information."""
        # WHOX response format: <channel> <nick> <user> <host> <ip> <realname> <account> <flags>
        parts = params.split()
        if len(parts) >= 8:
            channel = parts[0]
            user_nick = parts[1]
            ident = parts[2]
            host = parts[3]
            account = parts[6] if parts[6] != '0' else None
            flags = parts[7]
            
            if channel in self.bot.channel_users:
                if user_nick not in self.bot.channel_users[channel]:
                    self.logger.debug(f"WHOX: Creating new entry for {user_nick} in {channel}")
                    self.bot.channel_users[channel][user_nick] = {}
                
                old_data = self.bot.channel_users[channel][user_nick].copy() if user_nick in self.bot.channel_users[channel] else {}
                self.bot.channel_users[channel][user_nick].update({
                    'op': '@' in flags or '*' in flags,
                    'voice': '+' in flags,
                    'host': f"{ident}@{host}",
                    'account': account
                })
                
                self.logger.debug(f"WHOX: Updated {user_nick} in {channel} - Old data: {old_data}, New data: {self.bot.channel_users[channel][user_nick]}")
                self.logger.debug(f"WHOX response - Current users in {channel}: {', '.join(sorted(self.bot.channel_users[channel].keys()))}")

    def handle_315(self, nick, userhost, params):
        """Handle end of WHO list."""
        # Format: <nick> <channel> :End of /WHO list
        parts = params.split()
        if len(parts) >= 1:
            channel = parts[0]
            if channel in self.bot.channel_users:
                self.logger.debug(f"WHO list complete for {channel} - Final user list: {', '.join(sorted(self.bot.channel_users[channel].keys()))}")
                self.logger.debug(f"Full channel_users data for {channel}: {self.bot.channel_users[channel]}")

    def handle_invite(self, nick, userhost, params):
        """Handle INVITE command."""
        parts = params.split()
        if len(parts) < 2:
            return
            
        target_nick = parts[0]
        invited_channel = parts[1].lstrip(':')
        
        # Only accept invites meant for us
        if target_nick.lower() != self.bot.nick.lower():
            return
            
        # Check if this is a configured channel we're not in
        configured_channels = [chan['name'].lower() for chan in self.bot.channels]
        if invited_channel.lower() in configured_channels:
            if invited_channel not in self.bot.channel_users:
                self.logger.info(f"Accepting invite to configured channel {invited_channel} from {nick}")
                # Find the channel config to get the key if any
                for chan in self.bot.channels:
                    if chan['name'].lower() == invited_channel.lower():
                        key = chan.get('key', '')
                        self.bot.send_raw(f"JOIN {invited_channel} {key}")
                        break

    def handle_kick(self, nick, userhost, params):
        """Handle KICK command."""
        parts = params.split()
        if len(parts) >= 2:
            channel = parts[0]
            kicked_nick = parts[1]
            
            if channel in self.bot.channel_users:
                if kicked_nick in self.bot.channel_users[channel]:
                    del self.bot.channel_users[channel][kicked_nick]
                    self.logger.debug(f"Removed kicked user {kicked_nick} from {channel}")
                    
                # If we were kicked, clear the channel's user list
                if kicked_nick.lower() == self.bot.current_nick.lower():
                    del self.bot.channel_users[channel]
                    self.logger.info(f"Bot was kicked from {channel}")

    def _check_command_permissions(self, nick, channel, cmd_config):
        """Check if a user has permission to use a command.
        
        Args:
            nick: The nickname trying to use the command
            channel: The channel where the command was used
            cmd_config: The command configuration dict
            
        Returns:
            bool: True if user has permission, False otherwise
        """
        # Get user info including host
        user_info = self.bot.users.get(nick, {})
        if not user_info:
            self.logger.debug(f"No user info found for {nick}")
            
        # Get channel-specific user info
        channel_info = self.bot.channel_users.get(channel, {}).get(nick, {})
        
        # Check if user is admin first - admins can use any command
        is_admin = False
        if user_info.get('host'):
            is_admin = self.bot.permissions.is_admin(nick, user_info['host'])
            if is_admin:
                return True
            
        # Check admin_only flag
        if cmd_config.get('admin_only', False):
            self.bot.send_channel_message(channel, f"Sorry {nick}, that command is for admins only.")
            return False
            
        # For non-admins, check op requirement
        if cmd_config.get('requires_op', False):
            if not channel_info.get('op', False):
                self.bot.send_channel_message(channel, f"Sorry {nick}, that command requires op status.")
                return False
                
        # For non-admins, check voice requirement (ops can also use voice-required commands)
        if cmd_config.get('requires_voice', False):
            if not (channel_info.get('voice', False) or channel_info.get('op', False)):
                self.bot.send_channel_message(channel, f"Sorry {nick}, that command requires voice or op status.")
                return False
                
        return True

    def _handle_command(self, command, nick, channel, args):
        """Handle a command."""
        # Get command config
        cmd_config = self.bot.get_channel_command_config(channel, command)
        
        # Check permissions
        if not self._check_command_permissions(nick, channel, cmd_config):
            return
            
        # Handle commands
        if command in self.commands:
            response = self.commands[command].execute(nick, channel, args)
            if response:
                self.bot.send_channel_message(channel, response)
        else:
            self.bot.send_channel_message(channel, f"Unknown command: {command}")

    def _parse_prefix(self, prefix):
        """Parse IRC prefix into nick and userhost."""
        if "!" in prefix and "@" in prefix:
            nick, userhost = prefix.split("!", 1)
            return nick, userhost
        return prefix, "" 