"""Module reloading system for QuipBot."""

import sys
import types
import importlib
import logging
import threading
import inspect
import ast
import time
from pathlib import Path
from typing import Dict, Set, Any, List, Tuple

# Initialize logger at module level
logger = logging.getLogger('QuipBot')

class ReloadError(Exception):
    """Custom exception for reload errors."""
    pass

class ModuleReloader:
    """Handles dynamic reloading of Python modules while preserving state."""
    
    def __init__(self):
        """Initialize the module reloader."""
        self.loaded_modules: Dict[str, types.ModuleType] = {}
        self.preserved_state: Dict[str, Any] = {}
        self.reload_lock = threading.Lock()
        self.thread_timeout = 5.0  # Seconds to wait for threads to pause
        
        # Store essential modules that must be preserved
        self._original_modules = {
            'sys': sys,
            'types': types,
            'importlib': importlib,
            'logging': logging,
            'threading': threading,
            'inspect': inspect,
            'ast': ast,
            'time': time,
            'Path': Path,
            'logger': logger
        }
        
        # Keep reference to logger
        self.logger = logger
        
    def _analyze_imports(self, module_path: str) -> Set[str]:
        """Analyze module imports using AST.
        
        Args:
            module_path: Path to the module file
            
        Returns:
            Set of imported module names
        """
        imports = set()
        if not module_path:
            return imports
            
        try:
            with open(module_path, 'r') as f:
                tree = ast.parse(f.read())
                
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for name in node.names:
                        if name.name.startswith('quipbot'):
                            imports.add(name.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module and node.module.startswith('quipbot'):
                        imports.add(node.module)
                        
        except Exception as e:
            logger.debug(f"Could not analyze imports in {module_path}: {e}")
            
        return imports
        
    def _get_module_dependencies(self, module_name: str) -> Set[str]:
        """Get the set of module dependencies for a given module.
        
        Args:
            module_name: The name of the module to check
            
        Returns:
            Set of module names that are dependencies
        """
        dependencies = set()
        module = self._original_modules['sys'].modules.get(module_name)
        if not module:
            return dependencies
            
        # Get module file path if available
        module_file = getattr(module, '__file__', None)
        if module_file:
            # Check static imports using AST
            dependencies.update(self._analyze_imports(module_file))
            
        # Check runtime dependencies
        for name, obj in module.__dict__.items():
            try:
                # Check module references
                if isinstance(obj, types.ModuleType):
                    if hasattr(obj, '__name__') and obj.__name__.startswith('quipbot'):
                        dependencies.add(obj.__name__)
                        
                # Check class inheritance
                elif inspect.isclass(obj):
                    for base in obj.__bases__:
                        if hasattr(base, '__module__') and base.__module__.startswith('quipbot'):
                            dependencies.add(base.__module__)
                            
                # Check function references
                elif inspect.isfunction(obj):
                    # Get module references from function's global namespace
                    for ref_name, ref_obj in obj.__globals__.items():
                        if (isinstance(ref_obj, types.ModuleType) and 
                            hasattr(ref_obj, '__name__') and 
                            ref_obj.__name__.startswith('quipbot')):
                            dependencies.add(ref_obj.__name__)
                            
            except Exception as e:
                self.logger.debug(f"Error checking dependency for {name} in {module_name}: {e}")
                continue
                
        return dependencies
        
    def _get_reload_order(self) -> List[str]:
        """Determine the correct order to reload modules.
        
        Returns:
            List of module names in dependency order
        """
        # Build dependency graph
        graph = {}
        modules_to_reload = []
        
        # Find all quipbot modules
        for name, module in self._original_modules['sys'].modules.items():
            if name.startswith('quipbot'):
                modules_to_reload.append(name)
                try:
                    graph[name] = self._get_module_dependencies(name)
                except Exception as e:
                    logger.debug(f"Error getting dependencies for {name}: {e}")
                    graph[name] = set()
                    
        # Topological sort
        result = []
        visited = set()
        temp_visited = set()
        
        def visit(node):
            if node in temp_visited:
                # Only log circular dependency warnings if they don't involve quipbot.commands
                if 'quipbot.commands' not in node:
                    logger.warning(f"Circular dependency detected involving {node}")
                return
            if node not in visited:
                temp_visited.add(node)
                for dep in graph.get(node, []):
                    visit(dep)
                temp_visited.remove(node)
                visited.add(node)
                result.append(node)
                
        # Sort modules
        try:
            for module in modules_to_reload:
                if module not in visited:
                    visit(module)
        except Exception as e:
            logger.error(f"Error during dependency sort: {e}")
            # Fall back to simple directory-based ordering
            result = sorted(modules_to_reload, 
                          key=lambda x: (0 if 'utils' in x else 
                                       1 if 'core' in x else 
                                       2 if 'commands' in x else 3))
            
        return result
        
    def _pause_threads(self, bot) -> List[Tuple[threading.Thread, bool]]:
        """Pause bot threads for safe reloading.
        
        Args:
            bot: The IRCBot instance
            
        Returns:
            List of (thread, original_state) tuples
        """
        paused_threads = []
        deadline = time.time() + self.thread_timeout
        
        # Find all bot-related threads
        bot_threads = [t for t in threading.enumerate() 
                      if t.name in ["RandomActionsLoop", "ListenLoop"]]
        
        if not bot_threads:
            logger.warning("No bot threads found to pause")
            return []
            
        logger.debug(f"Found {len(bot_threads)} threads to pause: {[t.name for t in bot_threads]}")
        
        # Signal all threads to pause
        original_state = bot.reload_paused
        bot.reload_paused = True
        for thread in bot_threads:
            paused_threads.append((thread, original_state))
            logger.debug(f"Signaled thread to pause: {thread.name}")
        
        # Wait for threads to actually pause
        while time.time() < deadline:
            all_paused = True
            for thread in bot_threads:
                is_processing = getattr(thread, 'is_processing', True)
                logger.debug(f"Thread {thread.name} processing state: {is_processing}")
                if is_processing:
                    all_paused = False
                    break
            
            if all_paused:
                logger.debug("All threads successfully paused")
                return paused_threads
                
            time.sleep(0.1)
            
        # If we get here, we timed out
        still_processing = [t.name for t in bot_threads if getattr(t, 'is_processing', True)]
        raise ReloadError(f"Timeout waiting for threads to pause. Still processing: {still_processing}")
        
    def _resume_threads(self, bot, paused_threads):
        """Resume previously paused bot threads.
        
        Args:
            bot: The IRCBot instance
            paused_threads: List of (thread, original_state) tuples
        """
        logger.debug(f"Resuming {len(paused_threads)} threads")
        
        # Restore original pause state
        original_state = paused_threads[0][1] if paused_threads else False
        bot.reload_paused = original_state
        
        # Wait for threads to resume or restart if needed
        deadline = time.time() + self.thread_timeout
        while time.time() < deadline:
            all_resumed = True
            for thread, _ in paused_threads:
                if not thread.is_alive():
                    # Thread died, restart it
                    if thread.name == "RandomActionsLoop":
                        new_thread = threading.Thread(target=bot.random_actions_loop, 
                                                   daemon=True, 
                                                   name="RandomActionsLoop")
                        new_thread.start()
                        logger.info(f"Restarted {thread.name} thread")
                        continue
                    else:
                        raise ReloadError(f"Thread died during reload: {thread.name}")
                    
                # Check if thread has started processing again
                if not original_state:  # Only if we're supposed to be running
                    is_processing = getattr(thread, 'is_processing', False)
                    logger.debug(f"Thread {thread.name} processing state: {is_processing}")
                    if not is_processing:
                        all_resumed = False
                        break
            
            if all_resumed:
                logger.debug("All threads successfully resumed")
                return
                
            time.sleep(0.1)
            
        # If we get here, we timed out
        not_resumed = [t.name for t, _ in paused_threads 
                      if not original_state and not getattr(t[0], 'is_processing', False)]
        raise ReloadError(f"Timeout waiting for threads to resume. Not resumed: {not_resumed}")
        
    def _validate_state(self, state_dict: Dict[str, Any]) -> bool:
        """Validate preserved state.
        
        Args:
            state_dict: Dictionary of preserved state
            
        Returns:
            bool: True if state is valid
        """
        required_keys = {
            'connected': bool,
            'current_nick': str,
            'users': dict,
            'channel_users': dict,
            'sock': object,  # Socket object
            'running': bool
        }
        
        try:
            # Check required keys and types
            for key, expected_type in required_keys.items():
                if key not in state_dict:
                    raise ReloadError(f"Missing required state key: {key}")
                if not isinstance(state_dict[key], expected_type):
                    raise ReloadError(f"Invalid type for {key}: expected {expected_type}, got {type(state_dict[key])}")
                    
            # Validate socket is still valid
            if state_dict['sock']:
                try:
                    state_dict['sock'].getpeername()
                except Exception:
                    raise ReloadError("Invalid socket object in preserved state")
                    
            return True
            
        except Exception as e:
            logger.error(f"State validation failed: {e}")
            return False
        
    def preserve_state(self, bot):
        """Preserve bot state before reload."""
        try:
            # Get handler state
            handler = bot.handler
            handler_state = getattr(handler, '_event_bindings', {}).copy()
            
            # Get flood protection state
            flood_state = {
                'flood_channel_history': bot.floodpro.channel_history.copy(),
                'flood_privmsg_history': bot.floodpro.privmsg_history.copy(),
                'flood_ignored_users': bot.floodpro.ignored_users.copy(),
                'flood_banned_users': bot.floodpro.banned_users.copy()
            }
            
            # Get command state
            command_state = {}
            for name, cmd in bot.handler.commands.items():
                try:
                    command_state[name] = self._preserve_command_state(cmd)
                except Exception as e:
                    self.logger.warning(f"Could not preserve state for command {name}: {e}")
            
            # Store complete state
            self.preserved_state = {
                'event_bindings': handler_state,
                'command_state': command_state,
                **flood_state,
                'module_refs': {
                    name: list(module.__dict__.keys()) 
                    for name, module in self._original_modules['sys'].modules.items() 
                    if name.startswith('quipbot')
                }
            }
            
            self.logger.info("Successfully preserved bot state")
            return True
            
        except Exception as e:
            self.logger.error(f"Error preserving state: {e}", exc_info=True)
            return False
        
    def _preserve_handler_state(self, handler) -> Dict[str, Any]:
        """Preserve message handler state.
        
        Args:
            handler: The MessageHandler instance
            
        Returns:
            dict: Preserved handler state
        """
        return getattr(handler, '_event_bindings', {}).copy()

    def _preserve_permissions_state(self, permissions) -> Dict[str, Any]:
        """Preserve permissions manager state.
        
        Args:
            permissions: The PermissionManager instance
            
        Returns:
            dict: Preserved permissions state
        """
        return {
            'admin_cache': getattr(permissions, '_admin_cache', {}).copy(),
            'admin_cache_times': getattr(permissions, '_admin_cache_times', {}).copy(),
            'admin_patterns': permissions.admin_patterns.copy() if hasattr(permissions, 'admin_patterns') else []
        }

    def _preserve_floodpro_state(self, floodpro) -> Dict[str, Any]:
        """Preserve flood protection state.
        
        Args:
            floodpro: The FloodPro instance
            
        Returns:
            dict: Preserved flood protection state
        """
        return {
            'channel_history': {k: {nick: timestamps.copy() for nick, timestamps in v.items()} 
                              for k, v in floodpro.channel_history.items()},
            'privmsg_history': {k: v.copy() for k, v in floodpro.privmsg_history.items()},
            'ignored_users': floodpro.ignored_users.copy(),
            'banned_users': {k: v.copy() for k, v in floodpro.banned_users.items()}
        }

    def _preserve_ai_client_state(self, ai_client) -> Dict[str, Any]:
        """Preserve AI client state.
        
        Args:
            ai_client: The AIClient instance
            
        Returns:
            dict: Preserved AI client state
        """
        return {
            'chat_history': ai_client.chat_history.copy(),
            'last_response_times': getattr(ai_client, 'last_response_times', {}).copy(),
            'conversation_contexts': getattr(ai_client, 'conversation_contexts', {}).copy()
        }
        
    def restore_state(self, bot, state):
        """Restore bot state after reload."""
        try:
            if not state:
                self.logger.error("No state to restore")
                return False
                
            # Restore event bindings
            bot.handler._event_bindings = state.get('event_bindings', {}).copy()
            
            # Restore flood protection state
            bot.floodpro.channel_history = state.get('flood_channel_history', {}).copy()
            bot.floodpro.privmsg_history = state.get('flood_privmsg_history', {}).copy()
            bot.floodpro.ignored_users = state.get('flood_ignored_users', set()).copy()
            bot.floodpro.banned_users = state.get('flood_banned_users', {}).copy()
            
            # Restore command state
            command_state = state.get('command_state', {})
            for name, cmd_state in command_state.items():
                if name in bot.handler.commands:
                    try:
                        self._restore_command_state(bot.handler.commands[name], cmd_state)
                    except Exception as e:
                        self.logger.warning(f"Could not restore state for command {name}: {e}")
            
            # Verify module references
            module_refs = state.get('module_refs', {})
            for module_name, expected_refs in module_refs.items():
                if module_name in self._original_modules['sys'].modules:
                    module = self._original_modules['sys'].modules[module_name]
                    missing_refs = [ref for ref in expected_refs if ref not in module.__dict__]
                    if missing_refs:
                        self.logger.warning(f"Module {module_name} is missing references: {missing_refs}")
            
            self.logger.info("Successfully restored bot state")
            return True
            
        except Exception as e:
            self.logger.error(f"Error restoring state: {e}", exc_info=True)
            return False
        
    def _cleanup_old_modules(self):
        """Clean up references to old module versions."""
        # Get all quipbot modules
        quipbot_modules = [name for name in self._original_modules['sys'].modules if name.startswith('quipbot')]
        
        # Remove old references
        for name in quipbot_modules:
            if name in self.loaded_modules:
                old_module = self.loaded_modules[name]
                # Preserve original imports and critical variables
                preserved_globals = {k: v for k, v in old_module.__dict__.items() 
                                  if k in self._original_modules or k in ('logger', '_original_modules')}
                # Clear module's dictionary
                old_module.__dict__.clear()
                # Restore preserved items
                old_module.__dict__.update(preserved_globals)
                
        # Clear loaded modules cache
        self.loaded_modules.clear()
        
    def reload_modules(self, bot) -> bool:
        """Reload all QuipBot modules in the correct order.
        
        Args:
            bot: The IRCBot instance
            
        Returns:
            bool: True if reload was successful, False otherwise
            
        Note:
            Some core components cannot be fully hot-reloaded:
            - irc.py: Socket connections and network state must be preserved
            - Core bot instance attributes and connections are maintained
        """
        try:
            with self.reload_lock:
                # Pause threads
                paused_threads = self._pause_threads(bot)
                
                try:
                    # Get modules in correct reload order
                    modules_to_reload = self._get_reload_order()
                    self.logger.debug(f"Modules to reload in order: {modules_to_reload}")
                    
                    # Store references to critical instances
                    old_ai_client = bot.ai_client
                    old_floodpro = bot.floodpro
                    old_logger = self.logger
                    old_permissions = bot.permissions
                    
                    # Preserve states
                    ai_client_state = {
                        'chat_history': old_ai_client.chat_history.copy(),
                        'config': old_ai_client.config.copy()
                    }
                    
                    floodpro_state = {
                        'channel_history': {k: {nick: timestamps.copy() for nick, timestamps in v.items()} 
                                          for k, v in old_floodpro.channel_history.items()},
                        'privmsg_history': {k: v.copy() for k, v in old_floodpro.privmsg_history.items()},
                        'ignored_users': old_floodpro.ignored_users.copy(),
                        'banned_users': {k: v.copy() for k, v in old_floodpro.banned_users.items()}
                    }
                    
                    # Preserve permissions state
                    permissions_state = {
                        'config': old_permissions.config.copy(),
                        'admin_hosts': old_permissions.admin_hosts.copy() if hasattr(old_permissions, 'admin_hosts') else set(),
                        'trusted_hosts': old_permissions.trusted_hosts.copy() if hasattr(old_permissions, 'trusted_hosts') else set(),
                        'banned_hosts': old_permissions.banned_hosts.copy() if hasattr(old_permissions, 'banned_hosts') else set()
                    }
                    
                    # Clear module cache first
                    for module_name in modules_to_reload:
                        if module_name in self._original_modules['sys'].modules:
                            del self._original_modules['sys'].modules[module_name]
                            self.logger.debug(f"Cleared module from cache: {module_name}")
                    
                    # Track reloaded modules
                    reloaded = {}
                    
                    # First reload utils modules in specific order
                    utils_order = [
                        'quipbot.utils.logger',
                        'quipbot.utils.config',
                        'quipbot.utils.tokenbucket',
                        'quipbot.utils.floodpro',
                        'quipbot.utils.ai_client',
                        'quipbot.utils.reloader'
                    ]
                    
                    for module_name in utils_order:
                        if module_name in modules_to_reload:
                            try:
                                self.logger.debug(f"Reloading utils module: {module_name}")
                                reloaded[module_name] = self._original_modules['importlib'].import_module(module_name)
                                self._original_modules['sys'].modules[module_name] = reloaded[module_name]
                                
                                # Special handling for logger module
                                if module_name == 'quipbot.utils.logger':
                                    # Ensure logger is properly reinitialized
                                    new_logger = reloaded[module_name].setup_logger('QuipBot', bot.config)
                                    self.logger = new_logger
                                    self._original_modules['logger'] = new_logger
                                    bot.logger = new_logger
                                    
                            except Exception as e:
                                self.logger.error(f"Error reloading {module_name}: {e}", exc_info=True)
                                return False
                    
                    # Then reload core modules in specific order (except handler which is handled specially)
                    core_order = [
                        'quipbot.core.permissions',  # Permissions first as other modules may depend on it
                        'quipbot.core.irc'  # IRC module last as it contains main bot class
                    ]
                    
                    for module_name in core_order:
                        if module_name in modules_to_reload:
                            try:
                                self.logger.debug(f"Reloading core module: {module_name}")
                                reloaded[module_name] = self._original_modules['importlib'].import_module(module_name)
                                self._original_modules['sys'].modules[module_name] = reloaded[module_name]
                                
                                # Special handling for permissions module
                                if module_name == 'quipbot.core.permissions':
                                    PermissionManager = reloaded[module_name].PermissionManager
                                    new_permissions = PermissionManager(bot.config)
                                    # Restore state
                                    new_permissions.admin_hosts = permissions_state['admin_hosts']
                                    new_permissions.trusted_hosts = permissions_state['trusted_hosts']
                                    new_permissions.banned_hosts = permissions_state['banned_hosts']
                                    new_permissions.set_bot(bot)  # Set bot reference
                                    bot.permissions = new_permissions
                                    self.logger.debug("Successfully recreated permissions manager with reloaded code")
                                
                            except Exception as e:
                                self.logger.error(f"Error reloading {module_name}: {e}", exc_info=True)
                                return False
                    
                    # Then reload commands module
                    if 'quipbot.commands' in modules_to_reload:
                        try:
                            self.logger.debug("Reloading commands module")
                            reloaded['quipbot.commands'] = self._original_modules['importlib'].import_module('quipbot.commands')
                            self._original_modules['sys'].modules['quipbot.commands'] = reloaded['quipbot.commands']
                        except Exception as e:
                            self.logger.error(f"Error reloading commands module: {e}", exc_info=True)
                            return False
                    
                    # Then reload handler
                    if 'quipbot.core.handler' in modules_to_reload:
                        try:
                            self.logger.debug("Reloading handler module")
                            
                            # Store old handler state
                            old_handler = bot.handler
                            old_event_bindings = old_handler._event_bindings.copy()
                            old_commands = old_handler.commands.copy()
                            
                            # Import fresh handler module
                            handler_module = self._original_modules['importlib'].import_module('quipbot.core.handler')
                            reloaded['quipbot.core.handler'] = handler_module
                            self._original_modules['sys'].modules['quipbot.core.handler'] = handler_module
                            
                            # Get the new MessageHandler class
                            handler_class = getattr(handler_module, 'MessageHandler')
                            
                            # Create new handler instance
                            new_handler = handler_class(bot)
                            
                            # Restore state
                            new_handler._event_bindings = old_event_bindings
                            new_handler.commands = old_commands
                            
                            # Update bot's handler reference
                            bot.handler = new_handler
                            
                            self.logger.debug("Successfully recreated handler with reloaded code")
                            
                        except Exception as e:
                            self.logger.error(f"Error reloading handler module: {e}", exc_info=True)
                            return False
                    
                    # Finally reload individual command modules
                    for module_name in modules_to_reload:
                        if '.commands.' in module_name and module_name != 'quipbot.commands':
                            try:
                                self.logger.debug(f"Reloading command module: {module_name}")
                                reloaded[module_name] = self._original_modules['importlib'].import_module(module_name)
                                self._original_modules['sys'].modules[module_name] = reloaded[module_name]
                            except Exception as e:
                                self.logger.error(f"Error reloading {module_name}: {e}", exc_info=True)
                                return False
                    
                    # Store reloaded modules
                    self.loaded_modules = reloaded
                    
                    # Recreate utility instances with preserved state
                    try:
                        # Recreate AI client
                        AIClient = reloaded['quipbot.utils.ai_client'].AIClient
                        new_ai_client = AIClient(bot.config)
                        new_ai_client.chat_history = ai_client_state['chat_history']
                        new_ai_client.bot = bot  # Ensure bot reference is set
                        bot.ai_client = new_ai_client
                        
                        # Recreate flood protection
                        FloodProtection = reloaded['quipbot.utils.floodpro'].FloodProtection
                        new_floodpro = FloodProtection(bot.config)
                        new_floodpro.channel_history = floodpro_state['channel_history']
                        new_floodpro.privmsg_history = floodpro_state['privmsg_history']
                        new_floodpro.ignored_users = floodpro_state['ignored_users']
                        new_floodpro.banned_users = floodpro_state['banned_users']
                        new_floodpro.logger = self.logger  # Ensure logger reference is set
                        bot.floodpro = new_floodpro
                        
                    except Exception as e:
                        self.logger.error(f"Error recreating utility instances: {e}", exc_info=True)
                        return False
                    
                    # Force reload of commands in handler
                    bot.handler._load_commands()
                    
                    # Verify commands were loaded
                    if not bot.handler.commands:
                        self.logger.error("No commands were loaded after module reload")
                        return False
                        
                    self.logger.info(f"Successfully reloaded {len(bot.handler.commands)} commands")
                    return True
                    
                except Exception as e:
                    self.logger.error(f"Error reloading modules: {e}", exc_info=True)
                    return False
                    
                finally:
                    # Resume threads
                    try:
                        self._resume_threads(bot, paused_threads)
                    except Exception as e:
                        self.logger.error(f"Error resuming threads: {e}", exc_info=True)
                        return False
                    
        except Exception as e:
            self.logger.error(f"Error during module reload: {e}", exc_info=True)
            return False
            
    def reload_commands(self, bot) -> bool:
        """Reload command instances while preserving state.
        
        Args:
            bot: The IRCBot instance
            
        Returns:
            bool: True if reload was successful, False otherwise
        """
        try:
            with self.reload_lock:
                # Preserve old commands and their state
                old_commands = bot.handler.commands.copy()  # Make a copy
                command_state = {name: self._preserve_command_state(cmd) 
                               for name, cmd in old_commands.items()}
                
                # Clear existing commands
                bot.handler.commands = {}
                
                # Reload commands module
                if 'quipbot.commands' in self._original_modules['sys'].modules:
                    self.logger.debug("Reloading commands module")
                    commands_module = self._original_modules['sys'].modules['quipbot.commands']
                    self.loaded_modules['quipbot.commands'] = self._original_modules['importlib'].reload(commands_module)
                
                # Reinitialize commands
                try:
                    bot.handler._load_commands()
                except Exception as e:
                    self.logger.error(f"Error loading commands: {e}", exc_info=True)
                    bot.handler.commands = old_commands  # Restore old commands
                    return False
                
                # Verify commands were loaded
                if not bot.handler.commands:
                    self.logger.error("No commands were loaded after reload")
                    bot.handler.commands = old_commands  # Restore old commands
                    return False
                
                # Restore command state where possible
                for name, state in command_state.items():
                    if name in bot.handler.commands:
                        try:
                            self._restore_command_state(bot.handler.commands[name], state)
                        except Exception as e:
                            self.logger.warning(f"Could not restore state for command {name}: {e}")
                
                self.logger.info(f"Successfully reloaded {len(bot.handler.commands)} commands")
                return True
                
        except Exception as e:
            self.logger.error(f"Error reloading commands: {e}", exc_info=True)
            if old_commands:  # Restore old commands on failure
                bot.handler.commands = old_commands
            return False
            
    def _preserve_command_state(self, command) -> Dict[str, Any]:
        """Preserve command-specific state.
        
        Args:
            command: Command instance
            
        Returns:
            dict: Preserved command state
        """
        # Get all instance variables that don't start with _
        return {key: value for key, value in vars(command).items() 
                if not key.startswith('_') and not callable(value)}
                
    def _restore_command_state(self, command, state: Dict[str, Any]) -> None:
        """Restore command-specific state.
        
        Args:
            command: Command instance
            state: Preserved command state
        """
        for key, value in state.items():
            if hasattr(command, key):
                setattr(command, key, value) 