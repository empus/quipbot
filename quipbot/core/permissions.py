"""Permissions management for QuipBot."""

import fnmatch
import logging

logger = logging.getLogger('QuipBot')

class PermissionManager:
    def __init__(self, config):
        """Initialize permission manager."""
        self.config = config
        self.logger = logger

    def update_config(self, new_config):
        """Update configuration."""
        self.config = new_config

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
        """Check if a user is a bot administrator.
        
        Args:
            nick: The nickname to check
            userhost: The user@host to check
            
        Returns:
            bool: True if user is an admin, False otherwise
        """
        if not userhost:
            return False
            
        # Get admin list from config
        admins = self.config.get('admins', [])
        
        # Check each admin pattern
        for pattern in admins:
            # If pattern contains @ it's a userhost pattern
            if '@' in pattern:
                if self._match_userhost(userhost, pattern):
                    return True
            # Otherwise it's a nickname pattern
            else:
                if nick.lower() == pattern.lower():
                    return True
                    
        return False
        
    def _match_userhost(self, userhost, pattern):
        """Match a userhost against a pattern.
        
        Args:
            userhost: The user@host to check
            pattern: The pattern to match against
            
        Returns:
            bool: True if userhost matches pattern, False otherwise
        """
        # Convert pattern to regex
        import re
        pattern = pattern.replace('.', '\\.').replace('*', '.*')
        return bool(re.match(pattern, userhost, re.IGNORECASE))
        
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