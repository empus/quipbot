# QuipBot - A Sarcastic IRC Bot

```quip (verb): make a witty remark```

An intelligent, sarcastic IRC bot powered by OpenAI-compatible APIs that brings personality and fun to your IRC channels. QuipBot can engage in conversations and perform various automated actions while maintaining a witty persona.

## How It Works

The bot is designed to encourage and deliver fun channel conversation by kickstarting and participating in chatter.

Many features can be toggled on and off and specific behaviour may be fine-tuned to suit your requirements, including for specific channels.

By default, the bot will operate like the below:

1. After entering the channel, announce a fun AI generated entrance message

2. Every `idle_chat_interval` seconds, speak a fun conversation starting message if the channel has been idle for more than `idle_chat_time` seconds.

3. Every `random_action_interval` seconds, if the channel has been idle for more than `idle_chat_time` seconds, randomly choose to set a fun AI generated topic or kick a random non-opped (and non-admin) user from the recent chat history (from last `channels.chat_history` lines)

4. Respond when someone speaks to or about the bot and continue chatting every `ai_continue_freq` seconds for `ai_continue_mins` minutes after the last bot mention.

5. Allow ops and admins to use the `@boot` command to randomly kick a non-opped and non-admin user from the chat history with a fun kick message.


## Commands

All commands can be configured to require specific user permissions, being either admin, op, voice, or any.

Admin supercedes op and voice; op supercedes voice; voice supercedes any.

The bot supports the following commands:

- `@boot`: Kick a random non-opped and non-admin user from the chat history with a fun kick message.
- `@topic [topic]`: Set a custom topic if given, otherwise automate a fun AI generated topic for the channel.
- `@sleep <mins>`: Put the bot to sleep for a specified amount of time.
- `@wake`: Wake the bot up from sleep.
- `@say <message>`: Speak a message to the channel.
- `@reload`: Reload both configuration and code modules while preserving network state. See [Hot Reloading Documentation](docs/hotreload.md).
- `@rehash`: Reload only the configuration file.
- `@die`: Shutdown the bot.
- `@jump [server]`: Jump to a specific server or the next server in the list.
- `@var <variable>`: Print the value of a variable to the log.
- `@config <variable>`: Print the value of a configuration variable to the log.
- `@help [command]`: Show the help message for a given command.


## Features

### Hot Reloading
- Dynamic code reloading without bot restart
- Preserves network connections and state
- Reloads configuration and module changes
- Maintains chat history and user tracking
- See [Hot Reloading Documentation](docs/hotreload.md) for details

### AI-Powered Interactions
- Responds to direct messages (prefix with botnick:)
- Responds to mentions of its nickname when enabled (configurable per channel)
- Generates contextually aware responses using OpenAI-compatible APIs
- Maintains conversation history per channel for context
- Configurable AI personality and response style
- Supports multiple AI providers (OpenAI, Perplexity, Grok)
- Selective chat history context for different interaction types
- Configurable random response delays to appear more natural
- Sleep and wake commands to create quiet times
- Avoids responding to its own messages
- Tracks user activity for targeted interactions

### Channel Management
- Auto-joins configured channels after server registration
- Handles channel invites to configured channels
- Tracks user presence and permissions
- Maintains separate chat history per channel
- Supports channel-specific configurations
- User and service bot ignoring capabilities
- Smart message rate limiting
- Joins channels only after proper registration
- Handles channel keys and invites
- Tracks user modes (op, voice)

### Automated Actions
- Random idle chat when channels are inactive
- Random topic changes with AI-generated content
- Funny kick messages with AI-generated reasons
- Configurable intervals for automated actions per channel
- Smart flood protection for both channels and private messages
- All actions respect channel operator status

### Message Processing and Formatting
- Supports markdown-style formatting in messages
  - Bold text using **asterisks**
  - Underlined text using _underscores_
- Automatic quote removal for cleaner responses
- Intelligent message splitting at sentence boundaries
- Rate limiting with burst allowance
- Ignored nick filtering
- Context-aware responses

### Error Handling and Protection
- Automatic server reconnection
- Fallback server support
- Robust flood protection
- Graceful error recovery
- Detailed debug logging

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
- `log_raw`: Log raw IRC messages (true/false)
- `log_api`: Log AI queries (true/false)
- `pid_file`: Path to PID file when running as daemon


### Channel-Specific Settings
The below can be set at a global level and overridden per channel:

- `ai_service`: AI service settings
- `ai_key`: AI API key settings
- `ai_model`: AI model settings
- `ai_delay`: Response delay range
- `ai_entrance`: Entrance settings
- `ai_prompt_entrance`: Entrance prompt settings
- `ai_prompt_default`: Default prompt settings
- `ai_prompt_idle`: Custom prompt for idle chat
- `ai_prompt_topic`: Custom prompt for topic generation
- `ai_prompt_kick`: Custom prompt for kick reasons
- `ai_mention`: Whether to respond when the bot's nickname is mentioned
- `ai_context_direct`: Whether to include chat history for direct messages
- `ai_context_mention`: Whether to include chat history for mentions of the bot's nick
- `ai_context_idle`: Whether to include chat history for idle chat
- `ai_context_topic`: Whether to include chat history for topic generation
- `ai_nicklist`: Whether to send the channel's nicklist to the AI for added context
- `chat_history`: Lines to retain from chat history for AI context
- `ignore_nicks`: Nicks to ignore (in addition to global ignores)
- `ignore_regex`: Lines to ignore by regex pattern
- `floodpro`: Flood protection settings
- `idle_chat_interval`: Time between random chat messages (0 to disable)
- `random_action_interval`: Time between random actions
- `random_actions`: Whether to enable random actions (kicks, topic changes)
- `idle_chat_time`: Idle time required to trigger chat or random actions (0 to disable)
- `commands`: Allowing individual commands to be toggled or have permissions changed per channel
  
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

### Start

```bash
source .venv/bin/activate
python3 -m quipbot
```

### Startup Options

Start the bot with the `-h` option to see the help message.
```bash
❯ python3 -m quipbot -h
Usage: quipbot [-h] [-n] [-c CONFIG]

QuipBot - An AI-powered IRC bot

Options:
  -h, --help           show this help message and exit
  -n, --no-fork        Do not fork to background (run in foreground)
  -c, --config CONFIG  Path to config file (default: config.yaml)
```

### Signals

The bot supports the following signals:

- `SIGHUP`: Rehash the configuration file.
- `SIGUSR1`: Reload the config file and code modules.

Rehash Example:
```bash
kill -SIGHUP $(pgrep -f quipbot)
```

Reload Example:
```bash
kill -USR1 $(pgrep -f quipbot)
```


## Requirements

- Python 3.6+
- OpenAI API key (or other supported AI service)
- Required Python packages (see requirements.txt)
- Rust compiler

## Troubleshooting

### Missing Rust compiler

If you get an error about the Rust compiler, you need to install it. 

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
```

### Bot Logging

Consider increasing the log verbosity to `DEBUG` with the `log_level` setting in the `config.yaml` file to get more information about what the bot is doing. 

The bot can be started in console mode with the following command:
```bash
python3 -m quipbot -c
```

Alternatively, check the `quip.log` file for more information.

## Contributing

Feel free to submit issues and pull requests. The bot is designed to be easily extensible with new features and capabilities.

## License

MIT License - See [LICENSE](LICENSE) file for details 