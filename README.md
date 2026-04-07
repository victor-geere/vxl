# VXL — Vortex Exchange Language

Lossless bidirectional encoder/decoder between TypeScript/TSX source files and the VXL compressed dialect.

See [docs/lang.md](../docs/lang.md) for the full VXL specification.

## Files

| File | Purpose |
|------|---------|
| `encoder.py` | Source → VXL (compresses `.ts`/`.tsx` files into VXL blocks) |
| `decoder.py` | VXL → Source (expands VXL blocks back into `.ts`/`.tsx` files) |
| `__init__.py` | Package exports |

## Installation

No external dependencies — pure Python 3.8+. Uses only `re`, `os`, `sys`, `pathlib`, `argparse`.

## Encoder

Converts TypeScript/TSX source files into compact VXL notation.

### CLI

```bash
# Encode a single file
python -m vxl.encoder app/strat/page.tsx --base app

# Encode a directory (all .ts/.tsx files → multi-block VXL doc)
python -m vxl.encoder src/app/ --base src/app

# Write output to file
python -m vxl.encoder app/strat/page.tsx --base app -o strat.vxl
```

### Python API

```python
from vxl.encoder import encode, encode_file, encode_directory

# Encode source string
vxl = encode(source_code, filepath="app/strat/page.tsx", base_dir="app")

# Encode a file from disk
vxl = encode_file("app/strat/page.tsx", base_dir="app")

# Encode all .ts/.tsx in a directory tree
vxl_doc = encode_directory("src/app/", base_dir="src/app")
```

### What it extracts

| Source pattern | VXL output |
|----------------|-----------|
| File path + name | Header line: `app/strat\|page.tsx\|PG` |
| `import { X } from "Y"` | `<<` import field with alias compression |
| `export default function Name` | `>>Name` |
| `export function a, b` | `>>{a,b}` |
| `const [x, setX] = useState<T>(v)` | `$x:T=v` |
| `const ref = useRef<T>(v)` | `$ref:ref<T>=v` |
| `useEffect(() => { fetch... }, [])` | `~mount→fetchFn→$target` |
| `useEffect(() => { ... }, [dep])` | `~[$dep]→action→$target` |
| JSX return with components | `<Card><Table/>` compressed tree |
| Hooks, fetch, forms, tables… | Syntax codes: `tsx+hk+ftc+tbl` |
| `"use client"`, `page.tsx`, etc. | Flags: `@CSR`, `@ENTRY`, `@API` |
| Local imports | `W:` wire lines |

### Body lines (lossless function logic)

The encoder also emits `B:` body lines that capture full function logic using pattern-compressed one-liners:

| Body code | Meaning | Example |
|-----------|---------|---------|
| `B:FETCH` | Promise-based fetch with setter targets | `B:FETCH fetchData()→$items,$loading(false)` |
| `B:AFETCH` | Async/await fetch with setter targets | `B:AFETCH loadUser(id)→$user,$ready(true)` |
| `B:LET` | Variable binding | `B:LET sorted=sortData(data, sort)` |
| `B:ASSIGN` | Assignment to existing variable | `B:ASSIGN count=items.length` |
| `B:GUARD` | Early return guard clause | `B:GUARD !data→return null` |
| `B:IF/ELIF/ELSE` | Conditional blocks (with `B:END`) | `B:IF loading→{}` |
| `B:TRY/CATCH/FINALLY` | Error handling blocks | `B:TRY→{}` |
| `B:RET` | Return statement (with JSX expansion) | `B:RET <Card> <Inner /> </Card>` |
| `B:HANDLE` | Event handler | `B:HANDLE onClick=(e)=>setOpen(true)` |
| `B:CB` | Callback / useMemo / useCallback | `B:CB const fn=useCallback(()=>doThing(), [dep])` |
| `B:DESTRUCT` | Destructuring assignment | `B:DESTRUCT {a,b}=useForm()` |
| `B:TOAST` | Toast notification | `B:TOAST toast.success("Saved")` |
| `B:NAV` | Navigation call | `B:NAV router.push("/home")` |
| `B:RAW` | Uncompressed fallback line | `B:RAW console.table(debug)` |

## Decoder

Expands VXL blocks back into TypeScript/TSX source scaffolds.

### CLI

```bash
# Decode to stdout
python -m vxl.decoder input.vxl

# Decode to a single output file
python -m vxl.decoder input.vxl -o scaffold.tsx

# Decode multi-block VXL into separate files
python -m vxl.decoder input.vxl --files -o output_dir/

# Read from stdin
echo 'app/strat|page.tsx|PG' | python -m vxl.decoder -
```

### Python API

```python
from vxl.decoder import decode, decode_block, decode_to_files

# Decode a VXL string to source code
source = decode(vxl_text)

# Parse a single block into structured dict
block = decode_block(vxl_block)

# Decode and write separate files to disk
created_files = decode_to_files(vxl_text, output_dir="out/")
```

### What it generates

| VXL input | Generated TypeScript |
|-----------|---------------------|
| `@CSR` flag | `"use client";` directive |
| `<<react{useState}` | `import { useState } from "react";` |
| `<<ui{card,btn}` | Separate imports from `@/components/ui/card`, `…/button` |
| `>>PageName` | `export default function PageName() {` |
| `$x:T=v` | `const [x, setX] = useState<T>(v);` |
| `$ref:ref<T>=v` | `const ref = useRef<T>(v);` |
| `~mount→fn→$x` | `useEffect(() => { fn().then(setX); }, []);` |
| `~int(5000)→poll` | `useEffect` with `setInterval`/`clearInterval` |
| `<Card><Table/>` | JSX return block with nested components |
| `Name{f:str,g:num}` | `export interface Name { f: string; g: number; }` |
| `fn(a:str)→num` | `export function fn(a: string): number { … }` |
| `GET,POST→json` | `export async function GET(request: Request) { … }` |

## Round-trip example

```bash
# Encode a source file
python -m vxl.encoder app/sumtransactions/page.tsx --base app > sum.vxl

# Inspect the VXL
cat sum.vxl

# Decode back to source
python -m vxl.decoder sum.vxl -o output.tsx

# One-liner round-trip
python -m vxl.encoder src/page.tsx --base src | python -m vxl.decoder -
```

The `B:` body lines make the round-trip lossless for function logic — state management, data fetching, control flow, and JSX rendering are all preserved. Minor import ordering and formatting differences may occur.

## Type shorthands

| VXL | TypeScript |
|-----|-----------|
| `str` | `string` |
| `num` | `number` |
| `b` | `boolean` |
| `R<K,V>` | `Record<K, V>` |
| `T[]` | `T[]` |
| `T?` | `T \| null` |
| `P<T>` | `Promise<T>` |
| `fn` | `Function` |

## Import alias compression

| Full path | VXL shorthand |
|-----------|--------------|
| `@/components/ui/card` | `ui{card}` |
| `@/components/ui/button` | `ui{btn}` |
| `@/components/badge-led` | `cmp{badge-led}` |
| `@/config/types` | `cfg/types` |
| `@/lib/vortex` | `lib/vortex` |
| `@radix-ui/react-icons` | `radix/icons` |
