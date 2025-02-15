"""Command to kick a random user from the channel."""

import random
from . import Command

class BootCommand(Command):
    @property
    def name(self):
        return "boot"

    @property
    def help(self):
        # Get prefix from channel if available, otherwise use global
        prefix = self.bot.get_channel_config(self.bot.channel if hasattr(self.bot, 'channel') else None, 'cmd_prefix', '!')
        return f"Kick a random user from the channel. Usage: {prefix}boot"

    def execute(self, nick, channel, args):
        """Execute the boot command."""
        # Get list of recently active users from chat history
        channel_lower = channel.lower()
        recent_users = self.bot.ai_client.get_recent_users(channel_lower)
        channel_users = self.bot.channel_users.get(channel, {})
        
        self.bot.logger.debug(f"Recent users in {channel}: {recent_users}")
        self.bot.logger.debug(f"Channel users in {channel}: {list(channel_users.keys())}")
        
        # Filter possible targets to only include recent users who are still in channel and not protected
        possible_targets = []
        for user in recent_users:
            if user not in channel_users:  # Skip if not in channel
                self.bot.logger.debug(f"Skipping {user} - not in channel")
                continue
                
            if channel_users[user].get('op', False):  # Skip if opped
                self.bot.logger.debug(f"Skipping {user} - is opped")
                continue
                
            if user.lower() == self.bot.current_nick.lower():  # Skip if bot
                self.bot.logger.debug(f"Skipping {user} - is bot")
                continue
                
            if user == nick:  # Skip if command issuer
                self.bot.logger.debug(f"Skipping {user} - is command issuer")
                continue
                
            if self.bot.is_protected_user(channel, user):  # Skip if admin
                self.bot.logger.debug(f"Skipping {user} - is admin/protected")
                continue
                
            possible_targets.append(user)
        
        self.bot.logger.debug(f"Possible targets after filtering in {channel}: {possible_targets}")
        
        if not possible_targets:
            return "No suitable targets found. Everyone's either too powerful or hasn't spoken recently!"
            
        # Pick a random target
        target = random.choice(possible_targets)
        self.bot.logger.debug(f"Selected target in {channel}: {target}")
        
        # Get an AI-generated kick reason
        prompt = self.bot.get_channel_config(channel, 'ai_prompt_kick', self.bot.config['ai_prompt_kick'])
        reason = self.bot.ai_client.generate_kick_reason(prompt, channel=channel)
        
        if reason:
            # Format the kick reason to remove encapsulating quotes
            formatted_reason = self.bot.format_message(reason)
            self.bot.send_raw(f"KICK {channel} {target} :{formatted_reason}")
        else:
            self.bot.send_raw(f"KICK {channel} {target} :Random boot activated!")
            
        return None  # No response needed since we're sending the KICK directly 