# Hot Reloading in QuipBot

QuipBot supports hot reloading of code changes without requiring a bot restart. This allows for dynamic updates to the bot's functionality while maintaining its connection to IRC servers and preserving important state.

## Triggering Hot Reload

Hot reloading can be triggered using two commands:

1. `@reload` - Reloads both configuration and code modules
2. `@rehash` - Reloads only the configuration file

Note: Both commands require admin privileges to execute.

## What Gets Reloaded

The hot reloading system handles different components in a specific order to ensure dependencies are properly managed:

### 1. Utility Modules (`quipbot/utils/*.py`)
- Logger
- Configuration
- Token Bucket
- Flood Protection
- AI Client
- Reloader

### 2. Core Modules (`quipbot/core/*.py`)
- Permissions Manager
- Message Handler
- IRC Core (partial)

### 3. Command System
- Base Command Framework
- Individual Command Modules

## State Preservation

The following state is preserved during hot reloading:

### Network State
- Active socket connections
- Current nickname
- Channel memberships
- User lists
- Connection status

### Bot State
- Event bindings
- Command registrations
- Channel configurations
- User permissions
- Flood protection history
- Chat history
- AI conversation contexts

### Thread Management
- Running threads are paused during reload
- Thread state is preserved
- Threads are resumed after reload
- Dead threads are automatically restarted

## Limitations

Some components cannot be fully hot-reloaded due to their nature:

### IRC Core (`irc.py`)
- Active socket connections must be preserved
- Network buffers must be maintained
- Core bot attributes cannot be modified
- Changes to connection handling require a bot restart

### Thread-Related Changes
- Modifications to thread initialization require a restart
- Changes to core loop logic require a restart
- New thread types cannot be added via hot reload

### Configuration Changes
Some configuration changes may require a bot restart:
- Server connection parameters
- Core authentication settings
- Fundamental bot identity changes

## Best Practices

1. **Test Changes First**
   - Test modifications in a development environment
   - Verify changes don't affect critical functionality
   - Use logging to track reload process

2. **Modular Development**
   - Keep modules independent when possible
   - Avoid circular dependencies
   - Use proper state management

3. **Safe Reloading**
   - Backup configuration before changes
   - Monitor logs during reload
   - Have a rollback plan for critical changes

## Debugging Hot Reload Issues

If hot reloading fails:

1. Check the logs for specific error messages
2. Verify file permissions and syntax
3. Ensure all required state is properly preserved
4. Check for circular dependencies
5. Verify thread states

## Example Usage

```
# Reload both configuration and code:
@reload

# Reload only configuration:
@rehash

# Check reload status in logs:
tail -f quip.log | grep "reload"
```

## Technical Details

The hot reloading system uses Python's module system and follows these steps:

1. Pause all bot threads
2. Preserve current state
3. Clear module cache
4. Reload modules in dependency order
5. Restore preserved state
6. Resume threads

The process is managed by the `ModuleReloader` class in `quipbot/utils/reloader.py`.

## Error Handling

The hot reloading system includes several safety mechanisms:

- Thread timeout detection
- State validation
- Dependency checking
- Automatic rollback on failure
- Detailed error logging

If a reload fails, the bot will attempt to restore its previous state and continue operating. 