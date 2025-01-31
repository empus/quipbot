"""Command to kick a random user from the channel."""

import random
from . import Command

class BootCommand(Command):
    @property
    def name(self):
        return "boot"

    @property
    def help(self):
        prefix = self.bot.config.get('cmd_prefix', '!')
        return f"Kick a random user from the channel. Usage: {prefix}boot"

    def execute(self, nick, channel, args):
        """Execute the boot command."""
        # Check permissions
        if not self.bot.permissions.has_permission('boot', nick, 
            self.bot.users.get(nick, {}), 
            self.bot.channel_users.get(channel, {}).get(nick, {}),
            channel):
            return "Nice try, but you don't have the power to boot anyone!"
            
        # Get list of recently active users in the channel
        recent_users = self.bot.ai_client.get_recent_users(channel)
        channel_users = self.bot.channel_users.get(channel, {})
        
        # Filter possible targets to only include non-protected users who are still in the channel
        possible_targets = [
            user for user in recent_users
            if user in channel_users  # User is still in channel
            and not self.bot.is_protected_user(channel, user)  # Not protected (bot, op, or admin)
            and user != nick  # Not the command issuer
        ]
        
        if not possible_targets:
            return "No suitable targets found. Everyone's either too powerful or too quiet!"
            
        # Pick a random target
        target = random.choice(possible_targets)
        
        # Get an AI-generated kick reason
        prompt = self.bot.get_channel_config(channel, 'ai_prompt_kick', self.bot.config['ai_prompt_kick'])
        reason = self.bot.ai_client.generate_kick_reason(prompt, channel=channel)
        
        if reason:
            # Format the kick reason to remove encapsulating quotes
            formatted_reason = self.bot.format_message(reason)
            self.bot.send_raw(f"KICK {channel} {target} :{formatted_reason}")
            return None
        else:
            self.bot.send_raw(f"KICK {channel} {target} :Random boot activated!")
            return None 