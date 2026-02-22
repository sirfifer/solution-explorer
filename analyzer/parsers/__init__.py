"""Language parser registry."""

from .base import BaseParser
from .go import GoParser
from .python_lang import PythonParser
from .ruby import RubyParser
from .rust import RustParser
from .swift import SwiftParser
from .typescript import TypeScriptParser

# Start with regex parsers as baseline
PARSERS = {
    "swift": SwiftParser(),
    "python": PythonParser(),
    "rust": RustParser(),
    "typescript": TypeScriptParser(),
    "javascript": TypeScriptParser(),
    "go": GoParser(),
    "ruby": RubyParser(),
}

# Upgrade to tree-sitter parsers when available.
# Each import is independent so one failing does not block others.

try:
    from .swift_ts import SwiftTreeSitterParser
    PARSERS["swift"] = SwiftTreeSitterParser()
except ImportError:
    pass

try:
    from .typescript_ts import TypeScriptTreeSitterParser
    _ts_parser = TypeScriptTreeSitterParser()
    PARSERS["typescript"] = _ts_parser
    PARSERS["javascript"] = _ts_parser
except ImportError:
    pass

try:
    from .rust_ts import RustTreeSitterParser
    PARSERS["rust"] = RustTreeSitterParser()
except ImportError:
    pass

try:
    from .python_ts import PythonTreeSitterParser
    PARSERS["python"] = PythonTreeSitterParser()
except ImportError:
    pass

try:
    from .go_ts import GoTreeSitterParser
    PARSERS["go"] = GoTreeSitterParser()
except ImportError:
    pass

try:
    from .ruby_ts import RubyTreeSitterParser
    PARSERS["ruby"] = RubyTreeSitterParser()
except ImportError:
    pass

__all__ = [
    "BaseParser", "PARSERS",
    "SwiftParser", "PythonParser", "RustParser",
    "TypeScriptParser", "GoParser", "RubyParser",
]
