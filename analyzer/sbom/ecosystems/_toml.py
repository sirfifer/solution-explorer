"""Deterministic TOML loading for the SBOM parsers.

pyproject.toml, poetry.lock, Cargo.toml, and Cargo.lock are TOML. The standard
library ships ``tomllib`` from Python 3.11 on; the analyzer's floor is 3.10
(pyproject requires-python), so this wraps the import and reports the gap loudly
rather than silently dropping a manifest on 3.10.

``load`` returns the parsed dict. ``TomlUnavailable`` is raised when no TOML
parser is present, and the ecosystem parsers turn it into a ParseWarning naming
the exact remediation (run on Python 3.11+), so the failure is visible in the
supply chain surface, never invisible.
"""

from __future__ import annotations

try:  # Python 3.11+
    import tomllib as _tomllib
except ImportError:  # pragma: no cover - exercised only on Python 3.10
    _tomllib = None

__all__ = ["load", "TomlUnavailable", "TomlError", "toml_available"]


class TomlUnavailable(RuntimeError):
    """No TOML parser is available on this interpreter (Python < 3.11)."""


# The concrete decode-error type callers catch, independent of which backend
# parsed the text.
TomlError = _tomllib.TOMLDecodeError if _tomllib is not None else ValueError


def toml_available() -> bool:
    return _tomllib is not None


def load(text: str) -> dict:
    """Parse a TOML document string into a dict.

    Raises ``TomlUnavailable`` when no parser is present and ``TomlError`` on a
    malformed document.
    """
    if _tomllib is None:
        raise TomlUnavailable(
            "TOML parsing requires Python 3.11+ (tomllib); run the analyzer on "
            "Python 3.11 or newer to include this manifest in the SBOM"
        )
    return _tomllib.loads(text)
