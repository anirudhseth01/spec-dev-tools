"""Language plugins for code generation."""

from src.agents.coding.plugins.base import LanguagePlugin, LanguageConventions, GeneratedFile
from src.agents.coding.plugins.python_plugin import PythonPlugin
from src.agents.coding.plugins.typescript_plugin import TypeScriptPlugin
from src.agents.coding.plugins.registry import PluginRegistry

__all__ = [
    "GeneratedFile",
    "LanguageConventions",
    "LanguagePlugin",
    "PluginRegistry",
    "PythonPlugin",
    "TypeScriptPlugin",
]
