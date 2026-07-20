"""Symbol-reference extraction for Tier 1 (D5, P9-0 gate defect wave B).

The gate found code-level relationship extraction far too sparse: the iOS
projection carried 93 edges for 190 components, nearly all UI navigation, and
intra-module type usage produced nothing, so core engines read as orphans (D4).

This module closes that gap at extraction time. For each supported language it
scans a file's content for the NAMES of type-like symbols it references (type
usages, constructor calls, conformances, casts, generics) and emits one
``symbol_reference`` signal per distinct referenced name, carrying the
first-seen line and a reference count. Tier 3 derivation
(:mod:`analyzer.derive.relationships`) resolves those names against the store's
own symbol table and draws component-to-component ``uses`` edges. This is a
NAME-based join, deliberately KISS (invariant I1: mechanical, no type inference,
no call-graph): a referenced name that matches no local type definition simply
resolves to nothing (stdlib and framework names harmlessly drop out), an
ambiguous name that resolves to several components is dropped at derive time
rather than guessed, a single-definer match in a per-name-import language
requires import evidence, and a common Swift platform name requires another tie
to the resolved component (PR #55 review finding 1; see
:data:`PER_NAME_IMPORT_LANGUAGES` and :data:`SWIFT_COMMON_TYPE_NAMES`).

Only reference candidates whose START is real code are kept: a name appearing
inside a string literal or a masked comment is not a usage (the shared
:class:`~analyzer.extract.frameworks.StringMask` filters them), and the
trailing member of a qualified access (``requests.Session()``) is excluded
because it resolves in the qualifier's namespace, not locally. Extraction is
deterministic (invariant I4): names are emitted in first-occurrence order and
the per-file candidate scan is capped (:data:`MAX_REFERENCE_NAMES`) so a
pathological generated file cannot blow up signal volume.

Extractor maturity is honest and per-language (:data:`REFERENCE_LANGUAGES`).
Swift, Python, TypeScript, JavaScript, C#, and Java have reference extractors
here; Go, Rust, and Ruby do not yet, and the D4 orphan reframing consults this
set so a substantial component in a weakly-scanned language is heavily de-ranked
with an
explicit blind-spot caveat instead of being asserted as unreferenced at full
strength.

Import semantics differ by language and gate how strongly a single-definer name
resolves (see :data:`PER_NAME_IMPORT_LANGUAGES`). Java is a per-name-import
language: an ``import com.example.service.UserService;`` names one specific type,
so a reference to ``UserService`` that resolves to exactly one component still
REQUIRES the file to import that type before an edge is drawn. This is the safe
choice: a cross-component Java reference always carries an import (only
same-package classes, which live in the same component, can omit it), so the
import requirement suppresses coincidental same-name matches without losing the
cross-component edges this whole pass exists to find. Java differs from C# here,
whose ``using`` directive imports a whole namespace rather than a single type and
therefore is NOT per-name evidence.
"""

from __future__ import annotations

import re

from .facts import SignalRecord
from .frameworks import StringMask

__all__ = [
    "REFERENCE_LANGUAGES",
    "PER_NAME_IMPORT_LANGUAGES",
    "SWIFT_COMMON_TYPE_NAMES",
    "MAX_REFERENCE_NAMES",
    "extract_reference_signals",
]

# Languages with a symbol-reference extractor below. The D4 orphan reframing
# treats every OTHER language as a "weak" reference extractor (honest maturity).
REFERENCE_LANGUAGES = frozenset(
    {"swift", "python", "typescript", "javascript", "csharp", "java"}
)

# Cap on distinct referenced names emitted per file. A generated or minified
# file can name thousands of identifiers; beyond this the marginal edge value is
# nil and the scan cost is not worth it. Recorded scale guard (D5).
MAX_REFERENCE_NAMES = 400

# Languages whose import syntax names modules or symbols precisely enough to
# serve as reference evidence (Python `from x import Y`, TS/JS `import { Y }
# from './x'`). For these, derive time REQUIRES import evidence before drawing a
# `uses` edge even when exactly one component defines the name (PR #55 review
# finding 1: `requests.Session()` must never edge to an unrelated local
# `session` component just because it is the only definer). Swift is absent by
# design: its imports are module-level with no per-name form, so it relies on
# the qualified-access exclusion plus SWIFT_COMMON_TYPE_NAMES below.
PER_NAME_IMPORT_LANGUAGES = frozenset({"python", "typescript", "javascript", "java"})

# Common Swift platform type names (Foundation/UIKit/SwiftUI/stdlib). Swift has
# no per-name imports to prove a local resolution, so when a referenced name is
# on this list AND the referencing file shows no other relationship with the
# resolved component (no non-common-name reference from the same file, no
# module import of it), the reference is dropped rather than risk a false edge
# to a user component that happens to share a platform type name (PR #55 review
# finding 1: a bare `Timer()` must not edge to a component defining its own
# `Timer`). HONEST BOUNDARY: a user type genuinely named `Timer` or `Task` used
# from a file with no other tie to its component draws no uses edge; recorded
# in TASKS.md (Discovered).
SWIFT_COMMON_TYPE_NAMES = frozenset({
    # Foundation / stdlib / concurrency
    "Timer", "Notification", "NotificationCenter", "Data", "Date", "URL",
    "UUID", "Error", "Result", "Task", "Session", "URLSession", "URLRequest",
    "URLComponents", "Bundle", "FileManager", "UserDefaults", "OperationQueue",
    "DispatchQueue", "JSONDecoder", "JSONEncoder", "Calendar", "Locale",
    "TimeZone", "Character", "Substring", "Regex", "IndexPath", "IndexSet",
    "Thread", "RunLoop", "Progress", "Measurement", "Decimal", "Set", "Array",
    "Dictionary", "String", "Int", "Double", "Float", "Bool", "Optional",
    # SwiftUI
    "State", "Binding", "Environment", "EnvironmentObject", "ObservedObject",
    "StateObject", "Published", "Color", "Image", "Text", "List", "Label",
    "Link", "Button", "Toggle", "Picker", "Section", "Form", "Spacer",
    "Divider", "Menu", "Alert", "Slider", "Stepper", "TextField",
    "SecureField", "TextEditor", "ProgressView", "ScrollView", "VStack",
    "HStack", "ZStack", "LazyVStack", "LazyHStack", "Grid", "Table",
    "NavigationLink", "NavigationStack", "NavigationView", "TabView",
    "GeometryReader", "Group", "Namespace", "Font", "Angle", "Animation",
    "Path", "Shape", "Circle", "Rectangle", "RoundedRectangle", "Capsule",
    "Ellipse", "App", "Scene", "View", "ViewBuilder", "Gradient",
    "LinearGradient", "AnyView", "EmptyView",
    # UIKit / CoreGraphics
    "UIView", "UIViewController", "UIColor", "UIImage", "UIApplication",
    "UIWindow", "UIScreen", "UILabel", "UIButton", "UITableView",
    "UICollectionView", "CGFloat", "CGPoint", "CGSize", "CGRect", "NSObject",
})

# A referenced type-like name: an uppercase-initial identifier. group(1) is the
# name in every pattern. These are intentionally simple anchors; precision comes
# from resolving against real local type definitions at derive time, not from
# the regex. Constructor/call `Name(` is common to all four languages.
_CTOR = r"\b([A-Z]\w+)\s*\("
_ANNOT = r":\s*([A-Z]\w+)"          # `: Type` annotation / conformance
_RETURN = r"->\s*([A-Z]\w+)"        # `-> Type` return type
# Static member access `Name.member` (AudioEngine.shared, Config.value). The
# dominant reference shape for singleton-style iOS code, and the reason the
# core engines still read unreferenced after the ctor/annotation patterns
# landed. Direction matters and keeps this safe against the qualified-access
# fabrication class: the extractor separately EXCLUDES any name preceded by a
# dot, so requests.Session and Foundation.Timer stay dead while Session.shared
# counts. Requires a word character after the dot so a plain trailing period
# in prose never matches.
_STATIC = r"\b([A-Z]\w+)\.\w"

_REFERENCE_RULES: dict[str, list[re.Pattern]] = {
    "swift": [
        re.compile(_CTOR),
        re.compile(_ANNOT),
        re.compile(_RETURN),
        re.compile(r"\b(?:as[?!]?|is)\s+([A-Z]\w+)"),   # casts: `as Foo`, `is Foo`
        re.compile(r"<\s*([A-Z]\w+)"),                   # generic argument
        re.compile(_STATIC),
    ],
    "python": [
        re.compile(_CTOR),
        re.compile(_ANNOT),
        re.compile(_RETURN),
        re.compile(r"\bclass\s+\w+\s*\(\s*([A-Z]\w+)"),  # base class
    ],
    "typescript": [
        re.compile(r"\bnew\s+([A-Z]\w+)"),
        re.compile(_ANNOT),
        re.compile(r"\bextends\s+([A-Z]\w+)"),
        re.compile(r"\bimplements\s+([A-Z]\w+)"),
        re.compile(r"<\s*([A-Z]\w+)"),                   # generic / JSX open
    ],
    "javascript": [
        re.compile(r"\bnew\s+([A-Z]\w+)"),
        re.compile(r"\bextends\s+([A-Z]\w+)"),
        re.compile(r"<\s*([A-Z]\w+)"),                   # JSX open tag
    ],
    # C# names types in PascalCase and, like Swift, imports whole namespaces
    # (`using X.Y;`) with no per-name form, so it stays out of
    # PER_NAME_IMPORT_LANGUAGES and a single local definer resolves by name.
    # The qualified-access exclusion in extract_reference_signals keeps
    # member access (`x.Foo`) and namespaced calls (`System.Console`) from
    # counting as local references.
    "csharp": [
        re.compile(r"\bnew\s+([A-Z]\w+)"),
        re.compile(
            r"\b(?:class|struct|interface|record(?:\s+struct)?)\s+\w+"
            r"(?:<[^>]*>)?\s*:\s*([A-Z]\w+)"             # base type / interface
        ),
        re.compile(r"<\s*([A-Z]\w+)"),                   # generic argument
        re.compile(_STATIC),
    ],
    "java": [
        re.compile(r"\bnew\s+([A-Z]\w+)"),               # constructor call
        re.compile(r"\bextends\s+([A-Z]\w+)"),
        re.compile(r"\bimplements\s+([A-Z]\w+)"),
        re.compile(r"\bthrows\s+([A-Z]\w+)"),
        re.compile(r"<\s*([A-Z]\w+)"),                   # generic argument
        re.compile(_STATIC),                             # static access Name.member
        # A type used in a field, parameter, local, or return-type declaration:
        # an uppercase-initial type name, an optional generic section, then a
        # lowercase-initial variable or method name. Java convention keeps type
        # names uppercase and identifiers lowercase, so this stays precise; a
        # stdlib name (String, List) simply resolves to nothing at derive time.
        re.compile(r"\b([A-Z]\w+)(?:<[^;={}()]*>)?\s+[a-z_$]\w*"),
    ],
}


def _line_of(content: str, pos: int) -> int:
    return content.count("\n", 0, pos) + 1


def extract_reference_signals(
    content: str, language: str, mask: StringMask
) -> list[SignalRecord]:
    """Emit ``symbol_reference`` signals for one file (D5).

    Each signal value is ``{"name": <referenced type name>, "count": <n>}`` with
    the 1-based line of the first occurrence. Names are emitted in
    first-occurrence order (deterministic, invariant I4). ``mask`` is the shared
    :class:`StringMask` so a name inside a string or ``#`` comment is not counted
    as a reference.
    """
    rules = _REFERENCE_RULES.get(language)
    if not rules:
        return []
    # name -> [first_pos, count]. Insertion order is first-occurrence order once
    # candidates are processed in position order, so sort matches by start.
    candidates: list[tuple[int, str]] = []
    for pat in rules:
        for m in pat.finditer(content):
            start = m.start(1)
            if mask.in_string(start):
                continue  # inside a string literal or comment, not a reference
            if start > 0 and content[start - 1] == ".":
                # Qualified access (PR #55 review finding 1a): `requests.Session()`,
                # `Foundation.Timer()`, Swift enum shorthand `.SomeCase(...)`. The
                # trailing member is resolved by the QUALIFIER's namespace, not
                # the local symbol table, so it is never a local type reference.
                continue
            candidates.append((start, m.group(1)))
    candidates.sort()

    agg: dict[str, list[int]] = {}
    for start, name in candidates:
        entry = agg.get(name)
        if entry is None:
            if len(agg) >= MAX_REFERENCE_NAMES:
                continue  # scale guard: stop taking new distinct names
            agg[name] = [start, 1]
        else:
            entry[1] += 1

    ordered = sorted(agg.items(), key=lambda kv: (kv[1][0], kv[0]))
    return [
        SignalRecord("symbol_reference", {"name": name, "count": count},
                     _line_of(content, first_pos))
        for name, (first_pos, count) in ordered
    ]
