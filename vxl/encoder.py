#!/usr/bin/env python3
"""
VXL Encoder — Source (TS/TSX) → VXL
====================================

Reads a TypeScript or TSX source file and emits a compressed VXL block.
See docs/lang.md for the full VXL specification.

Usage:
    python -m vxl.encoder path/to/page.tsx
    python -m vxl.encoder path/to/page.tsx --base app
    python -m vxl.encoder src/app/strat/page.tsx --base src/app
"""

import re
import sys
import os
from pathlib import Path
from typing import List, Dict, Optional, Tuple


# ── File-type codes (§3.1) ──────────────────────────────────────────────────

def _detect_file_type(filename: str, dirpath: str) -> str:
    """Infer VXL file-type code from filename and directory context."""
    name = filename.lower()
    if name == "page.tsx":
        return "PG"
    if name == "layout.tsx":
        return "LY"
    if name == "route.ts":
        return "RT"
    if name.startswith("use") and name.endswith((".ts", ".tsx")):
        return "HK"
    if name == "types.ts":
        return "TP"
    if name in ("api.ts", "api.tsx"):
        return "API"
    if name in ("index.ts", "index.tsx"):
        return "IDX"
    if name.endswith((".css", ".module.css")):
        return "STY"
    if name == "middleware.ts":
        return "MDW"
    if ".test." in name or ".spec." in name:
        return "TEST"
    if "config" in name:
        return "CFG"
    if "-context." in name or "-provider." in name:
        return "CTX"
    if name in ("helpers.tsx", "helpers.ts", "utils.ts", "utils.tsx"):
        return "UT"
    if "lib" in dirpath.split(os.sep):
        return "LIB"
    if "components" in dirpath.split(os.sep) and name.endswith(".tsx"):
        return "CMP"
    if name.endswith(".tsx"):
        return "CMP"
    return "LIB"


# ── Import compression (§5) ─────────────────────────────────────────────────

_NAME_ABBREV = {
    "button": "btn",
    "filter": "flt",
    "skeleton": "skeleton",
    "navigation": "nav",
}

_IMPORT_RE = re.compile(
    r"""import\s+"""
    r"""(?:type\s+)?"""             # optional 'type'
    r"""(?:"""
    r"""(?P<default>\w+)"""         # default import
    r"""|"""
    r"""\{(?P<named>[^}]+)\}"""     # named imports
    r"""|"""
    r"""(?P<default2>\w+)\s*,\s*\{(?P<named2>[^}]+)\}"""  # default + named
    r""")\s+from\s+"""
    r"""["'](?P<path>[^"']+)["']""",
    re.VERBOSE,
)


def _parse_imports(source: str) -> List[Dict[str, str]]:
    """Extract all import statements into structured dicts."""
    results = []
    for line in source.splitlines():
        line = line.strip()
        if not line.startswith("import"):
            continue
        m = _IMPORT_RE.match(line)
        if not m:
            # Simpler patterns: import "module" or import default from "mod"
            simple = re.match(
                r"""import\s+(?:type\s+)?(?:(\w+)\s*,\s*)?\{([^}]*)\}\s+from\s+["']([^"']+)["']""",
                line,
            )
            if simple:
                default_name = simple.group(1) or ""
                named = [n.strip() for n in simple.group(2).split(",") if n.strip()]
                path = simple.group(3)
                results.append({"default": default_name, "named": named, "path": path})
                continue
            simple2 = re.match(
                r"""import\s+(?:type\s+)?(\w+)\s+from\s+["']([^"']+)["']""", line
            )
            if simple2:
                results.append(
                    {"default": simple2.group(1), "named": [], "path": simple2.group(2)}
                )
                continue
            continue
        default_name = m.group("default") or m.group("default2") or ""
        named_str = m.group("named") or m.group("named2") or ""
        named = [n.strip().split(" as ")[0].strip() for n in named_str.split(",") if n.strip()]
        path = m.group("path")
        results.append({"default": default_name, "named": named, "path": path})
    return results


def _compress_import_path(path: str) -> str:
    """Apply §5 alias compression to an import path."""
    if path.startswith("@/components/ui/"):
        component = path.replace("@/components/ui/", "")
        return f"ui{{{_NAME_ABBREV.get(component, component)}}}"
    if path.startswith("@/components/"):
        component = path.replace("@/components/", "")
        component = _NAME_ABBREV.get(component, component)
        return f"cmp{{{component}}}"
    if path.startswith("@/config/"):
        return "cfg/" + path.replace("@/config/", "")
    if path.startswith("@/lib/"):
        return "lib/" + path.replace("@/lib/", "")
    if path.startswith("@radix-ui/react-"):
        return "radix/" + path.replace("@radix-ui/react-", "")
    if path.startswith("@radix-ui/"):
        return "radix/" + path.replace("@radix-ui/", "")
    return path


def _build_import_field(imports: List[Dict[str, str]]) -> str:
    """Build the << import field string from parsed imports."""
    # Group named imports by compressed module path
    grouped: Dict[str, List[str]] = {}
    order: List[str] = []
    for imp in imports:
        cpath = _compress_import_path(imp["path"])
        # For ui{} and cmp{} the component name is already in cpath's braces
        # Check if we already embedded the component in the path shorthand
        if cpath.startswith("ui{") or cpath.startswith("cmp{"):
            # Already compressed; extract the inner name so we can group
            inner = cpath[cpath.index("{") + 1 : cpath.index("}")]
            prefix = cpath[: cpath.index("{")]
            if prefix not in grouped:
                grouped[prefix] = []
                order.append(prefix)
            if inner not in grouped[prefix]:
                grouped[prefix].append(inner)
        else:
            if imp["named"]:
                if cpath not in grouped:
                    grouped[cpath] = []
                    order.append(cpath)
                for n in imp["named"]:
                    if n not in grouped[cpath]:
                        grouped[cpath].append(n)
            else:
                if cpath not in grouped:
                    grouped[cpath] = []
                    order.append(cpath)

    parts = []
    for key in order:
        names = grouped[key]
        if names:
            parts.append(f"{key}{{{','.join(names)}}}")
        else:
            parts.append(key)
    return ",".join(parts)


# ── Export detection ─────────────────────────────────────────────────────────

def _parse_exports(source: str) -> Tuple[str, bool]:
    """Extract exports. Returns (vxl_export_string, is_default)."""
    defaults = []
    named = []
    for line in source.splitlines():
        line = line.strip()
        # export default function Name
        m = re.match(r"export\s+default\s+function\s+(\w+)", line)
        if m:
            defaults.append(m.group(1))
            continue
        # export default Name   (variable)
        m = re.match(r"export\s+default\s+(\w+)", line)
        if m:
            defaults.append(m.group(1))
            continue
        # export function Name
        m = re.match(r"export\s+(?:async\s+)?function\s+(\w+)", line)
        if m:
            named.append(m.group(1))
            continue
        # export const Name
        m = re.match(r"export\s+const\s+(\w+)", line)
        if m:
            named.append(m.group(1))
            continue
        # export interface/type Name
        m = re.match(r"export\s+(?:interface|type)\s+(\w+)", line)
        if m:
            named.append(m.group(1))
            continue

    if defaults:
        return ">>" + defaults[0], True
    if named:
        return ">>{" + ",".join(named) + "}", False
    return "", False


# ── State extraction ─────────────────────────────────────────────────────────

_TYPE_SHORTS = {
    "string": "str",
    "number": "num",
    "boolean": "b",
}

_USESTATE_RE = re.compile(
    r"""const\s+\[(\w+),\s*\w+\]\s*=\s*useState"""
    r"""(?:<([^>]+)>)?"""     # optional generic
    r"""\(([^)]*)\)""",       # initial value
    re.VERBOSE,
)

_USEREF_RE = re.compile(
    r"""const\s+(\w+)\s*=\s*useRef"""
    r"""(?:<([^>]+)>)?"""
    r"""\(([^)]*)\)""",
    re.VERBOSE,
)


def _shorten_type(t: str) -> str:
    """Apply §3.3 type shorthands."""
    t = t.strip()
    # Handle T | null → T?
    if " | null" in t:
        inner = t.replace(" | null", "").strip()
        return _shorten_type(inner) + "?"
    if "null | " in t:
        inner = t.replace("null | ", "").strip()
        return _shorten_type(inner) + "?"
    # Record<K,V>
    m = re.match(r"Record<(.+),\s*(.+)>", t)
    if m:
        return f"R<{_shorten_type(m.group(1))},{_shorten_type(m.group(2))}>"
    # Promise<T>
    m = re.match(r"Promise<(.+)>", t)
    if m:
        return f"P<{_shorten_type(m.group(1))}>"
    return _TYPE_SHORTS.get(t, t)


def _shorten_value(val: str) -> str:
    """Shorten common default values."""
    val = val.strip()
    if val in ("null", "undefined", ""):
        return "null"
    if val == "true":
        return "true"
    if val == "false":
        return "false"
    if val == "[]":
        return "[]"
    if val == "{}":
        return "{}"
    return val


def _parse_state(source: str) -> List[str]:
    """Extract useState and useRef calls into VXL $-declarations."""
    decls = []
    for m in _USESTATE_RE.finditer(source):
        name = m.group(1)
        type_str = m.group(2) or ""
        default = m.group(3).strip()
        type_short = _shorten_type(type_str) if type_str else ""
        default_short = _shorten_value(default)
        if type_short and default_short and default_short != "null":
            decls.append(f"${name}:{type_short}={default_short}")
        elif type_short:
            nullable = "?" in type_short or default_short == "null"
            t = type_short
            if nullable and not t.endswith("?"):
                t += "?"
            if default_short == "null":
                decls.append(f"${name}:{t}=null")
            else:
                decls.append(f"${name}:{t}")
        else:
            if default_short:
                decls.append(f"${name}={default_short}")
            else:
                decls.append(f"${name}")

    for m in _USEREF_RE.finditer(source):
        name = m.group(1)
        type_str = m.group(2) or ""
        default = m.group(3).strip()
        type_short = _shorten_type(type_str) if type_str else ""
        default_short = _shorten_value(default)
        ref_type = f"ref<{type_short}>" if type_short else "ref"
        if default_short and default_short != "null":
            decls.append(f"${name}:{ref_type}={default_short}")
        else:
            decls.append(f"${name}:{ref_type}")

    return decls


# ── Effect extraction ────────────────────────────────────────────────────────

def _parse_effects(source: str) -> List[str]:
    """Extract useEffect calls into VXL ~ effect lines."""
    effects = []
    # Find useEffect blocks (rough: looks for useEffect( and its deps array)
    # We can't fully parse nested code, so we use heuristics.
    eff_starts = [m.start() for m in re.finditer(r"useEffect\s*\(", source)]
    for start in eff_starts:
        # Find the deps array — scan forward for ], [deps]); pattern
        # Grab a chunk of text after useEffect(
        chunk = source[start : start + 2000]

        # Determine trigger: look for the dependency array
        # Pattern: }, [dep1, dep2]);  or }, []);
        dep_match = re.search(r",\s*\[([^\]]*)\]\s*\)", chunk)
        if dep_match:
            deps_str = dep_match.group(1).strip()
            if not deps_str:
                trigger = "~mount"
            else:
                dep_names = [d.strip() for d in deps_str.split(",") if d.strip()]
                trigger = "~[" + ",".join("$" + d for d in dep_names) + "]"
        else:
            trigger = "~mount"

        # Determine action: look for fetch calls or function calls in the body
        body = chunk[: dep_match.start() if dep_match else 500]
        actions = []
        targets = []

        # fetch() calls
        fetch_calls = re.findall(r"fetch\s*\(\s*[`\"']([^`\"']+)[`\"']", body)
        if fetch_calls:
            actions.append(f"fetch({fetch_calls[0]})")
        # Named function calls that look like data fetchers
        fn_calls = re.findall(r"(?<!\w)(\w+(?:fetch\w*|load\w*|get\w*))\s*\(", body, re.IGNORECASE)
        if not fn_calls:
            fn_calls = re.findall(r"(?<!\w)(fetch\w+|load\w+|get\w+)\s*\(", body, re.IGNORECASE)
        for fn in fn_calls:
            if fn not in actions and fn not in ("fetch",):
                actions.append(fn)

        # Detect setState targets: setXxx(
        set_calls = re.findall(r"(set[A-Z]\w*)\s*\(", body)
        for sc in set_calls:
            # setFoo → $foo
            var_name = sc[3].lower() + sc[4:]
            # Check if there's a transform inside
            targets.append(f"${var_name}")

        action_str = actions[0] if actions else "effect"
        target_str = ",".join(dict.fromkeys(targets)) if targets else ""

        parts = [trigger, action_str]
        if target_str:
            parts.append(target_str)
        effects.append("→".join(parts))

    # setInterval patterns
    interval_matches = re.finditer(
        r"setInterval\s*\(\s*(?:(?:async\s*)?\(\)\s*=>\s*\{?|function\s*\(\)\s*\{)",
        source,
    )
    for m in interval_matches:
        chunk = source[m.start() : m.start() + 1000]
        # Find interval duration
        dur_match = re.search(r",\s*(\d+)\s*\)", chunk)
        dur = dur_match.group(1) if dur_match else "5000"
        # Find what it calls
        fn_match = re.findall(r"(?:fetch|load|get)\w+", chunk[:200])
        action = fn_match[0] if fn_match else "poll"
        effects.append(f"~int({dur})→{action}")

    return effects


# ── JSX extraction ───────────────────────────────────────────────────────────

def _extract_jsx_tree(source: str) -> str:
    """Extract a compressed JSX tree from the return statement."""
    # Find return ( ... ) in the function body
    return_match = re.search(r"return\s*\(", source)
    if not return_match:
        return_match = re.search(r"return\s*<", source)
    if not return_match:
        return ""

    start = return_match.start()
    chunk = source[start : start + 3000]

    # Extract top-level component tags
    components = []
    seen = set()
    for m in re.finditer(r"<(\/?[A-Z]\w*)", chunk):
        tag = m.group(1)
        if tag.startswith("/"):
            tag = "/" + tag[1:]
            if tag[1:] in seen:
                components.append(f"<{tag}>")
        else:
            if tag not in seen:
                components.append(f"<{tag}>")
                seen.add(tag)

    if not components:
        return ""

    # Build a simplified tree — just list unique top-level components
    # Strip closing tags and build compact form
    result_parts = []
    for c in components:
        if not c.startswith("</"):
            name = c[1:-1]
            result_parts.append(f"<{name}/>")

    return "".join(result_parts[:6])  # max 6 components


# ── Syntax codes detection (§3.2) ───────────────────────────────────────────

_SYNTAX_SIGNALS = {
    "tsx": [r"return\s*\(?\s*<", r"<\w+[\s/>]"],
    "hk": [r"use(?:State|Effect|Ref|Memo|Callback|Reducer)\s*[(<]"],
    "ftc": [r"fetch\s*\(", r"useSWR", r"\.then\s*\(", r"await\s+fetch"],
    "st": [r"useState\s*[(<]", r"useReducer\s*\("],
    "eff": [r"useEffect\s*\(", r"useLayoutEffect\s*\("],
    "prp": [r"(?:props|Props)\s*[:{]", r":\s*\w+Props\b"],
    "ctx": [r"useContext\s*\(", r"createContext\s*\("],
    "frm": [r"<form[\s>]", r"onSubmit", r"handleSubmit"],
    "auth": [r"session", r"signIn", r"signOut", r"useAuth", r"getServerSession"],
    "cch": [r"\bcache\s*\(", r"revalidate", r"unstable_cache"],
    "ssr": [r"getServerSideProps", r"getStaticProps"],
    "mut": [r"method:\s*[\"'](?:POST|PUT|DELETE|PATCH)", r"\.(?:post|put|delete|patch)\s*\("],
    "qry": [r"useSearchParams", r"searchParams", r"URLSearchParams"],
    "val": [r"\.parse\s*\(", r"schema\.", r"\.safeParse", r"validate"],
    "err": [r"\bcatch\s*\(", r"ErrorBoundary", r"error\.tsx"],
    "nav": [r"useRouter\s*\(", r"<Link[\s>]", r"redirect\s*\(", r"usePathname"],
    "sty": [r"\bcn\s*\(", r"className=\{", r"clsx\s*\("],
    "tbl": [r"<Table[\s/>]", r"<DataTable", r"column[Dd]ef"],
    "chrt": [r"<Chart", r"Recharts", r"<Line[\s/>]", r"<Bar[\s/>]", r"<Area[\s/>]"],
    "mod": [r"<Dialog[\s/>]", r"<AlertDialog", r"<Modal[\s/>]"],
    "sort": [r"sort(?:Data|By|ed)\b", r"sortState", r"comparator"],
    "flt": [r"filter(?:Data|ed|State)\b", r"predicate"],
    "ws": [r"WebSocket\s*\(", r"EventSource\s*\(", r"SSE"],
    "calc": [r"Math\.", r"\.reduce\s*\(", r"aggregate", r"calculate"],
    "anm": [r"framer-motion", r"motion\.", r"transition", r"animate"],
    "dl": [r"blob", r"download", r"\.csv", r"createObjectURL"],
    "pag": [r"page(?:Size|Number|Index)\b", r"offset.*limit", r"pagination"],
}


def _detect_syntax_codes(source: str) -> List[str]:
    """Scan source for syntax code signals and return matching codes (max 4)."""
    codes = []
    for code, patterns in _SYNTAX_SIGNALS.items():
        for pattern in patterns:
            if re.search(pattern, source, re.IGNORECASE):
                codes.append(code)
                break
        if len(codes) >= 4:
            break
    return codes


# ── Flag detection (§3.4) ───────────────────────────────────────────────────

def _detect_flags(source: str, filename: str, dirpath: str) -> List[str]:
    """Detect structural flags from source and file metadata."""
    flags = []
    name = filename.lower()

    if name in ("page.tsx", "layout.tsx"):
        flags.append("@ENTRY")
    if name == "route.ts":
        flags.append("@API")

    if '"use client"' in source or "'use client'" in source:
        flags.append("@CSR")
    elif name.endswith(".tsx") and "use client" not in source and name not in ("page.tsx",):
        # Server component by default in Next.js app router
        if "useState" not in source and "useEffect" not in source:
            flags.append("@SSR")

    if "async function" in source or "await " in source or ".then(" in source:
        if "@API" in flags or name == "route.ts":
            flags.append("@ASYNC")

    if "force-dynamic" in source or "'force-dynamic'" in source:
        flags.append("@DYN")

    if "runtime" in source and "'edge'" in source:
        flags.append("@EDGE")

    # @PURE: no hooks, no fetch, no side effects in a utility/types file
    ftype = _detect_file_type(filename, dirpath)
    if ftype in ("UT", "TP") and not re.search(r"use(?:State|Effect|Ref)\s*\(", source):
        if "fetch(" not in source:
            flags.append("@PURE")

    return flags[:3]


# ── Wire lines ───────────────────────────────────────────────────────────────


# ── Body extraction (§2.7 — lossless function logic) ────────────────────────

def _extract_function_body(source: str) -> Optional[str]:
    """Extract the main function body (between first `{` after export function and its matching `}`)."""
    # Find the main function declaration
    m = re.search(
        r"export\s+(?:default\s+)?(?:async\s+)?function\s+\w+\s*\([^)]*\)\s*(?::\s*\S+\s*)?\{",
        source,
    )
    if not m:
        return None
    start = m.end()  # index right after the opening brace
    depth = 1
    i = start
    while i < len(source) and depth > 0:
        ch = source[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        elif ch in ('"', "'", "`"):
            # Skip string literals
            quote = ch
            i += 1
            while i < len(source) and source[i] != quote:
                if source[i] == "\\" and quote != "`":
                    i += 1  # skip escaped char
                i += 1
        elif ch == "/" and i + 1 < len(source):
            if source[i + 1] == "/":
                # Skip line comment
                while i < len(source) and source[i] != "\n":
                    i += 1
            elif source[i + 1] == "*":
                i += 2
                while i + 1 < len(source) and not (source[i] == "*" and source[i + 1] == "/"):
                    i += 1
                i += 1  # skip the /
        i += 1
    if depth != 0:
        return None
    return source[start : i - 1]  # exclude the closing brace


def _emit_useeffect_body(
    first_line: str,
    body_lines: List[str],
    out: List[str],
    setters: set,
) -> None:
    """Extract a B:FETCH line from a useEffect body.

    Looks for patterns like:
      fetchFn().then(res => { setA(res); setB(transform(res)); setC(val); });
      const res = await fetchFn(); setA(res); ...
    """
    all_text = first_line + "\n" + "\n".join(body_lines)

    # Helper: extract balanced parenthesized arg from a setter call
    def _extract_setter_calls(text: str) -> List[Tuple[str, str]]:
        """Find all setXxx(...) calls and return (setter_name, full_arg) pairs."""
        results = []
        for m in re.finditer(r"(set[A-Z]\w*)\s*\(", text):
            setter_name = m.group(1)
            start = m.end()  # position right after the (
            depth = 1
            pos = start
            while pos < len(text) and depth > 0:
                if text[pos] == "(":
                    depth += 1
                elif text[pos] == ")":
                    depth -= 1
                pos += 1
            arg = text[start:pos - 1].strip()
            results.append((setter_name, arg))
        return results

    # Pattern: fn().then(res => { ... })  or  fn(...).then(res => { ... })
    fetch_m = re.search(r"(\w+)\s*\(([^)]*)\)\s*\.then\s*\(\s*(?:(\w+)|.+?)\s*=>\s*\{?", all_text)
    if fetch_m:
        fn_name = fetch_m.group(1)
        fn_args = fetch_m.group(2).strip()
        res_name = fetch_m.group(3) or "res"
        # Find all setState calls in the body
        targets: List[str] = []
        for setter_name, setter_arg in _extract_setter_calls(all_text):
            var_name = setter_name[3].lower() + setter_name[4:]
            if setter_arg == res_name:
                targets.append(f"${var_name}")
            elif re.match(r"\w+\(" + re.escape(res_name) + r"\)$", setter_arg):
                # transform(res) → just the transform name
                transform = setter_arg.split("(")[0]
                targets.append(f"${var_name}({transform})")
            else:
                # Literal value like false, null, etc.
                targets.append(f"${var_name}({setter_arg})")
        call_str = f"{fn_name}({fn_args})" if fn_args else f"{fn_name}()"
        if targets:
            out.append(f"B:FETCH {call_str}→{','.join(targets)}")
        return

    # Pattern: await fn()
    await_m = re.search(r"(?:const\s+(\w+)\s*=\s*)?await\s+(\w+)\s*\(([^)]*)\)", all_text)
    if await_m:
        res_name = await_m.group(1) or "res"
        fn_name = await_m.group(2)
        fn_args = await_m.group(3).strip()
        targets = []
        for setter_name, setter_arg in _extract_setter_calls(all_text):
            var_name = setter_name[3].lower() + setter_name[4:]
            if setter_arg == res_name:
                targets.append(f"${var_name}")
            elif re.match(r"\w+\(" + re.escape(res_name) + r"\)$", setter_arg):
                transform = setter_arg.split("(")[0]
                targets.append(f"${var_name}({transform})")
            else:
                targets.append(f"${var_name}({setter_arg})")
        call_str = f"{fn_name}({fn_args})" if fn_args else f"{fn_name}()"
        if targets:
            out.append(f"B:AFETCH {call_str}→{','.join(targets)}")
        return


def _compress_body_stmts(body: str, state_names: List[str]) -> List[str]:
    """Compress a function body into B: lines using pattern codes (§2.7)."""
    lines: List[str] = []
    # Build a set of known state setter names
    setters = {f"set{n[0].upper()}{n[1:]}" for n in state_names if n}

    # Normalise: strip leading/trailing whitespace per line, skip blanks
    raw_lines = [l.strip() for l in body.splitlines() if l.strip()]

    # Skip lines already captured by structural VXL lines (useState, useEffect decls)
    filtered: List[str] = []
    effect_body_lines: List[str] = []  # B: lines extracted from useEffect bodies
    in_useeffect = False
    ue_paren_depth = 0  # parenthesis depth for useEffect(...)
    ue_body_lines: List[str] = []  # collect useEffect body for B:FETCH extraction
    for rl in raw_lines:
        # Skip useState / useRef declarations (already in $-lines)
        if re.match(r"const\s+\[.*\]\s*=\s*use(?:State|Reducer)\b", rl):
            continue
        if re.match(r"const\s+\w+\s*=\s*useRef\b", rl):
            continue
        # Capture useEffect blocks — extract inner fetcher logic as B:FETCH
        if re.match(r"useEffect\s*\(", rl):
            in_useeffect = True
            ue_paren_depth = 0
            ue_body_lines = []
            for ch in rl:
                if ch == "(":
                    ue_paren_depth += 1
                elif ch == ")":
                    ue_paren_depth -= 1
            if ue_paren_depth <= 0:
                in_useeffect = False
                _emit_useeffect_body(rl, ue_body_lines, effect_body_lines, setters)
            continue
        if in_useeffect:
            ue_body_lines.append(rl)
            for ch in rl:
                if ch == "(":
                    ue_paren_depth += 1
                elif ch == ")":
                    ue_paren_depth -= 1
            if ue_paren_depth <= 0:
                in_useeffect = False
                _emit_useeffect_body("", ue_body_lines, effect_body_lines, setters)
            continue
        filtered.append(rl)

    # Start with B:FETCH lines from useEffect bodies
    lines.extend(effect_body_lines)

    i = 0
    while i < len(filtered):
        stmt = filtered[i]

        # ── B:MEMO — const x = useMemo(() => expr, [deps]) ──
        memo_m = re.match(
            r"const\s+(\w+)\s*=\s*useMemo\s*\(\s*\(\)\s*=>\s*(.+?)\s*,\s*\[([^\]]*)\]\s*\)\s*;?$",
            stmt,
        )
        if memo_m:
            name, expr, deps = memo_m.group(1), memo_m.group(2), memo_m.group(3)
            lines.append(f"B:MEMO {name}={expr},[{deps}]")
            i += 1
            continue

        # ── B:CB — const x = useCallback((params) => ..., [deps]) ──
        cb_m = re.match(
            r"const\s+(\w+)\s*=\s*useCallback\s*\(\s*\(([^)]*)\)\s*=>\s*(.+?)\s*,\s*\[([^\]]*)\]\s*\)\s*;?$",
            stmt,
        )
        if cb_m:
            name = cb_m.group(1)
            params = cb_m.group(2)
            body_expr = cb_m.group(3)
            deps = cb_m.group(4)
            lines.append(f"B:CB {name}({params})→{body_expr},[{deps}]")
            i += 1
            continue

        # ── B:CB — multi-line useCallback ──
        cb_ml = re.match(r"const\s+(\w+)\s*=\s*useCallback\s*\(\s*\(([^)]*)\)\s*=>\s*\{\s*$", stmt)
        if cb_ml:
            name = cb_ml.group(1)
            params = cb_ml.group(2)
            inner_lines = []
            i += 1
            depth = 1
            deps = ""
            while i < len(filtered) and depth > 0:
                ln = filtered[i]
                for ch in ln:
                    if ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                if depth <= 0:
                    dep_m = re.search(r"\[([^\]]*)\]", ln)
                    if dep_m:
                        deps = dep_m.group(1)
                    break
                inner_lines.append(ln)
                i += 1
            inner_body = _compress_body_stmts("\n".join(inner_lines), state_names)
            if inner_body:
                lines.append(f"B:CB {name}({params})→{{}},[{deps}]")
                lines.extend(inner_body)
                lines.append("B:END")
            else:
                lines.append(f"B:CB {name}({params})→{{}},[{deps}]")
            i += 1
            continue

        # ── B:DESTRUCT — const { a, b } = expr ──
        destr_m = re.match(r"const\s+\{([^}]+)\}\s*=\s*(.+?)\s*;?$", stmt)
        if destr_m:
            names = destr_m.group(1).strip()
            expr = destr_m.group(2).strip()
            lines.append(f"B:DESTRUCT {{{names}}}={expr}")
            i += 1
            continue

        # ── B:GUARD — if (cond) return ...; ──
        guard_m = re.match(r"if\s*\((.+)\)\s+return\s*(.*?)\s*;?$", stmt)
        if guard_m:
            cond = guard_m.group(1).strip()
            val = guard_m.group(2).strip()
            if val:
                lines.append(f"B:GUARD {cond}→return {val}")
            else:
                lines.append(f"B:GUARD {cond}→return")
            i += 1
            continue

        # ── B:IF / B:ELIF / B:ELSE — block conditionals ──
        if_m = re.match(r"(if|else\s+if|else)\s*\(?([^{]*?)\)?\s*\{\s*$", stmt)
        if if_m:
            keyword = if_m.group(1).strip()
            cond = if_m.group(2).strip() if if_m.group(2) else ""
            inner_lines = []
            i += 1
            depth = 1
            while i < len(filtered) and depth > 0:
                ln = filtered[i]
                for ch in ln:
                    if ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                if depth <= 0:
                    break
                inner_lines.append(ln)
                i += 1
            inner_compressed = _compress_body_stmts("\n".join(inner_lines), state_names)
            if keyword == "if":
                code = "IF"
            elif "else if" in keyword:
                code = "ELIF"
            else:
                code = "ELSE"
            if cond:
                lines.append(f"B:{code} {cond}→{{}}")
            else:
                lines.append(f"B:{code}→{{}}")
            lines.extend(inner_compressed)
            lines.append("B:END")
            i += 1
            continue

        # ── B:TRY / B:CATCH / B:FINALLY ──
        try_m = re.match(r"try\s*\{\s*$", stmt)
        if try_m:
            inner_lines = []
            i += 1
            depth = 1
            while i < len(filtered) and depth > 0:
                ln = filtered[i]
                for ch in ln:
                    if ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                if depth <= 0:
                    break
                inner_lines.append(ln)
                i += 1
            inner_compressed = _compress_body_stmts("\n".join(inner_lines), state_names)
            lines.append("B:TRY {}")
            lines.extend(inner_compressed)
            # Check for catch/finally
            i += 1
            if i < len(filtered):
                catch_m = re.match(r"\}?\s*catch\s*\((\w+)\)\s*\{\s*$", filtered[i])
                if not catch_m:
                    catch_m = re.match(r"catch\s*\((\w+)\)\s*\{\s*$", filtered[i])
                if catch_m:
                    err_name = catch_m.group(1)
                    catch_lines = []
                    i += 1
                    depth = 1
                    while i < len(filtered) and depth > 0:
                        ln = filtered[i]
                        for ch in ln:
                            if ch == "{":
                                depth += 1
                            elif ch == "}":
                                depth -= 1
                        if depth <= 0:
                            break
                        catch_lines.append(ln)
                        i += 1
                    catch_compressed = _compress_body_stmts("\n".join(catch_lines), state_names)
                    lines.append(f"B:CATCH({err_name})→{{}}")
                    lines.extend(catch_compressed)
                    i += 1
                # finally
                if i < len(filtered):
                    fin_m = re.match(r"\}?\s*finally\s*\{\s*$", filtered[i])
                    if not fin_m:
                        fin_m = re.match(r"finally\s*\{\s*$", filtered[i])
                    if fin_m:
                        fin_lines = []
                        i += 1
                        depth = 1
                        while i < len(filtered) and depth > 0:
                            ln = filtered[i]
                            for ch in ln:
                                if ch == "{":
                                    depth += 1
                                elif ch == "}":
                                    depth -= 1
                            if depth <= 0:
                                break
                            fin_lines.append(ln)
                            i += 1
                        fin_compressed = _compress_body_stmts("\n".join(fin_lines), state_names)
                        lines.append("B:FINALLY {}")
                        lines.extend(fin_compressed)
                        i += 1
            lines.append("B:END")
            continue

        # ── B:HANDLE — const name = (params) => { ... } ──
        handle_m = re.match(
            r"const\s+(\w+)\s*=\s*(?:async\s+)?\(([^)]*)\)\s*=>\s*\{\s*$", stmt
        )
        if handle_m:
            name = handle_m.group(1)
            params = handle_m.group(2)
            inner_lines = []
            i += 1
            depth = 1
            while i < len(filtered) and depth > 0:
                ln = filtered[i]
                for ch in ln:
                    if ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                if depth <= 0:
                    break
                inner_lines.append(ln)
                i += 1
            inner_compressed = _compress_body_stmts("\n".join(inner_lines), state_names)
            is_async = "async" in stmt
            prefix = "async " if is_async else ""
            lines.append(f"B:HANDLE {prefix}{name}({params})→{{}}")
            lines.extend(inner_compressed)
            lines.append("B:END")
            i += 1
            continue

        # ── B:HANDLE — single-line arrow: const name = (params) => expr; ──
        handle_sl = re.match(
            r"const\s+(\w+)\s*=\s*(?:async\s+)?\(([^)]*)\)\s*=>\s*(.+?)\s*;?$", stmt
        )
        if handle_sl:
            name = handle_sl.group(1)
            params = handle_sl.group(2)
            expr = handle_sl.group(3).rstrip(";").strip()
            lines.append(f"B:HANDLE {name}({params})→{expr}")
            i += 1
            continue

        # ── B:AWAIT — const x = await fn(...) ──
        await_m = re.match(r"const\s+(\w+)\s*=\s*await\s+(.+?)\s*;?$", stmt)
        if await_m:
            name = await_m.group(1)
            expr = await_m.group(2).strip()
            lines.append(f"B:AWAIT ${name}={expr}")
            i += 1
            continue

        # ── B:TOAST — toast(...) ──
        toast_m = re.match(r"toast(?:\.(\w+))?\s*\((.+)\)\s*;?$", stmt)
        if toast_m:
            variant = toast_m.group(1) or ""
            msg = toast_m.group(2).strip()
            if variant:
                lines.append(f'B:TOAST {msg},"{variant}"')
            else:
                lines.append(f"B:TOAST {msg}")
            i += 1
            continue

        # ── B:NAV — router.push/replace ──
        nav_m = re.match(r"router\.(push|replace)\s*\((.+)\)\s*;?$", stmt)
        if nav_m:
            method = nav_m.group(1)
            path_expr = nav_m.group(2).strip()
            if method == "replace":
                lines.append(f"B:NAV.replace {path_expr}")
            else:
                lines.append(f"B:NAV {path_expr}")
            i += 1
            continue

        # ── B:LOG — console.log(...) ──
        log_m = re.match(r"console\.(?:log|warn|error|info)\s*\((.+)\)\s*;?$", stmt)
        if log_m:
            lines.append(f"B:LOG {log_m.group(1).strip()}")
            i += 1
            continue

        # ── B:ASSIGN — setState(value) ──
        assign_m = re.match(r"(set[A-Z]\w*)\s*\((.+)\)\s*;?$", stmt)
        if assign_m:
            setter = assign_m.group(1)
            val = assign_m.group(2).strip()
            var_name = setter[3].lower() + setter[4:]
            lines.append(f"B:ASSIGN ${var_name}({val})")
            i += 1
            continue

        # ── B:SPREAD — setState(prev => ({...prev, key: val})) ──
        spread_m = re.match(
            r"(set[A-Z]\w*)\s*\(\s*(?:\w+\s*=>\s*)?(?:\(\s*)?\{\.\.\.(\w+)\s*,\s*(.+?)\s*\}(?:\s*\))?\s*\)\s*;?$",
            stmt,
        )
        if spread_m:
            setter = spread_m.group(1)
            prev = spread_m.group(2)
            rest = spread_m.group(3).strip()
            var_name = setter[3].lower() + setter[4:]
            lines.append(f"B:SPREAD ${var_name}←{{...{prev},{rest}}}")
            i += 1
            continue

        # ── B:LET — const x = expr ──
        let_m = re.match(r"(?:const|let|var)\s+(\w+)(?::([^=]+))?\s*=\s*(.+?)\s*;?$", stmt)
        if let_m:
            name = let_m.group(1)
            type_ann = let_m.group(2)
            expr = let_m.group(3).strip()
            if type_ann:
                type_short = _shorten_type(type_ann.strip())
                lines.append(f"B:LET {name}:{type_short}={expr}")
            else:
                lines.append(f"B:LET {name}={expr}")
            i += 1
            continue

        # ── B:RET — return ( multiline JSX ) ──
        ret_paren = re.match(r"return\s*\(\s*$", stmt)
        if ret_paren:
            jsx_lines = []
            i += 1
            depth = 1
            while i < len(filtered):
                ln = filtered[i]
                for ch in ln:
                    if ch == "(":
                        depth += 1
                    elif ch == ")":
                        depth -= 1
                if depth <= 0:
                    break
                jsx_lines.append(ln)
                i += 1
            jsx_content = " ".join(l.strip() for l in jsx_lines)
            # Compress JSX conditionals inline
            jsx_content = _compress_jsx_inline(jsx_content)
            lines.append(f"B:RET {jsx_content}")
            i += 1
            continue

        # ── B:RET — return expr ──
        ret_m = re.match(r"return\s+(.+?)\s*;?$", stmt)
        if ret_m:
            expr = ret_m.group(1).strip()
            lines.append(f"B:RET {expr}")
            i += 1
            continue

        # ── B:CALL — plain function call ──
        call_m = re.match(r"(?:await\s+)?(\w[\w.]*)\s*\((.*)?\)\s*;?$", stmt)
        if call_m:
            fn_name = call_m.group(1)
            args = call_m.group(2) or ""
            if "await" in stmt:
                lines.append(f"B:AWAIT ${fn_name}={fn_name}({args})")
            else:
                lines.append(f"B:CALL {fn_name}({args})")
            i += 1
            continue

        # ── B:RAW — fallback ──
        lines.append(f"B:RAW {stmt}")
        i += 1

    return lines


def _compress_jsx_inline(jsx: str) -> str:
    """Compress JSX patterns inline: ternary conditionals, map renders."""
    # Compress {cond ? <A/> : <B/>} into B:JSXCOND markers — but keep inline in the RET
    # This is already fairly compressed; just strip excessive whitespace
    jsx = re.sub(r"\s+", " ", jsx).strip()
    return jsx

def _build_wires(filename: str, imports: List[Dict[str, str]]) -> List[str]:
    """Generate W: wire lines from imports to local files."""
    wires = []
    for imp in imports:
        path = imp["path"]
        if path.startswith("./") or path.startswith("../"):
            # Local import — worth wiring
            target_base = path.split("/")[-1]
            # Guess extension
            if not any(target_base.endswith(ext) for ext in (".ts", ".tsx", ".js", ".jsx", ".css")):
                target_base += ".ts"
            names = imp["named"]
            if imp["default"]:
                names = [imp["default"]] + names
            if names:
                wires.append(f"W:{filename}→{target_base}|{','.join(names)}")
    return wires


# ── Route signature extraction ───────────────────────────────────────────────

def _extract_route_signatures(source: str) -> List[str]:
    """Extract HTTP method handlers from API route files."""
    sigs = []
    methods = re.findall(
        r"export\s+(?:async\s+)?function\s+(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s*\(",
        source,
    )
    for method in methods:
        sigs.append(f"{method}")
    return sigs


# ── Interface/type extraction ────────────────────────────────────────────────

def _extract_interfaces(source: str) -> List[str]:
    """Extract interface and type definitions as compact VXL lines."""
    lines = []
    # Match interface Foo { ... } — grab fields
    for m in re.finditer(
        r"(?:export\s+)?interface\s+(\w+)\s*\{([^}]*)\}", source, re.DOTALL
    ):
        name = m.group(1)
        body = m.group(2).strip()
        fields = []
        for field_match in re.finditer(r"(\w+)\??\s*:\s*([^;,\n]+)", body):
            fname = field_match.group(1)
            ftype = _shorten_type(field_match.group(2).strip())
            fields.append(f"{fname}:{ftype}")
        if fields:
            lines.append(f"{name}{{{','.join(fields)}}}")

    # Match type Foo = "a" | "b"
    for m in re.finditer(
        r"(?:export\s+)?type\s+(\w+)\s*=\s*([^;]+);", source
    ):
        name = m.group(1)
        value = m.group(2).strip()
        if len(value) < 60:
            lines.append(f"{name}={value}")

    return lines


# ── Function signature extraction ────────────────────────────────────────────

def _extract_function_sigs(source: str) -> List[str]:
    """Extract exported function signatures as VXL lines."""
    sigs = []
    for m in re.finditer(
        r"export\s+(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)\s*(?::\s*([^\s{]+))?",
        source,
    ):
        name = m.group(1)
        # Skip component functions (uppercase first letter, likely handled elsewhere)
        if name[0].isupper() and name not in ("GET", "POST", "PUT", "DELETE", "PATCH"):
            continue
        params = m.group(2).strip()
        ret = m.group(3) or ""
        # Compress params
        param_parts = []
        for p in re.finditer(r"(\w+)\s*:\s*([^,]+)", params):
            pname = p.group(1)
            ptype = _shorten_type(p.group(2).strip())
            param_parts.append(f"{pname}:{ptype}")
        params_str = ",".join(param_parts)
        ret_str = _shorten_type(ret) if ret else ""
        if ret_str:
            sigs.append(f"{name}({params_str})→{ret_str}")
        elif params_str:
            sigs.append(f"{name}({params_str})")
    return sigs


# ── Main encoder ─────────────────────────────────────────────────────────────

def encode(source: str, filepath: str, base_dir: str = "") -> str:
    """
    Encode a TypeScript/TSX source file into a VXL block.

    Args:
        source: The full source code string.
        filepath: Path to the source file (used for header line).
        base_dir: Base directory to strip from path for wing-relative paths.

    Returns:
        VXL-encoded block string.
    """
    p = Path(filepath)
    filename = p.name
    dirpath = str(p.parent)

    # Build wing-relative path
    if base_dir:
        try:
            rel = p.parent.relative_to(base_dir)
            wing_path = str(rel)
        except ValueError:
            wing_path = dirpath
    else:
        wing_path = dirpath

    # Normalise separators
    wing_path = wing_path.replace(os.sep, "/")
    if wing_path == ".":
        wing_path = "app"

    file_type = _detect_file_type(filename, dirpath)
    imports = _parse_imports(source)

    lines: List[str] = []

    # 1. Header line
    lines.append(f"{wing_path}|{filename}|{file_type}")

    # 2. Export / Import line
    export_str, is_default = _parse_exports(source)
    import_str = _build_import_field(imports)

    exp_imp_parts = []
    if export_str:
        exp_imp_parts.append(export_str)
    if import_str:
        exp_imp_parts.append("<<" + import_str)
    if exp_imp_parts:
        lines.append("|".join(exp_imp_parts))

    # For type/utility files, emit interface/function lines instead of state/effects
    if file_type in ("TP",):
        ifaces = _extract_interfaces(source)
        lines.extend(ifaces)
    elif file_type in ("UT", "LIB", "IDX"):
        fn_sigs = _extract_function_sigs(source)
        lines.extend(fn_sigs)
        ifaces = _extract_interfaces(source)
        lines.extend(ifaces)

    # For route files, emit route signatures
    if file_type == "RT":
        route_methods = _extract_route_signatures(source)
        if route_methods:
            method_str = ",".join(route_methods)
            lines.append(f"{method_str}→json")

    # 3. State line (for components/pages)
    if file_type in ("PG", "CMP", "HK", "CTX"):
        state_decls = _parse_state(source)
        if state_decls:
            # Group into lines of max 4 declarations
            for i in range(0, len(state_decls), 4):
                batch = state_decls[i : i + 4]
                lines.append("|".join(batch))

    # 4. Effect lines
    if file_type in ("PG", "CMP", "HK", "CTX"):
        effects = _parse_effects(source)
        for eff in effects:
            lines.append(eff)

    # 5. Render / signature line with syntax codes and flags
    syntax_codes = _detect_syntax_codes(source)
    flags = _detect_flags(source, filename, dirpath)

    if file_type in ("PG", "CMP", "CTX"):
        jsx = _extract_jsx_tree(source)
        tail_parts = []
        if jsx:
            tail_parts.append(jsx)
        if syntax_codes:
            tail_parts.append("+".join(syntax_codes))
        if flags:
            tail_parts.append("+".join(flags))
        if tail_parts:
            lines.append("|".join(tail_parts))
    else:
        # Non-component: just codes and flags
        tail_parts = []
        if syntax_codes:
            tail_parts.append("+".join(syntax_codes))
        if flags:
            tail_parts.append("+".join(flags))
        if tail_parts:
            lines.append("|".join(tail_parts))

    # 6. Wire lines
    wires = _build_wires(filename, imports)

    # 7. Body lines (§2.7 — lossless function logic)
    state_names = [
        m.group(1)
        for m in _USESTATE_RE.finditer(source)
    ] + [
        m.group(1)
        for m in _USEREF_RE.finditer(source)
    ]
    body_text = _extract_function_body(source)
    body_lines: List[str] = []
    if body_text:
        body_lines = _compress_body_stmts(body_text, state_names)

    # Assemble: structural lines, body lines, wire lines
    if body_lines:
        lines.extend(body_lines)
    lines.extend(wires)

    return "\n".join(lines)


def encode_file(filepath: str, base_dir: str = "") -> str:
    """Read a file and encode it to VXL."""
    with open(filepath, "r", encoding="utf-8") as f:
        source = f.read()
    return encode(source, filepath, base_dir)


def encode_directory(dirpath: str, base_dir: str = "") -> str:
    """Encode all .ts/.tsx files in a directory tree into a multi-block VXL document."""
    blocks = []
    root = Path(dirpath)
    if not base_dir:
        base_dir = str(root)

    for fpath in sorted(root.rglob("*")):
        if fpath.suffix in (".ts", ".tsx") and "node_modules" not in str(fpath):
            try:
                block = encode_file(str(fpath), base_dir)
                blocks.append(block)
            except Exception as e:
                blocks.append(f"# ERROR encoding {fpath}: {e}")

    return "\n---\n".join(blocks)


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="VXL Encoder — Compile TypeScript/TSX source to VXL dialect"
    )
    parser.add_argument("path", help="Source file or directory to encode")
    parser.add_argument(
        "--base", default="", help="Base directory to strip for wing-relative paths"
    )
    parser.add_argument(
        "-o", "--output", default="", help="Output file (default: stdout)"
    )
    args = parser.parse_args()

    target = Path(args.path)
    if target.is_dir():
        result = encode_directory(str(target), args.base)
    elif target.is_file():
        result = encode_file(str(target), args.base)
    else:
        print(f"Error: {args.path} not found", file=sys.stderr)
        sys.exit(1)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(result)
        print(f"Wrote VXL to {args.output}", file=sys.stderr)
    else:
        print(result)


if __name__ == "__main__":
    main()
