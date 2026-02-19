# UI Actions, Source Code Linking, and Deep Navigation

## Vision

Make the architecture viewer a fully navigable, code-connected tool. Three layers:

1. **UI actions**: Capture every interactive element (buttons, toolbars, menus, swipe actions, state properties) as symbols in the analyzer
2. **Source linking**: Every symbol, file, and action links directly to the exact GitHub source location
3. **Bidirectional navigation**: Deep-link URLs let external tools navigate into the architecture viewer

---

## Phase 1: Source Code Linking (Quick Win)

Every file path and symbol line reference becomes a clickable GitHub link.

### 1A. Analyzer: detect default branch

**File: `analyzer/models.py` (Architecture dataclass)**

Add `default_branch` field:
```python
@dataclass
class Architecture:
    # ... existing fields ...
    default_branch: str = "main"
```

**File: `analyzer/scanner.py` (ArchitectureScanner, after repository URL detection)**

Detect from `.git/HEAD`:
```python
        head_ref = self.root / ".git" / "HEAD"
        if head_ref.exists():
            try:
                ref_content = head_ref.read_text(encoding="utf-8", errors="replace").strip()
                if ref_content.startswith("ref: refs/heads/"):
                    self.architecture.default_branch = ref_content.split("/")[-1]
            except OSError:
                pass
```

### 1B. Viewer: types

**File: `viewer/src/types.ts` (~line 134, Architecture interface)**

Add: `default_branch?: string;`

### 1C. Viewer: source link utility

**New file: `viewer/src/utils/sourceLink.ts`**

```typescript
export function buildSourceUrl(
  repository: string | null | undefined,
  defaultBranch: string | undefined,
  filePath: string,
  line?: number,
  endLine?: number,
): string | null {
  if (!repository) return null;
  const branch = defaultBranch || "main";
  let base = repository.replace(/\.git$/, "").replace(/^git@github\.com:/, "https://github.com/");
  let url = `${base}/blob/${branch}/${filePath}`;
  if (line) {
    url += `#L${line}`;
    if (endLine && endLine > line) url += `-L${endLine}`;
  }
  return url;
}
```

### 1D. Viewer: add links to DetailPanel

**File: `viewer/src/components/DetailPanel.tsx`**

- **SymbolsTab** (~line 803, the `{sym.file}:{sym.line}` span): Add a clickable external-link icon that opens the GitHub URL in a new tab. Only render when `architecture.repository` exists.
- **FilesTab** (~line 630): Add a small link icon on each file row.
- **FileDetail header** (~line 1028): Add "View on GitHub" link.
- **SymbolDetail** (~line 1126): Add "View on GitHub" link next to file:line.

### Phase 1 files

| File | Change |
|------|--------|
| `analyzer/models.py`, `analyzer/scanner.py` | `default_branch` field + `.git/HEAD` detection |
| `viewer/src/types.ts` :134 | `default_branch?: string` |
| `viewer/src/utils/sourceLink.ts` | **New**: `buildSourceUrl()` |
| `viewer/src/components/DetailPanel.tsx` | GitHub links on symbols, files, details |

---

## Phase 2: UI Action Detection in Analyzer

Capture interactive UI elements as new symbol kinds within the existing symbol extraction pipeline.

### 2A. New symbol kinds (no schema changes needed, `kind` is already a free-form string)

| Kind | SwiftUI pattern | Example |
|------|----------------|---------|
| `button` | `Button("Label") { action }` | Save, Delete, Toggle buttons |
| `toolbar-item` | `.toolbar { ToolbarItem { ... } }` | Nav bar buttons |
| `menu-item` | `Menu("Label") { Button... }` | Dropdown options |
| `swipe-action` | `.swipeActions { Button... }` | List row swipe buttons |
| `context-menu-item` | `.contextMenu { Button... }` | Long-press menu entries |
| `state-property` | `@State var showSheet: Bool` | Reactive state that drives UI |

### 2B. Shared brace-body extraction

**File: `analyzer/utils.py` (`_extract_brace_body` function)**

The `_extract_brace_body` helper has been extracted to `analyzer/utils.py` as a shared module-level function. Both `SwiftParser` and `SwiftUIFlowDetector` can import it for parsing nested blocks.

### 2C. Extend SwiftParser.extract_symbols

**File: `analyzer/parsers/swift.py` (SwiftParser.extract_symbols)**

Add new detection blocks after the existing function/extension detection (after line 640). The approach: within the same line-by-line loop, track the currently enclosing struct/class via a `current_type_id` variable that updates on type declaration entry and resets when brace depth returns to the entry level.

**Button detection** (after line 623):
```python
# Button("Label") { ... } or Button(action: { ... }) { ... }
m = re.match(r'.*Button\s*\(\s*"([^"]*)"', line)
if m:
    label = m.group(1)
    # Extract action target from the closure body
    action_target = self._extract_action_target(lines, i)
    symbols.append(Symbol(
        id=self._make_symbol_id(file_path, f"btn_{label}", i + 1),
        name=label,
        kind="button",
        file=file_path,
        line=i + 1,
        end_line=i + 1,
        code_preview=lines[i].strip(),
        visibility="internal",
        docstring=None,
        parent=current_type_id,
        dependencies=[action_target] if action_target else [],
    ))
```

**State property detection** (within the type-declaration scanning section):
```python
m = re.match(
    r'\s*@(State|Binding|StateObject|ObservedObject|Published)\s+'
    r'(?:private\s+|public\s+)?(?:var|let)\s+(\w+)',
    line
)
if m:
    wrapper = m.group(1)
    name = m.group(2)
    symbols.append(Symbol(
        id=self._make_symbol_id(file_path, f"state_{name}", i + 1),
        name=name,
        kind="state-property",
        file=file_path,
        line=i + 1,
        end_line=i + 1,
        code_preview=lines[i].strip(),
        visibility="private",
        docstring=f"@{wrapper} property",
        parent=current_type_id,
    ))
```

**Toolbar, context menu, swipe actions** (modifier-based detection):
```python
for modifier_re, kind in [
    (r'\.\s*toolbar\s*\{', "toolbar-item"),
    (r'\.\s*contextMenu\s*\{', "context-menu-item"),
    (r'\.\s*swipeActions\s*(?:\([^)]*\))?\s*\{', "swipe-action"),
]:
    m = re.search(modifier_re, line)
    if m:
        body = _extract_brace_body(lines, i, ...)
        # Scan body for Button patterns, create symbols for each
```

**New helper method on SwiftParser**:
```python
def _extract_action_target(self, lines, line_idx):
    """Extract the function/method called in a Button's action closure."""
    # Look at same line and next few lines for patterns like:
    #   viewModel.save()  -> "save"
    #   showSheet.toggle() -> "showSheet"
    #   dismiss() -> "dismiss"
```

### 2D. Cross-language (lighter touch)

**React** (`analyzer/parsers/typescript.py`, TypeScriptParser.extract_symbols): Scan JSX for `onClick={handleFoo}`, create `kind: "button"` symbols.

**Python** (`analyzer/parsers/python_lang.py`, PythonParser): Route decorators create `kind: "endpoint-handler"` symbols.

### Phase 2 files

| File | Change |
|------|--------|
| `analyzer/parsers/swift.py` | Extend `SwiftParser.extract_symbols`: Button, @State, toolbar, contextMenu, swipeActions, Menu |
| `analyzer/utils.py` | `_extract_brace_body` already extracted as shared utility |
| `analyzer/parsers/typescript.py` | `TypeScriptParser`: React event handler detection |
| `analyzer/parsers/python_lang.py` | `PythonParser`: endpoint handler symbols |

---

## Phase 3: Actions in the Viewer

### 3A. New "Actions" tab

**File: `viewer/src/components/DetailPanel.tsx`**

Add `"actions"` to Tab type (~line 18). Show conditionally when action symbols exist:
```typescript
const ACTION_KINDS = new Set(["button","toolbar-item","menu-item","swipe-action","context-menu-item","state-property"]);
const actionSymbols = symbols.filter(s => ACTION_KINDS.has(s.kind));
```

Group by kind, each row: kind badge, name, target function, GitHub link, line number.

### 3B. Extend kindIcons (~line 712)

```typescript
button: "B", "toolbar-item": "TB", "menu-item": "M",
"swipe-action": "SW", "context-menu-item": "CM", "state-property": "@",
```

### 3C. SYMBOL_KIND_DESCRIPTIONS

**File: `viewer/src/utils/techDocs.ts`** - Add tooltip descriptions for each new kind.

### 3D. ComponentNode indicator

**File: `viewer/src/components/ComponentNode.tsx`** (~line 916) - Show action count badge on screen nodes.

### 3E. OverviewTab summary

Show `UI Actions (12): 5 buttons, 3 toolbar items, 2 menus, 2 state vars` when present.

### Phase 3 files

| File | Change |
|------|--------|
| `viewer/src/components/DetailPanel.tsx` | Actions tab, kindIcons, overview summary |
| `viewer/src/utils/techDocs.ts` | Kind descriptions |
| `viewer/src/components/ComponentNode.tsx` | Action count badge |

---

## Phase 4: Bidirectional Navigation (Foundation)

### 4A. URL deep linking

**File: `viewer/src/App.tsx`** - Parse `?file=path&line=42` on mount. Look up component via file index, drill to it, open detail panel.

### 4B. File-to-component index

**New file: `viewer/src/utils/fileIndex.ts`** - Reverse map from file path to component ID.

### 4C. Store: navigateToFile

**File: `viewer/src/store.ts`** - New action that drills to the component owning a file, opens detail at the right symbol.

### Phase 4 files

| File | Change |
|------|--------|
| `viewer/src/App.tsx` | URL query param parsing |
| `viewer/src/utils/fileIndex.ts` | **New**: file-to-component index |
| `viewer/src/store.ts` | `navigateToFile` action |

---

## Implementation Order

| Phase | Impact | Risk |
|-------|--------|------|
| 1. Source Linking | HIGH | LOW |
| 2. UI Action Detection | HIGH | MEDIUM |
| 3. Viewer Actions Tab | MEDIUM | LOW |
| 4. Bidirectional Nav | MEDIUM | LOW |

Phase 1 first (quick, immediate value). Then Phase 2 (most complex). Phase 3 after 2. Phase 4 anytime.

## Backward Compatibility

- `default_branch` optional, defaults to `"main"`
- New symbol kinds are just string values; old viewers ignore them
- Actions tab only appears when action symbols exist
- Source links only render when `architecture.repository` is set
- Deep-link params ignored if absent
- No existing fields modified or removed

## Verification

1. **Phase 1**: Run analyzer, check `default_branch` in JSON. Open viewer, verify GitHub links on symbols/files.
2. **Phase 2**: `python3 -c "import json; d=json.load(open('test.json')); print(set(s['kind'] for s in d['symbols']))"` should show new kinds.
3. **Phase 3**: Load enhanced JSON, verify Actions tab appears on screen components with buttons.
4. **Phase 4**: Open `?file=X&line=Y`, verify navigation to correct component.
5. **Regression**: `python3 -m pytest tests/ -x` after each phase.
