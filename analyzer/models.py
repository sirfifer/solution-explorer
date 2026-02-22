"""Data models for architecture analysis.

Provides Pydantic BaseModel definitions when pydantic is installed,
with automatic fallback to stdlib dataclasses. Both backends expose
identical class names and field signatures.
"""

from dataclasses import asdict, dataclass, field, is_dataclass
from enum import Enum
from typing import Optional

# ---------------------------------------------------------------------------
# Enums (always available, no pydantic dependency)
# Using (str, Enum) for Python 3.10 compatibility (StrEnum requires 3.11)
# ---------------------------------------------------------------------------

class SymbolKind(str, Enum):
    CLASS = "class"
    STRUCT = "struct"
    ENUM = "enum"
    FUNCTION = "function"
    PROTOCOL = "protocol"
    TRAIT = "trait"
    INTERFACE = "interface"
    TYPE = "type"
    PROPERTY = "property"
    METHOD = "method"
    CONSTANT = "constant"
    EXTENSION = "extension"
    ACTOR = "actor"
    COMPONENT = "component"
    IMPL = "impl"


class Visibility(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    PRIVATE = "private"
    FILEPRIVATE = "fileprivate"
    PROTECTED = "protected"
    PACKAGE = "package"


class ComponentType(str, Enum):
    APPLICATION = "application"
    SERVICE = "service"
    LIBRARY = "library"
    PACKAGE = "package"
    MODULE = "module"
    INFRASTRUCTURE = "infrastructure"
    PROJECT = "project"
    REPOSITORY = "repository"
    MOBILE_CLIENT = "mobile-client"
    IOS_CLIENT = "ios-client"
    ANDROID_CLIENT = "android-client"
    WEB_CLIENT = "web-client"
    API_SERVER = "api-server"
    WATCH_APP = "watch-app"
    DESKTOP_APP = "desktop-app"
    CLI_TOOL = "cli-tool"
    SCREEN = "screen"
    TAB_CONTAINER = "tab-container"
    TAB = "tab"
    FEATURE_GROUP = "feature-group"
    CONTENT = "content"


class RelationshipType(str, Enum):
    IMPORT = "import"
    HTTP = "http"
    WEBSOCKET = "websocket"
    GRPC = "grpc"
    FFI = "ffi"
    DATABASE = "database"
    FILE = "file"
    DOCKER = "docker"
    NAVIGATION = "navigation"
    TAB = "tab"
    MODAL = "modal"
    EMBED = "embed"


# ---------------------------------------------------------------------------
# Serialization helper
# ---------------------------------------------------------------------------

def to_dict(obj):
    """Convert a model instance to a dict.

    Works with Pydantic BaseModel, stdlib dataclass, or plain dict.
    """
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    if isinstance(obj, dict):
        return obj
    raise TypeError(f"Cannot convert {type(obj)} to dict")


# ---------------------------------------------------------------------------
# Cross-reference validation (shared implementation)
# ---------------------------------------------------------------------------

def _validate_cross_refs(arch):
    """Check that all relationship sources/targets exist in component IDs.

    Returns a list of error strings. Empty list means validation passed.
    """
    errors = []

    component_ids = set()

    def collect_ids(components):
        for comp in components:
            if isinstance(comp, dict):
                component_ids.add(comp.get("id", ""))
                collect_ids(comp.get("children", []))
            elif hasattr(comp, "id"):
                component_ids.add(comp.id)
                collect_ids(getattr(comp, "children", []))

    collect_ids(arch.components if hasattr(arch, "components") else [])

    for rel in (arch.relationships if hasattr(arch, "relationships") else []):
        if isinstance(rel, dict):
            source, target = rel.get("source", ""), rel.get("target", "")
            rel_type = rel.get("type", "?")
        else:
            source, target, rel_type = rel.source, rel.target, rel.type

        if source not in component_ids:
            errors.append(
                f"Relationship {source} -> {target} ({rel_type}): "
                f"source '{source}' not found"
            )
        if target not in component_ids:
            errors.append(
                f"Relationship {source} -> {target} ({rel_type}): "
                f"target '{target}' not found"
            )

    return errors


# ---------------------------------------------------------------------------
# Model definitions (Pydantic when available, dataclass fallback)
# ---------------------------------------------------------------------------

try:
    from pydantic import BaseModel, Field, field_validator
    _PYDANTIC = True
except ImportError:
    _PYDANTIC = False


if _PYDANTIC:

    class Symbol(BaseModel):
        id: str
        name: str
        kind: str
        file: str
        line: int
        end_line: int
        code_preview: str
        visibility: str = "internal"
        docstring: Optional[str] = None
        parent: Optional[str] = None
        dependencies: list = Field(default_factory=list)
        annotations: list = Field(default_factory=list)

        @field_validator("line", "end_line")
        @classmethod
        def non_negative_line(cls, v):
            if v < 0:
                raise ValueError("Line number must be non-negative")
            return v

        @field_validator("name")
        @classmethod
        def name_not_empty(cls, v):
            if not v:
                raise ValueError("Symbol name must not be empty")
            return v

    class FileInfo(BaseModel):
        path: str
        language: str
        lines: int
        size_bytes: int
        symbols: list = Field(default_factory=list)
        imports: list = Field(default_factory=list)
        exports: list = Field(default_factory=list)
        module_doc: Optional[str] = None

        @field_validator("path")
        @classmethod
        def path_not_empty(cls, v):
            if not v:
                raise ValueError("File path must not be empty")
            return v

        @field_validator("lines")
        @classmethod
        def non_negative_lines(cls, v):
            if v < 0:
                raise ValueError("Line count must be non-negative")
            return v

    class ComponentDoc(BaseModel):
        """Rich documentation extracted for a component."""
        readme: Optional[str] = None
        claude_md: Optional[str] = None
        changelog: Optional[str] = None
        api_docs: Optional[str] = None
        architecture_notes: Optional[str] = None
        purpose: Optional[str] = None
        key_decisions: list = Field(default_factory=list)
        patterns: list = Field(default_factory=list)
        tech_stack: list = Field(default_factory=list)
        env_vars: list = Field(default_factory=list)
        api_endpoints: list = Field(default_factory=list)

    class Component(BaseModel):
        id: str
        name: str
        type: str
        path: str
        language: Optional[str] = None
        framework: Optional[str] = None
        description: Optional[str] = None
        port: Optional[int] = None
        children: list = Field(default_factory=list)
        files: list = Field(default_factory=list)
        entry_points: list = Field(default_factory=list)
        config_files: list = Field(default_factory=list)
        metrics: dict = Field(default_factory=dict)
        docs: dict = Field(default_factory=dict)
        external_services: list = Field(default_factory=list)

        @field_validator("id")
        @classmethod
        def id_not_empty(cls, v):
            if not v:
                raise ValueError("Component id must not be empty")
            return v

        @field_validator("port")
        @classmethod
        def valid_port(cls, v):
            if v is not None and not (1 <= v <= 65535):
                raise ValueError("Port must be between 1 and 65535")
            return v

    class Relationship(BaseModel):
        source: str
        target: str
        type: str
        label: Optional[str] = None
        protocol: Optional[str] = None
        port: Optional[int] = None
        bidirectional: bool = False

        @field_validator("source", "target")
        @classmethod
        def endpoints_not_empty(cls, v):
            if not v:
                raise ValueError("Relationship source and target must not be empty")
            return v

        @field_validator("port")
        @classmethod
        def valid_port(cls, v):
            if v is not None and not (1 <= v <= 65535):
                raise ValueError("Port must be between 1 and 65535")
            return v

    class Architecture(BaseModel):
        name: str
        description: str
        repository: Optional[str] = None
        generated_at: str = ""
        analyzer_version: str = "1.0.0"
        root_path: str = ""
        components: list = Field(default_factory=list)
        relationships: list = Field(default_factory=list)
        symbols: list = Field(default_factory=list)
        files: list = Field(default_factory=list)
        stats: dict = Field(default_factory=dict)
        repositories: list = Field(default_factory=list)

        def validate_cross_references(self):
            """Check that all relationship sources/targets exist in component IDs."""
            return _validate_cross_refs(self)

else:
    # -----------------------------------------------------------------------
    # Dataclass fallback (no pydantic installed)
    # -----------------------------------------------------------------------

    @dataclass
    class Symbol:
        id: str
        name: str
        kind: str
        file: str
        line: int
        end_line: int
        code_preview: str
        visibility: str = "internal"
        docstring: Optional[str] = None
        parent: Optional[str] = None
        dependencies: list = field(default_factory=list)
        annotations: list = field(default_factory=list)

    @dataclass
    class FileInfo:
        path: str
        language: str
        lines: int
        size_bytes: int
        symbols: list = field(default_factory=list)
        imports: list = field(default_factory=list)
        exports: list = field(default_factory=list)
        module_doc: Optional[str] = None

    @dataclass
    class ComponentDoc:
        """Rich documentation extracted for a component."""
        readme: Optional[str] = None
        claude_md: Optional[str] = None
        changelog: Optional[str] = None
        api_docs: Optional[str] = None
        architecture_notes: Optional[str] = None
        purpose: Optional[str] = None
        key_decisions: list = field(default_factory=list)
        patterns: list = field(default_factory=list)
        tech_stack: list = field(default_factory=list)
        env_vars: list = field(default_factory=list)
        api_endpoints: list = field(default_factory=list)

    @dataclass
    class Component:
        id: str
        name: str
        type: str
        path: str
        language: Optional[str] = None
        framework: Optional[str] = None
        description: Optional[str] = None
        port: Optional[int] = None
        children: list = field(default_factory=list)
        files: list = field(default_factory=list)
        entry_points: list = field(default_factory=list)
        config_files: list = field(default_factory=list)
        metrics: dict = field(default_factory=dict)
        docs: dict = field(default_factory=dict)
        external_services: list = field(default_factory=list)

    @dataclass
    class Relationship:
        source: str
        target: str
        type: str
        label: Optional[str] = None
        protocol: Optional[str] = None
        port: Optional[int] = None
        bidirectional: bool = False

    @dataclass
    class Architecture:
        name: str
        description: str
        repository: Optional[str] = None
        generated_at: str = ""
        analyzer_version: str = "1.0.0"
        root_path: str = ""
        components: list = field(default_factory=list)
        relationships: list = field(default_factory=list)
        symbols: list = field(default_factory=list)
        files: list = field(default_factory=list)
        stats: dict = field(default_factory=dict)
        repositories: list = field(default_factory=list)

        def validate_cross_references(self):
            """Check that all relationship sources/targets exist in component IDs."""
            return _validate_cross_refs(self)
