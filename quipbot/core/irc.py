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
import re
from ..utils.reloader import ModuleReloader
import signal
import sys

def _setup_signal_handlers(bot_instance):
    """Set up signal handlers for the bot.
    
    Args:
        bot_instance: The IRCBot instance to handle signals for
    """
    def handle_sighup(signum, frame):
        """Handle SIGHUP signal by reloading config."""
        bot_instance.logger.info("Received SIGHUP signal - reloading configuration")
        if bot_instance.reload_config():
            bot_instance.logger.info("Configuration reloaded successfully")
        else:
            bot_instance.logger.error("Failed to reload configuration")
            
    def handle_sigusr1(signum, frame):
        """Handle SIGUSR1 signal by performing a full reload."""
        bot_instance.logger.info("Received SIGUSR1 signal - performing full reload")
        if bot_instance.reloader.reload_modules(bot_instance):
            bot_instance.logger.info("Full reload completed successfully")
        else:
            bot_instance.logger.error("Failed to complete full reload")
            
    # Register signal handlers
    if sys.platform != 'win32':  # Signals not fully supported on Windows
        signal.signal(signal.SIGHUP, handle_sighup)
        signal.signal(signal.SIGUSR1, handle_sigusr1)
        bot_instance.logger.info("Registered signal handlers for SIGHUP and SIGUSR1")

class IRCBot:
    def __init__(self, config, config_file='config.yaml'):
        """Initialize IRC bot."""
        self.config = config
        self.config_file = config_file  # Store the config file path
        self.nick = config['nick']
        self.altnick = config.get('altnick', f"{self.nick}_")  # Default to nick_ if not specified
        self.current_nick = self.nick  # Track current nickname
        self.nick_attempt = 0  # Track nickname attempt number
        self.last_nick_recovery = 0  # Track last time we tried to recover primary nick
        self.realname = config['realname']
        self.ident = config['ident']
        self.servers = config['servers']
        self.channels = config['channels']
        
        # Sleep tracking
        self.sleep_until = {}  # {channel: wake_time}
        
        # SASL configuration
        self.sasl_config = config.get('sasl', {})
        self.sasl_authenticated = False
        self.registration_complete = False
        
        # Set up logger
        self.logger = setup_logger('QuipBot', config)
        
        # Set up signal handlers
        _setup_signal_handlers(self)
        
        self.current_server_index = 0
        self.sock = None
        self.running = True  # Flag to control bot lifecycle
        
        # Initialize components
        self.permissions = PermissionManager(config)
        self.permissions.set_bot(self)  # Set bot reference
        self.ai_client = AIClient(config)
        self.ai_client.set_bot(self)  # Set bot reference
        self.floodpro = FloodProtection(config)
        self.floodpro.logger = self.logger  # Set logger reference
        self.handler = MessageHandler(self)
        self.reloader = ModuleReloader()  # Initialize reloader
        
        # Initialize rate limiter
        burst_size = config.get('irc_burst_size', 4)
        fill_rate = config.get('irc_fill_rate', 1.0)
        self.rate_limiter = TokenBucket(capacity=burst_size, fill_rate=fill_rate)
        
        # User tracking
        self.users = {}  # {nick: {'account': None, 'host': None}}
        self.channel_users = {}  # {channel: {nick: {'op': False, 'voice': False}}}
        
        # Timers for random actions - per channel
        self.last_chat_times = {}  # {channel: timestamp} - When any user last spoke
        self.last_bot_times = {}   # {channel: timestamp} - When the bot last spoke
        self.last_action_times = {}  # {channel: timestamp}
        self.last_check_times = {}  # {channel: timestamp} - When we last checked for conversation
        
        # Conversation continuation tracking
        self.last_trigger_times = {}  # {channel: timestamp}
        self.conversation_timers = {}  # {channel: next_response_time}
        
        # Bot state flags
        self.reload_paused = False  # Controls temporary thread pausing for reloads
        self.connected = False

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
                    
                self.send_raw(f"NICK {self.current_nick}")
                self.send_raw(f"USER {self.ident} 0 * :{self.realname}")
                
                # If not using SASL, end capability negotiation
                if not self.sasl_config.get('enabled'):
                    self.send_raw("CAP END")
                
                # Set connected flag and start listen thread
                self.connected = True
                self.logger.info("Connected successfully")
                
                # Start listen thread
                listen_thread = threading.Thread(target=self.listen_loop, daemon=True)
                listen_thread.start()
                
                return  # Successfully connected, exit the loop
                
            except Exception as e:
                self.logger.error(f"Failed to connect to {self.host}:{self.port} - {e}")
                if self.sock:
                    try:
                        self.sock.close()
                    except:
                        pass
                self.sock = None
                self.connected = False  # Ensure connected flag is False on failure
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
        if numeric == "433":  # ERR_NICKNAMEINUSE
            # If this is during initial connection (not registered yet)
            if not self.registration_complete:
                if self.current_nick == self.nick:
                    # Primary nick is taken, try alternate
                    self.current_nick = self.altnick
                    self.logger.info(f"Primary nickname {self.nick} is taken, trying {self.current_nick}")
                else:
                    # Alternate nick is also taken, append number
                    self.nick_attempt += 1
                    self.current_nick = f"{self.altnick}{self.nick_attempt}"
                    self.logger.info(f"Alternate nickname is taken, trying {self.current_nick}")
                self.send_raw(f"NICK {self.current_nick}")
            else:
                # This is from a recovery attempt - just keep our current nick
                self.logger.debug(f"Primary nickname {self.nick} still unavailable, keeping {self.current_nick}")
            return
            
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
        elif numeric == "001":  # RPL_WELCOME - Start of registration
            if not self.registration_complete:
                self.registration_complete = True
                # Set user mode if configured
                usermode = self.config.get('usermode')
                if usermode:
                    self.logger.info(f"Setting user mode: {usermode}")
                    self.send_raw(f"MODE {self.current_nick} {usermode}")
        elif numeric in ("376", "422"):  # End of MOTD/MOTD Missing - End of registration
            if self.registration_complete:
                # Send post-connect commands
                post_connect_commands = self.config.get('post_connect_commands', [])
                if post_connect_commands:
                    self.logger.debug("Sending post-connect commands")
                    for cmd in post_connect_commands:
                        # Replace variables in command
                        cmd = cmd.replace('$nick', self.current_nick)
                        self.logger.debug(f"Sending command: {cmd}")
                        self.send_raw(cmd)
                        time.sleep(1)  # Add delay between commands to prevent flood
                
                # Start channel check thread now that we're registered
                self.handler.start_channel_check()
                
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
        self.logger.raw(f">>> {message}")
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
            # Server will send NAMES list automatically after JOIN
            # The handler will send a single WHO request after processing NAMES
            time.sleep(0.5)  # Small delay to prevent flood

    def _schedule_next_response(self, channel):
        """Schedule the next response time for a channel."""
        continue_freq = self.get_channel_config(channel, 'ai_continue_freq', 30)
        self.conversation_timers[channel.lower()] = time.time() + continue_freq
        self.logger.debug(f"Scheduled next response for {channel} in {continue_freq}s")

    def send_channel_message(self, channel, message, add_to_history=True):
        """Send a message to a channel.
        
        Args:
            channel: The channel to send the message to
            message: The message to send
            add_to_history: Whether to add this message to chat history (default: True)
        """
        # First, normalize newlines and remove any double newlines
        message = ' '.join(message.replace('\r', '').split('\n')).strip()
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
                # Add our own message to the channel history only if requested
                if add_to_history:
                    history_entry = f"{self.current_nick}: {chunk}"
                    # Use lowercase channel name for consistency
                    channel_lower = channel.lower()
                    self.ai_client.add_to_history(history_entry, channel_lower)
                # Update last bot time since we spoke
                self.last_bot_times[channel.lower()] = time.time()
                # Schedule next response time
                if self._should_continue_conversation(channel):
                    self._schedule_next_response(channel)
            except Exception as e:
                self.logger.error(f"Failed to send message to {channel}: {e}")

    def listen_loop(self):
        """Main listening loop for IRC messages."""
        thread = threading.current_thread()
        thread.is_processing = False
        buffer = ""
        
        while self.running:  # Check if bot should keep running
            try:
                # Skip processing if paused for reload
                if self.reload_paused:
                    thread.is_processing = False
                    self.logger.debug(f"Listen loop paused, processing: {thread.is_processing}")
                    time.sleep(0.1)
                    continue
                    
                # Set processing flag before any work
                thread.is_processing = True
                
                # Use non-blocking recv with timeout
                self.sock.settimeout(0.1)  # 100ms timeout
                try:
                    data = self.sock.recv(4096)
                    if not data:
                        self.logger.warning("Connection lost")
                        self.connected = False
                        self.reconnect()
                        break
                except socket.timeout:
                    # No data available, check pause state
                    thread.is_processing = False
                    continue
                except socket.error:
                    thread.is_processing = False
                    time.sleep(0.1)
                    continue

                buffer += data.decode('utf-8', errors='ignore')
                while '\r\n' in buffer and not self.reload_paused:
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
                    # Check pause state after each line
                    if self.reload_paused:
                        break
                    
            except Exception as e:
                self.logger.error(f"Error in listen loop: {e}")
                thread.is_processing = False
                time.sleep(1)
            finally:
                # Ensure processing flag is cleared if we're paused
                if self.reload_paused:
                    thread.is_processing = False

    def random_actions_loop(self):
        """Handle random actions on timers."""
        thread = threading.current_thread()
        thread.is_processing = False
        
        while self.running:  # Check if bot should keep running
            try:
                # Skip processing if paused for reload
                if self.reload_paused:
                    thread.is_processing = False
                    self.logger.debug(f"Random actions loop paused, processing: {thread.is_processing}")
                    time.sleep(0.1)
                    continue
                    
                # Set processing flag before any work
                thread.is_processing = True
                now = time.time()
                next_check = now + 60  # Default to 60 seconds between checks
                
                # Process each channel independently
                for channel in self.channels:
                    # Check pause state between channels
                    if self.reload_paused:
                        thread.is_processing = False
                        break
                        
                    channel_name = channel['name']
                    channel_lower = channel_name.lower()
                    
                    # Skip if we're not in the channel
                    if not self.is_in_channel(channel_name):
                        continue

                    # Skip if sleeping
                    if self.is_sleeping(channel_name):
                        continue
                                        
                    # Check for idle chat
                    idle_chat_interval = self.get_channel_config(channel_name, 'idle_chat_interval', 0)
                    if idle_chat_interval > 0:
                        last_chat = self.last_chat_times.get(channel_lower, 0)
                        idle_chat_time = self.get_channel_config(channel_name, 'idle_chat_time', idle_chat_interval)
                        time_since_last_chat = now - last_chat
                        time_until_next_chat = max(0, idle_chat_interval - (now - self.last_chat_times.get(channel_lower, 0)))
                        
                        self.logger.debug(
                            f"Idle chat timing for {channel_name}: "
                            f"interval={idle_chat_interval}s, "
                            f"required_idle={idle_chat_time}s, "
                            f"time_since_chat={time_since_last_chat:.0f}s, "
                            f"time_until_next={time_until_next_chat:.0f}s"
                        )
                        
                        if time_since_last_chat >= idle_chat_time and time_until_next_chat <= 0:
                            self._random_chat(channel_name)
                            self.last_chat_times[channel_lower] = now
                            
                    # Check for random actions
                    random_action_interval = self.get_channel_config(channel_name, 'random_action_interval', 0)
                    if random_action_interval > 0:
                        last_action = self.last_action_times.get(channel_lower, 0)
                        time_since_last_action = now - last_action
                        time_until_next_action = max(0, random_action_interval - time_since_last_action)
                        
                        self.logger.debug(
                            f"Random action timing for {channel_name}: "
                            f"interval={random_action_interval}s, "
                            f"time_since_action={time_since_last_action:.0f}s, "
                            f"time_until_next={time_until_next_action:.0f}s"
                        )
                        
                        if time_until_next_action <= 0:
                            # Skip if we were the last to speak
                            if self.was_last_speaker(channel_name):
                                self.logger.warning(f"Skipping random actions in {channel_name} - bot was last speaker")
                                continue
                            self._random_action(channel_name)
                            self.last_action_times[channel_lower] = now
                    
                    # Process conversation continuation
                    if self._should_continue_conversation(channel_name):
                        if self.reload_paused:
                            thread.is_processing = False
                            break
                            
                        next_response_time = self.conversation_timers.get(channel_lower, 0)
                        time_until_response = next_response_time - now
                        
                        if time_until_response <= 0:
                            self.logger.debug(f"Timer triggered for {channel_name} - generating response")
                            channel_history = self.ai_client.chat_history.get(channel_lower, [])
                            if channel_history:
                                last_message = channel_history[-1]
                                response = self.ai_client.get_response(
                                    last_message,
                                    self.current_nick,
                                    channel=channel_lower,
                                    add_to_history=True,
                                    include_history=True
                                )
                                
                                if response:
                                    self.send_channel_message(channel_name, response)
                                else:
                                    self._schedule_next_response(channel_name)
                            else:
                                self._schedule_next_response(channel_name)
                                
                        # Update next check time
                        next_check = min(next_check, now + max(0.1, time_until_response))
                    
                # Calculate sleep time with more frequent pause checks
                sleep_time = max(0.1, min(60, next_check - time.time()))
                
                # Break sleep into smaller chunks to check pause state
                end_time = time.time() + sleep_time
                while time.time() < end_time and not self.reload_paused:
                    time.sleep(0.1)
                    
                if self.reload_paused:
                    thread.is_processing = False
                    break
                    
            except Exception as e:
                self.logger.error(f"Error in random actions loop: {e}")
                thread.is_processing = False
                time.sleep(1)
            finally:
                # Ensure processing flag is cleared if we're paused
                if self.reload_paused:
                    thread.is_processing = False

    def is_in_channel(self, channel):
        """Check if the bot is currently in a channel."""
        # Case insensitive channel check
        channel_lower = channel.lower()
        
        # Check if we're in the channel and have our current nick registered there
        is_in = any(ch.lower() == channel_lower and self.current_nick in self.channel_users[ch] 
                   for ch in self.channel_users.keys())
        
        # Only log channel presence check once per minute per channel
        now = time.time()
        last_check_key = f"last_presence_check_{channel_lower}"
        last_check = getattr(self, last_check_key, 0)
        
        if not is_in and (now - last_check) >= 60:
            self.logger.debug(f"Not in channel {channel} (current_nick: {self.current_nick})")
            setattr(self, last_check_key, now)
        
        return is_in

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
                    is_last = last_nick.lower() == self.current_nick.lower()
                    return is_last
            except Exception as e:
                self.logger.error(f"Error checking last message in {channel}: {e}")
        self.logger.debug(f"No chat history for {channel}")
        return False

    def _random_chat(self, target_channel=None):
        """Generate and send a random chat message with context."""
        if not self.channel_users:
            return
            
        # If target_channel is specified, only check that channel
        channels_to_check = [target_channel] if target_channel else [c['name'] for c in self.channels]
            
        # Check each channel for idle chat
        for channel_name in channels_to_check:
            # Skip if we're not in the channel
            if not self.is_in_channel(channel_name):
                continue
                
            # Get channel-specific idle chat interval and required idle time
            idle_chat_interval = self.get_channel_config(channel_name, 'idle_chat_interval', 0)
            idle_chat_time = self.get_channel_config(channel_name, 'idle_chat_time', idle_chat_interval)  # Default to interval
            if idle_chat_interval <= 0:
                continue

            # Check if channel has been idle long enough
            channel_lower = channel_name.lower()
            channel_history = self.ai_client.chat_history.get(channel_lower, [])
            if channel_history:
                now = time.time()
                last_chat_time = self.last_chat_times.get(channel_lower, 0)
                time_since_last_chat = now - last_chat_time
                
                # Skip if channel hasn't been idle long enough
                if time_since_last_chat < idle_chat_time:
                    self.logger.debug(f"Skipping idle chat in {channel_name} - channel not idle long enough ({time_since_last_chat:.0f}s < {idle_chat_time}s)")
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
                self.current_nick,  # Use current_nick
                channel=channel_name, 
                include_history=include_history,
                add_to_history=False    # Don't add the prompt to history
            )
            if message:
                self.send_channel_message(channel_name, message)
                self.logger.info(f"Sent idle chat to {channel_name}: {message}")

    def _random_action(self, target_channel=None):
        """Perform a random action (topic change or kick) based on enabled actions in config."""
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

            # Check if channel has been idle long enough
            channel_lower = channel_name.lower()
            last_chat = self.last_chat_times.get(channel_lower, 0)
            idle_chat_time = self.get_channel_config(channel_name, 'idle_chat_time', random_action_interval)
            now = time.time()
            
            if (now - last_chat) < idle_chat_time:
                self.logger.warning(f"Skipping random action in {channel_name} - channel not idle long enough ({now - last_chat:.0f}s < {idle_chat_time}s)")
                continue

            # Check if bot is opped in the channel
            channel_users = self.channel_users.get(channel_name, {})
            bot_user = channel_users.get(self.current_nick, {})
            if not bot_user.get('op', False):
                self.logger.warning(f"Skipping random action in {channel_name} - bot is not opped")
                continue

            # Get enabled random actions from config
            random_actions = self.get_channel_config(channel_name, 'random_actions', {'kick': True, 'topic': True})
            enabled_actions = [action for action, enabled in random_actions.items() if enabled]

            if not enabled_actions:
                self.logger.debug(f"No random actions enabled for {channel_name}")
                continue

            action = random.choice(enabled_actions)
            self.logger.debug(f"Selected random action for {channel_name}: {action}")

            if action == 'topic':
                # Use the channel-specific topic prompt
                prompt = self.get_channel_config(channel_name, 'ai_prompt_topic', self.config['ai_prompt_topic'])
                topic = self.ai_client.generate_topic(channel_name)
                if topic:
                    # Format the topic to remove encapsulating quotes
                    formatted_topic = self.format_message(topic)
                    self.send_raw(f"TOPIC {channel_name} :{formatted_topic}")
            
            elif action == 'kick':
                # Get list of recently active users in the channel
                recent_users = self.ai_client.get_recent_users(channel_name)
                
                # Filter possible targets to only include recently active non-op users
                possible_targets = [
                    nick for nick in recent_users
                    if nick in channel_users  # User is still in channel
                    and nick.lower() != self.current_nick.lower()  # Not the bot (case insensitive)
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
        # Start random actions thread
        actions_thread = threading.Thread(target=self.random_actions_loop, daemon=True, name="RandomActionsLoop")
        actions_thread.start()
        self.logger.info("Started random actions loop thread")
        
        # Connect and handle reconnects
        self.connect()
        time.sleep(2)  # Wait for connection to stabilize
        
        # Keep the main thread alive while running
        while self.running:
            if not self.connected and self.running:  # Only reconnect if still running
                self.reconnect()
            time.sleep(1)
        
        self.logger.info("Bot shutdown complete")

    def update_config(self, new_config):
        """Update bot configuration and reset timers."""
        # Store old config for comparison
        old_config = self.config

        # Update main config
        self.config = new_config
        self.channels = new_config['channels']

        # Update core bot settings
        self.nick = new_config['nick']
        self.altnick = new_config.get('altnick', f"{self.nick}_")
        self.realname = new_config['realname']
        self.ident = new_config['ident']
        self.servers = new_config['servers']

        # Update component configurations
        self.permissions.update_config(new_config)
        self.ai_client.update_config(new_config)  # This will handle all AI-related settings
        self.floodpro = FloodProtection(new_config)

        # Update rate limiter settings if changed
        if (old_config.get('irc_burst_size') != new_config.get('irc_burst_size') or
            old_config.get('irc_fill_rate') != new_config.get('irc_fill_rate')):
            burst_size = new_config.get('irc_burst_size', 4)
            fill_rate = new_config.get('irc_fill_rate', 1.0)
            self.rate_limiter = TokenBucket(capacity=burst_size, fill_rate=fill_rate)
            self.logger.debug(f"Updated rate limiter: burst={burst_size}, rate={fill_rate}")

        # Reset action timers to trigger based on new intervals
        now = time.time()
        for channel in self.channels:
            channel_name = channel['name']
            channel_lower = channel_name.lower()
            
            # Reset idle chat timer if interval changed
            old_idle_interval = self.get_channel_config(channel_name, 'idle_chat_interval', 0)
            if old_idle_interval > 0:
                last_chat = self.last_chat_times.get(channel_lower, now)
                time_since_chat = now - last_chat
                # Only reset if we're past the new interval
                if time_since_chat >= old_idle_interval:
                    self.last_chat_times[channel_lower] = now
                    self.logger.debug(f"Reset idle chat timer for {channel_name} - was {time_since_chat:.0f}s since last chat")
            
            # Reset random action timer if interval changed
            old_action_interval = self.get_channel_config(channel_name, 'random_action_interval', 0)
            if old_action_interval > 0:
                last_action = self.last_action_times.get(channel_lower, now)
                time_since_action = now - last_action
                # Only reset if we're past the new interval
                if time_since_action >= old_action_interval:
                    self.last_action_times[channel_lower] = now
                    self.logger.debug(f"Reset random action timer for {channel_name} - was {time_since_action:.0f}s since last action")

        # Update usermode if changed
        if old_config.get('usermode') != new_config.get('usermode'):
            usermode = new_config.get('usermode')
            if usermode and self.registration_complete:
                self.logger.info(f"Setting new user mode: {usermode}")
                self.send_raw(f"MODE {self.current_nick} {usermode}")

        self.logger.debug("Updated configuration and reset action timers")

    def generate_idle_chat(self):
        """Generate and send an idle chat message."""
        message = self.ai_client.get_response(self.config['ai_prompt_idle'], self.current_nick)
        if message:
            self.send_channel_message(self.current_channel, message)

    def generate_random_topic(self):
        """Generate and set a random topic."""
        topic = self.ai_client.generate_topic(self.config['ai_prompt_topic'])
        if topic:
            # Format the topic to remove encapsulating quotes
            formatted_topic = self.format_message(topic)
            for channel in self.channel_users.keys():
                self.send_raw(f"TOPIC {channel} :{formatted_topic}")

    def generate_random_kick(self):
        """Generate and perform a random kick."""
        reason = self.ai_client.generate_kick_reason(self.config['ai_prompt_kick'])

    def _should_continue_conversation(self, channel):
        """Check if we should continue participating in conversation for this channel."""
        # Get channel-specific settings
        ai_continue = self.get_channel_config(channel, 'ai_continue', False)
        if not ai_continue:
            return False
            
        # Check if we've been triggered recently
        last_trigger = self.last_trigger_times.get(channel.lower(), 0)
        if not last_trigger:
            return False
            
        # Get continuation timeout
        timeout_mins = self.get_channel_config(channel, 'ai_continue_mins', 5)
        timeout_secs = timeout_mins * 60
        
        # Check if we're still within the timeout period
        time_since_trigger = time.time() - last_trigger
        within_timeout = time_since_trigger <= timeout_secs
        
        return within_timeout

    def _update_trigger_time(self, channel):
        """Update the last trigger time for a channel and initialize conversation timer."""
        channel_lower = channel.lower()
        now = time.time()
        self.last_trigger_times[channel_lower] = now
        
        # Initialize or update the conversation timer
        if self._should_continue_conversation(channel):
            continue_freq = self.get_channel_config(channel, 'ai_continue_freq', 30)
            self.conversation_timers[channel_lower] = now + continue_freq
            self.logger.debug(f"Scheduled next response for {channel} in {continue_freq}s")

    def handle_channel_message(self, nick, userhost, channel, message):
        """Handle a channel message."""
        # Use lowercase channel name for consistency
        channel_lower = channel.lower()
        
        # Get global ignores
        global_ignores = [n.lower() for n in self.get_channel_config(channel, 'ignore_nicks', [])]
        
        # Get channel-specific ignores
        channel_config = None
        for c in self.channels:
            if isinstance(c, dict) and c.get('name', '').lower() == channel.lower():
                channel_config = c
                break
        
        channel_ignores = [n.lower() for n in channel_config.get('ignore_nicks', [])] if channel_config else []
        
        # Combine ignore lists
        ignore_list = list(set(global_ignores + channel_ignores))  # Deduplicate combined list
        
        # Get global regex ignores
        global_regex = self.get_channel_config(channel, 'ignore_regex', [])
        
        # Get regex ignore patterns
        channel_regex = self.get_channel_config(channel, 'ignore_regex', [])
        regex_patterns = list(set(global_regex + channel_regex))  # Deduplicate combined list
        
        # Check if this nick should be ignored - do this first before any processing
        nick_lower = nick.lower()
        if nick_lower in ignore_list:
            ignore_source = 'global' if nick_lower in global_ignores else 'channel'
            self.logger.info(f"Ignored message in {channel} from {nick} ({ignore_source} ignore list) - message: {message}")
            return
            
        # Check if message matches any ignore regex patterns
        for pattern in regex_patterns:
            try:
                if re.search(pattern, message):
                    ignore_source = 'global' if pattern in global_regex else 'channel'
                    self.logger.info(f"Ignored message in {channel} matching pattern '{pattern}' ({ignore_source} ignore_regex) - message: {message}")
                    return
            except re.error as e:
                self.logger.error(f"Invalid regex pattern '{pattern}': {e}")
                continue

        # Check for channel flood
        if not self.floodpro.check_channel_flood(channel, nick, userhost):
            # Get and execute ban commands
            for cmd in self.floodpro.get_ban_command(channel, nick, userhost):
                self.send_raw(cmd)
            return

        # Check for commands first
        cmd_prefix = self.get_channel_config(channel, 'cmd_prefix', '!')  # Default to ! if not configured
        if message.startswith(cmd_prefix):
            parts = message[len(cmd_prefix):].split()
            if parts:
                command = parts[0].lower()
                args = parts[1:]
                self.logger.debug(f"Command detected: {command} from {nick} in {channel}")
                self.handler._handle_command(command, nick, channel, args)
                return

        # Add message to history (only if not a command)
        history_entry = f"{nick}: {message}"
        self.ai_client.add_to_history(history_entry, channel_lower)

        # Update last chat time for any user's message (except our own)
        if nick.lower() != self.current_nick.lower():
            self.last_chat_times[channel_lower] = time.time()

        # If sleeping and not a command, don't process AI responses
        if self.is_sleeping(channel):
            self.logger.debug(f"Skipping AI processing in {channel} - bot is sleeping")
            return

        # Skip if we were the last to speak (unless it's a direct message)
        message_lower = message.lower()
        is_direct = message_lower.startswith(f"{self.current_nick.lower()}:")
        if not is_direct and self.was_last_speaker(channel):
            self.logger.debug(f"Skipping response in {channel} - bot was last speaker")
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
        if is_direct:
            # Direct messages always get a response and update trigger time
            self._update_trigger_time(channel_lower)
            
            # Check if we should include chat history context
            include_history = self.get_channel_config(channel, 'ai_context_direct', False)
            self.logger.info(f"Direct message in {channel} - using {'context' if include_history else 'no context'}")
            
            response = self.ai_client.get_response(
                message, 
                self.current_nick,
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
            if is_direct:
                return
                
            # Check for nickname in message with more flexible matching
            if self.current_nick.lower() in message_lower:
                # Mentions also get a response and update trigger time
                self._update_trigger_time(channel_lower)
                
                self.logger.info(f"Bot mentioned by {nick} in {channel}")
                # Check if we should include chat history context
                include_history = self.get_channel_config(channel, 'ai_context_mention', True)
                response = self.ai_client.get_response(
                    message,
                    self.current_nick,
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

    def handle_private_message(self, nick, userhost, message):
        """Handle a private message."""
        # Check for private message flood
        if not self.floodpro.check_privmsg_flood(nick, userhost):
            return

        # Tempoary disable private messages
        return

        # Process message if not flood
        response = self.ai_client.get_response(message, self.current_nick)  # Use current_nick
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
        # Find channel config - ensure case-insensitive comparison
        channel_lower = channel.lower()
        channel_config = next(
            (c for c in self.channels if c['name'].lower() == channel_lower),
            None
        )
        
        # First check channel-specific override if it exists
        if channel_config is not None:
            # Handle nested keys with dots (e.g. 'commands.kick')
            if '.' in key:
                parts = key.split('.')
                value = channel_config
                for part in parts:
                    if isinstance(value, dict) and part in value:
                        value = value[part]
                    else:
                        value = None
                        break
                if value is not None:
                    return value
            elif key in channel_config:
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
        
        # If the command is explicitly configured for this channel, use those settings
        if channel_config and 'commands' in channel_config and command in channel_config['commands']:
            channel_cmd_config = channel_config['commands'][command]
            self.logger.debug(
                f"Using channel-specific config for {command} in {channel}: "
                f"channel={channel_cmd_config} (overriding global={global_cmd_config})"
            )
            return channel_cmd_config
            
        # Otherwise use global config
        self.logger.debug(
            f"Using global config for {command} in {channel}: {global_cmd_config}"
        )
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
        if nick.lower() == self.current_nick.lower():
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

    def handle_nick(self, nick, userhost, params):
        """Handle NICK command."""
        new_nick = params.lstrip(':')
        
        # Track our own nick changes
        if nick.lower() == self.current_nick.lower():
            old_nick = self.current_nick
            self.current_nick = new_nick
            if new_nick == self.nick:
                self.logger.info(f"Successfully recovered primary nickname {self.nick}")
            else:
                self.logger.debug(f"Our nickname changed from {old_nick} to {new_nick}")
        
        # Update user tracking
        if nick in self.users:
            user_data = self.users[nick]  # Save the data before removing
            self.users[new_nick] = user_data  # Add with new nick
            del self.users[nick]  # Remove old nick
            
        # Update channel user tracking
        for channel in self.channel_users.values():
            if nick in channel:
                user_data = channel[nick]  # Save the data before removing
                channel[new_nick] = user_data  # Add with new nick
                del channel[nick]  # Remove old nick
                
        self.logger.debug(f"User {nick} changed nick to {new_nick}")

    def is_sleeping(self, channel):
        """Check if the bot is currently sleeping in a channel."""
        channel_lower = channel.lower()
        if channel_lower in self.sleep_until:
            now = time.time()
            if now >= self.sleep_until[channel_lower]:
                # Sleep time has expired, wake up
                del self.sleep_until[channel_lower]
                self.logger.info(f"Bot automatically woke up in {channel}")
                return False
            return True
        return False

    def handle_sleep_command(self, nick, channel, args):
        """Handle the sleep command."""
        if not args:
            self.send_channel_message(channel, f"{self.get_channel_config(channel, 'cmd_prefix', '!')}sleep <minutes>")
            return

        try:
            minutes = int(args[0])
            if minutes <= 0:
                self.send_channel_message(channel, "Sleep time must be positive")
                return

            # Get sleep_max from config (channel-specific or global)
            sleep_max = self.get_channel_config(channel, 'sleep_max', 60)
            
            if minutes > sleep_max:
                self.send_channel_message(channel, f"Sleep time cannot exceed {sleep_max} minutes")
                return

            channel_lower = channel.lower()
            self.sleep_until[channel_lower] = time.time() + (minutes * 60)
            self.logger.info(f"Bot put to sleep in {channel} for {minutes} minutes by {nick}")
            self.send_channel_message(channel, f"Going to sleep for {minutes} minutes. Wake me with {self.get_channel_config(channel, 'cmd_prefix', '!')}wake")

        except ValueError:
            self.send_channel_message(channel, "Sleep time must be a number")

    def handle_wake_command(self, nick, channel, args):
        """Handle the wake command."""
        channel_lower = channel.lower()
        if channel_lower in self.sleep_until:
            del self.sleep_until[channel_lower]
            self.logger.info(f"Bot woken up in {channel} by {nick}")
            self.send_channel_message(channel, "I'm awake! Ready to chat again.")
        else:
            self.send_channel_message(channel, "I wasn't sleeping!")

    def handle_mode(self, nick, userhost, params):
        """Handle MODE command."""
        parts = params.split()
        if len(parts) < 2:
            return
            
        channel = parts[0]
        if channel not in self.channel_users:
            return

        modes = parts[1]
        mode_params = parts[2:]
        adding = True
        param_index = 0
        
        # Track which modes require parameters
        param_modes = 'ovbkl'  # Common IRC modes that require parameters
        
        # Process each mode character
        for mode in modes:
            if mode == '+':
                adding = True
                continue
            elif mode == '-':
                adding = False
                continue
                
            # If this mode requires a parameter and we have parameters left
            if mode in param_modes and param_index < len(mode_params):
                target = mode_params[param_index]
                
                # Handle user modes (op and voice)
                if mode in 'ov' and target in self.channel_users[channel]:
                    old_status = self.channel_users[channel][target].copy()
                    
                    if mode == 'o':
                        self.channel_users[channel][target]['op'] = adding
                        status = "opped" if adding else "de-opped"
                        self.logger.info(f"User {target} was {status} in {channel} by {nick}")
                    elif mode == 'v':
                        self.channel_users[channel][target]['voice'] = adding
                        status = "voiced" if adding else "de-voiced"
                        self.logger.info(f"User {target} was {status} in {channel} by {nick}")
                        
                    # Log the full mode change details
                    mode_char = '+' if adding else '-'
                    self.logger.debug(
                        f"Mode change in {channel} by {nick}: {mode_char}{mode} {target} "
                        f"(op: {old_status['op']}->{self.channel_users[channel][target]['op']}, "
                        f"voice: {old_status['voice']}->{self.channel_users[channel][target]['voice']})"
                    )
                
                param_index += 1
            
            # Handle modes that don't require parameters
            elif mode not in param_modes:
                # Just log channel modes that don't affect user status
                mode_char = '+' if adding else '-'
                self.logger.debug(f"Channel mode change in {channel} by {nick}: {mode_char}{mode}")

    def reload_config(self):
        """Reload configuration from file."""
        try:
            with open(self.config_file, 'r') as f:
                new_config = yaml.safe_load(f)
            self.update_config(new_config)
            return True
        except Exception as e:
            self.logger.error(f"Failed to reload configuration: {e}")
            return False