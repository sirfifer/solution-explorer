"""P5-5 rule extraction: the deterministic half of the Rules lens (L6).

Four layers, mirroring test_capabilities.py / test_entities.py:
  1. Direct unit tests over analyzer/extract/rules.extract_rules (the per-kind,
     per-language detector matrix: validation, calculation, policy, io across
     Python, TypeScript, and Ruby, plus SQL io).
  2. The NOISE proof: ordinary control flow (loop guards, internal null checks,
     bare error-handling re-raises, index/counter math, single if/else) yields
     ZERO rules. This is the precision-over-recall guarantee the card requires.
  3. End-to-end over the dedicated tests/fixtures/rules repo: rules land in the
     store and the arch dict with kind, mechanical summary, evidence, confidence,
     enclosing symbol / trigger, and io->entity links; projections carry them as
     optional keys; determinism.
  4. The schema migration (v2 -> v3 additive) that gives the rules table a home.

Rule detection is pure regex (parser-independent), so most tests need no
tree-sitter tier.
"""

from __future__ import annotations

import json
import os

from analyzer.derive import derive_all
from analyzer.extract.rules import extract_rules
from analyzer.extract.runner import extract_repo
from analyzer.project.monolith import write_monolith
from analyzer.store import FactStore
from analyzer.store.schema import SCHEMA_VERSION

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
RULES_FIXTURE = os.path.join(FIXTURES, "rules")


def _kinds(pairs):
    return [v["kind"] for v, _ in pairs]


def _by_kind(pairs, kind):
    return [v for v, _ in pairs if v["kind"] == kind]


def _derive(root=RULES_FIXTURE, name="rules"):
    store = FactStore(":memory:")
    extract_repo(root, store)
    d, arch = derive_all(store, name)
    return store, d, arch


# ===========================================================================
# 1. Per-kind, per-language detector matrix
# ===========================================================================

# -- validation -------------------------------------------------------------

def test_python_pydantic_validator_is_certain_validation():
    src = (
        "class Form(BaseModel):\n"
        "    @field_validator('email', 'name')\n"
        "    def check(cls, v):\n"
        "        return v\n"
    )
    v = _by_kind(extract_rules(src, "python", "f.py"), "validation")
    assert any(r["anchor"] == "pydantic_validator" and r["confidence"] == "certain"
               and set(r["inputs"]) == {"email", "name"} for r in v)


def test_python_guard_clause_is_inferred_validation():
    src = (
        "def create(email):\n"
        "    if not email:\n"
        "        raise ValueError('email required')\n"
        "    return email\n"
    )
    v = _by_kind(extract_rules(src, "python", "f.py"), "validation")
    guard = next(r for r in v if r["anchor"] == "guard_clause")
    assert guard["confidence"] == "inferred"
    assert "raise ValueError" in guard["summary"] and "not email" in guard["summary"]
    assert "email" in guard["inputs"]


def test_python_django_clean_method_is_validation():
    src = "class F(forms.Form):\n    def clean_email(self):\n        return self.cleaned_data\n"
    v = _by_kind(extract_rules(src, "python", "f.py"), "validation")
    assert any(r["anchor"] == "django_clean" and r.get("field") == "email" for r in v)


def test_typescript_zod_chain_is_certain_validation():
    src = "const S = { email: z.string().email(), age: z.number().min(0).max(9) };\n"
    v = _by_kind(extract_rules(src, "typescript", "s.ts"), "validation")
    email = next(r for r in v if r.get("field") == "email")
    assert email["anchor"] == "zod" and email["confidence"] == "certain"
    assert "email" in email["outputs"]


def test_typescript_guard_throw_is_inferred_validation():
    src = "function f(x){ if (x < 0) throw new ValidationError('bad'); return x; }\n"
    v = _by_kind(extract_rules(src, "typescript", "f.ts"), "validation")
    guard = next(r for r in v if r["anchor"] == "guard_clause")
    assert guard["confidence"] == "inferred" and "ValidationError" in guard["outputs"]


def test_ruby_validates_is_certain_validation():
    src = "class U < ApplicationRecord\n  validates :email, presence: true\nend\n"
    v = _by_kind(extract_rules(src, "ruby", "u.rb"), "validation")
    assert any(r["anchor"] == "rails_validates" and "email" in r["inputs"] for r in v)


def test_ruby_guard_raise_modifier_is_validation():
    src = "def f(x)\n  raise ArgumentError, 'bad' unless x > 0\nend\n"
    v = _by_kind(extract_rules(src, "ruby", "f.rb"), "validation")
    assert any(r["anchor"] == "guard_clause" and "ArgumentError" in r["outputs"] for r in v)


# -- calculation ------------------------------------------------------------

def test_python_calculation_needs_a_domain_anchor():
    src = (
        "def f(subtotal, rate):\n"
        "    tax = subtotal * rate\n"
        "    total = subtotal + tax\n"
        "    return total\n"
    )
    calc = _by_kind(extract_rules(src, "python", "f.py"), "calculation")
    summaries = {r["summary"] for r in calc}
    assert "tax = subtotal * rate" in summaries
    assert "total = subtotal + tax" in summaries
    tax = next(r for r in calc if r["summary"].startswith("tax ="))
    assert set(tax["inputs"]) == {"subtotal", "rate"} and tax["outputs"] == ["tax"]


def test_calculation_rejects_index_and_counter_math():
    # No domain anchor -> not a calculation (precision).
    src = "def f(items):\n    i = i + 1\n    count = count + 1\n    x = y * 2\n"
    assert _by_kind(extract_rules(src, "python", "f.py"), "calculation") == []


def test_typescript_and_ruby_calculation():
    ts = "function f(price, qty){\n  const amount = price * qty;\n  return amount;\n}\n"
    assert _by_kind(extract_rules(ts, "typescript", "f.ts"), "calculation")
    rb = "def f(subtotal, rate)\n  fee = subtotal * rate\n  fee\nend\n"
    assert _by_kind(extract_rules(rb, "ruby", "f.rb"), "calculation")


# -- policy -----------------------------------------------------------------

def test_python_match_is_policy_decision_table():
    src = (
        "def f(status):\n"
        "    match status:\n"
        "        case 'a':\n"
        "            return 1\n"
        "        case 'b':\n"
        "            return 2\n"
    )
    p = _by_kind(extract_rules(src, "python", "f.py"), "policy")
    m = next(r for r in p if r["anchor"] == "match")
    assert m["inputs"] == ["status"] and m["outputs"] == ["'a'", "'b'"]


def test_python_permission_gate_is_certain_policy():
    src = "def can_edit(user):\n    return user.admin\n"
    p = _by_kind(extract_rules(src, "python", "f.py"), "policy")
    assert any(r["anchor"] == "permission_check" and r["confidence"] == "certain" for r in p)


def test_typescript_switch_is_policy():
    src = (
        "function f(z){ switch (z) {\n  case 'x': return 1;\n"
        "  case 'y': return 2;\n  default: return 0;\n} }\n"
    )
    p = _by_kind(extract_rules(src, "typescript", "f.ts"), "policy")
    assert any(r["anchor"] == "switch" and r["inputs"] == ["z"] for r in p)


def test_ruby_before_action_and_case_when_are_policy():
    src = (
        "class C\n  before_action :authorize_owner\n"
        "  def label(s)\n    case s\n    when 'a'\n      1\n    when 'b'\n      2\n    end\n  end\nend\n"
    )
    p = _by_kind(extract_rules(src, "ruby", "c.rb"), "policy")
    anchors = {r["anchor"] for r in p}
    assert "permission_check" in anchors and "case_when" in anchors


def test_single_if_else_is_not_policy():
    # A one-branch if/else is not a decision table (threshold: >= 2 elif/case).
    src = "def f(x):\n    if x:\n        return 1\n    else:\n        return 2\n"
    assert _by_kind(extract_rules(src, "python", "f.py"), "policy") == []


def test_if_elif_chain_is_policy():
    src = (
        "def f(x):\n    if x == 1:\n        return 'a'\n"
        "    elif x == 2:\n        return 'b'\n"
        "    elif x == 3:\n        return 'c'\n"
    )
    p = _by_kind(extract_rules(src, "python", "f.py"), "policy")
    assert any(r["anchor"] == "if_elif_chain" for r in p)


# -- io ---------------------------------------------------------------------

def test_python_django_field_constraint_is_certain_io():
    src = "class M(models.Model):\n    name = models.CharField(max_length=200, null=False)\n"
    io = _by_kind(extract_rules(src, "python", "m.py"), "io")
    r = next(x for x in io if x["field"] == "name")
    assert r["confidence"] == "certain" and r["framework"] == "django"
    assert any("max_length=200" in o for o in r["outputs"])


def test_typescript_class_validator_is_io():
    src = "class Dto {\n  @MaxLength(120)\n  title!: string;\n}\n"
    io = _by_kind(extract_rules(src, "typescript", "d.ts"), "io")
    assert any(r["field"] == "title" and r["framework"] == "class-validator" for r in io)


def test_sql_ddl_constraints_are_io():
    src = "CREATE TABLE t (\n  email VARCHAR(255) NOT NULL,\n  bal NUMERIC CHECK (bal >= 0)\n);\n"
    io = _by_kind(extract_rules(src, "sql", "t.sql"), "io")
    fields = {r["field"] for r in io}
    assert {"email", "bal"} <= fields


def test_ruby_rails_schema_column_is_io():
    src = 'create_table "orders" do |t|\n  t.string "email", limit: 255, null: false\nend\n'
    io = _by_kind(extract_rules(src, "ruby", "schema.rb"), "io")
    assert any(r["field"] == "email" and r["framework"] == "rails" for r in io)


# ===========================================================================
# 2. NOISE proof: ordinary control flow yields ZERO rules (precision)
# ===========================================================================

_NOISE_PY = (
    "def process(items):\n"
    "    result = []\n"
    "    for i in range(len(items)):\n"
    "        if i >= len(items):\n"
    "            break\n"
    "        obj = items[i]\n"
    "        if obj is None:\n"
    "            continue\n"
    "        if obj.done:\n"
    "            return None\n"
    "    count = 0\n"
    "    count += 1\n"
    "    idx = idx + 1\n"
    "    n = len(items)\n"
    "    try:\n"
    "        do_work()\n"
    "    except KeyError:\n"
    "        raise\n"
    "    except Exception as e:\n"
    "        raise RuntimeError('internal') from e\n"
    "    if items:\n"
    "        return items\n"
    "    else:\n"
    "        return []\n"
    "    name = data['name']\n"
    "    x = y * 2\n"
)

_NOISE_TS = (
    "function loop(arr) {\n"
    "  for (let i = 0; i < arr.length; i++) {\n"
    "    if (arr[i] == null) continue;\n"
    "    if (i >= arr.length) break;\n"
    "  }\n"
    "  let count = 0;\n"
    "  count = count + 1;\n"
    "  const n = arr.length;\n"
    "  if (arr.length) { return arr; } else { return []; }\n"
    "  try { work(); } catch (e) { throw e; }\n"
    "}\n"
)

_NOISE_RB = (
    "def loop(arr)\n"
    "  arr.each do |x|\n"
    "    next if x.nil?\n"
    "    return nil if x.done\n"
    "  end\n"
    "  count = 0\n"
    "  count += 1\n"
    "  begin\n"
    "    work\n"
    "  rescue => e\n"
    "    raise\n"
    "  end\n"
    "end\n"
)


def test_noise_python_yields_zero_rules():
    assert extract_rules(_NOISE_PY, "python", "n.py") == []


def test_noise_typescript_yields_zero_rules():
    assert extract_rules(_NOISE_TS, "typescript", "n.ts") == []


def test_noise_ruby_yields_zero_rules():
    assert extract_rules(_NOISE_RB, "ruby", "n.rb") == []


def test_internal_error_raise_is_not_validation():
    # Raising a non-validation error on an internal check is error handling,
    # not a rule (the raise allowlist is the load-bearing filter).
    src = (
        "def f(resp):\n"
        "    if not resp.ok:\n"
        "        raise RuntimeError('upstream failed')\n"
    )
    assert extract_rules(src, "python", "f.py") == []


# ===========================================================================
# 3. End-to-end over the dedicated fixture
# ===========================================================================

def test_all_four_kinds_present_across_languages_on_fixture():
    _, _, arch = _derive()
    rules = arch["rules"]
    kinds = {r["kind"] for r in rules}
    assert kinds == {"validation", "calculation", "policy", "io"}
    # every required language contributes at least one rule.
    exts = {r["evidence"][0]["file"].rsplit(".", 1)[-1] for r in rules}
    assert {"py", "ts", "rb", "sql"} <= exts


def test_rules_land_in_store_with_detail_and_evidence():
    store, _, arch = _derive()
    rows = store.rules()
    assert len(rows) == len(arch["rules"]) > 0
    # detail_json carries the anchor and (where present) inputs/outputs.
    r = next(x for x in rows if x["kind"] == "calculation")
    assert r["detail"]["anchor"] == "formula" and r["detail"].get("inputs")
    assert r["evidence"] and "file" in r["evidence"][0] and "line" in r["evidence"][0]
    assert r["summary"]  # mechanical summary present


def test_summary_is_mechanical_not_prose():
    # A mechanical summary echoes the code, not an English sentence about intent.
    _, _, arch = _derive()
    calc = next(r for r in arch["rules"] if r["kind"] == "calculation"
                and r["summary"].startswith("tax ="))
    assert "=" in calc["summary"] and " the " not in calc["summary"].lower()


def test_confidence_tiers():
    _, _, arch = _derive()
    rules = arch["rules"]
    # declared validators / schema fields are certain; guards/formulae inferred.
    certain = {r["detail"]["anchor"] for r in rules if r["confidence"] == "certain"}
    inferred = {r["detail"]["anchor"] for r in rules if r["confidence"] == "inferred"}
    assert {"pydantic_validator", "rails_validates", "zod"} & certain
    assert {"guard_clause", "formula"} <= inferred


def test_rules_carry_enclosing_symbol_and_trigger():
    _, _, arch = _derive()
    rules = arch["rules"]
    # a guard clause inside a method resolves its enclosing symbol.
    guard = next(r for r in rules if r["detail"]["anchor"] == "guard_clause")
    assert guard["detail"].get("symbol")
    trigger = guard["detail"].get("trigger")
    assert trigger and (trigger.get("symbol") or trigger.get("capability"))


def test_rule_inside_api_handler_links_to_the_capability():
    # A guard clause inside a route handler resolves its trigger context to the
    # capability that handler defines (P5-5 trigger-context linkage).
    _, _, arch = _derive()
    cap_ids = {c["id"] for c in arch["capabilities"]}
    linked = [r for r in arch["rules"]
              if r["detail"].get("trigger", {}).get("capability")]
    assert linked, "expected a rule whose enclosing symbol defines a capability"
    for r in linked:
        assert r["detail"]["trigger"]["capability"] in cap_ids


def test_io_rules_link_to_data_entities():
    _, _, arch = _derive()
    io = [r for r in arch["rules"] if r["kind"] == "io"]
    linked = [r for r in io if r["detail"].get("entity")]
    assert linked, "expected io rules to link to the entity whose field they constrain"
    entity_ids = {e["id"] for e in arch["data_entities"]}
    for r in linked:
        assert r["detail"]["entity"] in entity_ids


def test_io_link_prefers_same_file_entity_not_field_collision():
    # A class-validator DTO field named 'email' must NOT link to an unrelated
    # SQL table's 'email' column in the same component (same-file-only linking).
    _, _, arch = _derive()
    dto_rule = next(
        r for r in arch["rules"]
        if r["kind"] == "io" and r["evidence"][0]["file"].endswith("checkout.ts")
        and r["detail"].get("field") == "email"
    )
    linked = dto_rule["detail"].get("entity")
    if linked:
        ent = next(e for e in arch["data_entities"] if e["id"] == linked)
        # if linked at all, it is an entity declared in checkout.ts, never the
        # db/schema.sql accounts table.
        assert any(ev["file"].endswith("checkout.ts") for ev in ent["evidence"])


def test_per_component_rules_key_attached():
    _, _, arch = _derive()

    def walk(cs):
        for c in cs:
            yield c
            yield from walk(c.get("children", []))

    comps_with_rules = [c for c in walk(arch["components"]) if c.get("rules")]
    assert comps_with_rules
    for c in comps_with_rules:
        for r in c["rules"]:
            assert r["component_id"] == c["id"]


def test_emission_is_deterministic():
    store, _, arch1 = _derive()
    _, arch2 = derive_all(store, "rules")
    assert json.dumps(arch1["rules"], sort_keys=True) == \
           json.dumps(arch2["rules"], sort_keys=True)


# ===========================================================================
# Backward compatibility + projection
# ===========================================================================

def test_rules_are_additive_optional_keys(tmp_path):
    # A repo with no rule-bearing code emits rules == [] and no component key.
    src_dir = tmp_path / "plain"
    src_dir.mkdir()
    (src_dir / "util.py").write_text(
        "def add(a, b):\n    return a\n\ndef greet(name):\n    return name\n"
    )
    (src_dir / "pyproject.toml").write_text("[project]\nname='p'\n")
    store = FactStore(":memory:")
    extract_repo(str(src_dir), store)
    _, arch = derive_all(store, "plain")
    assert arch["rules"] == []

    def walk(cs):
        for c in cs:
            yield c
            yield from walk(c.get("children", []))
    assert all("rules" not in c for c in walk(arch["components"]))


def test_projection_carries_rules_and_old_viewer_ignores(tmp_path):
    store, _, arch = _derive()
    out = tmp_path / "architecture.json"
    write_monolith(arch, out)
    doc = json.loads(out.read_text())
    # rules ride as an optional top-level key; every pre-existing key survives.
    assert isinstance(doc["rules"], list) and doc["rules"]
    for key in ("components", "relationships", "capabilities", "data_entities",
                "symbols", "files", "stats"):
        assert key in doc


# ===========================================================================
# 4. Schema migration v2 -> v3 (the rules table's home)
# ===========================================================================

def test_schema_is_at_v3():
    store = FactStore(":memory:")
    assert store.get_meta("schema_version") == str(SCHEMA_VERSION) == "3"


def test_migration_v2_to_v3_is_additive(tmp_path):
    # Simulate a warm v2 store: drop the rules table and stamp version 2, with a
    # pre-existing row that must survive the migration.
    path = tmp_path / "warm.db"
    store = FactStore(str(path))
    store.add_component("c1", "C1", type="service")
    store.commit()
    store._conn.execute("DROP TABLE rules")
    store.set_meta("schema_version", "2")
    store.commit()
    store.close()

    # Reopening with current code migrates v2 -> v3 additively.
    store2 = FactStore(str(path))
    assert store2.get_meta("schema_version") == "3"
    assert any(c["id"] == "c1" for c in store2.components())  # row survived
    # the rules table exists and is usable.
    store2.add_rule("rule:c1:policy:x-abc", "c1", "policy", summary="s",
                    detail={"anchor": "match"}, evidence=[], confidence="inferred")
    store2.commit()
    assert len(store2.rules()) == 1
    store2.close()
