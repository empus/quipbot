"""Command to kick a user from the channel."""

def handle_command(bot, channel, nick, args):
    """Handle the kick command."""
    
    # Check permissions
    if not bot.permissions.check_command_access(channel, nick, 'kick'):
        bot.send_channel_message(channel, "Nice try, but you don't have the power to kick anyone!")
        return
        
    if not args:
        bot.send_channel_message(channel, "Who do you want me to kick?")
        return
        
    target = args[0]
    
    # Check if target is in the channel
    channel_users = bot.channel_users.get(channel, {})
    if target not in channel_users:
        bot.send_channel_message(channel, f"I don't see {target} in the channel!")
        return
        
    # Check if target is protected
    if bot.is_protected_user(channel, target):
        bot.send_channel_message(channel, f"I can't kick {target} - they're too powerful!")
        return
        
    # Get kick reason from remaining args or generate one
    if len(args) > 1:
        reason = " ".join(args[1:])
    else:
        prompt = bot.get_channel_config(channel, 'ai_prompt_kick', bot.config['ai_prompt_kick'])
        reason = bot.ai_client.generate_kick_reason(prompt, channel=channel)
        
    if reason:
        # Format the kick reason to remove encapsulating quotes
        formatted_reason = bot.format_message(reason)
        bot.send_raw(f"KICK {channel} {target} :{formatted_reason}")
    else:
        bot.send_raw(f"KICK {channel} {target} :Kicked by {nick}") 