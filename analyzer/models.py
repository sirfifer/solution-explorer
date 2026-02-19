"""Data models for architecture analysis."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Symbol:
    id: str
    name: str
    kind: str  # class, struct, enum, function, protocol, trait, interface, type
    file: str
    line: int
    end_line: int
    code_preview: str  # first few lines of the declaration
    visibility: str = "internal"  # public, internal, private, fileprivate
    docstring: Optional[str] = None
    parent: Optional[str] = None  # parent symbol id
    dependencies: list = field(default_factory=list)
    annotations: list = field(default_factory=list)  # @attributes, decorators


@dataclass
class FileInfo:
    path: str
    language: str
    lines: int
    size_bytes: int
    symbols: list = field(default_factory=list)  # list of symbol ids
    imports: list = field(default_factory=list)
    exports: list = field(default_factory=list)
    module_doc: Optional[str] = None  # file-level docstring / header comment


@dataclass
class ComponentDoc:
    """Rich documentation extracted for a component."""
    readme: Optional[str] = None          # README.md content (markdown)
    claude_md: Optional[str] = None       # CLAUDE.md content (AI instructions)
    changelog: Optional[str] = None       # CHANGELOG.md content
    api_docs: Optional[str] = None        # API documentation if found
    architecture_notes: Optional[str] = None  # extracted from docs/ or inline
    purpose: Optional[str] = None         # one-line purpose from package metadata
    key_decisions: list = field(default_factory=list)  # architectural decisions
    patterns: list = field(default_factory=list)        # detected patterns
    tech_stack: list = field(default_factory=list)      # technologies used
    env_vars: list = field(default_factory=list)        # environment variables
    api_endpoints: list = field(default_factory=list)   # detected API routes


@dataclass
class Component:
    id: str
    name: str
    type: str  # application, service, library, module, package, infrastructure
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
    docs: dict = field(default_factory=dict)  # ComponentDoc as dict
    external_services: list = field(default_factory=list)  # External cloud APIs used


@dataclass
class Relationship:
    source: str
    target: str
    type: str  # import, http, websocket, grpc, ffi, database, file
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
    repositories: list = field(default_factory=list)  # multi-repo: [{name, url, ref}]
