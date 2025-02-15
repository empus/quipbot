"""Topic command for QuipBot."""

from . import Command

class TopicCommand(Command):
    @property
    def name(self):
        return "topic"

    @property
    def help(self):
        # Get prefix from channel if available, otherwise use global
        prefix = self.bot.get_channel_config(self.bot.channel if hasattr(self.bot, 'channel') else None, 'cmd_prefix', '!')
        return f"Change the channel topic. Usage: {prefix}topic <new topic>"

    def execute(self, nick, channel, args):
        """Execute the topic command."""
        if args:
            topic = " ".join(args)
        else:
            topic = self.bot.ai_client.generate_topic(channel=channel)
            
        if topic:
            # Format the topic to remove encapsulating quotes
            formatted_topic = self.bot.format_message(topic)
            self.bot.send_raw(f"TOPIC {channel} :{formatted_topic}")
            
        return None 