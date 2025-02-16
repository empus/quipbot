"""Message handler for QuipBot."""

import logging
import re
from pathlib import Path
import pkgutil
import importlib
from .. import commands
import time
import threading
from ..commands import load_commands

logger = logging.getLogger('QuipBot')

class MessageHandler:
    def __init__(self, bot):
        """Initialize message handler."""
        self.bot = bot
        self.logger = self.bot.logger
        self.commands = {}
        self._event_bindings = {}
        
        # Bind event handlers
        self.bind_event('JOIN', self.handle_join)
        self.bind_event('PART', self.handle_part)
        self.bind_event('QUIT', self.handle_quit)
        self.bind_event('NICK', self.handle_nick)
        self.bind_event('MODE', self.handle_mode)
        self.bind_event('PRIVMSG', self.handle_privmsg)
        self.bind_event('INVITE', self.handle_invite)
        self.bind_event('KICK', self.handle_kick)
        
        # Initialize but don't start channel check thread yet
        self.channel_check_thread = None
        
        # Load commands after everything else is initialized
        self._load_commands()
        self.logger.debug("Message handler initialized")

    def _load_commands(self):
        """Load and initialize all available commands."""
        self.commands = {}  # Reset commands dict
        logger.debug("Handler: Starting command load...")
        
        try:
            # Get command classes dictionary
            command_classes = load_commands()
            if not command_classes:
                logger.error("Handler: No commands were loaded!")
                return
                
            # Initialize each command
            for cmd_name, command_class in command_classes.items():
                try:
                    command = command_class(self.bot)
                    # Verify command name matches the key
                    if command.name != cmd_name:
                        logger.warning(f"Handler: Command name mismatch: {cmd_name} != {command.name}")
                        continue
                    self.commands[cmd_name] = command
                    logger.debug(f"Handler: Successfully initialized command: {cmd_name}")
                except Exception as e:
                    logger.error(f"Handler: Error initializing command {command_class.__name__}: {e}", exc_info=True)
            
            if self.commands:
                logger.info(f"Handler: Successfully loaded {len(self.commands)} commands: {', '.join(sorted(self.commands.keys()))}")
            else:
                logger.error("Handler: No commands were initialized!")
            
        except Exception as e:
            logger.error(f"Handler: Error loading commands: {e}", exc_info=True)
            raise  # Re-raise to ensure reload failure is detected

    def bind_event(self, event, callback):
        """Bind a callback to an IRC event.
        
        Args:
            event: The IRC event (e.g., 'PRIVMSG', 'JOIN')
            callback: The function to call when the event occurs
        """
        if event not in self._event_bindings:
            self._event_bindings[event] = set()
        self._event_bindings[event].add(callback)

    def handle_line(self, line):
        """Handle a line from the IRC server."""
        self.logger.raw(f"<<< {line}")

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
                    self.bot.users[nick] = {'host': userhost, 'account': None}
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
            # Get the full params including the target
            if params.startswith(':'):
                params = params[1:]
            
            numeric_handler = getattr(self, f'handle_{command}', None)
            if numeric_handler:
                # self.logger.debug(f"Handling numeric {command} with handler: {params}")
                try:
                    numeric_handler(nick, userhost, params)
                except Exception as e:
                    self.logger.error(f"Error in numeric handler {command}: {e}")
            else:
                # Try standard numeric handlers for specific numerics we care about
                if command in ('353', '366', '352', '354', '315'):
                    handler_name = f'handle_{command}'
                    if hasattr(self, handler_name):
                        try:
                            self.logger.debug(f"Found handler for {command}, calling {handler_name}")
                            getattr(self, handler_name)(nick, userhost, params)
                            return
                        except Exception as e:
                            self.logger.error(f"Error in numeric handler {handler_name}: {e}")
                # Fall back to generic numeric handler
                self.bot.handle_numeric(command, params)
            return

        # Handle different commands
        if command == "CAP":
            self.bot.handle_cap(params)
            return
        elif command == "AUTHENTICATE":
            self.bot.handle_authenticate(params)
            return

        # Trigger any registered event callbacks
        if command in self._event_bindings:
            for callback in self._event_bindings[command]:
                try:
                    callback(nick, userhost, params)
                except Exception as e:
                    logger.error(f"Error in event callback for {command}: {e}")

    def handle_privmsg(self, nick, userhost, params):
        """Handle PRIVMSG command."""
        if ' :' not in params:
            return

        target, message = params.split(' :', 1)
        
        # Handle CTCP requests
        if message.startswith('\x01'):
            return self.handle_ctcp(nick, userhost, message)
        
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
                'voice': False
            }
            self.logger.info(f"Joined channel: {channel} (as {self.bot.current_nick})")
            
            # Initialize timers for this channel
            self.bot.last_chat_times[channel.lower()] = time.time()
            self.bot.last_action_times[channel.lower()] = time.time()
            
            # Server will automatically send NAMES list after JOIN
            # handle_366 (end of NAMES) will trigger the WHO request
            
            # Generate and send entrance message if enabled
            if self.bot.get_channel_config(channel, 'ai_entrance', False):
                self.logger.debug(f"Generating entrance message for {channel}")
                entrance_prompt = self.bot.get_channel_config(channel, 'ai_prompt_entrance', 'Generate a channel entrance message')
                entrance_msg = self.bot.ai_client.get_response(
                    entrance_prompt,
                    self.bot.current_nick,
                    channel=channel,
                    add_to_history=True  # Add entrance message to history
                )
                if entrance_msg:
                    # Format the entrance message to remove encapsulating quotes
                    formatted_entrance = self.bot.format_message(entrance_msg)
                    self.bot.send_channel_message(channel, formatted_entrance, add_to_history=True)  # Add to history
                    self.logger.info(f"Sent entrance message to {channel}: {formatted_entrance}")
                else:
                    self.logger.debug(f"Failed to generate entrance message for {channel}")
        else:
            self.logger.info(f"User {nick} joined {channel}")
            if channel in self.bot.channel_users:
                self.bot.channel_users[channel][nick] = {
                    'op': False,
                    'voice': False
                }
                # Request WHOX info just for this user
                # %tnuhiraf gives us: channel, nick, user, host, ip, realname, account, flags
                self.bot.send_raw(f"WHO {nick} %tnuhiraf")
                self.logger.debug(f"Added {nick} to {channel} users")
        
        # Track user info from JOIN
        if userhost and "!" in userhost and "@" in userhost:
            ident, host = userhost.split("@", 1)
            if nick not in self.bot.users:
                self.bot.users[nick] = {
                    'ident': ident,
                    'host': host,
                    'ip': None,
                    'account': None,
                    'realname': None,  # Will be updated by WHO/WHOX response
                    'away': False,     # Assume not away until WHO/WHOX updates
                    'oper': False      # Assume not oper until WHO/WHOX updates
                }
            elif not self.bot.users[nick].get('host'):
                self.bot.users[nick].update({
                    'ident': ident,
                    'host': host
                })

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
                self.logger.info(f"User {nick} left {channel}")

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
            self.logger.info(f"User {nick} quit")

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
            # Preserve all user data including new fields
            self.bot.users[new_nick] = self.bot.users.pop(nick)
            self.logger.debug(f"User {nick} changed nick to {new_nick} - Data: {self.bot.users[new_nick]}")

        self.logger.info(f"User {nick} changed nick to {new_nick}")

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
                            self.logger.info(f"User {target} {'given' if adding else 'removed from'} op in {channel}")
                        elif mode == 'v':
                            self.bot.channel_users[channel][target]['voice'] = adding
                            self.logger.info(f"User {target} {'given' if adding else 'removed from'} voice in {channel}")
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
                        'voice': '+' in prefix
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
                self.logger.debug(f"End of NAMES for {channel}")
                self.logger.debug(f"Sending WHO request to get full user info")
                # Send WHO request with WHOX format to get complete user info
                # %tnuhiraf gives us: channel, nick, user, host, ip, realname, account, flags
                self.bot.send_raw(f"WHO {channel} %tnuhiraf")
                self.logger.debug(f"Current users before WHO: {', '.join(sorted(self.bot.channel_users.get(channel, {}).keys()))}")
        except Exception as e:
            self.logger.error(f"Error processing end of NAMES: {e}")
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
            
            # Get realname (everything after the :)
            realname = ' '.join(parts[7:]).lstrip(':')
            
            # Parse status flags
            away = 'G' in status  # G = Gone/Away, H = Here
            oper = '*' in status  # * indicates server operator
            
            if channel in self.bot.channel_users:
                # Update or create user entry
                if nick not in self.bot.channel_users[channel]:
                    self.logger.debug(f"WHO: Creating new entry for {nick} in {channel}")
                    self.bot.channel_users[channel][nick] = {}
                
                # Update user info
                old_data = self.bot.channel_users[channel][nick].copy() if nick in self.bot.channel_users[channel] else {}
                self.bot.channel_users[channel][nick].update({
                    'op': '@' in status,
                    'voice': '+' in status
                })
                
                # Update global user info
                if nick not in self.bot.users:
                    self.bot.users[nick] = {
                        'ident': ident,
                        'host': host,
                        'ip': None,  # Standard WHO doesn't provide IP
                        'account': None,
                        'realname': realname,
                        'away': away,
                        'oper': oper
                    }
                else:
                    self.bot.users[nick].update({
                        'ident': ident,
                        'host': host,
                        'realname': realname,
                        'away': away,
                        'oper': oper
                    })
                
                self.logger.debug(f"WHO: Updated {nick} in {channel} - Old data: {old_data}, New data: {self.bot.channel_users[channel][nick]}")
                self.logger.debug(f"WHO: Global user data for {nick}: {self.bot.users[nick]}")

    def handle_354(self, nick, userhost, params):
        """Handle WHOX response (numeric 354) for account information."""
        # WHOX response format from Undernet:
        # <target/botnick> <dummy> <user> <host> <ip> <nick> <status+flags> <account> :<realname>
        parts = params.split()
        if len(parts) >= 8:
            # Note: parts[0] is our bot's nick, not the channel
            user_nick = parts[5]  # Nick is in position 5
            ident = parts[2]      # Username/ident
            ip = parts[3]         # IP address is in position 3
            host = parts[4]       # Hostname is in position 4
            account = parts[7]    # Account is in position 7
            flags = parts[6]      # Status+flags in position 6
            
            # Get realname (everything after the account field)
            realname = ' '.join(parts[8:]).lstrip(':') if len(parts) > 8 else ''
            
            # Parse status flags
            away = 'G' in flags   # G = Gone/Away, H = Here
            oper = '*' in flags   # * indicates server operator
            
            self.logger.debug(f"WHOX parsed data - Nick: {user_nick}, Ident: {ident}, Host: {host}, IP: {ip}, Account: {account}, Flags: {flags}, Realname: {realname}")
            
            # Convert '0' to None for no account
            account = None if account == '0' else account
            
            # Update global user info first
            if user_nick not in self.bot.users:
                self.bot.users[user_nick] = {
                    'ident': ident,
                    'host': host,
                    'ip': ip,
                    'account': account,
                    'realname': realname,
                    'away': away,
                    'oper': oper
                }
            else:
                self.bot.users[user_nick].update({
                    'ident': ident,
                    'host': host,
                    'ip': ip,
                    'account': account,
                    'realname': realname,
                    'away': away,
                    'oper': oper
                })
            
            # Update user in all channels they're in
            for channel, users in self.bot.channel_users.items():
                if user_nick in users:
                    old_data = users[user_nick].copy()
                    users[user_nick].update({
                        'op': '@' in flags or '*' in flags,
                        'voice': '+' in flags
                    })
                    self.logger.debug(f"WHOX: New channel data for {user_nick} in {channel}: {users[user_nick]}")
            
            self.logger.debug(f"WHOX: Global user data for {user_nick}: {self.bot.users[user_nick]}")
        else:
            self.logger.debug(f"WHOX: Insufficient parts in response ({len(parts)} < 8)")

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
        if target_nick.lower() != self.bot.current_nick.lower():
            return
            
        # Check if this is a configured channel
        configured_channels = {c['name'].lower(): c.get('key', '') for c in self.bot.channels}
        invited_channel_lower = invited_channel.lower()
        
        if invited_channel_lower in configured_channels:
            if invited_channel_lower not in self.bot.channel_users:
                self.logger.info(f"Accepting invite to configured channel {invited_channel} from {nick}")
                key = configured_channels[invited_channel_lower]
                self.bot.send_raw(f"JOIN {invited_channel} {key}")
            else:
                self.logger.debug(f"Ignoring invite to {invited_channel} - already in channel")
        else:
            self.logger.debug(f"Ignoring invite to {invited_channel} - not a configured channel")

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

    def _handle_command(self, command_name, nick, channel, args):
        """Handle a bot command.
        
        Args:
            command_name: The name of the command to execute
            nick: The nickname of the user who issued the command
            channel: The channel where the command was issued
            args: List of command arguments
        """
        command = self.commands.get(command_name)
        if not command:
            return
            
        try:
            # Get command configuration
            cmd_config = self.bot.get_channel_command_config(channel, command_name)
            
            # Check if command is enabled first
            if not cmd_config.get('enabled', True):
                self.logger.warning(f"Command '{command_name}' is disabled in {channel}")
                return
            
            # Get user info including host and account
            user_info = self.bot.users.get(nick, {})
            ident = user_info.get('ident', '')
            host = user_info.get('host', '')
            userhost = f"{ident}@{host}" if ident and host else None
            
            # Get channel-specific user info
            channel_info = self.bot.channel_users.get(channel, {}).get(nick, {})
            
            # Check permissions
            if not self._check_command_permissions(nick, channel, cmd_config):
                required = cmd_config.get('requires', 'any')
                self.logger.warning(f"User {nick} lacks required permission '{required}' for command '{command_name}' in {channel}")
                return
                    
            # Execute command
            response = command.execute(nick, channel, args)
            
            # Handle response
            if response:
                self.bot.send_channel_message(channel, response, add_to_history=False)
                
        except Exception as e:
            self.logger.error(f"Error executing command {command_name}: {e}")
            self.bot.send_channel_message(channel, f"Error executing command: {e}", add_to_history=False)
            
    def _check_command_permissions(self, nick, channel, cmd_config):
        """Check if a user has permission to use a command.
        
        Args:
            nick: The nickname trying to use the command
            channel: The channel where the command was used
            cmd_config: The command configuration dict
            
        Returns:
            bool: True if user has permission, False otherwise
        """
        # Get user info including host and account
        user_info = self.bot.users.get(nick, {})
        if not user_info:
            self.logger.debug(f"No user info found for {nick}")
            return False
            
        # Get channel-specific user info
        channel_info = self.bot.channel_users.get(channel, {}).get(nick, {})
        
        # Construct userhost from ident and host
        ident = user_info.get('ident', '')
        host = user_info.get('host', '')
        userhost = f"{ident}@{host}" if ident and host else None
        
        # Check if user is admin (admins can use any command)
        if userhost and self.bot.permissions.is_admin(nick, userhost):
            self.logger.debug(f"User {nick} ({userhost}) is admin - command permitted")
            return True
            
        # Get required permission level
        required = cmd_config.get('requires', 'any').lower()
        
        # Handle different permission levels
        if required == 'admin':
            return False
            
        elif required == 'op':
            if not channel_info.get('op', False):
                return False
                
        elif required == 'voice':
            if not (channel_info.get('voice', False) or channel_info.get('op', False)):
                return False
                
        # Check if command is enabled for the channel
        if not cmd_config.get('enabled', True):
            self.logger.debug(f"Command is disabled in {channel}")
            return False
            
        # 'any' permission level always returns True
        return True

    def _parse_prefix(self, prefix):
        """Parse IRC prefix into nick and userhost."""
        if "!" in prefix and "@" in prefix:
            nick, userhost = prefix.split("!", 1)
            return nick, userhost
        return prefix, ""

    def _check_channels_loop(self):
        """Periodically check if we're in all configured channels."""
        while True:
            try:
                # Only check if we're connected
                if self.bot.connected:
                    configured_channels = {c['name'].lower(): c.get('key', '') for c in self.bot.channels}
                    current_channels = {chan.lower() for chan in self.bot.channel_users.keys()}
                    
                    # Find channels we should be in but aren't
                    missing_channels = set(configured_channels.keys()) - current_channels
                    
                    for channel in missing_channels:
                        self.logger.info(f"Not in configured channel {channel}, attempting to join")
                        key = configured_channels[channel]
                        self.bot.send_raw(f"JOIN {channel} {key}")
                        
            except Exception as e:
                self.logger.error(f"Error in channel check loop: {e}")
                
            time.sleep(30)  # Check every 30 seconds 

    def start_channel_check(self):
        """Start the channel check thread if not already running."""
        if not self.channel_check_thread or not self.channel_check_thread.is_alive():
            self.channel_check_thread = threading.Thread(target=self._check_channels_loop, daemon=True)
            self.channel_check_thread.start()
            self.logger.debug("Started channel check thread") 


    def handle_ctcp(self, nick, userhost, message):
        """Handle CTCP requests from users"""
        if not self.bot.floodpro.check_privmsg_flood(nick, userhost):
            self.logger.warning(f"Ignoring CTCP {message} from {nick} ({userhost}) - flood protection triggered")
            return

        version = "2.0"
        source_url = "https://github.com/empus/quipbot"
        author = "Empus (empus@undernet.org)"

        # Handle CTCP VERSION request
        if message.startswith('\x01VERSION\x01'):
            version = f"QuipBot v{version} - A witty IRC bot powered by AI - {source_url} - by {author}"
            self.logger.info(f"Responding to CTCP VERSION request from {nick} ({userhost})")
            self.bot.send_raw(f"NOTICE {nick} :\x01VERSION {version}\x01")
            return
        
        # Handle CTCP PING request
        if message.startswith('\x01PING '):
            ping_params = message[6:-1]  # Extract parameters between PING and final \x01
            self.logger.info(f"Responding to CTCP PING from {nick} ({userhost}) with params: {ping_params}")
            self.bot.send_raw(f"NOTICE {nick} :\x01PING {ping_params}\x01")
            return
        
        # Handle CTCP TIME request
        if message.startswith('\x01TIME\x01'):
            self.logger.info(f"Received CTCP TIME request from {nick} ({userhost})")
            self.bot.send_raw(f"NOTICE {nick} :\x01TIME {time.strftime('%H:%M')} {time.strftime('%Z')} UTC\x01")
            return
        
        # Handle CTCP USERINFO request
        if message.startswith('\x01USERINFO\x01'):
            self.logger.info(f"Received CTCP USERINFO request from {nick} ({userhost})")
            self.bot.send_raw(f"NOTICE {nick} :\x01USERINFO {self.bot.current_nick} is a witty AI bot\x01")
            return
        
        # Handle CTCP CLIENTINFO request
        if message.startswith('\x01CLIENTINFO\x01'):
            self.logger.info(f"Received CTCP CLIENTINFO request from {nick} ({userhost})")
            supported_commands = "ACTION, CLIENTINFO, PING, TIME, VERSION, USERINFO, SOURCE"
            self.bot.send_raw(f"NOTICE {nick} :\x01CLIENTINFO {supported_commands}\x01")
            return
        
        # Handle CTCP SOURCE request
        if message.startswith('\x01SOURCE\x01'):
            self.logger.info(f"Received CTCP SOURCE request from {nick} ({userhost})")
            self.bot.send_raw(f"NOTICE {nick} :\x01SOURCE {source_url}\x01")
            return
        
        # Handle CTCP ACTION request
        if message.startswith('\x01ACTION\x01'):
            self.logger.info(f"Received CTCP ACTION request from {nick} ({userhost})")
            self.bot.send_raw(f"NOTICE {nick} :\x01ACTION {message[7:-1]}\x01")
            return
        
        # Handle unknown CTCP requests
        self.logger.warning(f"Received unknown CTCP request from {nick} ({userhost}): {message}")
        #self.bot.send_raw(f"NOTICE {nick} :Unknown CTCP request\x01")
        return 