"""Info command for QuipBot - displays key behavioral configuration settings."""

from . import Command

class InfoCommand(Command):
    @property
    def name(self):
        return "info"

    @property
    def help(self):
        prefix = self.get_prefix()
        return f"Display bot behavioral settings. Usage: {prefix}info"

    def execute(self, nick, channel, args):
        """Execute info command."""
        try:
            # Build response parts
            lines = []

            # Line 1: AI service info and command prefix
            ai_service = self.bot.get_channel_config(channel, 'ai_service', 'openai')
            ai_model = self.bot.get_channel_config(channel, 'ai_model', 'gpt-4o-mini')
            prefix = self.get_prefix(channel)
            lines.append(f"🤖 **QuipBot** v2.0 | ⚡ Prefix: **{prefix}** | 🎯 **AI**: Using **{ai_service}** with model **{ai_model}**")
            
            # Line 2: Group behavior settings
            behavior_parts = []
            if self.bot.get_channel_config(channel, 'ai_entrance', False):
                behavior_parts.append("entrance messages")
            idle_chat_interval = self.bot.get_channel_config(channel, 'idle_chat_interval', 0)
            idle_chat_time = self.bot.get_channel_config(channel, 'idle_chat_time', 0)
            if idle_chat_interval and idle_chat_time:
                # Convert to minutes if > 60 seconds
                if idle_chat_interval >= 60:
                    interval_str = f"**{idle_chat_interval // 60}** mins"
                else:
                    interval_str = f"**{idle_chat_interval}** secs"
                if idle_chat_time >= 60:
                    time_str = f"**{idle_chat_time // 60}** mins"
                else:
                    time_str = f"**{idle_chat_time}** secs"
                behavior_parts.append(f"idle chat every {interval_str} after {time_str} silence")

            random_action_interval = self.bot.get_channel_config(channel, 'random_action_interval', 0)
            if random_action_interval:
                if random_action_interval >= 60:
                    interval_str = f"**{random_action_interval // 60}** mins"
                else:
                    interval_str = f"**{random_action_interval}** secs"
                behavior_parts.append(f"random actions every {interval_str}")
            
            if behavior_parts:
                lines.append("🎭 **Behaviour**: " + " | ".join(behavior_parts))
            
            # Line 3: Interaction settings
            interaction_parts = []
            
            # Bot mentions and conversation continuation
            ai_mention = self.bot.get_channel_config(channel, 'ai_mention', False)
            ai_continue = self.bot.get_channel_config(channel, 'ai_continue', False)
            ai_continue_freq = self.bot.get_channel_config(channel, 'ai_continue_freq', 0)
            ai_continue_mins = self.bot.get_channel_config(channel, 'ai_continue_mins', 0)
            if ai_mention and ai_continue and ai_continue_freq and ai_continue_mins:
                if ai_continue_freq >= 60:
                    freq_str = f"**{ai_continue_freq // 60}** mins"
                else:
                    freq_str = f"**{ai_continue_freq}** secs"
                interaction_parts.append(f"continue chat every {freq_str} for **{ai_continue_mins}** mins after last mention")
            
            # Sleep settings
            sleep_max = self.bot.get_channel_config(channel, 'sleep_max', 0)
            if sleep_max:
                interaction_parts.append(f"sleep for up to **{sleep_max}** mins")
            
            # Response delay
            ai_delay = self.bot.get_channel_config(channel, 'ai_delay', [0, 0])
            if isinstance(ai_delay, list) and len(ai_delay) == 2:
                # Format delay values without .0
                delay_start = int(ai_delay[0]) if ai_delay[0].is_integer() else ai_delay[0]
                delay_end = int(ai_delay[1]) if ai_delay[1].is_integer() else ai_delay[1]
                interaction_parts.append(f"response delay **{delay_start}-{delay_end}** secs")
            
            if interaction_parts:
                lines.append("💭 **Interaction**: " + " | ".join(interaction_parts))

            # Line 4: Context settings
            context_types = []
            if self.bot.get_channel_config(channel, 'ai_context_direct', False):
                context_types.append("direct")
            if self.bot.get_channel_config(channel, 'ai_context_mention', False):
                context_types.append("mentions")
            if self.bot.get_channel_config(channel, 'ai_context_idle', False):
                context_types.append("idle")
            if self.bot.get_channel_config(channel, 'ai_context_topic', False):
                context_types.append("topics")
            
            chat_history = self.bot.get_channel_config(channel, 'chat_history', 0)
            if context_types and chat_history:
                context_info = f"📝 **Context**: **{chat_history}** lines for " + ", ".join(context_types)
                if self.bot.get_channel_config(channel, 'ai_nicklist', False):
                    context_info += ". Nicklist is included."
                lines.append(context_info)
            
            # Return list of lines for the bot to send separately
            if lines:
                # Send each line as a separate message, but don't add to chat history
                for line in lines:
                    self.bot.send_channel_message(channel, line, add_to_history=False)
                return None  # Return None since we've handled the sending
            else:
                return "No behavioral settings are currently enabled."
            
        except Exception as e:
            self.bot.logger.error(f"Error in info command: {e}", exc_info=True)
            return f"Error retrieving info: {e}" 