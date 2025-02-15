"""Jump command for QuipBot - switches to a different server."""

from .. import commands

class JumpCommand(commands.Command):
    @property
    def name(self):
        """Command name."""
        return "jump"

    @property
    def help(self):
        """Command help."""
        return "Disconnects from current server and connects to another. Usage: jump [server]"

    @property
    def usage(self):
        """Command usage."""
        return "[server]"

    def execute(self, nick, channel, args):
        """Execute the jump command."""
        # Get target server (ensure args is a list)
        args = args or []
        target_server = args[0] if args else None
        
        if target_server:
            # Find the server in the configured servers list
            server_found = False
            for i, server in enumerate(self.bot.servers):
                if server['host'].lower() == target_server.lower():
                    self.bot.current_server_index = i
                    server_found = True
                    break
            
            if not server_found:
                return f"Error: Server '{target_server}' not found in configured servers list."
        else:
            # Move to next server in rotation
            self.bot.current_server_index = (self.bot.current_server_index + 1) % len(self.bot.servers)

        # Get the target server info for logging
        next_server = self.bot.servers[self.bot.current_server_index]['host']
        self.bot.logger.info(f"Jumping to server: {next_server}")

        # Set connected to False to prevent auto-reconnect to current server
        self.bot.connected = False

        try:
            # Send QUIT and close socket
            if self.bot.sock:
                self.bot.send_raw("QUIT :Jumping servers...")
                self.bot.sock.close()
        except:
            pass  # Ignore errors during disconnect

        # Return message that will be sent to channel
        return f"Jumping to server: {next_server}" 