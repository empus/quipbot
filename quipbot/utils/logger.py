"""Custom logger for QuipBot with colored console output."""

import logging
import sys
import os
from datetime import datetime

# Add custom levels
RAW = 5  # Lower than DEBUG (10)
API = 15  # Between DEBUG (10) and INFO (20)
logging.addLevelName(RAW, 'RAW')
logging.addLevelName(API, 'API')

# Ensure custom levels are preserved during reloads
def raw(self, msg, *args, **kwargs):
    """Log 'msg % args' with severity 'RAW'."""
    if self.isEnabledFor(RAW):
        self._log(RAW, msg, args, **kwargs)

def api(self, msg, *args, **kwargs):
    """Log 'msg % args' with severity 'API'."""
    if self.isEnabledFor(API):
        self._log(API, msg, args, **kwargs)

# Add methods to Logger class if not already present
if not hasattr(logging.Logger, 'raw'):
    logging.Logger.raw = raw
if not hasattr(logging.Logger, 'api'):
    logging.Logger.api = api

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
    'INDIGO': '\033[38;5;54m',  # Using closest ANSI color to indigo
}

# Log level colors and emojis
LEVEL_STYLES = {
    'RAW': {
        'color': COLORS['INDIGO'],  # Base color for RAW messages
        'emoji': '📡'
    },
    'DEBUG': {
        'color': COLORS['BLUE'],
        'emoji': '🔍'
    },
    'INFO': {
        'color': COLORS['RESET'],
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
    },
    'API': {
        'color': COLORS['GREEN'],
        'emoji': '🤖'
    }
}

# Event-specific styles
EVENT_STYLES = {
    'CONNECT': {
        'emoji': '🔌'
    },
    'DISCONNECT': {
        'emoji': '🔌'
    },
    'JOIN': {
        'emoji': '👋'
    },
    'PART': {
        'emoji': '👋'
    },
    'QUIT': {
        'emoji': '🚶'
    },
    'KICK': {
        'emoji': '👢'
    },
    'BAN': {
        'emoji': '🚫'
    },
    'UNBAN': {
        'emoji': '✅'
    },
    'FLOOD': {
        'emoji': '🌊'
    },
    'IGNORE': {
        'emoji': '🔇'
    },
    'UNIGNORE': {
        'emoji': '🔊'
    },
    'TOPIC': {
        'emoji': '📢'
    },
    'MODE': {
        'emoji': '⚙️'
    },
    'NICK': {
        'emoji': '📝'
    },
    'AI': {
        'emoji': '🤖'
    },
    'COMMAND': {
        'emoji': '⚡'
    },
    'CONFIG': {
        'emoji': '⚙️'
    },
    'INVITE': {
        'emoji': '📨'
    }
}

class ColoredFormatter(logging.Formatter):
    """Custom formatter for colored console output."""
    
    def __init__(self, use_colors=True, fmt=None):
        super().__init__(fmt=fmt or self._get_default_format(use_colors))
        self.use_colors = use_colors
        # Calculate max level name length for padding
        self.max_level_width = max(len(level) for level in LEVEL_STYLES.keys())

    def _get_default_format(self, use_colors):
        """Get the default format string based on output type."""
        if use_colors:
            return '%(asctime)s - %(levelname)s %(message)s'  # Removed the - after levelname
        return '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

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
        # Always use level-based color unless event style explicitly defines one
        color = event_style.get('color', level_style['color']) if event_style else level_style['color']
        # Use event emoji if available, otherwise use level emoji
        emoji = event_style.get('emoji', level_style['emoji']) if event_style else level_style['emoji']
        
        # Special handling for RAW messages to distinguish incoming/outgoing
        if record_copy.levelname == 'RAW':
            if record_copy.msg.startswith('>>>'):
                color = COLORS['BRIGHT_MAGENTA']  # Outgoing messages
            elif record_copy.msg.startswith('<<<'):
                color = COLORS['INDIGO']  # Incoming messages

        # Format the level name with padding for alignment
        padding = ' ' * (self.max_level_width - len(record_copy.levelname))
        record_copy.levelname = f"{color}{record_copy.levelname}{padding} - "
        
        # Format the message with emoji and color the entire line
        record_copy.msg = f"{emoji}  {record_copy.msg}{COLORS['RESET']}"
        
        return super().format(record_copy)

def setup_logger(name, config):
    """Set up the logger with both file and console handlers."""
    logger = logging.getLogger(name)
    
    # Set log level from config
    log_level = getattr(logging, config.get('log_level', 'INFO').upper(), logging.INFO)
    
    # Enable RAW level if configured
    if config.get('log_raw', False):
        log_level = min(log_level, RAW)
    
    # Enable API level if configured
    if config.get('log_api', False):
        log_level = min(log_level, API)
        
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
    
    # Add custom logging methods
    def raw(msg, *args, **kwargs):
        if logger.isEnabledFor(RAW):
            logger._log(RAW, msg, args, **kwargs)
    
    def api(msg, *args, **kwargs):
        if logger.isEnabledFor(API):
            logger._log(API, msg, args, **kwargs)
    
    logger.raw = raw
    logger.api = api
    
    return logger 