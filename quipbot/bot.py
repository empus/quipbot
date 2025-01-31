#!/usr/bin/env python3
"""QuipBot - A sarcastic IRC bot."""

import yaml
from quipbot.core.irc import IRCBot
from quipbot.utils.logger import setup_logger

def main():
    """Main entry point."""
    # Load configuration
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)

    # Set up logging
    logger = setup_logger('QuipBot', config)
    logger.info("Starting QuipBot...")

    # Create and run bot
    bot = IRCBot(config)
    bot.run()

if __name__ == '__main__':
    main()

