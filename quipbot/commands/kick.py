"""Command to kick a user from the channel."""

from . import Command

class KickCommand(Command):
    def __init__(self, bot):
        """Initialize kick command."""
        super().__init__(bot)
        self._name = "kick"
        self._help = "Kick a user from the channel"
        self._usage = "kick <nick> [reason]"
        
    @property
    def name(self):
        """Command name."""
        return "kick"
        
    @property
    def help(self):
        """Command help text."""
        return self._help
        
    @property
    def usage(self):
        """Command usage text."""
        return self._usage
        
    def execute(self, nick, channel, args):
        """Execute the kick command."""
        if not args:
            return "Who do you want me to kick?"
            
        target = args[0]
        
        # Check if target is in the channel
        channel_users = self.bot.channel_users.get(channel, {})
        if target not in channel_users:
            return f"I don't see {target} in the channel!"
            
        # Check if target is protected
        if self.bot.is_protected_user(channel, target):
            return f"I can't kick {target} - they're too powerful!"
            
        # Get kick reason from remaining args or generate one
        if len(args) > 1:
            reason = " ".join(args[1:])
        else:
            prompt = self.bot.get_channel_config(channel, 'ai_prompt_kick', self.bot.config['ai_prompt_kick'])
            reason = self.bot.ai_client.generate_kick_reason(prompt, channel=channel)
            
        if reason:
            # Format the kick reason to remove encapsulating quotes
            formatted_reason = self.bot.format_message(reason)
            self.bot.send_raw(f"KICK {channel} {target} :{formatted_reason}")
        else:
            self.bot.send_raw(f"KICK {channel} {target} :Kicked by {nick}")
            
        return None  # No response needed since we're sending the KICK directly 