#!/usr/bin/env python3
"""
VXL Decoder — VXL → Source (TS/TSX)
====================================

Reads a VXL block and expands it into a TypeScript or TSX source file.
Body lines (B:) make the output lossless — full function logic is reconstructed.
See docs/lang.md for the full VXL specification.

Usage:
    python -m vxl.decoder input.vxl
    python -m vxl.decoder input.vxl -o output_dir/
    echo "app/strat|page.tsx|PG" | python -m vxl.decoder -
"""

import re
import sys
import os
from pathlib import Path
from typing import List, Dict, Optional, Tuple


# ── Import expansion (reverse of §5) ────────────────────────────────────────

_UI_COMPONENT_MAP = {
    "btn": "button",
    "flt": "filter",
    "nav": "navigation",
}

_TYPE_EXPAND = {
    "str": "string",
    "num": "number",
    "b": "boolean",
    "fn": "Function",
    "json": "any",
}


def _expand_type(t: str) -> str:
    """Expand VXL type shorthands back to TypeScript types."""
    t = t.strip()
    if not t:
        return "any"

    # R<K,V> → Record<K,V>
    m = re.match(r"R<(.+),(.+)>", t)
    if m:
        return f"Record<{_expand_type(m.group(1))}, {_expand_type(m.group(2))}>"

    # P<T> → Promise<T>
    m = re.match(r"P<(.+)>", t)
    if m:
        return f"Promise<{_expand_type(m.group(1))}>"

    # ref<T> → kept as-is (handled at state level)
    m = re.match(r"ref<(.+)>", t)
    if m:
        return _expand_type(m.group(1))

    # T? → T | null
    if t.endswith("?"):
        inner = t[:-1]
        return f"{_expand_type(inner)} | null"

    # T[] → keep as-is after expanding T
    if t.endswith("[]"):
        inner = t[:-2]
        expanded = _expand_type(inner)
        return f"{expanded}[]"

    return _TYPE_EXPAND.get(t, t)


def _expand_import_path(module: str) -> str:
    """Expand compressed import path back to full path."""
    # ui{card} → @/components/ui/card
    m = re.match(r"ui\{(.+)\}", module)
    if m:
        name = m.group(1)
        name = _UI_COMPONENT_MAP.get(name, name)
        return f"@/components/ui/{name}"

    # cmp{badge-led} → @/components/badge-led
    m = re.match(r"cmp\{(.+)\}", module)
    if m:
        name = m.group(1)
        name = _UI_COMPONENT_MAP.get(name, name)
        return f"@/components/{name}"

    # cfg/types → @/config/types
    if module.startswith("cfg/"):
        return "@/config/" + module[4:]

    # lib/vortex → @/lib/vortex
    if module.startswith("lib/") and not module.startswith("./"):
        return "@/" + module

    # radix/icons → @radix-ui/react-icons
    if module.startswith("radix/"):
        return "@radix-ui/react-" + module[6:]

    return module


# ── Line parsers ─────────────────────────────────────────────────────────────

def _parse_header(line: str) -> Dict[str, str]:
    """Parse a VXL header line: PATH|FILENAME|TYPE"""
    parts = line.split("|")
    return {
        "path": parts[0] if len(parts) > 0 else "",
        "filename": parts[1] if len(parts) > 1 else "",
        "type": parts[2] if len(parts) > 2 else "",
    }


def _parse_export_import(line: str) -> Tuple[Dict, List[Dict]]:
    """Parse >>EXPORTS|<<IMPORTS line."""
    exports = {"default": "", "named": []}
    imports = []

    parts = line.split("|")
    for part in parts:
        part = part.strip()
        if part.startswith(">>"):
            exp_str = part[2:]
            if exp_str.startswith("{") and exp_str.endswith("}"):
                exports["named"] = [n.strip() for n in exp_str[1:-1].split(",") if n.strip()]
            elif ":" in exp_str and not exp_str.startswith("{"):
                # method:name like POST:handler or metadata:{title:...}
                exports["default"] = exp_str
            else:
                exports["default"] = exp_str
        elif part.startswith("<<"):
            imp_str = part[2:]
            # Split by comma, but respect braces
            current_imports = _split_imports(imp_str)
            for imp in current_imports:
                imports.append(_parse_single_import(imp))

    return exports, imports


def _split_imports(s: str) -> List[str]:
    """Split comma-separated imports respecting braces."""
    result = []
    depth = 0
    current = ""
    for ch in s:
        if ch == "{":
            depth += 1
            current += ch
        elif ch == "}":
            depth -= 1
            current += ch
        elif ch == "," and depth == 0:
            if current.strip():
                result.append(current.strip())
            current = ""
        else:
            current += ch
    if current.strip():
        result.append(current.strip())
    return result


def _parse_single_import(s: str) -> Dict[str, str]:
    """Parse a single import item like react{useState,useEffect} or ./api."""
    m = re.match(r"^([^{]+)\{([^}]+)\}$", s)
    if m:
        module = m.group(1).strip()
        named = [n.strip() for n in m.group(2).split(",") if n.strip()]
        # For ui{} and cmp{} the braces hold component names (each → separate import)
        if module in ("ui", "cmp"):
            full_path = _expand_import_path(f"{module}{{{m.group(2)}}}")
            return {"module": module, "named": named, "path": full_path, "kind": "multi-ui"}
        # For everything else (react{useState}, ./api{fetch}, etc.) braces are named imports
        full_path = _expand_import_path(module)
        return {"module": module, "named": named, "path": full_path, "kind": "named"}
    # Plain module
    full_path = _expand_import_path(s)
    return {"module": s, "named": [], "path": full_path, "kind": "default"}


def _parse_state_decl(decl: str) -> Dict[str, str]:
    """Parse a single $name:Type=default declaration."""
    decl = decl.strip()
    if not decl.startswith("$"):
        return {}
    decl = decl[1:]  # strip $

    name = ""
    type_str = ""
    default = ""

    # name:Type=value
    m = re.match(r"(\w+):(.+?)=(.+)$", decl)
    if m:
        name = m.group(1)
        type_str = m.group(2)
        default = m.group(3)
    else:
        m = re.match(r"(\w+):(.+)$", decl)
        if m:
            name = m.group(1)
            type_str = m.group(2)
        else:
            m = re.match(r"(\w+)=(.+)$", decl)
            if m:
                name = m.group(1)
                default = m.group(2)
            else:
                name = decl

    return {"name": name, "type": type_str, "default": default}


def _parse_effect(line: str) -> Dict[str, str]:
    """Parse ~trigger→action→$targets into structured dict."""
    line = line.strip()
    if not line.startswith("~"):
        return {}
    line = line[1:]  # strip ~

    parts = line.split("→")
    trigger = parts[0] if len(parts) > 0 else "mount"
    action = parts[1] if len(parts) > 1 else ""
    targets = parts[2] if len(parts) > 2 else ""

    return {"trigger": trigger, "action": action, "targets": targets}


# ── Code generators ─────────────────────────────────────────────────────────

def _gen_imports(imports: List[Dict]) -> List[str]:
    """Generate import statements from parsed imports."""
    lines = []
    for imp in imports:
        if imp["kind"] == "multi-ui":
            # Each named item is a separate UI component import
            for name in imp["named"]:
                expanded_name = _UI_COMPONENT_MAP.get(name, name)
                pascal = _to_pascal(expanded_name)
                path = f"@/components/ui/{expanded_name}"
                lines.append(f'import {{ {pascal} }} from "{path}";')
        elif imp["kind"] == "named" and imp["named"]:
            # Skip react — already handled above with deduplication
            if imp.get("module") == "react":
                continue
            path = imp["path"]
            names = ", ".join(imp["named"])
            lines.append(f'import {{ {names} }} from "{path}";')
        elif imp["kind"] == "default":
            path = imp["path"]
            if imp["module"] == "react":
                continue  # handled above with hooks dedup
            if imp["module"] in ("next", "sonner"):
                lines.append(f'import {imp["module"]} from "{path}";')
            else:
                lines.append(f'import "{path}";')
    return lines


def _to_pascal(s: str) -> str:
    """Convert kebab-case to PascalCase."""
    return "".join(word.capitalize() for word in s.split("-"))


def _to_camel(s: str) -> str:
    """Convert to camelCase for setter name."""
    return s[0].upper() + s[1:]


def _gen_state(state: Dict) -> str:
    """Generate a useState or useRef declaration."""
    name = state["name"]
    type_str = state.get("type", "")
    default = state.get("default", "")

    is_ref = type_str.startswith("ref<") or type_str == "ref"
    if is_ref:
        inner = ""
        m = re.match(r"ref<(.+)>", type_str)
        if m:
            inner = _expand_type(m.group(1))
        default_val = default if default else "null"
        if inner:
            return f"  const {name} = useRef<{inner}>({default_val});"
        return f"  const {name} = useRef({default_val});"

    expanded_type = _expand_type(type_str) if type_str else ""
    default_val = default if default else _default_for_type(expanded_type)
    setter = "set" + _to_camel(name)

    if expanded_type:
        return f"  const [{name}, {setter}] = useState<{expanded_type}>({default_val});"
    return f"  const [{name}, {setter}] = useState({default_val});"


def _default_for_type(t: str) -> str:
    """Provide a sensible default value for a type if none given."""
    if not t:
        return "undefined"
    if t.endswith("[]"):
        return "[]"
    if t.endswith("| null"):
        return "null"
    if t == "boolean":
        return "false"
    if t == "string":
        return '""'
    if t == "number":
        return "0"
    return "undefined"


def _gen_effect(effect: Dict) -> List[str]:
    """Generate a useEffect block from parsed effect."""
    trigger = effect.get("trigger", "mount")
    action = effect.get("action", "")
    targets = effect.get("targets", "")

    lines = []

    # Determine deps
    if trigger == "mount":
        deps = "[]"
    elif trigger.startswith("["):
        # Parse [$x,$y] → [x, y]
        inner = trigger[1:-1]
        dep_names = [d.strip().lstrip("$") for d in inner.split(",") if d.strip()]
        deps = "[" + ", ".join(dep_names) + "]"
    elif trigger.startswith("int("):
        # setInterval
        m = re.match(r"int\((\d+)\)", trigger)
        interval = m.group(1) if m else "5000"
        lines.append(f"  useEffect(() => {{")
        lines.append(f"    const id = setInterval(() => {{")
        if action:
            lines.append(f"      {action}();")
        lines.append(f"    }}, {interval});")
        lines.append(f"    return () => clearInterval(id);")
        lines.append(f"  }}, []);")
        return lines
    else:
        deps = "[]"

    # Build the effect body
    lines.append(f"  useEffect(() => {{")
    if action and targets:
        # Parse targets: $data,$totals(calcTotals)
        target_parts = re.findall(r"\$(\w+)(?:\((\w+)\))?", targets)
        if len(target_parts) == 1:
            tname, transform = target_parts[0]
            setter = "set" + _to_camel(tname)
            if transform:
                lines.append(f"    {action}().then((res) => {setter}({transform}(res)));")
            else:
                lines.append(f"    {action}().then({setter});")
        elif target_parts:
            lines.append(f"    {action}().then((res) => {{")
            for tname, transform in target_parts:
                setter = "set" + _to_camel(tname)
                if transform:
                    lines.append(f"      {setter}({transform}(res));")
                else:
                    lines.append(f"      {setter}(res);")
            lines.append(f"    }});")
        else:
            lines.append(f"    {action}();")
    elif action:
        lines.append(f"    {action}();")
    else:
        lines.append(f"    // TODO: implement effect")
    lines.append(f"  }}, {deps});")
    return lines


# ── Body line expansion (§2.7 — lossless) ───────────────────────────────────

_JS_LITERALS = frozenset({"true", "false", "null", "undefined", "NaN", "Infinity"})


def _is_func_name(s: str) -> bool:
    """Return True if *s* looks like a function name (not a literal value)."""
    if s in _JS_LITERALS:
        return False
    # Numbers, quoted strings, template literals are not function names
    if re.match(r'^[-+]?\d|^["\']|^`', s):
        return False
    return bool(re.match(r"[a-zA-Z_]\w*$", s))


def _expand_body_lines(body_lines: List[str], indent: str = "  ") -> List[str]:
    """Expand B: body lines into TypeScript source lines."""
    out: List[str] = []
    i = 0
    while i < len(body_lines):
        line = body_lines[i]
        if not line.startswith("B:"):
            i += 1
            continue
        rest = line[2:]  # strip "B:"

        # ── B:END — scope terminator ──
        if rest == "END":
            i += 1
            continue

        # ── B:LET name:Type=expr or B:LET name=expr ──
        m = re.match(r"LET\s+(\w+)(?::([^=]+))?=(.+)$", rest)
        if m:
            name, type_ann, expr = m.group(1), m.group(2), m.group(3)
            if type_ann:
                expanded_type = _expand_type(type_ann.strip())
                out.append(f"{indent}const {name}: {expanded_type} = {expr};")
            else:
                out.append(f"{indent}const {name} = {expr};")
            i += 1
            continue

        # ── B:CALL fn(args) ──
        m = re.match(r"CALL\s+(.+)$", rest)
        if m:
            out.append(f"{indent}{m.group(1)};")
            i += 1
            continue

        # ── B:ASSIGN $name(expr) ──
        m = re.match(r"ASSIGN\s+\$(\w+)\((.+)\)$", rest)
        if m:
            var_name = m.group(1)
            expr = m.group(2)
            setter = "set" + var_name[0].upper() + var_name[1:]
            out.append(f"{indent}{setter}({expr});")
            i += 1
            continue

        # ── B:AWAIT $res=expr ──
        m = re.match(r"AWAIT\s+\$(\w+)=(.+)$", rest)
        if m:
            name = m.group(1)
            expr = m.group(2)
            out.append(f"{indent}const {name} = await {expr};")
            i += 1
            continue

        # ── B:FETCH fn(args)→$a,$b(transform),$c(val) ──
        m = re.match(r"FETCH\s+(.+?)→(.+)$", rest)
        if m:
            call = m.group(1)
            targets_str = m.group(2)
            targets = re.findall(r"\$(\w+)(?:\(([^)]*)\))?", targets_str)
            inner = indent + "  "
            out.append(f"{indent}useEffect(() => {{")
            if len(targets) == 1:
                tname, transform = targets[0]
                setter = "set" + tname[0].upper() + tname[1:]
                if transform:
                    val = f"{transform}(res)" if _is_func_name(transform) else transform
                    out.append(f"{inner}{call}.then(res => {setter}({val}));")
                else:
                    out.append(f"{inner}{call}.then({setter});")
            elif targets:
                out.append(f"{inner}{call}.then(res => {{")
                for tname, transform in targets:
                    setter = "set" + tname[0].upper() + tname[1:]
                    if transform:
                        val = f"{transform}(res)" if _is_func_name(transform) else transform
                        out.append(f"{inner}  {setter}({val});")
                    else:
                        out.append(f"{inner}  {setter}(res);")
                out.append(f"{inner}}});")
            out.append(f"{indent}}}, []);")
            out.append("")
            i += 1
            continue

        # ── B:AFETCH fn(args)→$a,$b(tx) ──
        m = re.match(r"AFETCH\s+(.+?)→(.+)$", rest)
        if m:
            call = m.group(1)
            targets_str = m.group(2)
            targets = re.findall(r"\$(\w+)(?:\(([^)]*)\))?", targets_str)
            out.append(f"{indent}const res = await {call};")
            for tname, transform in targets:
                setter = "set" + tname[0].upper() + tname[1:]
                if transform:
                    val = f"{transform}(res)" if _is_func_name(transform) else transform
                    out.append(f"{indent}{setter}({val});")
                else:
                    out.append(f"{indent}{setter}(res);")
            i += 1
            continue

        # ── B:GUARD cond→return val ──
        m = re.match(r"GUARD\s+(.+?)→return\s*(.*)?$", rest)
        if m:
            cond = m.group(1).strip()
            val = (m.group(2) or "").strip()
            if val:
                out.append(f"{indent}if ({cond}) return {val};")
            else:
                out.append(f"{indent}if ({cond}) return;")
            i += 1
            continue

        # ── B:IF cond→{} / B:ELIF cond→{} / B:ELSE→{} ──
        m = re.match(r"(IF|ELIF|ELSE)\s*(.*?)→\{\}$", rest)
        if m:
            code = m.group(1)
            cond = m.group(2).strip()
            # Collect inner body lines until B:END
            inner = []
            i += 1
            while i < len(body_lines) and body_lines[i] != "B:END":
                inner.append(body_lines[i])
                i += 1
            inner_expanded = _expand_body_lines(inner, indent + "  ")
            if code == "IF":
                out.append(f"{indent}if ({cond}) {{")
            elif code == "ELIF":
                out.append(f"{indent}}} else if ({cond}) {{")
            else:
                out.append(f"{indent}}} else {{")
            out.extend(inner_expanded)
            out.append(f"{indent}}}")
            i += 1  # skip B:END
            continue

        # ── B:TRY {} ──
        if rest.startswith("TRY"):
            inner = []
            i += 1
            while i < len(body_lines) and not body_lines[i].startswith("B:CATCH") and body_lines[i] != "B:END":
                inner.append(body_lines[i])
                i += 1
            inner_expanded = _expand_body_lines(inner, indent + "  ")
            out.append(f"{indent}try {{")
            out.extend(inner_expanded)
            # Check for CATCH
            if i < len(body_lines) and body_lines[i].startswith("B:CATCH"):
                catch_m = re.match(r"B:CATCH\((\w+)\)→\{\}", body_lines[i])
                err_name = catch_m.group(1) if catch_m else "e"
                catch_inner = []
                i += 1
                while i < len(body_lines) and not body_lines[i].startswith("B:FINALLY") and body_lines[i] != "B:END":
                    catch_inner.append(body_lines[i])
                    i += 1
                catch_expanded = _expand_body_lines(catch_inner, indent + "  ")
                out.append(f"{indent}}} catch ({err_name}) {{")
                out.extend(catch_expanded)
            # Check for FINALLY
            if i < len(body_lines) and body_lines[i].startswith("B:FINALLY"):
                fin_inner = []
                i += 1
                while i < len(body_lines) and body_lines[i] != "B:END":
                    fin_inner.append(body_lines[i])
                    i += 1
                fin_expanded = _expand_body_lines(fin_inner, indent + "  ")
                out.append(f"{indent}}} finally {{")
                out.extend(fin_expanded)
            out.append(f"{indent}}}")
            if i < len(body_lines) and body_lines[i] == "B:END":
                i += 1
            continue

        # ── B:RET expr ──
        m = re.match(r"RET\s+(.+)$", rest)
        if m:
            expr = m.group(1).strip()
            # Check if it's a multiline JSX return (starts with <)
            if expr.startswith("<"):
                jsx = _format_jsx_return(expr, indent)
                out.extend(jsx)
            else:
                out.append(f"{indent}return {expr};")
            i += 1
            continue

        # ── B:TERN cond?a:b ──
        m = re.match(r"TERN\s+(.+)$", rest)
        if m:
            out.append(f"{indent}{m.group(1)};")
            i += 1
            continue

        # ── B:MAP arr→(item)=>expr ──
        m = re.match(r"MAP\s+(\w+)→\((.+?)\)=>(.+)$", rest)
        if m:
            arr, param, expr = m.group(1), m.group(2), m.group(3)
            out.append(f"{indent}{arr}.map(({param}) => {expr});")
            i += 1
            continue

        # ── B:FILTER arr→(item)=>cond ──
        m = re.match(r"FILTER\s+(\w+)→\((.+?)\)=>(.+)$", rest)
        if m:
            arr, param, expr = m.group(1), m.group(2), m.group(3)
            out.append(f"{indent}{arr}.filter(({param}) => {expr});")
            i += 1
            continue

        # ── B:REDUCE arr→(acc,item)=>expr,init ──
        m = re.match(r"REDUCE\s+(\w+)→\((.+?)\)=>(.+),(.+)$", rest)
        if m:
            arr = m.group(1)
            params = m.group(2)
            expr = m.group(3)
            init = m.group(4)
            out.append(f"{indent}{arr}.reduce(({params}) => {expr}, {init});")
            i += 1
            continue

        # ── B:SORT arr→(a,b)=>expr ──
        m = re.match(r"SORT\s+(\w+)→\((.+?)\)=>(.+)$", rest)
        if m:
            arr, params, expr = m.group(1), m.group(2), m.group(3)
            out.append(f"{indent}{arr}.sort(({params}) => {expr});")
            i += 1
            continue

        # ── B:SPREAD $target←{...prev,key:val} ──
        m = re.match(r"SPREAD\s+\$(\w+)←(.+)$", rest)
        if m:
            var_name = m.group(1)
            spread_expr = m.group(2)
            setter = "set" + var_name[0].upper() + var_name[1:]
            out.append(f"{indent}{setter}({spread_expr});")
            i += 1
            continue

        # ── B:CB name(params)→expr,[deps] or B:CB name(params)→{},[deps] ──
        m = re.match(r"CB\s+(\w+)\(([^)]*)\)→(.*),\[([^\]]*)\]$", rest)
        if m:
            name = m.group(1)
            params = m.group(2)
            body_expr = m.group(3).strip()
            deps = m.group(4)
            if body_expr == "{}":
                # Multi-line: collect until B:END
                inner = []
                i += 1
                while i < len(body_lines) and body_lines[i] != "B:END":
                    inner.append(body_lines[i])
                    i += 1
                inner_expanded = _expand_body_lines(inner, indent + "  ")
                out.append(f"{indent}const {name} = useCallback(({params}) => {{")
                out.extend(inner_expanded)
                out.append(f"{indent}}}, [{deps}]);")
                i += 1  # skip B:END
            else:
                out.append(f"{indent}const {name} = useCallback(({params}) => {body_expr}, [{deps}]);")
                i += 1
            continue

        # ── B:MEMO name=expr,[deps] ──
        m = re.match(r"MEMO\s+(\w+)=(.+),\[([^\]]*)\]$", rest)
        if m:
            name = m.group(1)
            expr = m.group(2).strip()
            deps = m.group(3)
            out.append(f"{indent}const {name} = useMemo(() => {expr}, [{deps}]);")
            i += 1
            continue

        # ── B:TOAST msg,"variant" ──
        m = re.match(r'TOAST\s+(.+),"(\w+)"$', rest)
        if m:
            msg = m.group(1).strip()
            variant = m.group(2)
            out.append(f"{indent}toast.{variant}({msg});")
            i += 1
            continue
        m = re.match(r"TOAST\s+(.+)$", rest)
        if m:
            out.append(f"{indent}toast({m.group(1).strip()});")
            i += 1
            continue

        # ── B:NAV / B:NAV.replace path ──
        m = re.match(r"NAV(?:\.replace)?\s+(.+)$", rest)
        if m:
            path_expr = m.group(1).strip()
            method = "replace" if ".replace" in rest[:12] else "push"
            out.append(f"{indent}router.{method}({path_expr});")
            i += 1
            continue

        # ── B:LOG expr ──
        m = re.match(r"LOG\s+(.+)$", rest)
        if m:
            out.append(f"{indent}console.log({m.group(1).strip()});")
            i += 1
            continue

        # ── B:HANDLE name(params)→{} (multi-line) ──
        m = re.match(r"HANDLE\s+(?:async\s+)?(\w+)\(([^)]*)\)→\{\}$", rest)
        if m:
            name = m.group(1)
            params = m.group(2)
            is_async = "async " in rest[:20]
            inner = []
            i += 1
            while i < len(body_lines) and body_lines[i] != "B:END":
                inner.append(body_lines[i])
                i += 1
            inner_expanded = _expand_body_lines(inner, indent + "  ")
            prefix = "async " if is_async else ""
            out.append(f"{indent}const {name} = {prefix}({params}) => {{")
            out.extend(inner_expanded)
            out.append(f"{indent}}};")
            i += 1  # skip B:END
            continue

        # ── B:HANDLE name(params)→expr (single-line) ──
        m = re.match(r"HANDLE\s+(\w+)\(([^)]*)\)→(.+)$", rest)
        if m:
            name = m.group(1)
            params = m.group(2)
            expr = m.group(3).strip()
            out.append(f"{indent}const {name} = ({params}) => {expr};")
            i += 1
            continue

        # ── B:DESTRUCT {a,b}=expr ──
        m = re.match(r"DESTRUCT\s+\{(.+?)\}=(.+)$", rest)
        if m:
            names = m.group(1)
            expr = m.group(2).strip()
            out.append(f"{indent}const {{ {names} }} = {expr};")
            i += 1
            continue

        # ── B:JSXMAP arr→(item)=><Comp.../> ──
        m = re.match(r"JSXMAP\s+(.+?)→\((.+?)\)=>(.+)$", rest)
        if m:
            arr, param, jsx = m.group(1), m.group(2), m.group(3)
            out.append(f"{indent}{{{arr}.map(({param}) => {jsx})}}")
            i += 1
            continue

        # ── B:JSXCOND cond?<A/>:<B/> ──
        m = re.match(r"JSXCOND\s+(.+)$", rest)
        if m:
            expr = m.group(1).strip()
            # Strip leading $ from state var names
            expr = re.sub(r"\$(\w+)", r"\1", expr)
            out.append(f"{indent}{{{expr}}}")
            i += 1
            continue

        # ── B:SUBMIT handler→POST url,body→$saving,$error ──
        m = re.match(r"SUBMIT\s+(\w+)→(POST|PUT|PATCH|DELETE)\s+(.+?),(.+?)→(.+)$", rest)
        if m:
            handler = m.group(1)
            method = m.group(2)
            url = m.group(3)
            body_param = m.group(4)
            targets_str = m.group(5)
            targets = re.findall(r"\$(\w+)", targets_str)
            out.append(f"{indent}const {handler} = async (e: React.FormEvent) => {{")
            out.append(f"{indent}  e.preventDefault();")
            if targets:
                setter0 = "set" + targets[0][0].upper() + targets[0][1:]
                out.append(f"{indent}  {setter0}(true);")
            out.append(f'{indent}  try {{')
            out.append(f'{indent}    const res = await fetch({url}, {{')
            out.append(f'{indent}      method: "{method}",')
            out.append(f"{indent}      body: JSON.stringify({body_param}),")
            out.append(f"{indent}    }});")
            out.append(f"{indent}    const data = await res.json();")
            if len(targets) > 1:
                setter1 = "set" + targets[1][0].upper() + targets[1][1:]
                out.append(f"{indent}    {setter1}(null);")
            if targets:
                out.append(f"{indent}  }} catch (err) {{")
                if len(targets) > 1:
                    out.append(f"{indent}    {setter1}(err.message);")
            out.append(f"{indent}  }} finally {{")
            if targets:
                out.append(f"{indent}    {setter0}(false);")
            out.append(f"{indent}  }}")
            out.append(f"{indent}}};")
            i += 1
            continue

        # ── B:FN name(params):RetType ──
        m = re.match(r"FN\s+(\w+)\(([^)]*)\)(?::(.+))?$", rest)
        if m:
            name = m.group(1)
            params = m.group(2)
            ret = m.group(3) or ""
            inner = []
            i += 1
            while i < len(body_lines) and body_lines[i] != "B:END":
                inner.append(body_lines[i])
                i += 1
            inner_expanded = _expand_body_lines(inner, indent + "  ")
            ret_str = f": {_expand_type(ret)}" if ret else ""
            out.append(f"{indent}function {name}({params}){ret_str} {{")
            out.extend(inner_expanded)
            out.append(f"{indent}}}")
            i += 1  # skip B:END
            continue

        # ── B:RAW — verbatim pass-through ──
        m = re.match(r"RAW\s+(.+)$", rest)
        if m:
            out.append(f"{indent}{m.group(1)}")
            i += 1
            continue

        # Unrecognised body line — emit as comment
        out.append(f"{indent}// {line}")
        i += 1

    return out


def _format_jsx_return(jsx: str, indent: str) -> List[str]:
    """Format a compressed JSX return into indented multi-line output."""
    lines = [f"{indent}return ("]
    # Tokenize by JSX boundaries: opening tags, closing tags, self-closing, and content
    # Split on spaces between top-level tokens  
    tokens = _tokenize_jsx(jsx.strip())
    depth = 0
    base_indent = indent + "  "
    for token in tokens:
        cur = base_indent + ("  " * depth)
        if token.startswith("</"):
            # Closing tag — dedent first
            depth = max(0, depth - 1)
            cur = base_indent + ("  " * depth)
            lines.append(f"{cur}{token}")
        elif token.startswith("<") and not token.endswith("/>") and ">" in token:
            # Opening tag — print then indent
            lines.append(f"{cur}{token}")
            depth += 1
        else:
            # Self-closing tag, expression, or text
            lines.append(f"{cur}{token}")
    lines.append(f"{indent});")
    return lines


def _tokenize_jsx(jsx: str) -> List[str]:
    """Split compressed JSX into logical tokens (tags, expressions, text)."""
    tokens = []
    i = 0
    while i < len(jsx):
        # Skip whitespace
        while i < len(jsx) and jsx[i] == " ":
            i += 1
        if i >= len(jsx):
            break
        if jsx[i] == "{":
            # JSX expression — find matching }
            depth = 0
            start = i
            while i < len(jsx):
                if jsx[i] == "{":
                    depth += 1
                elif jsx[i] == "}":
                    depth -= 1
                    if depth == 0:
                        i += 1
                        break
                i += 1
            tokens.append(jsx[start:i])
        elif jsx[i] == "<":
            # Tag — find matching >
            start = i
            i += 1
            while i < len(jsx) and jsx[i] != ">":
                i += 1
            i += 1  # past >
            tokens.append(jsx[start:i])
        else:
            # Text content
            start = i
            while i < len(jsx) and jsx[i] not in "<{":
                i += 1
            text = jsx[start:i].strip()
            if text:
                tokens.append(text)
    return tokens


def _gen_jsx(jsx_str: str) -> List[str]:
    """Generate a JSX return block from compressed JSX string."""
    if not jsx_str:
        return ["  return null;"]

    # Extract component names from <Name/> or <Name>
    components = re.findall(r"<(\w+)(?:\s[^/>]*)?\s*/?>", jsx_str)
    if not components:
        return [f"  return ({jsx_str});"]

    lines = ["  return ("]
    # If multiple components, nest them
    if len(components) == 1:
        lines.append(f"    <{components[0]} />")
    else:
        # First component wraps the rest
        wrapper = components[0]
        lines.append(f"    <{wrapper}>")
        for comp in components[1:]:
            lines.append(f"      <{comp} />")
        lines.append(f"    </{wrapper}>")
    lines.append("  );")
    return lines


def _gen_interface(line: str) -> List[str]:
    """Generate an interface from Type{field:T,field:T} notation."""
    m = re.match(r"(\w+)\{(.+)\}", line)
    if not m:
        return []
    name = m.group(1)
    fields_str = m.group(2)
    lines = [f"export interface {name} {{"]

    # Split fields by comma, but respect nested generics
    fields = _split_imports(fields_str)
    for field in fields:
        fm = re.match(r"(\w+):(.+)", field.strip())
        if fm:
            fname = fm.group(1)
            ftype = _expand_type(fm.group(2).strip())
            lines.append(f"  {fname}: {ftype};")
    lines.append("}")
    return lines


def _gen_type_alias(line: str) -> str:
    """Generate a type alias from Name=value notation."""
    m = re.match(r"(\w+)=(.+)", line)
    if not m:
        return ""
    name = m.group(1)
    value = m.group(2).strip()
    return f"export type {name} = {value};"


def _gen_function_sig(line: str) -> List[str]:
    """Generate a function stub from name(params)→ReturnType notation."""
    m = re.match(r"(\w+)\(([^)]*)\)→(.+)", line)
    if not m:
        return []
    name = m.group(1)
    params_str = m.group(2).strip()
    ret = _expand_type(m.group(3).strip())

    # Expand param types
    params = []
    if params_str:
        for p in _split_imports(params_str):
            pm = re.match(r"(\w+):(.+)", p.strip())
            if pm:
                pname = pm.group(1)
                ptype = _expand_type(pm.group(2).strip())
                params.append(f"{pname}: {ptype}")
            else:
                params.append(p.strip())

    params_out = ", ".join(params)
    lines = [
        f"export function {name}({params_out}): {ret} {{",
        f"  // TODO: implement",
        f"  throw new Error('Not implemented');",
        f"}}",
    ]
    return lines


def _gen_route_handler(methods_line: str) -> List[str]:
    """Generate route handler stubs from GET,POST→json notation."""
    m = re.match(r"([\w,]+)\s*(?:/\S+)?\s*(?:\{[^}]*\})?\s*→", methods_line)
    if not m:
        return []
    methods = [x.strip() for x in m.group(1).split(",")]
    lines = []
    for method in methods:
        lines.append(f"export async function {method}(request: Request) {{")
        lines.append(f"  // TODO: implement {method} handler")
        lines.append(f"  return NextResponse.json({{ error: 'Not implemented' }});")
        lines.append(f"}}")
        lines.append("")
    return lines


# ── HTML block decoder ───────────────────────────────────────────────────────

def _decode_html_block(block: str) -> Dict:
    """Parse an HTML-type VXL block into a structured dict with verbatim sections.

    Sections: HEAD, CSS, BODY, JS — each stored verbatim between BEGIN/END markers.
    """
    raw_lines = block.strip().split("\n")
    if not raw_lines:
        return {}

    result = {
        "header": _parse_header(raw_lines[0]),
        "doctype": "<!DOCTYPE html>",
        "html_attrs": "",
        "body_attrs": "",
        "head": "",
        "css": "",
        "body_html": "",
        "js": "",
    }

    i = 1
    while i < len(raw_lines):
        line = raw_lines[i]
        stripped = line.strip()

        if stripped.startswith("DOCTYPE:"):
            result["doctype"] = stripped[len("DOCTYPE:"):]
            i += 1
            continue

        if stripped.startswith("ATTR:"):
            result["html_attrs"] = stripped[len("ATTR:"):]
            i += 1
            continue

        if stripped.startswith("BODY_ATTR:"):
            result["body_attrs"] = stripped[len("BODY_ATTR:"):]
            i += 1
            continue

        # Section markers: collect everything between BEGIN and END verbatim
        if stripped == "HEAD:BEGIN":
            section_lines = []
            i += 1
            while i < len(raw_lines) and raw_lines[i].strip() != "HEAD:END":
                section_lines.append(raw_lines[i])
                i += 1
            result["head"] = "\n".join(section_lines)
            i += 1  # skip END
            continue

        if stripped == "CSS:BEGIN":
            section_lines = []
            i += 1
            while i < len(raw_lines) and raw_lines[i].strip() != "CSS:END":
                section_lines.append(raw_lines[i])
                i += 1
            result["css"] = "\n".join(section_lines)
            i += 1
            continue

        if stripped == "BODY:BEGIN":
            section_lines = []
            i += 1
            while i < len(raw_lines) and raw_lines[i].strip() != "BODY:END":
                section_lines.append(raw_lines[i])
                i += 1
            result["body_html"] = "\n".join(section_lines)
            i += 1
            continue

        if stripped == "JS:BEGIN":
            section_lines = []
            i += 1
            while i < len(raw_lines) and raw_lines[i].strip() != "JS:END":
                section_lines.append(raw_lines[i])
                i += 1
            result["js"] = "\n".join(section_lines)
            i += 1
            continue

        i += 1

    return result


def _generate_html_source(block: Dict) -> str:
    """Reassemble an HTML file from a parsed HTML VXL block."""
    doctype = block.get("doctype", "<!DOCTYPE html>")
    html_attrs = block.get("html_attrs", "")
    head = block.get("head", "")
    css = block.get("css", "")
    body_attrs = block.get("body_attrs", "")
    body_html = block.get("body_html", "")
    js = block.get("js", "")

    html_open = f"<html {html_attrs}>" if html_attrs else "<html>"

    parts = [doctype, html_open, "<head>"]

    if head:
        parts.append(head)

    if css:
        parts.append(f"<style>{css}</style>")

    parts.append("</head>")

    body_open = f"<body {body_attrs}>" if body_attrs else "<body>"
    parts.append(body_open)

    if body_html:
        parts.append(body_html)

    if js:
        parts.append(f"\n<script>{js}</script>")

    parts.append("</body>")
    parts.append("</html>")

    return "\n".join(parts)


# ── Block decoder ────────────────────────────────────────────────────────────

def decode_block(block: str) -> Dict:
    """Parse a single VXL block into a structured dict."""
    lines = [l for l in block.strip().splitlines() if l.strip()]
    if not lines:
        return {}

    result = {
        "header": {},
        "exports": {"default": "", "named": []},
        "imports": [],
        "states": [],
        "effects": [],
        "jsx": "",
        "syntax_codes": [],
        "flags": [],
        "wires": [],
        "interfaces": [],
        "functions": [],
        "type_aliases": [],
        "route_methods": [],
        "body": [],
    }

    # First line is always the header
    result["header"] = _parse_header(lines[0])

    for line in lines[1:]:
        stripped = line.strip()

        # Body line (§2.7)
        if stripped.startswith("B:"):
            result["body"].append(stripped)
            continue

        # Wire line
        if stripped.startswith("W:"):
            result["wires"].append(stripped)
            continue

        # Export/Import line
        if stripped.startswith(">>") or (">>" in stripped and "<<" in stripped):
            exports, imports = _parse_export_import(stripped)
            result["exports"] = exports
            result["imports"] = imports
            continue

        # State line (contains $)
        if stripped.startswith("$"):
            for decl in stripped.split("|"):
                decl = decl.strip()
                if decl.startswith("$"):
                    result["states"].append(_parse_state_decl(decl))
            continue

        # Effect line
        if stripped.startswith("~"):
            result["effects"].append(_parse_effect(stripped))
            continue

        # Interface: Name{field:type,...}
        if re.match(r"^\w+\{.+:.+\}$", stripped):
            result["interfaces"].append(stripped)
            continue

        # Type alias: Name="a"|"b" or Name=value
        if re.match(r"^\w+=.+$", stripped) and not stripped.startswith("$"):
            result["type_aliases"].append(stripped)
            continue

        # Function signature: name(params)→Return
        if re.match(r"^\w+\([^)]*\)→.+$", stripped):
            result["functions"].append(stripped)
            continue

        # Route methods: GET,POST→json
        if re.match(r"^(?:GET|POST|PUT|DELETE|PATCH)", stripped) and "→" in stripped:
            result["route_methods"].append(stripped)
            continue

        # Render / signature line: <jsx>|codes|flags  or  codes|flags
        if "|" in stripped:
            parts = stripped.split("|")
            for part in parts:
                part = part.strip()
                if part.startswith("<"):
                    result["jsx"] = part
                elif part.startswith("@") or "+" in part and part.startswith("@"):
                    # Flags
                    result["flags"] = [f.strip() for f in part.split("+") if f.strip()]
                elif re.match(r"^[a-z]", part) and ("+" in part or part in (
                    "tsx", "hk", "ftc", "st", "eff", "prp", "ctx", "frm",
                    "auth", "cch", "ssr", "mut", "qry", "val", "err", "nav",
                    "sty", "tbl", "chrt", "mod", "sort", "flt", "ws", "calc",
                    "anm", "dl", "pag",
                )):
                    result["syntax_codes"] = [c.strip() for c in part.split("+") if c.strip()]
                elif "+" in part:
                    # Could be flags or codes — check first token
                    tokens = [t.strip() for t in part.split("+")]
                    if tokens and tokens[0].startswith("@"):
                        result["flags"] = tokens
                    else:
                        result["syntax_codes"] = tokens

    return result


# ── Main decoder ─────────────────────────────────────────────────────────────

def decode(vxl_text: str) -> str:
    """
    Decode a VXL document (one or more blocks) into TypeScript/TSX source.

    When body lines (B:) are present, output is lossless — full source is
    reconstructed. Without body lines, output is a structural scaffold.
    For multi-block documents, files are separated by banner comments.
    """
    blocks = re.split(r"\n---\n", vxl_text.strip())
    outputs = []

    for block_text in blocks:
        # Detect HTML block by checking the header line
        first_line = block_text.strip().split("\n", 1)[0] if block_text.strip() else ""
        header = _parse_header(first_line)
        if header.get("type") == "HTML":
            block = _decode_html_block(block_text)
            if not block or not block.get("header"):
                continue
            code = _generate_html_source(block)
            filepath = f"{block['header']['path']}/{block['header']['filename']}"
            outputs.append((filepath, code))
            continue

        block = decode_block(block_text)
        if not block or not block.get("header"):
            continue
        code = _generate_source(block)
        header = block["header"]
        filepath = f"{header['path']}/{header['filename']}"
        outputs.append((filepath, code))

    if len(outputs) == 1:
        return outputs[0][1]

    parts = []
    for filepath, code in outputs:
        parts.append(f"// ═══ {filepath} ═══")
        parts.append(code)
    return "\n\n".join(parts)


def _generate_source(block: Dict) -> str:
    """Generate TypeScript/TSX source from a parsed VXL block."""
    header = block["header"]
    ftype = header.get("type", "")
    filename = header.get("filename", "")
    flags = block.get("flags", [])
    lines: List[str] = []

    # "use client" directive
    if "@CSR" in flags:
        lines.append('"use client";')
        lines.append("")

    # Determine what React imports we need (these may also come from
    # an explicit <<react{...} import — we deduplicate below)
    react_hooks = set()
    if block["states"]:
        for s in block["states"]:
            if s.get("type", "").startswith("ref"):
                react_hooks.add("useRef")
            else:
                react_hooks.add("useState")
    if block["effects"]:
        react_hooks.add("useEffect")

    # Merge any explicitly-imported react names from <<react{...}
    for imp in block.get("imports", []):
        if imp.get("module") == "react" and imp.get("named"):
            react_hooks.update(imp["named"])

    if react_hooks:
        hooks_str = ", ".join(sorted(react_hooks))
        lines.append(f'import {{ {hooks_str} }} from "react";')

    # Other imports
    import_lines = _gen_imports(block.get("imports", []))
    lines.extend(import_lines)
    if lines and lines[-1] != "":
        lines.append("")

    # Dynamic/edge exports
    if "@DYN" in flags:
        lines.append("export const dynamic = 'force-dynamic';")
        lines.append("")
    if "@EDGE" in flags:
        lines.append("export const runtime = 'edge';")
        lines.append("")

    # Route handler files
    if ftype == "RT":
        if block.get("route_methods"):
            for rm in block["route_methods"]:
                lines.extend(_gen_route_handler(rm))
        elif block["exports"].get("default"):
            exp = block["exports"]["default"]
            if ":" in exp:
                method, name = exp.split(":", 1)
                lines.append(f"export async function {method.upper()}(request: Request) {{")
                lines.append(f"  // TODO: implement {method} handler")
                lines.append(f"  return NextResponse.json({{ error: 'Not implemented' }});")
                lines.append(f"}}")
        return "\n".join(lines)

    # Type definition files
    if ftype == "TP":
        for iface in block.get("interfaces", []):
            lines.extend(_gen_interface(iface))
            lines.append("")
        for ta in block.get("type_aliases", []):
            result = _gen_type_alias(ta)
            if result:
                lines.append(result)
                lines.append("")
        # Also handle exports that list type names
        if block["exports"].get("named") and not block.get("interfaces"):
            for name in block["exports"]["named"]:
                lines.append(f"export interface {name} {{")
                lines.append(f"  // TODO: define {name}")
                lines.append(f"}}")
                lines.append("")
        return "\n".join(lines)

    # Utility / Library files with function signatures
    if ftype in ("UT", "LIB", "IDX") and block.get("functions"):
        for fn in block["functions"]:
            lines.extend(_gen_function_sig(fn))
            lines.append("")
        for iface in block.get("interfaces", []):
            lines.extend(_gen_interface(iface))
            lines.append("")
        return "\n".join(lines)

    # Layout files
    if ftype == "LY":
        exports = block["exports"]
        if exports.get("default") and "metadata" in exports["default"]:
            # Extract metadata
            meta_match = re.search(r"metadata:\{(.+)\}", exports["default"])
            if meta_match:
                meta_inner = meta_match.group(1)
                lines.append("import type { Metadata } from 'next';")
                lines.append("")
                lines.append(f"export const metadata: Metadata = {{ {meta_inner} }};")
            else:
                lines.append("import type { Metadata } from 'next';")
                lines.append("")
                lines.append("export const metadata: Metadata = {};")
            lines.append("")
        lines.append("export default function Layout({ children }: { children: React.ReactNode }) {")
        lines.append("  return <>{children}</>;")
        lines.append("}")
        return "\n".join(lines)

    # Component / Page / Hook files
    exports = block["exports"]
    is_default = bool(exports.get("default"))
    export_name = exports.get("default", "")

    # For hooks
    if ftype == "HK":
        # Parse hook signature from export
        hook_match = re.match(r"(\w+)\(([^)]*)\)→(.+)", export_name)
        if hook_match:
            hook_name = hook_match.group(1)
            params_str = hook_match.group(2)
            ret_str = hook_match.group(3)

            params = []
            if params_str:
                for p in _split_imports(params_str):
                    pm = re.match(r"(\w+):(.+)", p.strip())
                    if pm:
                        params.append(f"{pm.group(1)}: {_expand_type(pm.group(2))}")
                    else:
                        params.append(p.strip())

            lines.append(f"export function {hook_name}({', '.join(params)}) {{")
        else:
            lines.append(f"export function {export_name or 'useHook'}() {{")

        # State declarations
        for state in block.get("states", []):
            lines.append(_gen_state(state))
        if block["states"]:
            lines.append("")

        # Effects
        for effect in block.get("effects", []):
            lines.extend(_gen_effect(effect))
            lines.append("")

        # Return
        if hook_match:
            ret_fields = re.findall(r"(\w+)", hook_match.group(3))
            first_fields = [f for f in ret_fields if f not in ("loading", "error", "data")]
            state_names = [s["name"] for s in block.get("states", [])]
            return_fields = [n for n in state_names if n]
            lines.append(f"  return {{ {', '.join(return_fields)} }};")
        else:
            lines.append("  return {};")
        lines.append("}")
        return "\n".join(lines)

    # Page / Component (default)
    if is_default:
        func_name = export_name or "Component"
        # Check if it looks like a named export with parentheses (function sig)
        if "(" in func_name:
            sig_match = re.match(r"(\w+)\(([^)]*)\)", func_name)
            if sig_match:
                func_name = sig_match.group(1)
                props_str = sig_match.group(2)
        lines.append(f"export default function {func_name}() {{")
    elif exports.get("named"):
        # Named exports only — generate separate functions
        for name in exports["named"]:
            if name[0].isupper():
                lines.append(f"export function {name}() {{")
                # Add state, effects, jsx inline for first component only
                break
        else:
            lines.append(f"export function Component() {{")
    else:
        lines.append("export default function Component() {")

    # State declarations
    for state in block.get("states", []):
        lines.append(_gen_state(state))
    if block["states"]:
        lines.append("")

    # Body lines present — use lossless expansion instead of structural stubs
    has_body = bool(block.get("body"))
    if has_body:
        # When body lines exist, skip structural effect generation — the body
        # contains the real implementation (B:FETCH captures the useEffect logic).
        body_expanded = _expand_body_lines(block["body"])
        lines.extend(body_expanded)
    else:
        # No body — fall back to structural stubs
        # Effects
        for effect in block.get("effects", []):
            lines.extend(_gen_effect(effect))
            lines.append("")

        # JSX return
        jsx = block.get("jsx", "")
        lines.extend(_gen_jsx(jsx))
    lines.append("}")

    # Additional named exports (components in the same file)
    if not is_default and exports.get("named"):
        for name in exports["named"][1:]:
            if name[0].isupper():
                lines.append("")
                lines.append(f"export function {name}() {{")
                lines.append("  return null;")
                lines.append("}")

    return "\n".join(lines)


# ── File output ──────────────────────────────────────────────────────────────

def decode_to_files(vxl_text: str, output_dir: str) -> List[str]:
    """
    Decode a VXL document and write each block as a separate file.

    Returns list of created file paths.
    """
    blocks = re.split(r"\n---\n", vxl_text.strip())
    created = []

    for block_text in blocks:
        # Detect HTML block
        first_line = block_text.strip().split("\n", 1)[0] if block_text.strip() else ""
        hdr = _parse_header(first_line)
        if hdr.get("type") == "HTML":
            block = _decode_html_block(block_text)
            if not block or not block.get("header"):
                continue
            code = _generate_html_source(block)
            header = block["header"]
        else:
            block = decode_block(block_text)
            if not block or not block.get("header"):
                continue
            code = _generate_source(block)
            header = block["header"]

        filepath = os.path.join(output_dir, header["path"], header["filename"])

        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(code)
            f.write("\n")
        created.append(filepath)

    return created


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="VXL Decoder — Expand VXL dialect to TypeScript/TSX source"
    )
    parser.add_argument(
        "input", help="VXL file to decode (use '-' for stdin)"
    )
    parser.add_argument(
        "-o", "--output",
        default="",
        help="Output directory (creates files per block) or file (single output)",
    )
    parser.add_argument(
        "--files",
        action="store_true",
        help="Write separate files per VXL block into --output directory",
    )
    args = parser.parse_args()

    if args.input == "-":
        vxl_text = sys.stdin.read()
    else:
        with open(args.input, "r", encoding="utf-8") as f:
            vxl_text = f.read()

    if args.files and args.output:
        created = decode_to_files(vxl_text, args.output)
        for p in created:
            print(f"  Created: {p}", file=sys.stderr)
        print(f"Wrote {len(created)} files to {args.output}", file=sys.stderr)
    else:
        result = decode(vxl_text)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(result)
                f.write("\n")
            print(f"Wrote scaffold to {args.output}", file=sys.stderr)
        else:
            print(result)


if __name__ == "__main__":
    main()
