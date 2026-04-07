# AAAK Compression Dialect — Technical Specification

> **Version:** Aligned with mempalace v3.0.0  
> **Implementation:** `dialect.py`  
> **Compression:** ~30× lossless, readable by any LLM without a decoder

---

## 1. Overview

AAAK is a **lossless symbolic compression dialect** designed for AI agent memory. It compresses natural-language knowledge into a structured, token-efficient format that any large language model (Claude, GPT, Gemini, Llama, Mistral) can read natively — no decoder required.

**Key properties:**

- ~30× token reduction over equivalent English prose
- Deterministic encoding — same input always produces the same output
- Human-readable (terse, but parseable by a person)
- Works on plain text or structured zettel JSON
- Integrated into the mempalace memory stack at Layer 1 (L1)

**Example — English (~1000 tokens):**

```
Priya manages the Driftwood team: Kai (backend, 3 years), Soren (frontend),
Maya (infrastructure), and Leo (junior, started last month). They're building
a SaaS analytics platform. Current sprint: auth migration to Clerk. Kai
recommended Clerk over Auth0 based on pricing and DX.
```

**AAAK equivalent (~120 tokens):**

```
TEAM: PRI(lead) | KAI(backend,3yr) SOR(frontend) MAY(infra) LEO(junior,new)
PROJ: DRIFTWOOD(saas.analytics) | SPRINT: auth.migration→clerk
DECISION: KAI.rec:clerk>auth0(pricing+dx) | ★★★★
```

---

## 2. Format Structure

An AAAK-encoded block consists of a **header line** followed by one or more **content lines**. Files can contain multiple blocks separated by `---`.

### 2.1 Header Line

```
FILE_NUM|PRIMARY_ENTITY|DATE|TITLE
```

| Field            | Description                                | Example      |
|------------------|--------------------------------------------|--------------|
| `FILE_NUM`       | Source file number or wing identifier       | `001`, `app` |
| `PRIMARY_ENTITY` | Dominant entity codes, `+`-joined           | `KAI+PRI`    |
| `DATE`           | Date context string                        | `2024-03`    |
| `TITLE`          | Short title derived from source filename   | `auth-setup` |

When compressing plain text with metadata, the header uses `wing|room|date|source_stem`.

### 2.2 Content Lines (Zettel Lines)

```
ZID:ENTITIES|topic_keywords|"key_quote"|WEIGHT|EMOTIONS|FLAGS
```

| Field          | Description                                          | Example                        |
|----------------|------------------------------------------------------|--------------------------------|
| `ZID`          | Zettel ID (numeric suffix from full ID)              | `0`, `12`                      |
| `ENTITIES`     | Entity short codes, `+`-joined                       | `KAI+PRI`                      |
| `topic_keywords` | Underscore-joined topic words (max 3)              | `auth_migration_clerk`         |
| `"key_quote"`  | Most important sentence fragment, quoted (≤55 chars) | `"switched to Clerk for DX"`   |
| `WEIGHT`       | Emotional weight, `0.0`–`1.0`                        | `0.92`                         |
| `EMOTIONS`     | Emotion codes, `+`-joined (max 3)                    | `determ+trust`                 |
| `FLAGS`        | Importance flags, `+`-joined                         | `DECISION+TECHNICAL`           |

For plain-text compression (no zettel JSON), the format simplifies to:

```
0:ENTITIES|topics|"key_quote"|emotions|flags
```

Weight is omitted; the ZID is always `0`.

### 2.3 Tunnel Lines

Tunnels encode cross-references between zettels:

```
T:ZID_A<->ZID_B|label
```

### 2.4 Arc Lines

Emotional arcs track sentiment progression across a file:

```
ARC:emotion->emotion->emotion
```

---

## 3. Encoding Rules

### 3.1 Entity Encoding

Entities (people, systems, projects) are compressed to **3-character uppercase codes**.

| Rule                         | Input             | Output  |
|------------------------------|-------------------|---------|
| Configured mapping           | `"Alice": "ALC"`  | `ALC`   |
| Case-insensitive lookup      | `alice`           | `ALC`   |
| Substring match in known map | `Alice Smith`     | `ALC`   |
| Auto-code (fallback)         | `Priya`           | `PRI`   |

- Codes are derived from the **first 3 characters**, uppercased
- Unknown entities in plain text are detected via capitalized words (not at sentence start, ≥2 chars, not stop words)
- Max 3 entities per line
- If no entities are found, `???` is used

### 3.2 Topic Extraction

Topics are extracted from text by frequency analysis with boosting:

1. Tokenize into alphanumeric words (≥3 chars)
2. Remove stop words (~150 common English words)
3. Count frequency
4. Boost proper nouns (+2) and technical terms with `_`, `-`, or camelCase (+2)
5. Take the top 3 by frequency
6. Join with `_`

### 3.3 Key Quote Selection

The most important sentence fragment is selected by scoring:

| Signal                             | Score modifier |
|------------------------------------|----------------|
| Contains decision word (`decided`, `because`, `prefer`, `switched`, `chose`, `realized`, `important`, `key`, `critical`, `discovered`, `learned`, `conclusion`, `solution`, `breakthrough`, `insight`) | +2 each |
| Sentence < 80 chars               | +1             |
| Sentence < 40 chars               | +1             |
| Sentence > 150 chars              | −2             |

The highest-scoring sentence is selected and truncated to 55 characters if needed.

### 3.4 Emotion Codes

Emotions are detected from text via keyword signals and compressed to short codes (max 3 per line):

| Emotion        | Code      | Signal keywords          |
|----------------|-----------|--------------------------|
| vulnerability  | `vul`     | —                        |
| joy            | `joy`     | `happy`                  |
| fear           | `fear`    | `fear`                   |
| trust          | `trust`   | `trust`                  |
| grief          | `grief`   | `sad`, `disappoint`      |
| wonder         | `wonder`  | `wonder`                 |
| rage           | `rage`    | `hate`                   |
| love           | `love`    | `love`                   |
| hope           | `hope`    | `hope`                   |
| despair        | `despair` | —                        |
| peace          | `peace`   | —                        |
| relief         | `relief`  | `relieved`               |
| humor          | `humor`   | —                        |
| tenderness     | `tender`  | —                        |
| raw honesty    | `raw`     | —                        |
| self-doubt     | `doubt`   | —                        |
| anxiety        | `anx`     | `worried`, `anxious`, `concern` |
| exhaustion     | `exhaust` | —                        |
| conviction     | `convict` | `prefer`                 |
| quiet passion  | `passion` | —                        |
| warmth         | `warmth`  | —                        |
| curiosity      | `curious` | `curious`                |
| gratitude      | `grat`    | `grateful`               |
| frustration    | `frust`   | `frustrated`             |
| confusion      | `confuse` | `confused`               |
| satisfaction   | `satis`   | `satisf`                 |
| excitement     | `excite`  | `excited`                |
| determination  | `determ`  | `decided`                |
| surprise       | `surprise`| `surprised`              |

Codes are `+`-joined and deduplicated. Max 3 per zettel.

### 3.5 Flags

Flags mark structural importance. Detected via keyword signals in text:

| Flag        | Meaning                           | Signal keywords                                                |
|-------------|-----------------------------------|----------------------------------------------------------------|
| `ORIGIN`    | Origin moment — birth of something | `founded`, `created`, `started`, `born`, `launched`, `first time` |
| `CORE`      | Core belief or identity pillar    | `core`, `fundamental`, `essential`, `principle`, `belief`, `always`, `never forget` |
| `SENSITIVE` | Handle with absolute care         | Sensitivity metadata (zettel mode)                             |
| `PIVOT`     | Emotional turning point           | `turning point`, `changed everything`, `realized`, `breakthrough`, `epiphany` |
| `GENESIS`   | Led directly to something existing | Genesis metadata (zettel mode)                                |
| `DECISION`  | Explicit decision or choice       | `decided`, `chose`, `switched`, `migrated`, `replaced`, `instead of`, `because` |
| `TECHNICAL` | Technical detail                  | `api`, `database`, `architecture`, `deploy`, `infrastructure`, `algorithm`, `framework`, `server`, `config` |

Flags are `+`-joined. Max 3 per line.

---

## 4. Notation Symbols

| Symbol | Meaning                        | Example                          |
|--------|--------------------------------|----------------------------------|
| `\|`   | Field separator                | `KAI\|auth_migration\|"quote"`   |
| `+`    | Conjunction / multi-value      | `KAI+PRI`, `determ+trust`       |
| `_`    | Topic word join                | `auth_migration_clerk`           |
| `.`    | Qualified name / namespace     | `saas.analytics`                 |
| `→`    | Transition / direction         | `auth.migration→clerk`           |
| `>`    | Comparison / preference        | `clerk>auth0`                    |
| `:`    | Key-value binding              | `KAI.rec:clerk`                  |
| `()`   | Contextual annotation          | `(pricing+dx)`, `(backend,3yr)` |
| `★`    | Importance rating              | `★★★★`                          |
| `""`   | Key quote delimiter            | `"switched to Clerk for DX"`     |
| `<->`  | Bidirectional tunnel link      | `T:12<->15\|shared_theme`        |
| `---`  | Block separator between files  | (standalone line)                |

---

## 5. Memory Stack Integration

AAAK operates at **Layer 1 (L1)** of the mempalace memory stack:

| Layer | Name             | Content                                    | Token budget |
|-------|------------------|--------------------------------------------|-------------|
| L0    | Identity         | Agent identity, personality                | ~50 tokens  |
| **L1** | **Critical Facts (AAAK)** | **Compressed essential knowledge** | **~120 tokens** |
| L2    | Room Recall      | Full drawer content from relevant rooms    | Variable    |
| L3    | Deep Search      | Semantic search across entire palace       | Variable    |

### Layer 1 Generation

`dialect.generate_layer1()` auto-generates a L1 wake-up file by:

1. Scanning all zettel files in a directory
2. Selecting zettels with `emotional_weight ≥ 0.85` OR `ORIGIN`/`CORE`/`GENESIS` flags
3. Sorting by weight (descending)
4. Grouping by date
5. Emitting them under `=MOMENTS[date]=` sections with tunnel summaries under `=TUNNELS=`

Output format:

```
## LAYER 1 -- ESSENTIAL STORY
## Auto-generated from zettel files. Updated 2025-01-15.

=MOMENTS[March 2024]=
KAI+PRI|auth-setup|"switched to Clerk for DX"|0.92|DECISION+TECHNICAL
...

=TUNNELS=
shared_theme
...
```

---

## 6. API Reference

### `Dialect` Class

```python
from mempalace.dialect import Dialect

# Basic — auto-codes entities from first 3 chars
dialect = Dialect()

# With entity mappings
dialect = Dialect(entities={"Alice": "ALC", "Bob": "BOB"})

# From config file (JSON with "entities" and "skip_names")
dialect = Dialect.from_config("entities.json")
```

### Core Methods

| Method | Input | Output | Description |
|--------|-------|--------|-------------|
| `compress(text, metadata=None)` | `str` | `str` | Compress plain text to AAAK |
| `compress_file(path, output=None)` | zettel JSON path | `str` | Compress a zettel JSON file |
| `compress_all(dir, output=None)` | directory path | `str` | Compress all zettel JSONs in a directory |
| `generate_layer1(dir, output=None, identity=None, threshold=0.85)` | directory path | `str` | Generate L1 wake-up file from high-weight zettels |
| `decode(dialect_text)` | `str` | `dict` | Parse AAAK back into structured dict |
| `compression_stats(original, compressed)` | `str`, `str` | `dict` | Token counts and ratio |

### Encoding Primitives

| Method | Description |
|--------|-------------|
| `encode_entity(name)` | Name → 3-char code |
| `encode_emotions(list)` | Emotion list → `+`-joined codes |
| `get_flags(zettel)` | Extract flag strings from zettel metadata |
| `encode_zettel(zettel)` | Single zettel dict → AAAK line |
| `encode_tunnel(tunnel)` | Tunnel dict → `T:` line |
| `encode_file(zettel_json)` | Full zettel JSON → multi-line AAAK block |

### Statistics

```python
stats = dialect.compression_stats(original_text, compressed_text)
# {
#   "original_tokens": 1000,
#   "compressed_tokens": 33,
#   "ratio": 30.3,
#   "original_chars": 3000,
#   "compressed_chars": 100
# }
```

Token estimation: **1 token ≈ 3 characters** (for structured text).

---

## 7. CLI Usage

```bash
# Compress plain text
python dialect.py "We decided to use GraphQL instead of REST..."

# Compress a zettel JSON file
python dialect.py --file zettel.json

# Compress all zettels in a directory
python dialect.py --all ./zettels/

# Show compression statistics
python dialect.py --stats zettel.json

# Generate Layer 1 wake-up file
python dialect.py --layer1 ./zettels/

# Initialize example entity config
python dialect.py --init

# Use custom entity mappings
python dialect.py --config entities.json "Alice met Bob at the lab"
```

Via mempalace CLI:

```bash
# Compress an entire wing
mempalace compress --wing myapp
```

---

## 8. MCP Server Integration

When mempalace runs as an MCP server, AAAK is self-bootstrapping:

1. **`mempalace_status`** — The status response includes the AAAK spec inline, so connected agents learn the dialect automatically on first call.
2. **`mempalace_get_aaak_spec`** — Dedicated MCP tool that returns the full AAAK specification for agent consumption.
3. **Agent diary entries** — Stored in AAAK format within the palace, keeping agent self-knowledge compressed.

No manual teaching is required. Any agent connecting via MCP learns AAAK from the server response.

---

## 9. Configuration

Entity mappings are stored in a JSON config file:

```json
{
  "entities": {
    "Alice": "ALC",
    "Bob": "BOB",
    "Dr. Chen": "CHN"
  },
  "skip_names": ["Gandalf", "Sherlock"]
}
```

- **`entities`**: Map of full names to 3-char codes
- **`skip_names`**: Names to ignore during entity detection (fictional characters, etc.)

Load with `Dialect.from_config("entities.json")` or `--config entities.json`.

---

## 10. Decoding

`Dialect.decode()` parses AAAK back into a structured dictionary:

```python
result = dialect.decode(aaak_text)
# {
#   "header": {"file": "001", "entities": "KAI+PRI", "date": "2024-03", "title": "auth-setup"},
#   "arc": "anx->determ->relief",
#   "zettels": ["12:KAI+PRI|auth_migration|\"switched to Clerk\"|0.92|determ|DECISION"],
#   "tunnels": ["T:12<->15|shared_theme"]
# }
```

Parsing rules:
- Lines starting with `ARC:` → arc
- Lines starting with `T:` → tunnels
- Lines containing `|` and `:` in the first segment → zettel content lines
- Other lines containing `|` → header

---

## 11. Design Principles

1. **Any-LLM native** — No custom tokenizer, no binary format, no decoder model. Plain text that every language model already understands.
2. **Lossless for decisions** — Key quotes, decisions, entity relationships, and emotional context are preserved. Only filler prose is stripped.
3. **Self-documenting** — The format is readable by humans (with practice) and by AI agents (immediately).
4. **Composable** — AAAK blocks concatenate with `---` separators. L1 files aggregate from individual blocks.
5. **Deterministic** — Same input produces the same output. No randomness, no model calls in the encoding path.
