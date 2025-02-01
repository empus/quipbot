"""Die command for QuipBot - shuts down the bot."""

import time
import sys
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
        
        # Send quit message to server
        self.bot.send_raw(f"QUIT :{reason}")
        
        # Schedule process exit after 2 seconds
        def delayed_exit():
            time.sleep(2)
            sys.exit(0)
            
        # Start exit timer in a new thread
        import threading
        threading.Thread(target=delayed_exit, daemon=True).start()
        
        return None  # No response needed since we're quitting 