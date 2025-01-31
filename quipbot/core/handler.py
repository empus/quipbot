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
        for _, name, _ in pkgutil.iter_modules([str(commands_path)]):
            if name != '__init__':
                try:
                    module = importlib.import_module(f'..commands.{name}', package=__package__)
                    # Find the command class (should be the only class that inherits from Command)
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if isinstance(attr, type) and issubclass(attr, commands.Command) and attr != commands.Command:
                            cmd = attr(self.bot)
                            self.commands[cmd.name] = cmd
                            self.logger.debug(f"Loaded command: {cmd.name}")
                except Exception as e:
                    self.logger.error(f"Failed to load command {name}: {e}")

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
        if nick == self.bot.nick:
            self.bot.channel_users[channel] = {}
            self.logger.info(f"Joined channel: {channel}")
            
            # Initialize timers for this channel
            self.bot.last_chat_times[channel] = time.time()
            self.bot.last_action_times[channel] = time.time()
            
            # Generate and send entrance message if enabled
            if self.bot.config.get('ai_entrance', False):
                self.logger.debug(f"Generating entrance message for {channel}")
                entrance_prompt = self.bot.config.get('ai_prompt_entrance', 'Generate a channel entrance message')
                entrance_msg = self.bot.ai_client.get_response(
                    entrance_prompt,
                    self.bot.nick,
                    channel=channel,
                    add_to_history=True  # Add to history so we know we were last speaker
                )
                if entrance_msg:
                    self.bot.send_channel_message(channel, entrance_msg)
                else:
                    self.logger.debug(f"Failed to generate entrance message for {channel}")
        else:
            if channel in self.bot.channel_users:
                self.bot.channel_users[channel][nick] = {
                    'op': False,
                    'voice': False
                }
                self.logger.debug(f"User {nick} joined {channel}")
                
        # Track user info
        if nick not in self.bot.users:
            self.bot.users[nick] = {'host': userhost}
        elif not self.bot.users[nick].get('host'):
            self.bot.users[nick]['host'] = userhost

    def handle_part(self, nick, userhost, params):
        """Handle PART command."""
        channel = params.split()[0]
        if nick == self.bot.nick:
            if channel in self.bot.channel_users:
                del self.bot.channel_users[channel]
                self.logger.info(f"Left channel: {channel}")
        else:
            if channel in self.bot.channel_users and nick in self.bot.channel_users[channel]:
                del self.bot.channel_users[channel][nick]
                self.logger.debug(f"User {nick} left {channel}")

    def handle_quit(self, nick, userhost, params):
        """Handle QUIT command."""
        if nick in self.bot.users:
            del self.bot.users[nick]
        for channel in self.bot.channel_users.values():
            if nick in channel:
                del channel[nick]
        self.logger.debug(f"User {nick} quit")

    def handle_nick(self, nick, userhost, params):
        """Handle NICK command."""
        new_nick = params.lstrip(':')
        if nick in self.bot.users:
            self.bot.users[new_nick] = self.bot.users.pop(nick)
        for channel in self.bot.channel_users.values():
            if nick in channel:
                channel[new_nick] = channel.pop(nick)
        self.logger.debug(f"User {nick} changed nick to {new_nick}")

    def handle_mode(self, nick, userhost, params):
        """Handle MODE command."""
        parts = params.split()
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
            if channel not in self.bot.channel_users:
                self.bot.channel_users[channel] = {}
            for n in nicks:
                prefix = ''
                while n[0] in '@+%~&!':
                    prefix += n[0]
                    n = n[1:]
                self.bot.channel_users[channel][n] = {
                    'op': '@' in prefix,
                    'voice': '+' in prefix
                }

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

    def _handle_command(self, command_name, nick, channel, args):
        """Handle a bot command."""
        command = self.commands.get(command_name)
        if not command:
            return

        # Get user info including host
        user_info = self.bot.users.get(nick, {})
        if not user_info:
            self.logger.debug(f"No user info found for {nick}")
            return
            
        self.logger.debug(f"Checking permissions for {nick} with host {user_info.get('host', 'None')}")

        # Get channel-specific user info
        channel_info = self.bot.channel_users.get(channel, {}).get(nick, {})

        # Check permissions with full user info
        if not self.bot.permissions.has_permission(
            command_name, 
            nick,
            user_info,
            channel_info,
            channel
        ):
            self.bot.send_raw(f"NOTICE {nick} :You don't have permission to use that command.")
            self.logger.warning(f"User {nick} attempted to use command {command_name} without permission")
            return

        self.logger.debug(f"Command {command_name} authorized for {nick} in {channel}")
        response = command.execute(nick, channel, args)
        if response:
            self.bot.send_channel_message(channel, response)

    def _parse_prefix(self, prefix):
        """Parse IRC prefix into nick and userhost."""
        if "!" in prefix and "@" in prefix:
            nick, userhost = prefix.split("!", 1)
            return nick, userhost
        return prefix, "" 