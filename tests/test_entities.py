"""P5-2 data-entity extraction, access edges, and the exclusion inversion.

Three layers, mirroring test_capabilities.py:
  1. Direct unit tests over analyzer/extract/entities (the per-ORM / per-schema
     extractor matrix).
  2. End-to-end tests that run the real extract + derive tiers over the
     dedicated tests/fixtures/entities repo and assert data_entities and
     entity_access land in the store and the arch dict with fields, evidence,
     mode, and confidence.
  3. The content-exclusion inversion: a models/ directory participates in
     derivation on the v2 path (fail-before via the shared CONTENT_DIR_NAMES).

Entity extraction is pure regex (parser-independent), so these tests do not need
the tree-sitter tier.
"""

from __future__ import annotations

import json
import os
import tempfile

from analyzer.constants import CONTENT_DIR_NAMES
from analyzer.derive import derive_all, roles
from analyzer.extract.entities import extract_entities, extract_schema_entities
from analyzer.extract.runner import extract_repo
from analyzer.project.monolith import write_monolith
from analyzer.store import FactStore

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
ENTITIES_FIXTURE = os.path.join(FIXTURES, "entities")


def _derive(root, name="entities"):
    store = FactStore(":memory:")
    extract_repo(root, store)
    d, arch = derive_all(store, name)
    return store, d, arch


def _find(entities, name, framework=None, kind=None):
    for e in entities:
        if e["name"] == name and (framework is None or e["framework"] == framework) \
                and (kind is None or e["kind"] == kind):
            return e
    return None


# ---------------------------------------------------------------------------
# 1. Per-ORM / per-schema extractor matrix (a case per source, card scope)
# ---------------------------------------------------------------------------

def _names(pairs):
    return {v["name"] for v, _ in pairs}


def _fields(pairs, name):
    for v, _ in pairs:
        if v["name"] == name:
            return {f["name"] for f in v["fields"]}
    return set()


def test_sqlalchemy_declarative_model():
    src = (
        "from sqlalchemy import Column, Integer, String\n"
        "from sqlalchemy.orm import declarative_base\n"
        "Base = declarative_base()\n"
        "class User(Base):\n"
        "    __tablename__ = 'users'\n"
        "    id = Column(Integer, primary_key=True)\n"
        "    email = Column(String)\n"
    )
    ents = extract_entities(src, "python")
    u = next(v for v, _ in ents if v["name"] == "User")
    assert u["kind"] == "model" and u["framework"] == "sqlalchemy"
    assert u["table"] == "users"
    assert {f["name"] for f in u["fields"]} == {"id", "email"}


def test_sqlalchemy_mapped_column_typing():
    src = (
        "from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column\n"
        "class Base(DeclarativeBase): pass\n"
        "class Post(Base):\n"
        "    __tablename__ = 'posts'\n"
        "    id: Mapped[int] = mapped_column(primary_key=True)\n"
        "    title: Mapped[str]\n"
    )
    ents = extract_entities(src, "python")
    p = next(v for v, _ in ents if v["name"] == "Post")
    assert {f["name"] for f in p["fields"]} == {"id", "title"}


def test_django_model_fields():
    src = (
        "from django.db import models\n"
        "class Article(models.Model):\n"
        "    title = models.CharField(max_length=200)\n"
        "    body = models.TextField()\n"
    )
    ents = extract_entities(src, "python")
    a = next(v for v, _ in ents if v["name"] == "Article")
    assert a["framework"] == "django" and a["kind"] == "model"
    assert {f["name"] for f in a["fields"]} == {"title", "body"}


def test_django_migration_create_model():
    src = (
        "from django.db import migrations, models\n"
        "class Migration(migrations.Migration):\n"
        "    operations = [migrations.CreateModel(name='Order', fields=[\n"
        "        ('id', models.AutoField()), ('total', models.DecimalField())])]\n"
    )
    ents = extract_entities(src, "python")
    o = next(v for v, _ in ents if v["name"] == "Order" and v["kind"] == "migration")
    assert o["framework"] == "django"
    assert {f["name"] for f in o["fields"]} == {"id", "total"}


def test_alembic_migration_create_table():
    src = (
        "import sqlalchemy as sa\n"
        "from alembic import op\n"
        "def upgrade():\n"
        "    op.create_table('payments', sa.Column('id', sa.Integer),"
        " sa.Column('amount', sa.Numeric))\n"
    )
    ents = extract_entities(src, "python")
    p = next(v for v, _ in ents if v["name"] == "payments")
    assert p["framework"] == "alembic" and p["kind"] == "migration"
    assert p["table"] == "payments"
    assert {f["name"] for f in p["fields"]} == {"id", "amount"}


def test_activerecord_model_and_schema_rb():
    model = "class Comment < ApplicationRecord\n  belongs_to :article\nend\n"
    m = next(v for v, _ in extract_entities(model, "ruby") if v["name"] == "Comment")
    assert m["framework"] == "activerecord" and m["kind"] == "model"

    schema = (
        "ActiveRecord::Schema.define(version: 1) do\n"
        "  create_table \"comments\", force: :cascade do |t|\n"
        "    t.string \"body\"\n"
        "    t.integer \"article_id\"\n"
        "  end\nend\n"
    )
    t = next(v for v, _ in extract_entities(schema, "ruby") if v["name"] == "comments")
    assert t["kind"] == "table" and t["table"] == "comments"
    assert {f["name"] for f in t["fields"]} == {"body", "article_id"}


def test_rails_migration_create_table():
    src = (
        "class CreateOrders < ActiveRecord::Migration[7.0]\n"
        "  def change\n"
        "    create_table :orders do |t|\n"
        "      t.string :status\n"
        "      t.decimal :total\n"
        "    end\n  end\nend\n"
    )
    o = next(v for v, _ in extract_entities(src, "ruby")
             if v["name"] == "orders" and v["kind"] == "migration")
    assert o["framework"] == "rails"
    assert {f["name"] for f in o["fields"]} == {"status", "total"}


def test_swiftdata_model_partial_inferred():
    src = (
        "import SwiftData\n@Model\nfinal class Item {\n"
        "    var title: String\n    var quantity: Int\n"
        "    init(title: String) { self.title = title }\n}\n"
    )
    i = next(v for v, _ in extract_entities(src, "swift") if v["name"] == "Item")
    assert i["framework"] == "swiftdata" and i["inferred"] is True
    assert {f["name"] for f in i["fields"]} == {"title", "quantity"}


def test_coredata_managed_object():
    src = (
        "import CoreData\nclass Note: NSManagedObject {\n"
        "    @NSManaged var text: String\n    @NSManaged var pinned: Bool\n}\n"
    )
    n = next(v for v, _ in extract_entities(src, "swift") if v["name"] == "Note")
    assert n["framework"] == "coredata" and n["inferred"] is True
    assert {f["name"] for f in n["fields"]} == {"text", "pinned"}


def test_typeorm_entity():
    src = (
        "import { Entity, Column, PrimaryGeneratedColumn } from 'typeorm';\n"
        "@Entity()\nexport class Account {\n"
        "  @PrimaryGeneratedColumn() id: number;\n"
        "  @Column() username: string;\n}\n"
    )
    a = next(v for v, _ in extract_entities(src, "typescript") if v["name"] == "Account")
    assert a["framework"] == "typeorm"
    assert {f["name"] for f in a["fields"]} == {"id", "username"}


def test_gorm_struct():
    src = (
        "package main\nimport \"gorm.io/gorm\"\n"
        "type Order struct {\n\tgorm.Model\n\tStatus string `gorm:\"index\"`\n"
        "\tTotal float64\n}\n"
    )
    o = next(v for v, _ in extract_entities(src, "go") if v["name"] == "Order")
    assert o["framework"] == "gorm"
    assert {"Status", "Total"} <= {f["name"] for f in o["fields"]}


def test_gorm_requires_marker():
    # A plain struct with no gorm marker is not an entity.
    src = "package main\ntype Point struct {\n\tX int\n\tY int\n}\n"
    assert extract_entities(src, "go") == []


def test_prisma_schema():
    src = (
        "model Product {\n  id Int @id\n  name String\n  price Float\n}\n"
        "model Category {\n  id Int @id\n  name String\n}\n"
    )
    ents = extract_schema_entities(src, "prisma", "schema.prisma")
    assert _names(ents) == {"Product", "Category"}
    assert _fields(ents, "Product") == {"id", "name", "price"}


def test_sql_ddl_create_table():
    src = (
        "CREATE TABLE invoices (\n  id INTEGER PRIMARY KEY,\n"
        "  number TEXT NOT NULL,\n  amount NUMERIC\n);\n"
    )
    ents = extract_schema_entities(src, "sql", "tables.sql")
    inv = next(v for v, _ in ents if v["name"] == "invoices")
    assert inv["kind"] == "table" and inv["table"] == "invoices"
    # PRIMARY / FOREIGN / constraint tokens are not columns.
    assert {f["name"] for f in inv["fields"]} == {"id", "number", "amount"}


def test_json_schema_data_shaped_only():
    schema = json.dumps({
        "title": "Event", "type": "object",
        "properties": {"id": {"type": "string"}, "ts": {"type": "integer"}},
    })
    ents = extract_schema_entities(schema, "json", "event.schema.json")
    e = next(v for v, _ in ents if v["name"] == "Event")
    assert e["kind"] == "schema" and {f["name"] for f in e["fields"]} == {"id", "ts"}

    # An ordinary config JSON (no top-level properties map) is NOT a schema.
    config = json.dumps({"name": "pkg", "version": "1.0.0", "dependencies": {}})
    assert extract_schema_entities(config, "json", "package.json") == []


# ---------------------------------------------------------------------------
# 2. End-to-end: entities land in the store and the arch dict
# ---------------------------------------------------------------------------

def test_all_orms_extracted_on_the_fixture():
    _, _, arch = _derive(ENTITIES_FIXTURE)
    ents = arch["data_entities"]
    frameworks = {e["framework"] for e in ents}
    assert {
        "sqlalchemy", "django", "alembic", "activerecord", "rails",
        "swiftdata", "typeorm", "gorm", "prisma", "sql", "json-schema",
    } <= frameworks
    # A representative model carries its fields and table.
    user = _find(ents, "User", "sqlalchemy")
    assert user and user["table"] == "users"
    assert {f["name"] for f in user["fields"]} == {"id", "email", "name"}


def test_entities_land_in_store_with_fields_and_evidence():
    store, _, arch = _derive(ENTITIES_FIXTURE)
    rows = store.data_entities()
    assert len(rows) == len(arch["data_entities"]) > 0
    user = next(r for r in rows if r["name"] == "User")
    # fields_json is the entity detail payload (fields + framework + table).
    assert user["fields"]["framework"] == "sqlalchemy"
    assert user["fields"]["table"] == "users"
    assert {f["name"] for f in user["fields"]["fields"]} == {"id", "email", "name"}
    assert user["evidence"] and user["evidence"][0]["file"].endswith(".py")


def test_defining_symbol_linked_where_resolvable():
    _, _, arch = _derive(ENTITIES_FIXTURE)
    user = _find(arch["data_entities"], "User", "sqlalchemy")
    assert user.get("symbol"), "expected a defining-symbol link for a class model"


# ---------------------------------------------------------------------------
# 3. entity_access edges (mode + confidence + evidence)
# ---------------------------------------------------------------------------

def test_access_certain_read_and_write_from_orm_usage():
    store, _, arch = _derive(ENTITIES_FIXTURE)
    user = _find(arch["data_entities"], "User", "sqlalchemy")
    edges = [a for a in arch["entity_access"] if a["entity_id"] == user["id"]]
    modes = {a["mode"]: a for a in edges}
    assert "read" in modes and "write" in modes
    for a in edges:
        assert a["confidence"] == "certain"  # class-name ORM usage
        assert a["evidence"] and all("file" in e and "line" in e for e in a["evidence"])
    # store round-trips the same edges.
    assert len(store.entity_access()) == len(arch["entity_access"])


def test_access_inferred_from_table_string_reference():
    _, _, arch = _derive(ENTITIES_FIXTURE)
    invoices = _find(arch["data_entities"], "invoices", "sql")
    edges = [a for a in arch["entity_access"] if a["entity_id"] == invoices["id"]]
    assert edges, "expected an inferred access edge from the raw-SQL reference"
    assert all(a["confidence"] == "inferred" for a in edges)
    assert any(a["mode"] == "read" for a in edges)


def test_declaration_files_are_not_self_access():
    # An entity's own defining file must not appear as an accessor of it.
    _, _, arch = _derive(ENTITIES_FIXTURE)
    by_id = {e["id"]: e for e in arch["data_entities"]}
    for a in arch["entity_access"]:
        ent = by_id[a["entity_id"]]
        decl_files = {ev["file"] for ev in ent["evidence"]}
        access_files = {ev["file"] for ev in a["evidence"]}
        # access evidence never comes from the entity's own declaration file.
        assert not (access_files & decl_files), (a, decl_files)


# ---------------------------------------------------------------------------
# 4. Content-exclusion inversion (models/ participates on the v2 path)
# ---------------------------------------------------------------------------

def _content_dir_component():
    """A models/ directory dominated by schema files (low code ratio).

    This is the case the inversion targets: an ORM/schema `models/` directory
    whose files are data-shaped schemas, not code. schema.prisma is not a
    LANGUAGE_MAP code extension and .json/.yaml are content extensions, so the
    directory has 0 code files (the pre-fix content-only trigger).
    """
    from analyzer.models import Component
    comp = Component(id="models", name="models", type="module", path="models")
    comp.files = ["models/schema.prisma", "models/event.schema.json", "models/data.yaml"]
    return comp


def test_is_content_only_inversion_load_bearing(monkeypatch):
    """The inversion decides the classification. Direct, deterministic proof at
    the decision point, independent of component-discovery thresholds."""
    comp = _content_dir_component()
    # v2 (fixed): models/ is architectural.
    assert roles._is_content_only(None, comp, "models") is False
    assert "models" not in roles._V2_CONTENT_DIR_NAMES

    # Fail-before: restore the shared v1 CONTENT_DIR_NAMES and the same models/
    # directory is wrongly classified content-only.
    assert "models" in CONTENT_DIR_NAMES
    monkeypatch.setattr(roles, "_V2_CONTENT_DIR_NAMES", CONTENT_DIR_NAMES)
    assert roles._is_content_only(None, comp, "models") is True


def test_migrations_and_schemas_dirs_also_inverted():
    # All three data-lens directory names are architectural on the v2 path.
    for name in ("models", "migrations", "schemas"):
        assert name not in roles._V2_CONTENT_DIR_NAMES


def test_models_dir_schema_entities_participate():
    # The schema files under the fixture's models/ directory are parsed and
    # their entities are surfaced (not excluded from derivation).
    store, _, arch = _derive(ENTITIES_FIXTURE)
    disp = {c["path"]: c["disposition"] for c in store.coverage()}
    assert disp.get("models/schema.prisma") == "parsed"
    assert disp.get("models/event.schema.json") == "parsed"
    names = {e["name"] for e in arch["data_entities"]}
    assert {"Product", "Category", "Event"} <= names


def test_prisma_sql_json_files_are_parsed_not_excluded():
    store, _, _ = _derive(ENTITIES_FIXTURE)
    disp = {c["path"]: c["disposition"] for c in store.coverage()}
    assert disp.get("models/schema.prisma") == "parsed"      # v2 schema-ext add
    assert disp.get("sql/tables.sql") == "parsed"
    assert disp.get("models/event.schema.json") == "parsed"


def test_config_json_is_not_a_data_entity():
    _, _, arch = _derive(ENTITIES_FIXTURE)
    names = {e["name"] for e in arch["data_entities"]}
    assert "not-a-schema" not in names  # package_like.json must not be an entity


# ---------------------------------------------------------------------------
# 5. Projection backward compatibility (additive optional keys)
# ---------------------------------------------------------------------------

def test_entities_are_additive_optional_keys(tmp_path):
    # A repo with no ORM code emits empty entity indexes and NO per-component key.
    (tmp_path / "main.py").write_text("def hello():\n    return 1\n")
    _, _, arch = _derive(str(tmp_path), "plain")
    assert arch["data_entities"] == []
    assert arch["entity_access"] == []

    def no_key(cs):
        for c in cs:
            assert "data_entities" not in c
            no_key(c.get("children", []))
    no_key(arch["components"])


def test_projection_carries_entities_and_old_viewer_ignores():
    store, _, arch = _derive(ENTITIES_FIXTURE)
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "architecture.json")
        write_monolith(arch, out)
        with open(out) as f:
            data = json.load(f)
    # additive keys present; pre-existing keys still readable.
    assert isinstance(data["data_entities"], list) and data["data_entities"]
    assert isinstance(data["entity_access"], list)
    assert "components" in data and "relationships" in data and "stats" in data


# ---------------------------------------------------------------------------
# 6. Determinism (invariant I4)
# ---------------------------------------------------------------------------

def test_entity_emission_is_deterministic():
    _, _, a1 = _derive(ENTITIES_FIXTURE)
    _, _, a2 = _derive(ENTITIES_FIXTURE)
    assert json.dumps(a1["data_entities"], sort_keys=True) == \
           json.dumps(a2["data_entities"], sort_keys=True)
    assert json.dumps(a1["entity_access"], sort_keys=True) == \
           json.dumps(a2["entity_access"], sort_keys=True)
