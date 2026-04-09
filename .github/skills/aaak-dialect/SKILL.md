---
name: aaak-dialect
description: 'Generate an AAAK-style lossless encoder and decoder for any file type. Use when: creating a VXL encoder/decoder pair; adding a new file format to VXL; building an AAAK compression dialect for HTML, CSS, JS, Python, YAML, JSON, Markdown, or any source file. Produces structured summary lines (pipe-separated, syntax codes, flags) plus verbatim body sections for lossless roundtrip.'
argument-hint: 'File type or path to a sample file (e.g. "Python" or "src/app.py")'
---

# AAAK Dialect Generator

Generate a lossless AAAK-style encoder and decoder for any given file type, following the VXL pattern established in `docs/lang.md`.

## When to Use

- Adding support for a new file type (Python, YAML, JSON, Markdown, etc.) to the VXL encoder/decoder
- Creating a custom AAAK compression dialect for a specific domain
- Encoding any source file into a structured, LLM-readable format with lossless roundtrip

## Architecture

An AAAK dialect encoder/decoder pair consists of:

1. **Encoder** (`encode_<type>()` in `vxl/encoder.py`): Source → VXL block
2. **Decoder** (`_decode_<type>_block()` + `_generate_<type>_source()` in `vxl/decoder.py`): VXL block → Source
3. **File-type detection** in `_detect_file_type()` to route new extensions
4. **CLI routing** in `encode()` and `decode()` to dispatch to the new functions

## Procedure

### Step 1: Analyze the File Type

Read the sample file(s) and identify:

- **Structural sections**: What logical parts does the file have? (e.g., HTML has HEAD, CSS, BODY, JS; Python has imports, classes, functions; YAML has top-level keys)
- **Compressible patterns**: What repeating patterns exist? (e.g., import statements, function signatures, variable declarations, config keys)
- **Domain vocabulary**: What are the key concepts for this file type? These become syntax codes and flags.

### Step 2: Define the VXL Format

Design the VXL block format following these rules from [the format spec](./references/format-spec.md):

**Required lines:**
```
PATH|FILENAME|TYPE_CODE      # Header (always first line)
```

**Structural summary lines** (AAAK-style, for LLM readability):
Pick from these sigils based on what the file type has:

| Sigil | Purpose | Use when file has... |
|-------|---------|---------------------|
| `<<` | Imports / dependencies / metadata | imports, includes, links, meta tags |
| `>>` | Exports / public interface | exported functions, classes, public API |
| `$` | State / variables / config | state variables, constants, config values |
| `V:` | Custom properties / variables | CSS vars, env vars, template vars |
| `~` | Lifecycle / events / hooks | event listeners, lifecycle hooks, triggers |
| `INIT:` | Initialization | startup calls, main entry |
| `<tree>` | Structure / DOM / layout | component tree, DOM elements, sections |

**Syntax codes** (pipe-separated, max 6): Domain-specific feature detectors.
**Flags** (max 3): Structural characteristics like `@STANDALONE`, `@VIZ`, etc.

**Lossless content sections**: Verbatim content between `SECTION:BEGIN` / `SECTION:END` markers.

### Step 3: Implement the Encoder

Add to `vxl/encoder.py`:

1. **Helper functions** for extracting structural metadata:
   ```python
   def _<type>_extract_<feature>(content: str) -> str:
       """Build summary line for <feature>."""
   ```

2. **Syntax signal map** for detecting domain features:
   ```python
   _<TYPE>_SYNTAX_SIGNALS = {
       "code": [r"regex_pattern", ...],
   }
   ```

3. **Main encode function**:
   ```python
   def encode_<type>(source: str, filepath: str, base_dir: str = "") -> str:
       # 1. Parse path → header line
       # 2. Extract structural metadata → summary lines
       # 3. Detect syntax codes + flags
       # 4. Split into logical sections
       # 5. Emit summary lines, then verbatim sections
   ```

4. **Route in `_detect_file_type()`**: Add file extension mapping.
5. **Route in `encode()`**: Dispatch to `encode_<type>()`.

### Step 4: Implement the Decoder

Add to `vxl/decoder.py`:

1. **Block parser**:
   ```python
   def _decode_<type>_block(block: str) -> Dict:
       # Parse header, skip summary lines, collect verbatim sections
   ```

2. **Source generator**:
   ```python
   def _generate_<type>_source(block: Dict) -> str:
       # Reassemble original file from parsed sections
   ```

3. **Route in `decode()` and `decode_to_files()`**: Detect TYPE_CODE and dispatch.

### Step 5: Test Lossless Roundtrip

```bash
./cmd/enc.sh <input_file> src/vxl/
./cmd/dec.sh src/vxl/<output>.txt src/reverse/
diff <input_file> src/reverse/<path>/<input_file>
```

The diff MUST produce zero output. If there are differences:
- Check whitespace handling around section boundaries
- Ensure content between BEGIN/END is stored/emitted verbatim
- Verify the reassembly joins sections without adding/removing newlines

## Key Principles

1. **Lossless first**: The verbatim sections guarantee exact reconstruction. Summary lines are redundant metadata for readability.
2. **Summary lines are derived**: They extract info from the same content that's stored verbatim. The decoder can safely skip them.
3. **Domain vocabulary**: Syntax codes and flags should use terms native to the file type, not React/TS terms.
4. **Pipe-separated notation**: Follow AAAK conventions — `|` separates fields, `+` joins multi-values, `→` shows data flow.

## Reference Files

- [Format specification & examples](./references/format-spec.md): Detailed VXL format rules, HTML example, template for new file types
