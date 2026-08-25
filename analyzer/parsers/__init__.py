"""Language parser registry.

There is no fallback tier, by decision and after an incident.

This registry used to install the regex parsers as a baseline and then "upgrade"
to tree-sitter where the import happened to succeed, each attempt wrapped in
`except ImportError: pass`. On 2026-08-24 a VS Code regeneration ran under an
interpreter without tree-sitter installed, and all 3.8M lines of TypeScript were
read by the regex parser without a single line of output saying so. The analyzer
reported "Coverage: 100% of source analyzed, 0 gaps" and meant it: every file was
parsed. Nothing measured whether any of it was parsed WELL. The projection had
355,617 symbols instead of 153,231 and 55 methods instead of 28,501, and it came
within one command of being enriched at real expense.

So a language is either read by its real parser or the run stops. A degraded
answer is worse than no answer, because a degraded answer is indistinguishable
from a good one downstream.

The regex modules still exist, and they are NOT parsers any more. Each
tree-sitter parser delegates to its regex counterpart for the things tree-sitter
does not do here: framework detection, import extraction, endpoint sniffing.
They are helpers reached THROUGH a real parser, and nothing in this file will
ever register one as a standalone parser for a language again.
"""

from typing import Optional

from .base import BaseParser
from .storyboard import StoryboardParser

# language -> why its real parser is unavailable. Consulted on the way to a hard
# failure, so the message can name the missing package instead of "no parser".
DEGRADED_LANGUAGES: dict[str, str] = {}

# Storyboards and xibs are XML. There is no tree-sitter grammar for them here and
# there is no better parser being substituted for, so this is the real parser for
# that language rather than a fallback standing in for one.
PARSERS: dict[str, BaseParser] = {
    "storyboard": StoryboardParser(),
}


class DegradedParserError(RuntimeError):
    """Raised when a language's real parser is missing and work needs it.

    Deliberately fatal. The alternative, which this replaced, is a projection
    that looks complete and is quietly wrong.
    """


def _register(languages: list[str], module: str, symbol: str, package: str) -> None:
    """Install one tree-sitter parser, or record precisely why it is missing.

    The import is still guarded, because a missing grammar for Ruby must not stop
    someone analysing a Python repo. What changed is what happens on failure:
    nothing takes the parser's place, and the reason is kept so that a run which
    actually needs that language can say what to install.
    """
    try:
        mod = __import__(f"analyzer.parsers.{module}", fromlist=[symbol])
        parser = getattr(mod, symbol)()
    except ImportError as exc:
        for language in languages:
            DEGRADED_LANGUAGES[language] = f"{package} is not installed ({exc})"
        return

    # A module that imports is not a parser that works. Each _ts module guards
    # its own grammar import and sets _ts_available, so the module loads
    # perfectly well with no grammar behind it. Asking the parser whether it
    # actually holds its grammar is the only honest test, and without it
    # DEGRADED_LANGUAGES stays empty on exactly the machine that has the
    # problem. Any preflight built on it would then give a false all-clear,
    # which is the same shape as the incident this file exists to prevent: the
    # failure was real and nothing on the way in could see it.
    if not getattr(parser, "_ts_available", False):
        for language in languages:
            DEGRADED_LANGUAGES[language] = (
                f"{package} imported but its grammar did not load, so this "
                f"parser cannot read anything"
            )
        return

    for language in languages:
        PARSERS[language] = parser


_register(["typescript", "javascript"], "typescript_ts", "TypeScriptTreeSitterParser", "tree-sitter-typescript")
_register(["python"], "python_ts", "PythonTreeSitterParser", "tree-sitter-python")
_register(["swift"], "swift_ts", "SwiftTreeSitterParser", "tree-sitter-swift")
_register(["rust"], "rust_ts", "RustTreeSitterParser", "tree-sitter-rust")
_register(["go"], "go_ts", "GoTreeSitterParser", "tree-sitter-go")
_register(["ruby"], "ruby_ts", "RubyTreeSitterParser", "tree-sitter-ruby")
_register(["csharp"], "csharp_ts", "CSharpTreeSitterParser", "tree-sitter-c-sharp")
_register(["java"], "java_ts", "JavaTreeSitterParser", "tree-sitter-java")
_register(["cpp"], "cpp_ts", "CppTreeSitterParser", "tree-sitter-cpp")


def get_parser(language: Optional[str]) -> Optional[BaseParser]:
    """The parser for a language, or a hard failure if the real one is missing.

    Returns None for languages this tool does not parse at all, such as markdown
    and json, which is an ordinary and expected answer. Raises for a language it
    DOES parse but cannot right now, which is the case that used to be silent.
    """
    if language is None:
        return None
    if language in DEGRADED_LANGUAGES:
        raise DegradedParserError(
            f"cannot analyse {language}: {DEGRADED_LANGUAGES[language]}. "
            f"This run is stopping rather than falling back to a weaker parser, "
            f"which would produce a projection that looks complete and is not. "
            f"Install the missing grammar (pip install -e '.[treesitter]') and "
            f"run again."
        )
    return PARSERS.get(language)


def degraded_languages_present(languages) -> dict[str, str]:
    """Which of these languages cannot be read properly. Empty means go ahead."""
    return {lang: DEGRADED_LANGUAGES[lang] for lang in languages if lang in DEGRADED_LANGUAGES}


__all__ = [
    "BaseParser", "PARSERS", "DEGRADED_LANGUAGES", "DegradedParserError",
    "get_parser", "degraded_languages_present", "StoryboardParser",
]
