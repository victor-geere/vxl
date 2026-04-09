# VXL Format Specification — Reference for New Dialects

## Block Structure

Every VXL block describes one source file. A block has:

1. **Header line** (required, always first)
2. **Structural summary lines** (AAAK-style, for LLM readability)
3. **Lossless content sections** (verbatim, for exact reconstruction)

## Header Line

```
PATH|FILENAME|TYPE_CODE
```

- `PATH`: Directory path relative to project root (use `/` separator)
- `FILENAME`: Source filename with extension
- `TYPE_CODE`: File-type code (uppercase, 2-4 chars)

### File-Type Codes

| Code | Meaning | Extensions |
|------|---------|------------|
| `HTML` | HTML document | `.html`, `.htm` |
| `PG` | Page component | `page.tsx` |
| `CMP` | UI component | `.tsx` in `components/` |
| `LIB` | Library module | `.ts`, `.js` |
| `PY` | Python module | `.py` |
| `YML` | YAML config | `.yml`, `.yaml` |
| `JSON` | JSON data | `.json` |
| `MD` | Markdown | `.md` |
| `CSS` | Stylesheet | `.css` |
| `SH` | Shell script | `.sh`, `.bash` |

Add new codes as needed. Keep them short and mnemonic.

## Structural Summary Lines

These lines follow AAAK notation — pipe-separated, symbol-dense, LLM-readable.
They are **derived from** the verbatim content (redundant metadata).
The decoder **skips** them — they exist for readability only.

### Sigils

| Sigil | Purpose | Example |
|-------|---------|---------|
| `<<` | Imports/deps/meta | `<<charset=UTF-8\|viewport=...\|title=Hilbert Maze` |
| `>>` | Exports/public API | `>>d2xy,xy2d,buildCurve,render` |
| `$` | State/variables | `$S={order,scale}\|$BASE=512` |
| `V:` | Custom properties | `V:--neo-bg=#e0e5ec\|--neo-text=#2c3e50` |
| `~` | Events/lifecycle | `~sl-order.input→regenerateAll` |
| `INIT:` | Initialization | `INIT:regenerateAll()` |
| `ATTR:` | Element attributes | `ATTR:lang="en"` |
| `DOCTYPE:` | Non-default doctype | `DOCTYPE:<!DOCTYPE html5>` |

### DOM/Structure Tree

```
<tag#id.class><tag.class><tag#id>|syntax+codes|@FLAGS
```

Compact element summary with id (`#`) and first class (`.`) selectors.

### Syntax Codes

Domain-specific feature codes. Max 6 per block, `+`-joined.

**For HTML/CSS/JS:**

| Code | Meaning | Detection patterns |
|------|---------|-------------------|
| `canvas` | Canvas 2D/3D | `<canvas`, `getContext(`, `beginPath(` |
| `dom` | DOM manipulation | `getElementById(`, `createElement(`, `.innerHTML` |
| `evt` | Event listeners | `addEventListener(` |
| `math` | Math/algorithms | `Math.`, bitwise ops |
| `tbl` | Table rendering | `<table`, `<th`, `<td` |
| `grid` | CSS flex/grid layout | `display: flex`, `flex-direction` |
| `neo` | Neumorphic design | `box-shadow.*inset`, `neo-` |
| `var` | CSS custom props | `var(--`, `:root` |
| `rng` | Range/slider input | `type="range"` |
| `anim` | Animation/transition | `transition:`, `@keyframes` |
| `font` | Custom fonts | `fonts.googleapis`, `font-family` |
| `scroll` | Scroll behavior | `overflow: auto`, `position: sticky` |

**For Python:**

| Code | Meaning | Detection patterns |
|------|---------|-------------------|
| `cls` | Class definitions | `class \w+` |
| `dec` | Decorators | `@\w+` |
| `gen` | Generators/iterators | `yield` |
| `ctx` | Context managers | `with`, `__enter__` |
| `re` | Regex operations | `re.search`, `re.match` |
| `io` | File I/O | `open(`, `Path(` |
| `cli` | CLI/argparse | `argparse`, `sys.argv` |
| `exc` | Exception handling | `try:`, `except:` |

### Flags

Structural characteristics. Max 3 per block, `+`-joined.

| Flag | Meaning |
|------|---------|
| `@STANDALONE` | Self-contained, no external deps |
| `@VIZ` | Visualization (canvas/SVG/charts) |
| `@INTERACTIVE` | User interaction (events, forms) |
| `@SPA` | Single page application |
| `@ENTRY` | Entry point |
| `@PURE` | No side effects |
| `@ASYNC` | Async operations |

## Lossless Content Sections

```
SECTION:BEGIN
... verbatim content ...
SECTION:END
```

Content between BEGIN and END is stored **exactly as-is** — preserving whitespace, indentation, comments, blank lines.

### Section Names by File Type

**HTML:**
- `HEAD:BEGIN/END` — `<head>` content (minus `<style>`)
- `CSS:BEGIN/END` — `<style>` content
- `BODY:BEGIN/END` — `<body>` content (minus `<script>`)
- `JS:BEGIN/END` — `<script>` content

**Python:**
- `IMPORTS:BEGIN/END` — import statements
- `CODE:BEGIN/END` — main code body

**YAML/JSON:**
- `DATA:BEGIN/END` — full file content

**Markdown:**
- `CONTENT:BEGIN/END` — full file content

## HTML Example

Input (`hilbert.html`, 576 lines):

```
src/html|hilbert.html|HTML
ATTR:lang="en"
<<charset=UTF-8|viewport=width=device-width,initial-scale=1.0|title=Hilbert Maze|preconnect(fonts.googleapis.com)|stylesheet(fonts.googleapis.com/css2?...)
V:--neo-bg=#e0e5ec|--neo-text=#2c3e50|--neo-shadow-light=#ffffff|...
<h1><div.app-col><div.controls><canvas#maze><div#path-card><table#ptable>|canvas+dom+evt+math+tbl+grid|@STANDALONE+@VIZ+@INTERACTIVE
$S={order,scale,selPath,curve,paths,entries}|$BASE=512|$MAX_TABLE_COLS=150
>>d2xy,xy2d,colLetter,cellName,buildCurve,edgeCells,shuffle,...,render,regenerateAll
~sl-order.input→regenerateAll|~sl-scale.input→updateLabels+render|~reset.click→regenerateAll
INIT:regenerateAll()
HEAD:BEGIN
<meta charset="UTF-8">
...
HEAD:END
CSS:BEGIN
  :root { --neo-bg: #e0e5ec; ... }
  ...
CSS:END
BODY:BEGIN
<h1><span class="text-gradient">Hilbert Maze</span></h1>
...
BODY:END
JS:BEGIN
const S = { order: 3, scale: 1.0, ... };
function d2xy(order, d) { ... }
...
JS:END
```

The summary lines (lines 2-9) give an LLM instant context.
The verbatim sections (HEAD/CSS/BODY/JS) enable exact reconstruction.

## Template for New File Types

When adding a new file type, follow this template:

### 1. Define syntax signals

```python
_<TYPE>_SYNTAX_SIGNALS = {
    "feature_code": [r"detection_regex", ...],
    ...
}
```

### 2. Create extraction helpers

```python
def _<type>_extract_imports(content: str) -> str:
    """Build << import summary."""
    ...

def _<type>_extract_exports(content: str) -> str:
    """Build >> export summary."""
    ...

# Add more as needed for the file type
```

### 3. Create encoder

```python
def encode_<type>(source: str, filepath: str, base_dir: str = "") -> str:
    out = []
    # Header
    out.append(f"{wing_path}|{filename}|TYPE_CODE")
    # Summary lines (AAAK-style)
    out.append(_<type>_extract_imports(source))
    out.append(_<type>_extract_exports(source))
    # ... more summary lines
    # Verbatim content
    out.append("SECTION:BEGIN")
    out.append(content)
    out.append("SECTION:END")
    return "\n".join(out)
```

### 4. Create decoder

```python
def _decode_<type>_block(block: str) -> Dict:
    # Parse header, collect verbatim sections, skip summary lines
    ...

def _generate_<type>_source(block: Dict) -> str:
    # Reassemble original from verbatim sections
    ...
```

### 5. Wire up routing

In `encoder.py`:
- Add extension check in `_detect_file_type()`
- Add dispatch in `encode()`

In `decoder.py`:
- Add TYPE_CODE check in `decode()` and `decode_to_files()`
