#!/usr/bin/env python3
"""Main entry point for QuipBot."""

import os
import sys
import argparse
import yaml
import signal
import atexit
from .core.irc import IRCBot

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        prog='quipbot',
        description='QuipBot - An AI-powered IRC bot'
    )
    parser.add_argument('-n', '--no-fork', action='store_true',
                      help='Do not fork to background (run in foreground)')
    parser.add_argument('-c', '--config', default='config.yaml',
                      help='Path to config file (default: config.yaml)')
    return parser.parse_args()

def daemonize(pid_file):
    """Fork the process to the background and write PID file."""
    # Store the working directory
    working_dir = os.getcwd()

    # First fork (detaches from parent)
    try:
        pid = os.fork()
        if pid > 0:
            # Parent process exits
            sys.exit(0)
    except OSError as err:
        sys.stderr.write(f'fork #1 failed: {err}\n')
        sys.exit(1)
    
    # Decouple from parent environment
    os.setsid()
    os.umask(0)
    
    # Second fork (relinquish session leadership)
    try:
        pid = os.fork()
        if pid > 0:
            # Parent process exits
            sys.exit(0)
    except OSError as err:
        sys.stderr.write(f'fork #2 failed: {err}\n')
        sys.exit(1)
    
    # Change to the original working directory
    os.chdir(working_dir)
    
    # Write pidfile before redirecting outputs
    pid = str(os.getpid())
    with open(pid_file, 'w+') as f:
        f.write(pid + '\n')
    
    # Register cleanup function
    atexit.register(cleanup_pid, pid_file)
    
    # Flush standard file descriptors
    sys.stdout.flush()
    sys.stderr.flush()
    
    # Replace file descriptors for stdin, stdout, and stderr
    with open(os.devnull, 'r') as f:
        os.dup2(f.fileno(), sys.stdin.fileno())
    with open(os.devnull, 'a+') as f:
        os.dup2(f.fileno(), sys.stdout.fileno())
    with open(os.devnull, 'a+') as f:
        os.dup2(f.fileno(), sys.stderr.fileno())

def cleanup_pid(pid_file):
    """Remove PID file on exit."""
    if os.path.exists(pid_file):
        os.remove(pid_file)

def main():
    """Main entry point."""
    args = parse_args()
    
    # Load config file
    try:
        with open(args.config, 'r') as f:
            config = yaml.safe_load(f)
    except Exception as e:
        sys.stderr.write(f'Error loading config file: {e}\n')
        sys.exit(1)
    
    # Get PID file path from config
    pid_file = config.get('pid_file', '/tmp/quipbot.pid')
    
    # Fork to background unless --no-fork is specified
    if not args.no_fork:
        try:
            daemonize(pid_file)
        except Exception as e:
            sys.stderr.write(f'Error daemonizing: {e}\n')
            sys.exit(1)
    
    # Set up signal handlers
    def signal_handler(signum, frame):
        cleanup_pid(pid_file)
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Create and run the bot
    bot = IRCBot(config)
    bot.run()

if __name__ == '__main__':
    main() 