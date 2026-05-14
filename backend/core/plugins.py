"""
Plugin system for JARVIS.
Allows loading custom actions and extensions dynamically.
"""
import importlib
import inspect
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger(__name__)

# Plugin metadata
PLUGIN_DIR = Path(__file__).parent.parent / "plugins"


class JarvisPlugin(ABC):
    """Base class for JARVIS plugins."""

    name: str = "plugin"
    version: str = "1.0.0"
    description: str = "A JARVIS plugin"
    author: str = "Community"

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize plugin. Called on startup."""
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        """Shutdown plugin. Called on shutdown."""
        pass

    @abstractmethod
    async def handle_message(self, message: str, session_id: str) -> Optional[str]:
        """
        Handle chat message.

        Args:
            message: User message
            session_id: Session ID

        Returns:
            Response string or None (if not handled)
        """
        pass

    def register_actions(self) -> Dict[str, Callable]:
        """
        Register custom actions.

        Returns:
            Dict of action_name -> callable
        """
        return {}

    def get_metadata(self) -> dict:
        """Get plugin metadata."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
        }


class PluginManager:
    """Manages plugin lifecycle and execution."""

    def __init__(self):
        self.plugins: Dict[str, JarvisPlugin] = {}
        self.actions: Dict[str, Callable] = {}
        self.hooks: Dict[str, List[Callable]] = {}

    async def load_plugins(self, plugin_dir: Optional[Path] = None) -> None:
        """
        Load all plugins from directory.

        Args:
            plugin_dir: Directory containing plugins (default: PLUGIN_DIR)
        """
        plugin_dir = plugin_dir or PLUGIN_DIR
        if not plugin_dir.exists():
            log.warning(f"Plugin directory not found: {plugin_dir}")
            return

        log.info(f"Loading plugins from {plugin_dir}")

        for plugin_path in plugin_dir.glob("*/plugin.py"):
            try:
                await self._load_plugin_file(plugin_path)
            except Exception as e:
                log.error(f"Failed to load plugin from {plugin_path}: {e}")

    async def _load_plugin_file(self, plugin_file: Path) -> None:
        """Load plugin from file."""
        module_name = f"jarvis_plugin_{plugin_file.parent.name}"

        # Dynamically import module
        spec = importlib.util.spec_from_file_location(module_name, plugin_file)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Find plugin class
        plugin_class = None
        for name, obj in inspect.getmembers(module):
            if (
                inspect.isclass(obj)
                and issubclass(obj, JarvisPlugin)
                and obj is not JarvisPlugin
            ):
                plugin_class = obj
                break

        if not plugin_class:
            log.warning(f"No JarvisPlugin found in {plugin_file}")
            return

        # Instantiate and register
        plugin = plugin_class()
        await self.register_plugin(plugin)

    async def register_plugin(self, plugin: JarvisPlugin) -> None:
        """Register plugin."""
        name = plugin.name
        self.plugins[name] = plugin

        # Initialize
        await plugin.initialize()

        # Register actions
        actions = plugin.register_actions()
        self.actions.update(actions)

        log.info(f"Plugin registered: {name} ({plugin.version})")

    async def unload_plugin(self, name: str) -> None:
        """Unload plugin."""
        if name not in self.plugins:
            log.warning(f"Plugin not found: {name}")
            return

        plugin = self.plugins.pop(name)
        await plugin.shutdown()

        # Remove actions
        for action_name in list(self.actions.keys()):
            # If action belongs to plugin, remove it
            if hasattr(self.actions[action_name], "__self__"):
                if self.actions[action_name].__self__ is plugin:
                    del self.actions[action_name]

        log.info(f"Plugin unloaded: {name}")

    async def handle_message(self, message: str, session_id: str) -> Optional[str]:
        """
        Route message through plugins.

        Returns:
            Response from first plugin that handles it
        """
        for plugin in self.plugins.values():
            response = await plugin.handle_message(message, session_id)
            if response is not None:
                return response

        return None

    async def call_action(self, action_name: str, **kwargs) -> Any:
        """
        Call registered action.

        Args:
            action_name: Name of action
            **kwargs: Action parameters

        Returns:
            Action result
        """
        if action_name not in self.actions:
            raise ValueError(f"Unknown action: {action_name}")

        action = self.actions[action_name]

        # Handle async
        if inspect.iscoroutinefunction(action):
            return await action(**kwargs)
        else:
            return action(**kwargs)

    def get_plugins(self) -> Dict[str, dict]:
        """Get all registered plugins."""
        return {
            name: plugin.get_metadata()
            for name, plugin in self.plugins.items()
        }

    def get_actions(self) -> List[str]:
        """Get all registered actions."""
        return list(self.actions.keys())


# Global instance
plugin_manager = PluginManager()


# Example plugin template
PLUGIN_TEMPLATE = '''"""
Example JARVIS Plugin

To use:
1. Create directory: backend/plugins/my_plugin/
2. Add this file as: backend/plugins/my_plugin/plugin.py
3. Restart JARVIS

Your plugin will be automatically loaded and registered.
"""

from backend.core.plugins import JarvisPlugin


class MyPlugin(JarvisPlugin):
    name = "my_plugin"
    version = "1.0.0"
    description = "My custom plugin"
    author = "Your Name"

    async def initialize(self) -> None:
        """Called on startup."""
        print("MyPlugin initialized")

    async def shutdown(self) -> None:
        """Called on shutdown."""
        print("MyPlugin shutdown")

    async def handle_message(self, message: str, session_id: str) -> str:
        """Handle chat messages."""
        if "my_keyword" in message.lower():
            return "My plugin handled this!"
        return None  # Not handled

    def register_actions(self) -> dict:
        """Register custom actions."""
        return {
            "my_action": self.my_action,
            "another_action": self.another_action,
        }

    async def my_action(self, param: str) -> str:
        """Custom action 1."""
        return f"Action result: {param}"

    async def another_action(self, x: int, y: int) -> int:
        """Custom action 2."""
        return x + y
'''
