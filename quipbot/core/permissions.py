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

    def has_permission(self, command, nick, user_info, channel_info, channel=None):
        """Check if a user has permission to use a command.
        
        Args:
            command: The command name
            nick: User's nickname
            user_info: Dict containing user information
            channel_info: Dict containing user's channel status
            channel: Channel name for channel-specific permissions
            
        Returns:
            bool: True if user has permission, False otherwise
        """
        # Get command config with channel overrides
        cmd_config = self._get_command_config(command, channel)
        
        # Check if user is admin (either by nick or hostmask)
        host = user_info.get('host', '')
        if self.is_admin(nick, host):
            self.logger.debug(f"User {nick} ({host}) is admin - command {command} allowed")
            return True
            
        # Check admin_only restriction
        if cmd_config.get('admin_only', False):
            return False
            
        # Check op requirement
        if cmd_config.get('requires_op', False) and not channel_info.get('op', False):
            return False
            
        # Check voice requirement
        if cmd_config.get('requires_voice', False) and not channel_info.get('voice', False):
            return False
            
        return True

    def is_admin(self, nick, host):
        """Check if a user is an admin based on nick!user@host or account."""
        # First check exact nick matches in admin list
        if nick in self.config.get('admins', []):
            self.logger.debug(f"Admin match: exact nick {nick}")
            return True
            
        # Then check hostmask patterns
        if '@' in host:  # If we have a full hostmask
            user_mask = host  # Use the full hostmask as is
        else:
            user_mask = f"{nick}!{host}"  # Construct it from nick and host
            
        self.logger.debug(f"Checking admin match for: {user_mask}")
            
        for pattern in self.config.get('admins', []):
            # Skip patterns that look like exact nicks
            if not any(c in pattern for c in '*!@?'):
                continue
                
            try:
                if fnmatch.fnmatch(user_mask.lower(), pattern.lower()):
                    self.logger.debug(f"Admin match: hostmask {pattern} matches {user_mask}")
                    return True
            except Exception as e:
                self.logger.error(f"Error matching hostmask pattern {pattern}: {e}")
                
        return False 