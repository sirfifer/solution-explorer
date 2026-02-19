"""Language parser registry."""

from .base import BaseParser
from .go import GoParser
from .python_lang import PythonParser
from .ruby import RubyParser
from .rust import RustParser
from .swift import SwiftParser
from .typescript import TypeScriptParser

# Map language to parser instance
PARSERS = {
    "swift": SwiftParser(),
    "python": PythonParser(),
    "rust": RustParser(),
    "typescript": TypeScriptParser(),
    "javascript": TypeScriptParser(),
    "go": GoParser(),
    "ruby": RubyParser(),
}

__all__ = [
    "BaseParser", "PARSERS",
    "SwiftParser", "PythonParser", "RustParser",
    "TypeScriptParser", "GoParser", "RubyParser",
]
