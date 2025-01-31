# QuipBot - A Sarcastic IRC Bot

```quip (verb): make a witty remark```

An intelligent, sarcastic IRC bot powered by OpenAI-compatible APIs that brings personality and fun to your IRC channels. QuipBot can engage in conversations and perform various automated actions while maintaining a witty persona.

## Features

### AI-Powered Interactions
- Responds to direct messages (prefix with botnick:)
- Responds to mentions of its nickname when enabled (configurable per channel)
- Generates contextually aware responses using OpenAI-compatible APIs
- Maintains conversation history per channel for context
- Configurable AI personality and response style
- Supports multiple AI providers (OpenAI, Perplexity, Grok)
- Selective chat history context for different interaction types
- Configurable random response delays

### Channel Management
- Auto-joins configured channels after server registration
- Handles channel invites to configured channels
- Tracks user presence and permissions
- Maintains separate chat history per channel
- Supports channel-specific configurations
- User and service bot ignoring capabilities
- Smart message rate limiting

### Automated Actions
- Random idle chat when channels are inactive
- Random topic changes with AI-generated content
- Funny kick messages with AI-generated reasons
- Configurable intervals for automated actions per channel
- Smart flood protection for both channels and private messages

### Message Formatting
- Supports markdown-style formatting in messages
  - Bold text using **asterisks**
  - Underlined text using _underscores_
- Automatic quote removal for cleaner responses
- Intelligent message splitting at sentence boundaries

### Flexible Configuration
- YAML-based configuration file
- Per-channel settings override global defaults
- Configurable timers and intervals
- Custom AI prompts per channel
- Multiple server support with failover
- Configurable rate limiting and flood protection

## Configuration

Configuration is handled via the `config.yaml` file. 

Custom configuration can be loaded from the command line with the `-c` option.

### Global Settings
- `nick`: Bot nickname
- `realname`: Bot real name (gecos)
- `ident`: Bot ident
- `usermode`: User mode to set after connecting (e.g. "+ix" for invisible and external immunity)
- `post_connect_commands`: Commands to send after connecting (before joining channels)
- `sasl`: SASL Authentication (optional)
- `cmd_prefix`: Command prefix (e.g., !, ., @, $, etc)
- `admins`: List of bot administrators (can use all commands)
- `servers`: List of IRC servers to connect to
- `channels`: List of channels to join
- `log_level`: Logging verbosity level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `log_file`: Log file name
- `pid_file`: Path to PID file when running as daemon


### Channel-Specific Settings
Each channel can override global settings:
- `idle_chat_interval`: Time between random chat messages (0 to disable)
- `random_action_interval`: Time between random actions (0 to disable)
- `ai_prompt_idle`: Custom prompt for idle chat
- `ai_prompt_topic`: Custom prompt for topic generation
- `ai_prompt_kick`: Custom prompt for kick reasons
- `ai_mention`: Whether to respond when the bot's nickname is mentioned
- `ignore_nicks`: Channel-specific nicks to ignore (in addition to global ignores)
- `ai_delay`: Channel-specific response delay range
- `ai_context_*`: Channel-specific history context settings
- `floodpro`: Channel-specific flood protection settings
- `chat_history`: Channel-specific chat history settings
- `ai_service`: Channel-specific AI service settings
- `ai_key`: Channel-specific AI API key settings
- `ai_model`: Channel-specific AI model settings
- `ai_entrance`: Channel-specific entrance settings
- `ai_prompt_entrance`: Channel-specific entrance prompt settings
- `ai_prompt_default`: Channel-specific default prompt settings


## Features in Detail

### AI Response System
- Maintains conversation context per channel
- Avoids responding to its own messages
- Tracks user activity for targeted interactions
- Supports different AI models and providers
- Configurable personality and response style
- Selective chat history context
- Random response delays

### Message Processing
- Rate limiting with burst allowance
- Intelligent message splitting
- Ignored nick filtering
- Flood protection
- Context-aware responses

### Channel Management
- Joins channels only after proper registration
- Handles channel keys and invites
- Tracks user modes (op, voice)
- Maintains separate history and settings per channel
- Smart flood protection with configurable thresholds

### Random Actions
- Idle chat when channel is inactive
- Topic changes with AI-generated content
- Random kicks with funny reasons
- All actions respect channel operator status
- Configurable intervals per channel

### Error Handling
- Automatic server reconnection
- Fallback server support
- Robust flood protection
- Graceful error recovery
- Detailed debug logging

## Installing Bot

1. Create a new virtual environment:
```bash
python3 -m venv .venv
```

2. Activate the virtual environment:
```bash
source .venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Configure your `config.yaml` file with appropriate settings:
```bash
cp config.yaml.example config.yaml
nvim config.yaml
```


## Running the Bot

1. Run the bot:
```bash
python3 -m quipbot
```

### Startup Options

Start the bot with the `-h` option to see the help message.
```bash
❯ python3 -m quipbot -h
usage: quipbot [-h] [-n] [-c CONFIG]

QuipBot - An AI-powered IRC bot

options:
  -h, --help           show this help message and exit
  -n, --no-fork        Do not fork to background (run in foreground)
  -c, --config CONFIG  Path to config file (default: config.yaml)

```

## Requirements

- Python 3.6+
- OpenAI API key (or other supported AI service)
- Required Python packages (see requirements.txt)

## Troubleshooting

Consider increasing the log verbosity to `DEBUG` with the `log_level` setting in the `config.yaml` file to get more information about what the bot is doing. 

The bot can be started in console mode with the following command:
```bash
python3 -m quipbot -c
```

Altneratively, check the `quip.log` file for more information.

## Contributing

Feel free to submit issues and pull requests. The bot is designed to be easily extensible with new features and capabilities.

## License

MIT License - See `LICENSE` file for details 