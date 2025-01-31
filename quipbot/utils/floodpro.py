"""Flood protection for QuipBot."""

import time
import logging
from collections import defaultdict

class FloodProtection:
    def __init__(self, config):
        """Initialize flood protection."""
        self.config = config
        self.logger = logging.getLogger('QuipBot')
        self.channel_history = defaultdict(lambda: defaultdict(list))  # {channel: {nick: [timestamps]}}
        self.privmsg_history = defaultdict(list)  # {nick: [timestamps]}
        self.ignored_users = {}  # {nick: expiry_timestamp}
        self.banned_users = defaultdict(dict)  # {channel: {nick: expiry_timestamp}}

    def check_channel_flood(self, channel, nick, userhost, is_op=False, is_admin=False):
        """Check if a user is flooding a channel.
        
        Returns:
            bool: True if the message should be processed, False if it's flood
        """
        # Skip if user is op or admin
        if is_op or is_admin:
            return True

        # Skip if no flood protection for this channel
        channel_config = next((c for c in self.config['channels'] if c['name'] == channel), None)
        if not channel_config or 'floodpro' not in channel_config:
            return True

        # Check if user is currently banned
        if self._is_banned(channel, nick):
            return False

        flood_config = channel_config['floodpro']
        timestamps = self.channel_history[channel][nick]
        current_time = time.time()

        # Remove old timestamps
        timestamps = [t for t in timestamps if current_time - t <= flood_config['seconds']]
        self.channel_history[channel][nick] = timestamps

        # Add new timestamp
        timestamps.append(current_time)

        # Check for flood
        if len(timestamps) >= flood_config['lines']:
            # User is flooding - ban them
            ban_duration = flood_config['ban_time'] * 60  # Convert to seconds
            self.banned_users[channel][nick] = current_time + ban_duration

            # Clear their message history
            self.channel_history[channel][nick] = []

            self.logger.warning(
                f"Channel flood detected from {nick} ({userhost}) in {channel}. "
                f"Banned for {flood_config['ban_time']} minutes."
            )

            return False

        return True

    def check_privmsg_flood(self, nick, userhost, is_admin=False):
        """Check if a user is flooding via private messages.
        
        Returns:
            bool: True if the message should be processed, False if it's flood
        """
        # Skip if user is admin
        if is_admin:
            return True

        # Skip if no flood protection config
        if 'privmsg_floodpro' not in self.config:
            return True

        # Check if user is currently ignored
        if self._is_ignored(nick):
            return False

        flood_config = self.config['privmsg_floodpro']
        timestamps = self.privmsg_history[nick]
        current_time = time.time()

        # Remove old timestamps
        timestamps = [t for t in timestamps if current_time - t <= flood_config['seconds']]
        self.privmsg_history[nick] = timestamps

        # Add new timestamp
        timestamps.append(current_time)

        # Check for flood
        if len(timestamps) >= flood_config['lines']:
            # User is flooding - ignore them
            ignore_duration = flood_config['ignore_time'] * 60  # Convert to seconds
            self.ignored_users[nick] = current_time + ignore_duration

            # Clear their message history
            self.privmsg_history[nick] = []

            self.logger.warning(
                f"Private message flood detected from {nick} ({userhost}). "
                f"Ignored for {flood_config['ignore_time']} minutes."
            )
            return False

        return True

    def _is_banned(self, channel, nick):
        """Check if a user is currently banned from a channel."""
        current_time = time.time()
        if channel in self.banned_users and nick in self.banned_users[channel]:
            if current_time < self.banned_users[channel][nick]:
                return True
            else:
                # Ban expired
                del self.banned_users[channel][nick]
                self.logger.info(f"Ban expired for {nick} in {channel}")
        return False

    def _is_ignored(self, nick):
        """Check if a user is currently ignored."""
        current_time = time.time()
        if nick in self.ignored_users:
            if current_time < self.ignored_users[nick]:
                return True
            else:
                # Ignore expired
                del self.ignored_users[nick]
                self.logger.info(f"Ignore expired for {nick}")
        return False

    def get_ban_command(self, channel, nick, userhost):
        """Get the ban command for a user."""
        # Convert nick!user@host to *!*@host format
        ban_mask = f"*!*@{userhost.split('@')[1]}"
        channel_config = next(c for c in self.config['channels'] if c['name'] == channel)
        duration = channel_config['floodpro']['ban_time']
        return [
            f"MODE {channel} +b {ban_mask}",
            f"KICK {channel} {nick} :Flood protection - banned for {duration} minutes"
        ] 