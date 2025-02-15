"""Custom logger for QuipBot with colored console output."""

import logging
import sys
import os
from datetime import datetime

# Add custom RAW level
RAW = 5  # Lower than DEBUG (10)
logging.addLevelName(RAW, 'RAW')

# Ensure RAW level is preserved during reloads
def raw(self, msg, *args, **kwargs):
    """Log 'msg % args' with severity 'RAW'."""
    if self.isEnabledFor(RAW):
        self._log(RAW, msg, args, **kwargs)

# Add raw method to Logger class if not already present
if not hasattr(logging.Logger, 'raw'):
    logging.Logger.raw = raw

# ANSI color codes
COLORS = {
    'RESET': '\033[0m',
    'BOLD': '\033[1m',
    'RED': '\033[31m',
    'GREEN': '\033[32m',
    'YELLOW': '\033[33m',
    'BLUE': '\033[34m',
    'MAGENTA': '\033[35m',
    'CYAN': '\033[36m',
    'WHITE': '\033[37m',
    'BRIGHT_RED': '\033[91m',
    'BRIGHT_GREEN': '\033[92m',
    'BRIGHT_YELLOW': '\033[93m',
    'BRIGHT_BLUE': '\033[94m',
    'BRIGHT_MAGENTA': '\033[95m',
    'BRIGHT_CYAN': '\033[96m',
    'BRIGHT_WHITE': '\033[97m',
}

# Log level colors and emojis
LEVEL_STYLES = {
    'RAW': {
        'color': COLORS['BRIGHT_WHITE'],
        'emoji': '📡'
    },
    'DEBUG': {
        'color': COLORS['BLUE'],
        'emoji': '🔍'
    },
    'INFO': {
        'color': COLORS['GREEN'],
        'emoji': 'ℹ️'
    },
    'WARNING': {
        'color': COLORS['YELLOW'],
        'emoji': '⚠️'
    },
    'ERROR': {
        'color': COLORS['RED'],
        'emoji': '❌'
    },
    'CRITICAL': {
        'color': COLORS['BRIGHT_RED'] + COLORS['BOLD'],
        'emoji': '💀'
    }
}

# Event-specific styles
EVENT_STYLES = {
    'CONNECT': {
        'color': COLORS['BRIGHT_GREEN'],
        'emoji': '🔌'
    },
    'DISCONNECT': {
        'color': COLORS['BRIGHT_RED'],
        'emoji': '🔌'
    },
    'JOIN': {
        'color': COLORS['BRIGHT_CYAN'],
        'emoji': '👋'
    },
    'PART': {
        'color': COLORS['CYAN'],
        'emoji': '👋'
    },
    'QUIT': {
        'color': COLORS['CYAN'],
        'emoji': '🚶'
    },
    'KICK': {
        'color': COLORS['BRIGHT_YELLOW'],
        'emoji': '👢'
    },
    'BAN': {
        'color': COLORS['BRIGHT_RED'],
        'emoji': '🚫'
    },
    'UNBAN': {
        'color': COLORS['BRIGHT_GREEN'],
        'emoji': '✅'
    },
    'FLOOD': {
        'color': COLORS['BRIGHT_MAGENTA'],
        'emoji': '🌊'
    },
    'IGNORE': {
        'color': COLORS['MAGENTA'],
        'emoji': '🔇'
    },
    'UNIGNORE': {
        'color': COLORS['GREEN'],
        'emoji': '🔊'
    },
    'TOPIC': {
        'color': COLORS['BRIGHT_BLUE'],
        'emoji': '📢'
    },
    'MODE': {
        'color': COLORS['YELLOW'],
        'emoji': '⚙️'
    },
    'NICK': {
        'color': COLORS['BRIGHT_CYAN'],
        'emoji': '📝'
    },
    'AI': {
        'color': COLORS['BRIGHT_MAGENTA'],
        'emoji': '🤖'
    },
    'COMMAND': {
        'color': COLORS['BRIGHT_WHITE'],
        'emoji': '⚡'
    },
    'CONFIG': {
        'color': COLORS['BRIGHT_YELLOW'],
        'emoji': '⚙️'
    },
    'INVITE': {
        'color': COLORS['BRIGHT_GREEN'],
        'emoji': '📨'
    }
}

class ColoredFormatter(logging.Formatter):
    """Custom formatter for colored console output."""
    
    def __init__(self, use_colors=True, fmt=None):
        super().__init__(fmt=fmt or self._get_default_format(use_colors))
        self.use_colors = use_colors

    def _get_default_format(self, use_colors):
        """Get the default format string based on output type."""
        if use_colors:
            return '%(asctime)s - %(levelname)s - %(message)s'
        return '%(asctime)s - %(name)s - [%(levelname)s] - %(message)s'

    def formatTime(self, record, datefmt=None):
        """Format the timestamp with milliseconds."""
        created = datetime.fromtimestamp(record.created)
        if datefmt:
            return created.strftime(datefmt)
        return created.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

    def format(self, record):
        # Create a copy of the record to avoid modifying the original
        record_copy = logging.makeLogRecord(record.__dict__)
        
        # Don't add colors/emojis if colors are disabled
        if not self.use_colors:
            return super().format(record_copy)

        # Get level style
        level_style = LEVEL_STYLES.get(record_copy.levelname, {'color': '', 'emoji': ''})
        
        # Check for specific events in the message
        event_style = None
        for event, style in EVENT_STYLES.items():
            if event.lower() in record_copy.msg.lower():
                event_style = style
                break
        
        # Apply colors and emojis
        if event_style:
            color = event_style['color']
            emoji = event_style['emoji']
        else:
            color = level_style['color']
            emoji = level_style['emoji']

        # Format the level name
        record_copy.levelname = (
            f"{color}[{record_copy.levelname}]{COLORS['RESET']}"
        )
        
        # Format the message with emoji
        record_copy.msg = f"{emoji}  {color}{record_copy.msg}{COLORS['RESET']}"
        
        # Add color to ERROR level logs
        if record_copy.levelno == logging.ERROR:
            record_copy.msg = f"{COLORS['RED']}{record_copy.msg}{COLORS['RESET']}"
        
        return super().format(record_copy)

def setup_logger(name, config):
    """Set up the logger with both file and console handlers."""
    logger = logging.getLogger(name)
    
    # Set log level from config
    log_level = getattr(logging, config.get('log_level', 'INFO').upper(), logging.INFO)
    
    # Enable RAW level if configured
    if config.get('log_raw', False):
        log_level = min(log_level, RAW)
        
    logger.setLevel(log_level)
    
    # Remove any existing handlers
    logger.handlers = []
    
    # File handler (no colors)
    if 'log_file' in config:
        file_handler = logging.FileHandler(config['log_file'])
        file_formatter = ColoredFormatter(use_colors=False)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    
    # Console handler (with colors)
    console_handler = logging.StreamHandler(sys.stdout)
    console_formatter = ColoredFormatter(use_colors=True)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # Add raw method to logger
    def raw(msg, *args, **kwargs):
        if logger.isEnabledFor(RAW):
            logger._log(RAW, msg, args, **kwargs)
    
    logger.raw = raw
    
    return logger 