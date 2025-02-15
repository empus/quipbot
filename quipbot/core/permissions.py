"""Permissions management for QuipBot."""

import fnmatch
import logging
from collections import defaultdict
import time

logger = logging.getLogger('QuipBot')

class PermissionManager:
    def __init__(self, config):
        """Initialize permission manager."""
        self.config = config
        self.logger = logger
        self.admin_cache = {}  # {(nick, userhost): (result, timestamp)}
        self.cache_ttl = 60  # Cache results for 60 seconds
        self.bot = None  # Will be set by IRCBot after initialization

    def set_bot(self, bot):
        """Set the bot instance reference."""
        self.bot = bot

    def update_config(self, new_config):
        """Update configuration."""
        self.config = new_config
        self.admin_cache.clear()  # Clear cache when config changes

    def _get_channel_config(self, channel, key, default=None):
        """Get channel-specific config value."""
        if not channel:
            return self.config.get(key, default)
            
        # Find channel config
        channel_config = next(
            (c for c in self.config['channels'] if c['name'].lower() == channel.lower()),
            None
        )
        
        # Check channel-specific override
        if channel_config and key in channel_config:
            return channel_config[key]
            
        # Fall back to global config
        return self.config.get(key, default)

    def _get_command_config(self, command, channel=None):
        """Get command configuration with channel overrides."""
        # Get global command config
        global_cmd_config = self.config.get('commands', {}).get(command, {})
        
        if not channel:
            return global_cmd_config
            
        # Get channel-specific command config
        channel_config = next(
            (c for c in self.config['channels'] if c['name'].lower() == channel.lower()),
            None
        )
        if channel_config and 'commands' in channel_config:
            channel_cmd_config = channel_config['commands'].get(command, {})
            # Merge with global config, channel config takes precedence
            return {**global_cmd_config, **channel_cmd_config}
            
        return global_cmd_config

    def is_admin(self, nick, userhost):
        """Check if a user is a bot administrator."""
        if not userhost:
            return False

        # Check cache first
        cache_key = (nick.lower(), userhost.lower())
        now = time.time()
        if cache_key in self.admin_cache:
            result, timestamp = self.admin_cache[cache_key]
            if now - timestamp < self.cache_ttl:
                return result
            else:
                # Remove expired cache entry
                del self.admin_cache[cache_key]
            
        # Get admin list from config
        admins = self.config.get('admins', [])
        
        # First check if we have user data stored
        user_data = self.bot.users.get(nick, {})
        if user_data:
            ident = user_data.get('ident', '')
            host = user_data.get('host', '')
        else:
            # Fall back to splitting userhost if no stored data
            if '@' in userhost:
                ident, host = userhost.split('@', 1)
            else:
                ident = ''
                host = userhost
        
        # Create full nick!user@host format
        full_mask = f"{nick}!{ident}@{host}"
        
        # Check each admin pattern
        for pattern in admins:
            # If pattern contains ! or @, it's a full mask pattern
            if '!' in pattern or '@' in pattern:
                # If pattern doesn't contain !, add wildcard for ident/host part
                if '!' not in pattern and '@' in pattern:
                    pattern = f"*!{pattern}"
                # If pattern doesn't contain @, add wildcard for host part
                elif '!' in pattern and '@' not in pattern:
                    pattern = f"{pattern}@*"
                # Match against full mask
                if self._match_mask(full_mask, pattern):
                    self.logger.debug(f"Admin match: {nick} matches pattern {pattern}")
                    self.admin_cache[cache_key] = (True, now)
                    return True
            # Otherwise it's a nickname or account pattern
            else:
                # Check for account match if we have account data
                if user_data.get('account') and user_data['account'].lower() == pattern.lower():
                    self.logger.debug(f"Admin match: {nick} matches account {pattern}")
                    self.admin_cache[cache_key] = (True, now)
                    return True
                # Check for nickname match
                if nick.lower() == pattern.lower():
                    self.logger.debug(f"Admin match: {nick} matches nickname {pattern}")
                    self.admin_cache[cache_key] = (True, now)
                    return True
                    
        # Cache negative result
        self.admin_cache[cache_key] = (False, now)
        return False
        
    def _match_mask(self, mask, pattern):
        """Match a mask against a pattern, supporting IRC-style wildcards."""
        # Convert IRC-style pattern to regex
        # 1. Escape special regex chars except * and ?
        special_chars = '.+^$[](){}|\\'
        regex_pattern = ''.join('\\' + c if c in special_chars else c for c in pattern)
        
        # 2. Convert * to match anything (including ! and @)
        regex_pattern = regex_pattern.replace('*', '.*?')
        
        # 3. Convert ? to match single character
        regex_pattern = regex_pattern.replace('?', '.')
        
        # 4. Add start/end anchors
        regex_pattern = f"^{regex_pattern}$"
        
        # Try to match
        try:
            import re
            return bool(re.match(regex_pattern, mask, re.IGNORECASE))
        except re.error as e:
            self.logger.error(f"Invalid pattern '{pattern}': {e}")
            return False
        
    def check_command_permission(self, command, nick, userhost, channel_info):
        """Check if a user has permission to use a command.
        
        Args:
            command: The command name
            nick: The user's nickname
            userhost: The user's userhost
            channel_info: The user's channel info dict
            
        Returns:
            bool: True if user has permission, False otherwise
        """
        # Get command config
        cmd_config = self.config.get('commands', {}).get(command, {})
        
        # Check if user is admin first
        if self.is_admin(nick, userhost):
            return True
            
        # Get required permission level
        required = cmd_config.get('requires', 'any').lower()
        
        # Handle different permission levels
        if required == 'admin':
            return False
            
        elif required == 'op':
            return channel_info.get('op', False)
            
        elif required == 'voice':
            return channel_info.get('voice', False) or channel_info.get('op', False)
            
        # 'any' permission level always returns True
        return True 