"""Token bucket rate limiter for IRC messages."""

import time

class TokenBucket:
    def __init__(self, capacity=4, fill_rate=1.0, initial_tokens=None):
        """Initialize token bucket.
        
        Args:
            capacity: Maximum number of tokens the bucket can hold
            fill_rate: Rate at which tokens are added (tokens per second)
            initial_tokens: Initial number of tokens (defaults to capacity)
        """
        self.capacity = float(capacity)
        self.fill_rate = float(fill_rate)
        self.tokens = float(initial_tokens if initial_tokens is not None else capacity)
        self.last_update = time.time()
        
    def _add_tokens(self):
        """Add tokens based on time elapsed since last update."""
        now = time.time()
        elapsed = now - self.last_update
        new_tokens = elapsed * self.fill_rate
        
        self.tokens = min(self.capacity, self.tokens + new_tokens)
        self.last_update = now
        
    def get_token(self, block=True):
        """Try to get a token from the bucket.
        
        Args:
            block: If True, wait for a token to become available
            
        Returns:
            float: Time to wait before sending (0 if token available now)
        """
        self._add_tokens()
        
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return 0.0
            
        if not block:
            return -1.0
            
        # Calculate time until next token
        time_needed = (1.0 - self.tokens) / self.fill_rate
        return time_needed 