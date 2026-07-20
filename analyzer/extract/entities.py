"""Per-ORM and per-schema data-entity extraction (Tier 1 support for P5-2).

The Data lens (LENS-DESIGN.md L3; TARGET-ARCHITECTURE.md section 5) is built
from data entities: ORM models, migration-declared tables, and standalone
schema files. This module holds the precise, framework-anchored extractors that
turn one file's content into ``(value, match_start)`` tuples; the caller
(signals.py ``extract_entity_signals``) turns ``match_start`` into a 1-based
line number and wraps each value in a ``data_entity`` SignalRecord. Derivation
(analyzer/derive/entities.py) joins those signals into ``data_entities`` and
``entity_access`` rows.

Every extractor is pure regex over content and needs no parser, so it runs for
parser-backed code files (SQLAlchemy, Django, ActiveRecord, SwiftData, TypeORM,
GORM) and for parser-less standalone schema files (Prisma, SQL DDL, JSON Schema)
alike. Results are position-ordered and deduped so extraction is deterministic
across processes (invariant I4).

A value dict carries: ``name`` (entity/class/table name), ``kind`` (``model`` |
``migration`` | ``table`` | ``schema``), ``framework``, optional ``table`` (the
physical table name where known), ``fields`` (a list of ``{"name", "type"}``
where parseable), and optional ``inferred`` (True where extraction is partial).
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _hint(content: str, *markers: str) -> bool:
    return any(m in content for m in markers)


def _block_lines(content: str, start_idx: int) -> tuple[list[str], int]:
    """Return the lines of a Python indented block starting at ``start_idx``.

    ``start_idx`` is the offset of the ``class`` (or ``def``) header line. The
    block is every subsequent line indented deeper than the header, stopping at
    the first line at or below the header indent (blank lines do not end it).
    Returns (body_lines, header_line_number).
    """
    lines = content.split("\n")
    header_line_no = content.count("\n", 0, start_idx) + 1
    header = lines[header_line_no - 1]
    header_indent = len(header) - len(header.lstrip())
    body: list[str] = []
    for ln in lines[header_line_no:]:
        if not ln.strip():
            body.append(ln)
            continue
        indent = len(ln) - len(ln.lstrip())
        if indent <= header_indent:
            break
        body.append(ln)
    return body, header_line_no


def _dedupe(items: list[tuple[dict, int]]) -> list[tuple[dict, int]]:
    """Keep the first match per (kind, name), position-ordered."""
    seen: set = set()
    out: list[tuple[dict, int]] = []
    for value, start in sorted(items, key=lambda t: t[1]):
        key = (value.get("kind"), value.get("name"))
        if key in seen:
            continue
        seen.add(key)
        out.append((value, start))
    return out


# ---------------------------------------------------------------------------
# Python: SQLAlchemy, Django, Django migrations, Alembic
# ---------------------------------------------------------------------------

_PY_CLASS = re.compile(r"(?m)^[ \t]*class\s+(\w+)\s*\(([^)]*)\)\s*:")
_SA_TABLENAME = re.compile(r"__tablename__\s*=\s*['\"]([^'\"]+)['\"]")
_SA_COLUMN = re.compile(
    r"^[ \t]*(\w+)\s*(?::\s*[^=]+)?=\s*(?:Column|mapped_column)\s*\(\s*"
    r"([A-Za-z_][\w.]*)?"
)
_SA_MAPPED = re.compile(r"^[ \t]*(\w+)\s*:\s*Mapped\[\s*([^\]]+)\]")
_DJ_FIELD = re.compile(r"^[ \t]*(\w+)\s*=\s*models\.(\w+Field|ForeignKey|ManyToManyField|OneToOneField)")


def _python_entities(content: str) -> list[tuple[dict, int]]:
    out: list[tuple[dict, int]] = []
    is_sqlalchemy = _hint(
        content, "declarative_base", "DeclarativeBase", "sqlalchemy",
        "db.Model", "Column(", "mapped_column",
    )
    is_django = _hint(content, "models.Model", "from django", "import django")

    for m in _PY_CLASS.finditer(content):
        name = m.group(1)
        bases = m.group(2)
        body, header_line = _block_lines(content, m.start())
        body_text = "\n".join(body)

        # SQLAlchemy declarative model: a Base/db.Model subclass with a
        # __tablename__ or Column-shaped attributes.
        sa_model = (
            is_sqlalchemy
            and (
                "Base" in bases or "db.Model" in bases or "DeclarativeBase" in bases
            )
            and ("__tablename__" in body_text or "Column(" in body_text
                 or "mapped_column" in body_text)
        )
        dj_model = is_django and ("models.Model" in bases or "Model" == bases.strip())

        if sa_model:
            tn = _SA_TABLENAME.search(body_text)
            fields = _sqlalchemy_fields(body)
            value: dict = {
                "name": name, "kind": "model", "framework": "sqlalchemy",
                "fields": fields,
            }
            if tn:
                value["table"] = tn.group(1)
            out.append((value, m.start()))
            continue

        if dj_model:
            fields = _django_fields(body)
            out.append((
                {"name": name, "kind": "model", "framework": "django",
                 "fields": fields},
                m.start(),
            ))
            continue

    out.extend(_django_migration_models(content))
    out.extend(_alembic_tables(content))
    return _dedupe(out)


def _sqlalchemy_fields(body: list[str]) -> list[dict]:
    fields: list[dict] = []
    seen: set[str] = set()
    for ln in body:
        m = _SA_COLUMN.match(ln)
        if m and m.group(1) not in ("__tablename__",):
            fname = m.group(1)
            if fname in seen or fname.startswith("__"):
                continue
            seen.add(fname)
            fields.append({"name": fname, "type": m.group(2) or None})
            continue
        m2 = _SA_MAPPED.match(ln)
        if m2:
            fname = m2.group(1)
            if fname in seen:
                continue
            seen.add(fname)
            fields.append({"name": fname, "type": m2.group(2).strip()})
    return fields


def _django_fields(body: list[str]) -> list[dict]:
    fields: list[dict] = []
    seen: set[str] = set()
    for ln in body:
        m = _DJ_FIELD.match(ln)
        if m and m.group(1) not in seen:
            seen.add(m.group(1))
            fields.append({"name": m.group(1), "type": m.group(2)})
    return fields


_DJ_CREATE_MODEL = re.compile(
    r"migrations\.CreateModel\s*\(\s*name\s*=\s*['\"](\w+)['\"]", re.DOTALL
)
_DJ_MIG_FIELD = re.compile(r"\(\s*['\"](\w+)['\"]\s*,\s*models\.(\w+)")


def _django_migration_models(content: str) -> list[tuple[dict, int]]:
    out: list[tuple[dict, int]] = []
    for m in _DJ_CREATE_MODEL.finditer(content):
        name = m.group(1)
        # fields declared in the following bracketed block, bounded to the next
        # CreateModel or the end of the statement.
        tail = content[m.end():m.end() + 2000]
        fields = [
            {"name": fm.group(1), "type": fm.group(2)}
            for fm in _DJ_MIG_FIELD.finditer(tail)
        ]
        out.append((
            {"name": name, "kind": "migration", "framework": "django",
             "fields": fields},
            m.start(),
        ))
    return out


_ALEMBIC_CREATE = re.compile(r"op\.create_table\s*\(\s*['\"](\w+)['\"]", re.DOTALL)
_ALEMBIC_COL = re.compile(r"sa\.Column\s*\(\s*['\"](\w+)['\"]\s*,\s*sa\.(\w+)")


def _alembic_tables(content: str) -> list[tuple[dict, int]]:
    out: list[tuple[dict, int]] = []
    for m in _ALEMBIC_CREATE.finditer(content):
        table = m.group(1)
        tail = content[m.end():m.end() + 2000]
        fields = [
            {"name": cm.group(1), "type": cm.group(2)}
            for cm in _ALEMBIC_COL.finditer(tail)
        ]
        out.append((
            {"name": table, "kind": "migration", "framework": "alembic",
             "table": table, "fields": fields},
            m.start(),
        ))
    return out


# ---------------------------------------------------------------------------
# Ruby: ActiveRecord model, schema.rb, Rails migration
# ---------------------------------------------------------------------------

_RB_MODEL = re.compile(
    r"(?m)^\s*class\s+(\w+)\s*<\s*(?:ApplicationRecord|ActiveRecord::Base)\b"
)
_RB_CREATE_TABLE = re.compile(r"create_table\s+[:'\"]+(\w+)['\"]?")
_RB_COLUMN = re.compile(r"t\.(\w+)\s+[:'\"]+(\w+)")


def _ruby_entities(content: str) -> list[tuple[dict, int]]:
    out: list[tuple[dict, int]] = []
    for m in _RB_MODEL.finditer(content):
        out.append((
            {"name": m.group(1), "kind": "model", "framework": "activerecord",
             "fields": []},
            m.start(),
        ))

    is_schema = "ActiveRecord::Schema" in content or "define(version" in content
    for m in _RB_CREATE_TABLE.finditer(content):
        table = m.group(1)
        # Column declarations until the matching `end` of this create_table.
        tail = content[m.end():]
        end_idx = tail.find("\n  end")
        block = tail[:end_idx] if end_idx >= 0 else tail[:1500]
        fields = [
            {"name": cm.group(2), "type": cm.group(1)}
            for cm in _RB_COLUMN.finditer(block)
        ]
        kind = "table" if is_schema else "migration"
        framework = "activerecord" if is_schema else "rails"
        out.append((
            {"name": table, "kind": kind, "framework": framework,
             "table": table, "fields": fields},
            m.start(),
        ))
    return _dedupe(out)


# ---------------------------------------------------------------------------
# Swift: SwiftData (@Model) and CoreData (NSManagedObject)
# ---------------------------------------------------------------------------

_SW_MODEL = re.compile(r"@Model\s+(?:final\s+)?class\s+(\w+)")
_SW_MANAGED = re.compile(r"(?m)^\s*class\s+(\w+)\s*:\s*NSManagedObject\b")
_SW_VAR = re.compile(
    r"(?m)^\s*(?:@NSManaged\s+)?(?:public\s+|private\s+)?var\s+(\w+)\s*:\s*([\w<>?\[\] .]+)"
)


def _swift_entities(content: str) -> list[tuple[dict, int]]:
    out: list[tuple[dict, int]] = []
    for rx, framework in ((_SW_MODEL, "swiftdata"), (_SW_MANAGED, "coredata")):
        for m in rx.finditer(content):
            name = m.group(1)
            body = _brace_body(content, m.end())
            fields: list[dict] = []
            seen: set[str] = set()
            for vm in _SW_VAR.finditer(body):
                fname = vm.group(1)
                if fname in seen:
                    continue
                seen.add(fname)
                fields.append({"name": fname, "type": vm.group(2).strip()})
            # SwiftData/CoreData extraction is partial (computed properties,
            # relationships, transformable attributes are not fully modeled).
            out.append((
                {"name": name, "kind": "model", "framework": framework,
                 "fields": fields, "inferred": True},
                m.start(),
            ))
    return _dedupe(out)


def _brace_body(content: str, from_idx: int) -> str:
    """Return the text inside the first ``{...}`` block at/after ``from_idx``."""
    open_idx = content.find("{", from_idx)
    if open_idx < 0:
        return ""
    depth = 0
    for i in range(open_idx, len(content)):
        c = content[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return content[open_idx + 1:i]
    return content[open_idx + 1:]


# ---------------------------------------------------------------------------
# TypeScript / JavaScript: TypeORM entities
# ---------------------------------------------------------------------------

_TS_ENTITY = re.compile(r"@Entity\s*\([^)]*\)\s*(?:export\s+)?class\s+(\w+)")
_TS_COLUMN = re.compile(
    r"@(?:Column|PrimaryColumn|PrimaryGeneratedColumn|CreateDateColumn|"
    r"UpdateDateColumn)\s*\([^)]*\)\s*(\w+)\s*[:!]?\s*([\w<>\[\] ]+)?"
)


def _ts_entities(content: str) -> list[tuple[dict, int]]:
    if "@Entity" not in content:
        return []
    out: list[tuple[dict, int]] = []
    for m in _TS_ENTITY.finditer(content):
        name = m.group(1)
        body = _brace_body(content, m.end())
        fields: list[dict] = []
        seen: set[str] = set()
        for cm in _TS_COLUMN.finditer(body):
            fname = cm.group(1)
            if fname in seen:
                continue
            seen.add(fname)
            ftype = (cm.group(2) or "").strip().rstrip(";") or None
            fields.append({"name": fname, "type": ftype})
        out.append((
            {"name": name, "kind": "model", "framework": "typeorm",
             "fields": fields},
            m.start(),
        ))
    return _dedupe(out)


# ---------------------------------------------------------------------------
# Go: GORM structs
# ---------------------------------------------------------------------------

_GO_STRUCT = re.compile(r"type\s+(\w+)\s+struct\s*\{")
_GO_FIELD = re.compile(r"^\s*(\w+)\s+([\w.\[\]*]+)")


def _go_entities(content: str) -> list[tuple[dict, int]]:
    # Gate on a GORM marker so ordinary structs are not treated as entities.
    if not _hint(content, "gorm.Model", "gorm:\"", "gorm.io/gorm"):
        return []
    out: list[tuple[dict, int]] = []
    for m in _GO_STRUCT.finditer(content):
        name = m.group(1)
        body = _brace_body(content, m.end() - 1)
        if "gorm:" not in body and "gorm.Model" not in body:
            continue
        fields: list[dict] = []
        seen: set[str] = set()
        for ln in body.split("\n"):
            fm = _GO_FIELD.match(ln)
            if fm and fm.group(1)[:1].isupper() and fm.group(1) not in seen:
                seen.add(fm.group(1))
                fields.append({"name": fm.group(1), "type": fm.group(2)})
        out.append((
            {"name": name, "kind": "model", "framework": "gorm", "fields": fields},
            m.start(),
        ))
    return _dedupe(out)


# ---------------------------------------------------------------------------
# Standalone schema files: Prisma, SQL DDL, JSON Schema
# ---------------------------------------------------------------------------

_PRISMA_MODEL = re.compile(r"(?m)^\s*model\s+(\w+)\s*\{")
_PRISMA_FIELD = re.compile(r"^\s*(\w+)\s+([\w\[\]?]+)")

_SQL_CREATE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`\"']?(\w+)[`\"']?\s*\(",
    re.IGNORECASE,
)
_SQL_COLUMN = re.compile(r"^\s*[`\"']?(\w+)[`\"']?\s+([A-Za-z]+)")
_SQL_RESERVED = {
    "primary", "foreign", "unique", "constraint", "key", "index", "check",
}


def _prisma_entities(content: str) -> list[tuple[dict, int]]:
    out: list[tuple[dict, int]] = []
    for m in _PRISMA_MODEL.finditer(content):
        name = m.group(1)
        body = _brace_body(content, m.end() - 1)
        fields: list[dict] = []
        seen: set[str] = set()
        for ln in body.split("\n"):
            ln_stripped = ln.strip()
            if not ln_stripped or ln_stripped.startswith("@@") or ln_stripped.startswith("//"):
                continue
            fm = _PRISMA_FIELD.match(ln)
            if fm and fm.group(1) not in seen:
                seen.add(fm.group(1))
                fields.append({"name": fm.group(1), "type": fm.group(2)})
        out.append((
            {"name": name, "kind": "model", "framework": "prisma", "fields": fields},
            m.start(),
        ))
    return _dedupe(out)


def _sql_entities(content: str) -> list[tuple[dict, int]]:
    out: list[tuple[dict, int]] = []
    for m in _SQL_CREATE.finditer(content):
        table = m.group(1)
        body = _paren_body(content, m.end() - 1)
        fields: list[dict] = []
        seen: set[str] = set()
        for raw in _split_top_level(body):
            cm = _SQL_COLUMN.match(raw)
            if not cm:
                continue
            fname = cm.group(1)
            if fname.lower() in _SQL_RESERVED or fname in seen:
                continue
            seen.add(fname)
            fields.append({"name": fname, "type": cm.group(2).upper()})
        out.append((
            {"name": table, "kind": "table", "framework": "sql",
             "table": table, "fields": fields},
            m.start(),
        ))
    return _dedupe(out)


def _paren_body(content: str, from_idx: int) -> str:
    open_idx = content.find("(", from_idx)
    if open_idx < 0:
        return ""
    depth = 0
    for i in range(open_idx, len(content)):
        c = content[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return content[open_idx + 1:i]
    return content[open_idx + 1:]


def _split_top_level(body: str) -> list[str]:
    """Split a SQL column list on top-level commas (not inside parens)."""
    out: list[str] = []
    depth = 0
    cur: list[str] = []
    for c in body:
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        if c == "," and depth == 0:
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(c)
    if "".join(cur).strip():
        out.append("".join(cur).strip())
    return out


def _json_schema_entities(content: str, path: str) -> list[tuple[dict, int]]:
    """A JSON file is a data schema only when clearly data-shaped.

    Requires a top-level object with ``type == "object"`` and a non-empty
    ``properties`` map, which excludes ordinary config JSON (package.json,
    tsconfig.json have no top-level ``properties``).
    """
    try:
        data = json.loads(content)
    except (ValueError, TypeError):
        return []
    if not isinstance(data, dict):
        return []
    props = data.get("properties")
    if data.get("type") != "object" or not isinstance(props, dict) or not props:
        return []
    name = data.get("title") or _name_from_path(path)
    fields: list[dict] = []
    for fname in sorted(props):
        spec = props[fname]
        ftype = spec.get("type") if isinstance(spec, dict) else None
        fields.append({"name": fname, "type": ftype})
    return [({"name": name, "kind": "schema", "framework": "json-schema",
             "fields": fields}, 0)]


def _coredata_entities(content: str) -> list[tuple[dict, int]]:
    """Entities from a Core Data model's ``contents`` XML (P4-9, Data lens).

    A ``.xcdatamodeld`` bundle stores its model as an extension-less ``contents``
    XML file. Each ``<entity>`` becomes a data entity with framework
    ``coredata``. Attributes map to ``{name, type}`` fields; relationships map to
    fields too, typed by their destination entity (bracketed ``[Dest]`` for a
    to-many relationship), so the Data lens shows the object graph in the same
    field list it uses for every other source, with no schema change.

    ElementTree does not resolve external entities, so parsing untrusted model
    files is XXE-safe. A malformed document raises ``ElementTree.ParseError``,
    which the worker turns into a ``failed`` disposition (never a crash).
    """
    root = ET.fromstring(content)
    out: list[tuple[dict, int]] = []
    for entity in root.iter():
        if entity.tag != "entity":
            continue
        ename = entity.get("name")
        if not ename:
            continue
        fields: list[dict] = []
        seen: set[str] = set()
        for child in entity:
            fname = child.get("name")
            if not fname or fname in seen:
                continue
            if child.tag == "attribute":
                seen.add(fname)
                fields.append({"name": fname, "type": child.get("attributeType")})
            elif child.tag == "relationship":
                seen.add(fname)
                dest = child.get("destinationEntity")
                to_many = child.get("toMany") == "YES"
                ftype = f"[{dest}]" if (dest and to_many) else dest
                fields.append({"name": fname, "type": ftype})
        # Anchor on the entity ELEMENT, not any name="..." occurrence: attributes,
        # relationships, and layout elements all carry name= too, so a bare name
        # search can report an entity at an unrelated line (review finding).
        start = content.find(f'<entity name="{ename}"')
        out.append((
            {"name": ename, "kind": "model", "framework": "coredata",
             "fields": fields},
            start if start >= 0 else 0,
        ))
    return _dedupe(out)


def _name_from_path(path: str) -> str:
    base = path.replace("\\", "/").rsplit("/", 1)[-1]
    for suffix in (".schema.json", ".json"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    return base or "schema"


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

_CODE_EXTRACTORS = {
    "python": _python_entities,
    "ruby": _ruby_entities,
    "swift": _swift_entities,
    "typescript": _ts_entities,
    "javascript": _ts_entities,
    "go": _go_entities,
}


def extract_entities(content: str, language: str) -> list[tuple[dict, int]]:
    """ORM/model entity tuples for a parser-backed code file."""
    fn = _CODE_EXTRACTORS.get(language)
    return fn(content) if fn else []


def extract_schema_entities(
    content: str, language: str, path: str
) -> list[tuple[dict, int]]:
    """Entity tuples for a standalone schema file (Prisma, SQL DDL, JSON Schema)."""
    if language == "prisma":
        return _prisma_entities(content)
    if language == "sql":
        return _sql_entities(content)
    if language == "json":
        return _json_schema_entities(content, path)
    if language == "coredata":
        return _coredata_entities(content)
    return []
