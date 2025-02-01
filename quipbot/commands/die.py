"""Die command for QuipBot - shuts down the bot."""

import time
import sys
import threading
import os
from .. import commands

class DieCommand(commands.Command):
    @property
    def name(self):
        """Command name."""
        return "die"

    @property
    def help(self):
        """Command help."""
        return "Shuts down the bot. Usage: die [reason]"

    @property
    def usage(self):
        """Command usage."""
        return "[reason]"

    def execute(self, nick, channel, args):
        """Execute the die command."""
        # Get quit reason
        reason = " ".join(args) if args else f"Shutdown requested by {nick}"
        
        # First stop the main bot loop to prevent reconnection
        self.bot.running = False
        
        # Then handle the connection cleanup
        self.bot.connected = False
        
        try:
            # Send final QUIT and close socket
            if self.bot.sock:
                self.bot.send_raw(f"QUIT :{reason}")
                time.sleep(0.1)  # Small delay to allow QUIT to send
                self.bot.sock.close()
        except:
            pass  # Ignore any errors during shutdown
        
        # Schedule process exit after 2 seconds
        def delayed_exit():
            time.sleep(2)
            os._exit(0)
            
        # Start exit timer in a non-daemon thread
        exit_thread = threading.Thread(target=delayed_exit)
        exit_thread.daemon = False
        exit_thread.start()
        
        return None  # No response needed since we're quitting 