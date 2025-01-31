"""Core IRC functionality for QuipBot."""

import socket
import time
import threading
import ssl
import base64
#import logging
from .handler import MessageHandler
from .permissions import PermissionManager
from ..utils.ai_client import AIClient
from ..utils.floodpro import FloodProtection
from ..utils.tokenbucket import TokenBucket
from ..utils.logger import setup_logger
import yaml

class IRCBot:
    def __init__(self, config):
        """Initialize IRC bot."""
        self.config = config
        self.nick = config['nick']
        self.realname = config['realname']
        self.ident = config['ident']
        self.servers = config['servers']
        self.channels = config['channels']
        
        # SASL configuration
        self.sasl_config = config.get('sasl', {})
        self.sasl_authenticated = False
        self.registration_complete = False
        
        # Set up logger
        self.logger = setup_logger('QuipBot', config)
        
        self.current_server_index = 0
        self.sock = None
        self.connected = False
        
        # Initialize components
        self.permissions = PermissionManager(config)
        self.ai_client = AIClient(config)
        self.floodpro = FloodProtection(config)
        self.handler = MessageHandler(self)
        
        # Initialize rate limiter
        burst_size = config.get('irc_burst_size', 4)
        fill_rate = config.get('irc_fill_rate', 1.0)
        self.rate_limiter = TokenBucket(capacity=burst_size, fill_rate=fill_rate)
        
        # User tracking
        self.users = {}  # {nick: {'account': None, 'host': None}}
        self.channel_users = {}  # {channel: {nick: {'op': False, 'voice': False}}}
        
        # Timers for random actions - per channel
        self.last_chat_times = {}  # {channel: timestamp}
        self.last_action_times = {}  # {channel: timestamp}

    def _sasl_plain_auth(self):
        """Perform SASL PLAIN authentication."""
        if not self.sasl_config.get('enabled'):
            return False
            
        username = self.sasl_config.get('username', self.nick)
        password = self.sasl_config.get('password', '')
        
        if not password:
            self.logger.warning("SASL enabled but no password configured")
            return False
            
        # Format for SASL PLAIN: \0username\0password
        auth_str = f"\0{username}\0{password}"
        auth_b64 = base64.b64encode(auth_str.encode('utf-8')).decode('utf-8')
        
        # Start SASL authentication
        self.send_raw("CAP REQ :sasl")
        self.send_raw("AUTHENTICATE PLAIN")
        self.send_raw(f"AUTHENTICATE {auth_b64}")
        
        return True

    def connect(self):
        """Connect to an IRC server."""
        while not self.connected:
            server = self.servers[self.current_server_index]
            self.host = server['host']
            self.port = server['port']
            self.password = server.get('password', '')
            use_tls = server.get('tls', False)
            verify_cert = server.get('verify_cert', True)
            bindhost = self.config.get('bindhost', '')
            
            try:
                self.logger.info(f"Connecting to {self.host}:{self.port} {'with' if use_tls else 'without'} TLS")
                if bindhost:
                    self.logger.info(f"Using bind host: {bindhost}")
                
                # Create base socket
                base_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                
                # Bind to specific local address if configured
                if bindhost:
                    try:
                        base_socket.bind((bindhost, 0))
                    except Exception as e:
                        self.logger.error(f"Failed to bind to {bindhost}: {e}")
                        raise
                
                if use_tls:
                    # Configure TLS context
                    context = ssl.create_default_context()
                    if not verify_cert:
                        context.check_hostname = False
                        context.verify_mode = ssl.CERT_NONE
                    
                    # Wrap socket with TLS
                    self.sock = context.wrap_socket(base_socket, server_hostname=self.host)
                else:
                    self.sock = base_socket
                
                self.sock.connect((self.host, self.port))
                self.sock.setblocking(False)
                
                # Reset authentication flags
                self.sasl_authenticated = False
                self.registration_complete = False
                
                # Start capability negotiation if using SASL
                if self.sasl_config.get('enabled'):
                    self.send_raw("CAP LS 302")
                
                if self.password:
                    self.send_raw(f"PASS {self.password}")
                    
                self.send_raw(f"NICK {self.nick}")
                self.send_raw(f"USER {self.ident} 0 * :{self.realname}")
                
                # If not using SASL, end capability negotiation
                if not self.sasl_config.get('enabled'):
                    self.send_raw("CAP END")
                
                threading.Thread(target=self.listen_loop, daemon=True).start()
                self.connected = True
                self.logger.info("Connected successfully")
                
            except Exception as e:
                self.logger.error(f"Failed to connect to {self.host}:{self.port} - {e}")
                if self.sock:
                    try:
                        self.sock.close()
                    except:
                        pass
                self.sock = None
                self.current_server_index = (self.current_server_index + 1) % len(self.servers)
                time.sleep(5)  # Wait before trying the next server

    def handle_cap(self, params):
        """Handle CAP messages for capability negotiation."""
        if ' ' not in params:
            return
            
        subcommand = params.split()[0]
        
        if subcommand == "LS":
            if "sasl" in params.lower():
                self._sasl_plain_auth()
            else:
                self.send_raw("CAP END")
        elif subcommand == "ACK":
            if "sasl" in params.lower():
                # SASL capability acknowledged, authentication will follow
                pass
        elif subcommand == "NAK":
            # Capability negotiation failed, end it
            self.send_raw("CAP END")

    def handle_authenticate(self, params):
        """Handle AUTHENTICATE messages."""
        if params == "+":
            # Server is ready for authentication
            self._sasl_plain_auth()

    def handle_numeric(self, numeric, params):
        """Handle numeric responses."""
        if numeric == "903":  # RPL_SASLSUCCESS
            self.logger.info("SASL authentication successful")
            self.sasl_authenticated = True
            self.send_raw("CAP END")
        elif numeric == "904":  # ERR_SASLFAIL
            self.logger.error("SASL authentication failed")
            self.send_raw("CAP END")
        elif numeric == "905":  # ERR_SASLTOOLONG
            self.logger.error("SASL authentication failed: message too long")
            self.send_raw("CAP END")
        elif numeric == "906":  # ERR_SASLABORTED
            self.logger.error("SASL authentication aborted")
            self.send_raw("CAP END")
        elif numeric == "907":  # ERR_SASLALREADY
            self.logger.warning("SASL authentication failed: already authenticated")
            self.send_raw("CAP END")
        elif numeric in ("001", "376", "422"):  # Welcome/MOTD
            self.registration_complete = True
            # Set user mode if configured
            usermode = self.config.get('usermode')
            if usermode:
                self.logger.debug(f"Setting user mode: {usermode}")
                self.send_raw(f"MODE {self.nick} {usermode}")
            
            # Send post-connect commands
            post_connect_commands = self.config.get('post_connect_commands', [])
            if post_connect_commands:
                self.logger.debug("Sending post-connect commands")
                for cmd in post_connect_commands:
                    # Replace variables in command
                    cmd = cmd.replace('$nick', self.nick)
                    self.logger.debug(f"Sending command: {cmd}")
                    self.send_raw(cmd)
                    time.sleep(1)  # Add delay between commands to prevent flood
            
            # Join channels after commands are sent
            self.join_channels()

    def reconnect(self):
        """Reconnect to the IRC server."""
        self.logger.info("Reconnecting...")
        self.connected = False
        self.connect()
        self.join_channels()

    def format_message(self, message):
        """Convert markdown-style formatting to IRC codes."""
        # IRC format codes
        BOLD = "\x02"
        UNDERLINE = "\x1F"
        
        # Remove encapsulating quotes if the entire message is quoted
        if message.startswith('"') and message.endswith('"'):
            message = message[1:-1]
        
        # Replace **text** with bold
        while "**" in message:
            message = message.replace("**", BOLD, 2)
            
        # Replace _text_ with underline
        while "_" in message:
            message = message.replace("_", UNDERLINE, 2)
            
        return message

    def send_raw(self, message):
        """Send raw message to the IRC server."""
        self.logger.debug(f">>> {message}")
        try:
            # Get token from rate limiter
            wait_time = self.rate_limiter.get_token()
            if wait_time > 0:
                time.sleep(wait_time)
                
            self.sock.sendall(f"{message}\r\n".encode('utf-8'))
        except Exception as e:
            self.logger.error(f"Failed to send message: {e}")
            self.reconnect()

    def join_channels(self):
        """Join all configured channels."""
        self.logger.info("Registration complete, joining channels...")
        for channel in self.channels:
            channel_name = channel['name']
            channel_key = channel.get('key', '')
            self.send_raw(f"JOIN {channel_name} {channel_key}")
            self.logger.debug(f"Joining channel: {channel_name}")

    def send_channel_message(self, channel, message):
        """Send a message to a channel."""
        formatted_message = self.format_message(message)
        
        # Calculate max message length (512 - overhead)
        # PRIVMSG #channel :message\r\n
        # overhead = len("PRIVMSG") + len(channel) + 4
        max_len = 512 - (len("PRIVMSG") + len(channel) + 4)
        
        # Split message if too long
        while formatted_message:
            # Find last sentence boundary within limit
            if len(formatted_message) > max_len:
                # Try to find sentence boundaries (. ! ? followed by space)
                split_point = -1
                for punct in ['. ', '! ', '? ']:
                    last_punct = formatted_message.rfind(punct, 0, max_len - 1)
                    if last_punct > split_point:
                        split_point = last_punct + len(punct)
                
                # If no sentence boundary found, try word boundary
                if split_point == -1:
                    split_point = formatted_message.rfind(' ', 0, max_len)
                
                # If still no good split point, just cut at max
                if split_point == -1:
                    split_point = max_len
                
                chunk = formatted_message[:split_point].rstrip()
                formatted_message = formatted_message[split_point:].lstrip()
            else:
                chunk = formatted_message
                formatted_message = ''
                
            try:
                self.send_raw(f"PRIVMSG {channel} :{chunk}")
                # Add our own message to the channel history
                history_entry = f"{self.nick}: {chunk}"
                # Use lowercase channel name for consistency
                channel_lower = channel.lower()
                self.ai_client.add_to_history(history_entry, channel_lower)
                # Update last chat time since we spoke
                self.last_chat_times[channel_lower] = time.time()
            except Exception as e:
                self.logger.error(f"Failed to send message to {channel}: {e}")

    def listen_loop(self):
        """Main listening loop for IRC messages."""
        buffer = ""
        while True:
            try:
                data = self.sock.recv(4096)
                if not data:
                    self.logger.warning("Connection lost")
                    self.connected = False
                    self.reconnect()
                    break

                buffer += data.decode('utf-8', errors='ignore')
                while '\r\n' in buffer:
                    line, buffer = buffer.split('\r\n', 1)
                    
                    # Log numeric responses that might indicate errors
                    if ' ' in line and line[0] == ':':
                        parts = line.split(' ')
                        if len(parts) >= 2 and parts[1].isdigit():
                            numeric = int(parts[1])
                            # Log error responses (400-599)
                            if 400 <= numeric <= 599:
                                self.logger.error(f"IRC Error: {line}")
                            
                    self.handler.handle_line(line)
                    
            except socket.error:
                time.sleep(0.1)
            except Exception as e:
                self.logger.error(f"Error in listen loop: {e}")
                time.sleep(1)

    def random_actions_loop(self):
        """Handle random actions on timers."""
        while True:
            try:
                time.sleep(5)
                now = time.time()
                
                # Check idle chat interval for each channel
                for channel in self.channels:
                    channel_name = channel['name']
                    # Skip if we're not in the channel
                    if not self.is_in_channel(channel_name):
                        self.logger.debug(f"Not in channel {channel_name}, skipping")
                        continue
                        
                    # Initialize timers for this channel if not exist
                    if channel_name not in self.last_chat_times:
                        self.last_chat_times[channel_name] = now
                    if channel_name not in self.last_action_times:
                        self.last_action_times[channel_name] = now
                    
                    # Check idle chat interval
                    idle_chat_interval = self.get_channel_config(channel_name, 'idle_chat_interval', 0)
                    time_since_last = now - self.last_chat_times[channel_name]
                    
                    if idle_chat_interval > 0 and time_since_last > idle_chat_interval:
                        # Skip idle chat if we were the last to speak
                        if self.was_last_speaker(channel_name):
                            self.logger.debug(f"Skipping idle chat in {channel_name} - last message was from bot")
                            continue
                        self.logger.debug(f"Attempting idle chat in {channel_name} (interval: {idle_chat_interval}s, last chat: {time_since_last:.0f}s ago)")
                        self._random_chat(channel_name)
                        # Only update the timer if we actually sent a message
                        self.last_chat_times[channel_name] = now
                    
                    # Check random action interval
                    random_action_interval = self.get_channel_config(channel_name, 'random_action_interval', 0)
                    if random_action_interval > 0 and now - self.last_action_times[channel_name] > random_action_interval:
                        self.last_action_times[channel_name] = now
                        self._random_action(channel_name)
                    
            except Exception as e:
                self.logger.error(f"Error in random actions loop: {e}")
                time.sleep(1)

    def is_in_channel(self, channel):
        """Check if the bot is currently in a channel."""
        # Case insensitive channel check
        channel_lower = channel.lower()
        return any(ch.lower() == channel_lower for ch in self.channel_users.keys())

    def was_last_speaker(self, channel):
        """Check if the bot was the last to speak in the channel."""
        # Use lowercase channel name for consistency
        channel_lower = channel.lower()
        channel_history = self.ai_client.chat_history.get(channel_lower, [])
        if channel_history:
            try:
                last_message = channel_history[-1]
                if ': ' in last_message:
                    last_nick = last_message.split(': ', 1)[0].strip()
                    is_last = last_nick.lower() == self.nick.lower()
                    return is_last
            except Exception as e:
                self.logger.error(f"Error checking last message in {channel}: {e}")
        self.logger.debug(f"No chat history for {channel}")
        return False

    def _random_chat(self, target_channel=None):
        """Generate and send a random chat message with context.
        
        Args:
            target_channel: Optional specific channel name to generate chat for
        """
        if not self.channel_users:
            return
            
        # If target_channel is specified, only check that channel
        channels_to_check = [target_channel] if target_channel else [c['name'] for c in self.channels]
            
        # Check each channel for idle chat
        for channel_name in channels_to_check:
            # Skip if we're not in the channel
            if not self.is_in_channel(channel_name):
                continue
                
            # Get channel-specific idle chat interval
            idle_chat_interval = self.get_channel_config(channel_name, 'idle_chat_interval', 0)
            if idle_chat_interval <= 0:
                continue
                
            # Skip if we were the last to speak
            if self.was_last_speaker(channel_name):
                self.logger.debug(f"Skipping idle chat in {channel_name} - bot was last speaker")
                continue
                
            # Check if we should include chat history context
            include_history = self.get_channel_config(channel_name, 'ai_context_idle', True)
            
            # Use the channel-specific idle chat prompt with chat history
            prompt = self.get_channel_config(channel_name, 'ai_prompt_idle', self.config['ai_prompt_idle'])
            message = self.ai_client.get_response(
                prompt, 
                self.nick, 
                channel=channel_name, 
                include_history=include_history,
                add_to_history=False    # Don't add the prompt to history
            )
            if message:
                self.send_channel_message(channel_name, message)
                self.logger.debug(f"Sent idle chat to {channel_name}")

    def _random_action(self, target_channel=None):
        """Perform a random action (topic change or kick).
        
        Args:
            target_channel: Optional specific channel to perform action in
        """
        import random
        if not self.channel_users:
            return

        channels_to_check = [{'name': target_channel}] if target_channel else self.channels
            
        # Check each channel for random actions
        for channel in channels_to_check:
            channel_name = channel['name']
            # Skip if we're not in the channel
            if not self.is_in_channel(channel_name):
                continue
                
            # Get channel-specific random action interval
            random_action_interval = self.get_channel_config(channel_name, 'random_action_interval', 0)
            if random_action_interval <= 0:
                continue

            action = random.choice(['topic', 'kick'])

            if action == 'topic':
                # Use the channel-specific topic prompt
                prompt = self.get_channel_config(channel_name, 'ai_prompt_topic', self.config['ai_prompt_topic'])
                topic = self.ai_client.generate_topic(prompt, channel=channel_name)
                if topic:
                    # Format the topic to remove encapsulating quotes
                    formatted_topic = self.format_message(topic)
                    self.send_raw(f"TOPIC {channel_name} :{formatted_topic}")
            
            elif action == 'kick':
                channel_users = self.channel_users.get(channel_name, {})
                # Get list of recently active users in the channel
                recent_users = self.ai_client.get_recent_users(channel_name)
                
                # Filter possible targets to only include recently active non-op users
                possible_targets = [
                    nick for nick in recent_users
                    if nick in channel_users  # User is still in channel
                    and nick != self.nick  # Not the bot
                    and not channel_users[nick].get('op', False)  # Not an op
                ]
                
                if possible_targets:
                    target = random.choice(possible_targets)
                    # Use channel-specific kick prompt
                    prompt = self.get_channel_config(channel_name, 'ai_prompt_kick', self.config['ai_prompt_kick'])
                    reason = self.ai_client.generate_kick_reason(prompt, channel=channel_name)
                    if reason:
                        # Format the kick reason to remove encapsulating quotes
                        formatted_reason = self.format_message(reason)
                        self.send_raw(f"KICK {channel_name} {target} :{formatted_reason}")

    def run(self):
        """Start the bot."""
        self.connect()
        time.sleep(2)  # Wait for connection to stabilize
        
        # Start random actions thread
        threading.Thread(target=self.random_actions_loop, daemon=True).start()
        
        # Keep the main thread alive
        while True:
            if not self.connected:
                self.reconnect()
            time.sleep(1)

    def update_config(self, new_config):
        """Update bot configuration and reset timers."""
        self.config = new_config
        self.permissions.update_config(new_config)
        self.ai_client.model = new_config['ai_model']
        self.ai_client.default_prompt = new_config['ai_prompt_default']
        self.floodpro = FloodProtection(new_config)  # Reset flood protection with new config
        
        # Reset action timers to trigger on next check
        self.last_chat_times = {}
        self.last_action_times = {}
        self.logger.debug("Reset action timers during config update")

    def generate_idle_chat(self):
        """Generate and send an idle chat message."""
        message = self.ai_client.get_response(self.config['ai_prompt_idle'], self.nick)
        if message:
            self.send_channel_message(self.current_channel, message)

    def generate_random_topic(self):
        """Generate and set a random topic."""
        topic = self.ai_client.generate_topic(self.config['ai_prompt_topic'])
        if topic:
            for channel in self.channel_users.keys():
                self.send_raw(f"TOPIC {channel} :{topic}")

    def generate_random_kick(self):
        """Generate and perform a random kick."""
        reason = self.ai_client.generate_kick_reason(self.config['ai_prompt_kick'])

    def reload_config(self):
        """Reload configuration from file."""
        try:
            with open('config.yaml', 'r') as f:
                new_config = yaml.safe_load(f)
            self.config = new_config
            self.ai_client.model = new_config['ai_model']
            self.ai_client.default_prompt = new_config['ai_prompt_default']
            return True
        except Exception as e:
            self.logger.error(f"Error reloading config: {e}")
            return False

    def handle_channel_message(self, nick, userhost, channel, message):
        """Handle a channel message."""
        # Use lowercase channel name for consistency
        channel_lower = channel.lower()
        
        # Check for channel flood
        if not self.floodpro.check_channel_flood(channel, nick, userhost):
            # Get and execute ban commands
            for cmd in self.floodpro.get_ban_command(channel, nick, userhost):
                self.send_raw(cmd)
            return

        # Get ignore list (combine global and channel-specific)
        global_ignores = self.config.get('ignore_nicks', [])
        channel_ignores = self.get_channel_config(channel, 'ignore_nicks', [])
        ignore_list = [n.lower() for n in global_ignores + channel_ignores]
        
        # Check if this nick should be ignored
        if nick.lower() in ignore_list:
            return

        # Add message to history
        history_entry = f"{nick}: {message}"
        self.ai_client.add_to_history(history_entry, channel_lower)

        # Only reset idle timer for messages from other users
        if nick.lower() != self.nick.lower():
            self.last_chat_times[channel_lower] = time.time()

        # Check for commands first
        cmd_prefix = self.config.get('cmd_prefix', '!')  # Default to ! if not configured
        if message.startswith(cmd_prefix):
            parts = message[len(cmd_prefix):].split()
            if parts:
                command = parts[0].lower()
                args = parts[1:]
                self.logger.debug(f"Command detected: {command} from {nick} in {channel}")
                self.handler._handle_command(command, nick, channel, args)
                return

        # Get AI response delay setting
        ai_delay_range = self.get_channel_config(channel, 'ai_delay', [0, 0])
        if isinstance(ai_delay_range, (int, float)):  # Handle old config format
            ai_delay_range = [ai_delay_range, ai_delay_range]
        
        # Calculate random delay if range is set
        ai_delay = 0
        if ai_delay_range and len(ai_delay_range) == 2 and (ai_delay_range[0] > 0 or ai_delay_range[1] > 0):
            import random
            ai_delay = random.uniform(ai_delay_range[0], ai_delay_range[1])

        # Process direct messages to the bot (nick: message)
        message_lower = message.lower()
        if message_lower.startswith(f"{self.nick.lower()}:"):
            # Check if we should include chat history context
            include_history = self.get_channel_config(channel, 'ai_context_direct', False)
            self.logger.debug(f"Direct message in {channel} - using {'context' if include_history else 'no context'}")
            
            response = self.ai_client.get_response(
                message, 
                nick, 
                channel=channel_lower, 
                add_to_history=True,
                include_history=include_history
            )
            if response:
                if ai_delay > 0:
                    self.logger.debug(f"Delaying response by {ai_delay:.1f}s")
                    time.sleep(ai_delay)
                self.send_channel_message(channel, response)
            return
            
        # Check for mentions of the bot's nick if ai_mention is enabled
        ai_mention = self.get_channel_config(channel, 'ai_mention', False)
        
        if ai_mention:
            # First check for direct prefix which we already handled
            if message_lower.startswith(f"{self.nick.lower()}:"):
                return
                
            # Split message into words and check if any word matches the bot's nick
            # Add a space before and after the message to handle edge cases
            message_with_spaces = f" {message_lower} "
            nick_lower = self.nick.lower()
            
            # Check for nickname followed by common punctuation or space
            if f" {nick_lower}" in message_with_spaces and any(
                message_with_spaces.find(f" {nick_lower}{p}") != -1 
                for p in ["", " ", "!", "?", ".", ",", ";", ":", ")", "]", "}", "~"]
            ):
                self.logger.debug(f"Bot mentioned by {nick} in {channel}")
                # Check if we should include chat history context
                include_history = self.get_channel_config(channel, 'ai_context_mention', True)
                response = self.ai_client.get_response(
                    message,
                    nick,
                    channel=channel_lower,
                    add_to_history=True,
                    include_history=include_history
                )
                if response:
                    if ai_delay > 0:
                        self.logger.debug(f"Delaying response by {ai_delay:.1f}s")
                        time.sleep(ai_delay)
                    self.send_channel_message(channel, response)

    def handle_private_message(self, nick, userhost, message):
        """Handle a private message."""
        # Check for private message flood
        if not self.floodpro.check_privmsg_flood(nick, userhost):
            return

        # Process message if not flood
        response = self.ai_client.get_response(message, nick)
        if response:
            self.send_raw(f"NOTICE {nick} :{response}")
        self.ai_client.add_to_history(f"{nick}: {message}")

    def get_channel_config(self, channel, key, default=None):
        """Get a channel-specific config value, falling back to global config.
        
        Args:
            channel: The channel name to get config for
            key: The config key to get
            default: Default value if not found in channel or global config
            
        Returns:
            The channel-specific value if it exists, otherwise the global value,
            or the default if neither exists.
        """
        # Find channel config
        channel_config = next(
            (c for c in self.channels if c['name'].lower() == channel.lower()),
            None
        )
        
        # First check channel-specific override if it exists
        if channel_config and key in channel_config:
            return channel_config[key]
            
        # Then check global config
        if key in self.config:
            return self.config[key]
            
        # Finally fall back to default
        return default

    def get_channel_command_config(self, channel, command):
        """Get channel-specific command configuration.
        
        Args:
            channel: The channel name
            command: The command name
            
        Returns:
            dict: Command configuration with channel overrides
        """
        # Get global command config
        global_cmd_config = self.config.get('commands', {}).get(command, {})
        
        # Get channel-specific command config
        channel_config = next(
            (c for c in self.channels if c['name'].lower() == channel.lower()),
            None
        )
        if channel_config and 'commands' in channel_config:
            channel_cmd_config = channel_config['commands'].get(command, {})
            # Merge with global config, channel config takes precedence
            return {**global_cmd_config, **channel_cmd_config}
            
        return global_cmd_config

    def is_protected_user(self, channel, nick, userhost=None):
        """Check if a user is protected from kicks (op, admin, or bot).
        
        Args:
            channel: The channel to check
            nick: The nickname to check
            userhost: Optional user@host for admin checking
            
        Returns:
            bool: True if user is protected, False otherwise
        """
        # Always protect the bot
        if nick.lower() == self.nick.lower():
            return True
            
        # Check if user is a channel op
        channel_users = self.channel_users.get(channel, {})
        if channel_users.get(nick, {}).get('op', False):
            return True
            
        # Check if user is a bot admin
        if userhost and self.permissions.is_admin(nick, userhost):
            return True
            
        # Check if nick matches an admin nick exactly (for cases where we don't have userhost)
        if nick in self.config.get('admins', []):
            return True
            
        return False