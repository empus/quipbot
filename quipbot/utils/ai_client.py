"""AI service integration for QuipBot using OpenAI-compatible APIs."""

from openai import OpenAI
import logging
from collections import defaultdict

logger = logging.getLogger('QuipBot')

# API base URLs for different services
API_URLS = {
    'openai': 'https://api.openai.com/v1',  # Base path for OpenAI API
    'perplexity': 'https://api.perplexity.ai/v1',  # Base path for Perplexity API
    'grok': 'https://api.grok.com/v1'  # Base path for Grok API
}

class AIClient:
    def __init__(self, config):
        """Initialize AI client with configuration."""
        self.config = config
        self.chat_history = defaultdict(list)  # {channel: [messages]}
        # Initialize with global config - will be overridden per channel as needed
        self.default_prompt = config['ai_prompt_default']
        self.model = config['ai_model']
        logger.info(f"Initialized AI client with model {self.model}")  # Add logging

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

    def _get_client_for_channel(self, channel):
        """Get OpenAI client with channel-specific configuration."""
        service = self._get_channel_config(channel, 'ai_service', 'openai')
        if service not in API_URLS:
            logger.warning(f"Unknown AI service '{service}' for channel {channel}, falling back to OpenAI")
            service = 'openai'
            
        api_key = self._get_channel_config(channel, 'ai_key', self.config['ai_key'])
        
        return OpenAI(
            api_key=api_key,
            base_url=API_URLS[service]
        )

    def _get_nicklist_context(self, channel):
        """Get nicklist context if enabled for the channel."""
        if not self._get_channel_config(channel, 'ai_nicklist', False):
            logger.debug(f"Nicklist disabled for channel {channel}")
            return ""
            
        if not hasattr(self, 'bot') or not self.bot:
            logger.warning("Bot reference not set in AI client")
            return ""
            
        channel_users = self.bot.channel_users.get(channel, {})
        if not channel_users:
            logger.debug(f"No users found in channel {channel}")
            return ""
            
        nicklist = sorted(channel_users.keys())  # Sort for consistent output
        nicklist_context = f"\nThis channel {channel} has users: {', '.join(nicklist)}"
        logger.debug(f"Generated nicklist context: {nicklist_context}")
        return nicklist_context

    def _get_prompt_with_nicklist(self, prompt_key, prompt_default, channel):
        """Get channel-specific prompt with nicklist context if enabled."""
        # Get base prompt
        prompt = self._get_channel_config(channel, prompt_key, prompt_default)
        
        # Add nicklist context if enabled
        nicklist_context = self._get_nicklist_context(channel)
        if nicklist_context:
            # If prompt ends with a newline, append directly, otherwise add a newline first
            if prompt.endswith('\n'):
                prompt += nicklist_context
            else:
                prompt += '\n' + nicklist_context
                
        return prompt

    def get_response(self, user_message, nick, channel=None, add_to_history=True, include_history=True):
        """Generate a response using the AI service."""
        try:
            # Get channel-specific configuration
            client = self._get_client_for_channel(channel)
            model = self._get_channel_config(channel, 'ai_model', self.config['ai_model'])
            
            # Get prompt with nicklist context
            prompt = self._get_prompt_with_nicklist('ai_prompt_default', self.config['ai_prompt_default'], channel)
            
            # Build context with or without history
            if include_history:
                # Get channel-specific history
                history = self.chat_history.get(channel, []) if channel else []
                history_size = self._get_channel_history_size(channel)
                
                # Get unique nicks from history for logging
                unique_nicks = set()
                for msg in history[-history_size:]:
                    if ': ' in msg:
                        unique_nicks.add(msg.split(': ', 1)[0])
                logger.debug(f"Including chat history with participants: {', '.join(sorted(unique_nicks))}")
                
                context = (
                    f"{prompt}\n\n"
                    "Conversation so far:\n"
                    + "\n".join(history[-history_size:])
                    + f"\n\n{nick}: {user_message}\n"
                    "Quip:"
                )
            else:
                # Just use the prompt and current message
                context = (
                    f"{prompt}\n\n"
                    f"{nick}: {user_message}\n"
                    "Quip:"
                )

            # Log the full API request payload
            api_payload = {
                "model": model,
                "messages": [{"role": "user", "content": context}],
                "max_tokens": 150,
                "temperature": 0.8,
            }
            logger.debug(f"API request payload for {channel}: {api_payload}")
            
            logger.debug(f"Sending API request to {client.base_url} for channel {channel}")
            response = client.chat.completions.create(**api_payload)
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"API error for channel {channel}: {str(e)}", exc_info=True)
            return "Uh... I'm speechless (error)."

    def add_to_history(self, message, channel):
        """Add a message to chat history for a specific channel."""
        if channel not in self.chat_history:
            self.chat_history[channel] = []
            
        history = self.chat_history[channel]
        history.append(message)
        
        # Get max history size for this channel
        max_history = self._get_channel_history_size(channel)
        
        # Trim history if needed
        if len(history) > max_history:
            history.pop(0)

    def _get_channel_history_size(self, channel):
        """Get the configured history size for a channel."""
        if not channel:
            return 20  # Default size
            
        # Find channel config
        channel_config = next(
            (c for c in self.config['channels'] if c['name'].lower() == channel.lower()),
            None
        )
        
        # Return configured size or default
        return channel_config.get('chat_history', 20) if channel_config else 20

    def get_recent_users(self, channel, within_messages=20):
        """Get list of users who have spoken recently in a channel."""
        if channel not in self.chat_history:
            return []
            
        recent_messages = self.chat_history[channel][-within_messages:]
        users = set()
        
        for msg in recent_messages:
            # Extract nick from "nick: message" format
            if ': ' in msg:
                nick = msg.split(': ', 1)[0]
                users.add(nick)
                
        return list(users)

    def generate_topic(self, prompt, channel=None):
        """Generate a random topic."""
        try:
            client = self._get_client_for_channel(channel)
            model = self._get_channel_config(channel, 'ai_model', self.config['ai_model'])
            
            # Get channel-specific topic prompt
            prompt = self._get_prompt_with_nicklist('ai_prompt_topic', prompt, channel)
            
            # Build context, including history only if enabled
            context = prompt
            
            # Check if we should include chat history context
            include_history = self._get_channel_config(channel, 'ai_context_topic', False)
            if include_history and channel:
                history = self.chat_history.get(channel, [])
                if history:
                    history_size = self._get_channel_history_size(channel)
                    recent_history = history[-history_size:]  # Only use most recent messages
                    context += "\n\nRecent channel conversation:\n"
                    context += "\n".join(recent_history)
                    context += "\n\nBased on this context, generate a topic that's relevant and witty.\n"
            
            # Log the full API request payload
            api_payload = {
                "model": model,
                "messages": [{"role": "user", "content": context}],
                "max_tokens": 50,
                "temperature": 0.9,
            }
            logger.debug(f"Topic API request payload for {channel}: {api_payload}")
            
            logger.debug(f"Sending topic generation request to {client.base_url} for channel {channel}")
            response = client.chat.completions.create(**api_payload)
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"API error generating topic for channel {channel}: {str(e)}", exc_info=True)
            return "Just another boring day in IRC..."

    def generate_entrance(self, prompt, channel=None):
        """Generate an entrance message."""
        try:
            # Check if entrance messages are enabled for this channel
            if not self._get_channel_config(channel, 'ai_entrance', True):
                return None
                
            client = self._get_client_for_channel(channel)
            model = self._get_channel_config(channel, 'ai_model', self.config['ai_model'])
            
            # Get prompt with nicklist context
            prompt = self._get_prompt_with_nicklist('ai_prompt_entrance', prompt, channel)
            
            # Log the full API request payload
            api_payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 50,
                "temperature": 0.9,
            }
            logger.debug(f"Entrance API request payload for {channel}: {api_payload}")
            
            logger.debug(f"Sending entrance message request to {client.base_url} for channel {channel}")
            response = client.chat.completions.create(**api_payload)
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"API error generating entrance for channel {channel}: {str(e)}", exc_info=True)
            return "Has arrived!"

    def generate_kick_reason(self, prompt, channel=None):
        """Generate a kick reason."""
        try:
            client = self._get_client_for_channel(channel)
            model = self._get_channel_config(channel, 'ai_model', self.config['ai_model'])
            
            # Get prompt with nicklist context
            prompt = self._get_prompt_with_nicklist('ai_prompt_kick', prompt, channel)
            
            # Log the full API request payload
            api_payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 50,
                "temperature": 0.9,
            }
            logger.debug(f"Kick API request payload for {channel}: {api_payload}")
            
            logger.debug(f"Sending kick reason request to {client.base_url} for channel {channel}")
            response = client.chat.completions.create(**api_payload)
            
            # Get the response and ensure it's not None
            reason = response.choices[0].message.content.strip() if response.choices else None
            if not reason:
                return "Because I said so!"
                
            # Remove encapsulating quotes if present
            if reason.startswith('"') and reason.endswith('"'):
                reason = reason[1:-1].strip()
                
            return reason
            
        except Exception as e:
            logger.error(f"API error generating kick reason for channel {channel}: {str(e)}", exc_info=True)
            return "Because I said so!" 