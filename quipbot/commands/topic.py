"""Topic command for QuipBot."""

from . import Command

class TopicCommand(Command):
    @property
    def name(self):
        return "topic"

    @property
    def help(self):
        prefix = self.bot.config.get('cmd_prefix', '!')
        return f"Change the channel topic. Usage: {prefix}topic <new topic>"

    def execute(self, nick, channel, args):
        """Execute the topic command."""
        if args:
            topic = " ".join(args)
        else:
            # Get channel-specific topic prompt if set, otherwise use global
            prompt = self.bot.get_channel_config(channel, 'ai_prompt_topic', self.bot.config['ai_prompt_topic'])
            topic = self.bot.ai_client.generate_topic(prompt, channel=channel)
            
        if topic:
            # Format the topic to remove encapsulating quotes
            formatted_topic = self.bot.format_message(topic)
            self.bot.send_raw(f"TOPIC {channel} :{formatted_topic}")
            
        return None 