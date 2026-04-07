# VXL — Vortex Exchange Language Specification

> **Dialect family:** AAAK-derived (code domain)  
> **Target:** mempalace `app` wing (Next.js / React / TypeScript)  
> **Compression:** ~20× vs raw source, developer-readable  
> **Fidelity:** Lossless — BODY section captures full function logic  
> **Transpilation:** VXL → source OR source → VXL (bidirectional)

---

## 1. Overview

VXL is a **code-description dialect** derived from AAAK. Where AAAK compresses narrative knowledge using emotion codes and entity codes, VXL compresses **source code structure** using **syntax codes** and **file-type codes** — the same pipe-separated, symbol-dense format, tuned for a developer reading or reconstructing application code.

A developer scanning VXL should immediately know: what the file exports, what it imports, what state it holds, how data flows, and what patterns are in play — without opening the source.

**Key properties:**

- AAAK-grade compression (~20× token reduction vs raw source)
- Developer-readable — every symbol maps to a React/TS/Next.js concept
- Bidirectional — transpile VXL → source, or mine code → VXL
- Syntax codes replace AAAK emotion codes (same slot, different vocabulary)
- File-type codes replace AAAK entity codes
- Flags replace AAAK importance flags with structural/architectural markers

**Example — Raw source (~800 tokens):**

```tsx
"use client";
import { useState, useEffect } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { fetchSumTransactions } from "./api";
import type { Transaction, Totals, SortState } from "./types";
import { calcTotals, sortData, buildMarkets } from "./helpers";

export default function PageSumTransactions() {
  const [data, setData] = useState<Transaction[]>([]);
  const [totals, setTotals] = useState<Totals | null>(null);
  const [sort, setSort] = useState<SortState>({ col: "pair", dir: "asc" });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchSumTransactions().then(res => {
      setData(res); setTotals(calcTotals(res)); setLoading(false);
    });
  }, []);

  const sorted = sortData(data, sort);
  return (
    <Card>
      <CardContent>
        {loading ? <Skeleton /> : <DataTable rows={sorted} totals={totals} />}
      </CardContent>
    </Card>
  );
}
```

**VXL equivalent (~60 tokens):**

```
app/sumtransactions|page.tsx|PG
>>PageSumTransactions|<<react,ui{card,select,skeleton},./api,./types,./helpers
$data:Transaction[]=[]|$totals:Totals?=null|$sort:SortState|$loading:b=true
~mount→fetchSumTransactions→$data,$totals(calcTotals)
<Card><DataTable rows={sorted} totals/>|tsx+hk+ftc+tbl+sort|@ENTRY
```

---

## 2. Line Types

Every VXL block describes one source file. A block has 1–6 lines, each with a distinct prefix or position.

### 2.1 Header Line (required)

```
PATH|FILENAME|TYPE
```

| Field      | Description                              | Example                    |
|------------|------------------------------------------|----------------------------|
| `PATH`     | Wing-relative directory                  | `app/strat`, `app/funding` |
| `FILENAME` | Source filename                           | `page.tsx`, `route.ts`     |
| `TYPE`     | File-type code (see §3.1)                | `PG`, `RT`, `CMP`         |

### 2.2 Export / Import Line

```
>>EXPORTS|<<IMPORTS
```

| Sigil | Meaning | Format |
|-------|---------|--------|
| `>>` | Exports | Comma-separated names. Default export has no braces. Named exports in `{}`  |
| `<<` | Imports | Module shorthand, `{}` for named. Path aliases compressed (see §4.3) |

Examples:
```
>>PageConfig|<<react{useState,useEffect},ui{card,btn,select},./types,./api
>>{calcTotals,sortData,buildMarkets}|<<./types
>>default:handler|<<next/server{NextResponse}
```

### 2.3 State Line

```
$name:Type=default|$name:Type=default|...
```

Pipe-separated state declarations. Each uses `$` prefix.

| Notation   | Meaning              | Example                   |
|------------|----------------------|---------------------------|
| `$x:T`     | State variable       | `$data:Transaction[]`     |
| `$x:T=v`   | With default value   | `$loading:b=true`         |
| `$x:T?`    | Nullable             | `$totals:Totals?`         |
| `$x:T?=null`| Nullable, null default | `$error:str?=null`     |

Type shorthands in §3.3.

### 2.4 Effect Line

```
~trigger→action→$target(transform)
```

| Sigil    | Meaning                       | Example                                    |
|----------|-------------------------------|--------------------------------------------|
| `~mount` | `useEffect(…, [])` on mount   | `~mount→fetchConfig→$config`               |
| `~[$x]`  | Effect watching `$x`          | `~[$strategy]→fetchParams→$params`         |
| `~int(n)`| `setInterval` every n ms      | `~int(5000)→fetchHealth→$status`           |
| `→`      | Data flow direction           | `~mount→fetch(/api/pairs)→$pairs`          |
| `(fn)`   | Transform applied             | `→$totals(calcTotals)`                     |

Multiple targets: `→$data,$totals(calcTotals),$loading(false)`

### 2.5 Render Line

```
<Component tree>|SYNTAX_CODES|FLAGS
```

Compressed JSX tree followed by syntax codes and flags. Only key structural elements included — skip wrappers, fragments, divs unless meaningful.

```
<Card><Select bind=$strategy/><ParamsForm data=$params/><ResultTable/>|tsx+hk+ftc+tbl|@ENTRY
```

For non-component files (types, utils, routes), this line is the **signature line** instead:

```
GET,POST /api/strat/parameters/[strategy]/[pair]→json|ftc+val|@API+@ASYNC
```

### 2.6 Wire Line

Cross-file references (analogous to AAAK tunnels):

```
W:source→target|label
```

```
W:page.tsx→api.ts|fetchPairs
W:page.tsx→helpers.tsx|calcTotals,sortData
W:route.ts→@/lib/vortex|getClient
```

### 2.7 Body Lines (lossless function logic)

Body lines capture the implementation logic that structural lines (state, effects, JSX) summarise. Each body line is prefixed with `B:` and encodes one statement or expression using **pattern shorthand codes**. Together the body lines make VXL lossless — a decoder can reconstruct the full source file, not just a scaffold.

#### 2.7.1 Pattern Shorthand Codes

Recurring multi-line patterns are compressed to a single `B:` line.

| Code | Pattern | Compressed form | Expands to |
|------|---------|----------------|------------|
| `LET` | Local variable | `B:LET name:Type=expr` | `const name: Type = expr;` |
| `CALL` | Plain function call | `B:CALL fn(args)` | `fn(args);` |
| `ASSIGN` | State setter call | `B:ASSIGN $name(expr)` | `setName(expr);` |
| `AWAIT` | Awaited call | `B:AWAIT $res=fn(args)` | `const res = await fn(args);` |
| `FETCH` | Fetch-then-set cascade | `B:FETCH fn(args)→$a,$b(transform),$c(val)` | `fn(args).then(res => { setA(res); setB(transform(res)); setC(val); });` |
| `AFETCH` | Async fetch-set | `B:AFETCH fn(args)→$a,$b(tx)` | `const res = await fn(args); setA(res); setB(tx(res));` |
| `GUARD` | Early return guard | `B:GUARD cond→return val` | `if (cond) return val;` |
| `IF` | Conditional block | `B:IF cond→{stmts}` | `if (cond) { stmts }` |
| `ELIF` | Else-if branch | `B:ELIF cond→{stmts}` | `else if (cond) { stmts }` |
| `ELSE` | Else branch | `B:ELSE→{stmts}` | `else { stmts }` |
| `RET` | Return statement | `B:RET expr` | `return expr;` |
| `TERN` | Ternary expression | `B:TERN cond?a:b` | `cond ? a : b` |
| `MAP` | Array map | `B:MAP arr→(item)=>expr` | `arr.map((item) => expr)` |
| `FILTER` | Array filter | `B:FILTER arr→(item)=>cond` | `arr.filter((item) => cond)` |
| `REDUCE` | Array reduce | `B:REDUCE arr→(acc,item)=>expr,init` | `arr.reduce((acc, item) => expr, init)` |
| `SORT` | Sort call | `B:SORT arr→(a,b)=>expr` | `arr.sort((a, b) => expr)` |
| `SPREAD` | Spread assignment | `B:SPREAD $target←{...prev,key:val}` | `setTarget({...prev, key: val});` |
| `TRY` | Try-catch block | `B:TRY {stmts} CATCH(e)→{stmts}` | `try { stmts } catch (e) { stmts }` |
| `FINALLY` | Finally block | `B:FINALLY {stmts}` | `finally { stmts }` |
| `CB` | useCallback | `B:CB name(params)→{stmts},[deps]` | `const name = useCallback((params) => { stmts }, [deps]);` |
| `MEMO` | useMemo | `B:MEMO name=expr,[deps]` | `const name = useMemo(() => expr, [deps]);` |
| `TOAST` | Toast notification | `B:TOAST msg,"variant"` | `toast(msg); / toast.success(msg); / toast.error(msg);` |
| `NAV` | Router navigation | `B:NAV path` or `B:NAV.replace path` | `router.push(path);` or `router.replace(path);` |
| `LOG` | Console log | `B:LOG expr` | `console.log(expr);` |
| `HANDLE` | Event handler | `B:HANDLE name(e)→{stmts}` | `const name = (e) => { stmts };` |
| `SUBMIT` | Form submit handler | `B:SUBMIT handler→POST url,body→$saving,$error` | Full async form submit with state management |
| `DESTRUCT` | Destructure | `B:DESTRUCT {a,b}=expr` | `const { a, b } = expr;` |
| `JSXMAP` | JSX list render | `B:JSXMAP arr→(item)=><Comp key={item.id} data={item}/>` | `{arr.map((item) => <Comp key={item.id} data={item} />)}` |
| `JSXCOND` | JSX conditional | `B:JSXCOND $loading?<Skeleton/>:<Content data={data}/>` | `{loading ? <Skeleton /> : <Content data={data} />}` |
| `RAW` | Verbatim line | `B:RAW any code here` | Output as-is (escape hatch for unrecognised patterns) |

#### 2.7.2 Body Line Syntax

```
B:CODE args               — single statement
B:FN name(params):RetType  — function body scope start
B:END                      — function body scope end
```

Body lines appear after the render/signature line and before wire lines. They describe the implementation between function braces. Multiple body lines compose sequentially to reconstruct the full function body.

#### 2.7.3 Nesting

Body lines are flat — indentation level is inferred from context:
- Lines after `B:IF`/`B:ELIF`/`B:ELSE` until the next `B:IF`/`B:ELIF`/`B:ELSE`/`B:END` are inside that branch.
- `B:TRY`…`B:CATCH`…`B:FINALLY` work the same way.
- `B:FN`…`B:END` scopes delimit inner function bodies (e.g. event handlers defined inline).

#### 2.7.4 Statement Compression Rules

1. **Setter chains** — consecutive `setX()` calls in a `.then()` compress to one `FETCH` line with comma-separated targets.
2. **Derived state** — `const x = fn(y)` compresses to `B:LET x=fn(y)` (type inferred).
3. **Guard clauses** — `if (!x) return;` compresses to `B:GUARD !x→return`.
4. **Ternary render** — `{cond ? <A/> : <B/>}` compresses to `B:JSXCOND cond?<A/>:<B/>`.
5. **Map render** — `{arr.map(item => <C key=… />)}` compresses to `B:JSXMAP arr→(item)=><C key=…/>`.
6. **Toast + state** — `toast.error(msg); setError(msg)` compresses to `B:TOAST msg,"error"|B:ASSIGN $error(msg)`.
7. **Verbatim fallback** — any line not matching a known pattern is emitted as `B:RAW`.

#### 2.7.5 Example — Full Body Encoding

**Source:**
```tsx
export default function PageSumTransactions() {
  const [data, setData] = useState<Transaction[]>([]);
  const [totals, setTotals] = useState<Totals | null>(null);
  const [sort, setSort] = useState<SortState>({ col: "pair", dir: "asc" });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchSumTransactions().then(res => {
      setData(res); setTotals(calcTotals(res)); setLoading(false);
    });
  }, []);

  const sorted = sortData(data, sort);
  return (
    <Card>
      <CardContent>
        {loading ? <Skeleton /> : <DataTable rows={sorted} totals={totals} />}
      </CardContent>
    </Card>
  );
}
```

**VXL with BODY:**
```
app/sumtransactions|page.tsx|PG
>>PageSumTransactions|<<react{useState,useEffect},ui{card,skeleton,select},./api,./types,./helpers
$data:Transaction[]=[]|$totals:Totals?=null|$sort:SortState={ col: "pair", dir: "asc" }|$loading:b=true
~mount→fetchSumTransactions→$data,$totals(calcTotals),$loading(false)
<Card><CardContent/><Skeleton/><DataTable/>|tsx+hk+ftc+tbl+sort|@ENTRY+@CSR
B:FETCH fetchSumTransactions()→$data,$totals(calcTotals),$loading(false)
B:LET sorted=sortData(data,sort)
B:RET <Card><CardContent>{B:JSXCOND $loading?<Skeleton/>:<DataTable rows={sorted} totals={totals}/>}</CardContent></Card>
W:page.tsx→api.ts|fetchSumTransactions
W:page.tsx→helpers.tsx|calcTotals,sortData,buildMarkets
```

The body lines (`B:FETCH`, `B:LET`, `B:RET`) capture everything the structural lines omit. A decoder receiving this block can reconstruct the original file exactly, not just a scaffold.

---

## 3. Code Tables

### 3.1 File-Type Codes (replace AAAK entity codes)

| Code  | Meaning              | Source pattern                     |
|-------|----------------------|------------------------------------|
| `PG`  | Page component       | `page.tsx`                         |
| `LY`  | Layout               | `layout.tsx`                       |
| `RT`  | API route handler    | `route.ts`                         |
| `CMP` | UI component         | Named `.tsx` in `components/`      |
| `HK`  | Custom hook          | `use*.ts`                          |
| `UT`  | Utility / helper     | `helpers.tsx`, `utils.ts`          |
| `TP`  | Type definitions     | `types.ts`                         |
| `CFG` | Configuration        | `config.ts`, `*.config.*`          |
| `LIB` | Library module       | Files under `lib/`                 |
| `MDW` | Middleware           | `middleware.ts`                    |
| `STY` | Stylesheet           | `*.css`, `*.module.css`            |
| `CTX` | Context provider     | `*-context.tsx`, `*-provider.tsx`  |
| `TEST`| Test file            | `*.test.*`, `*.spec.*`             |
| `API` | API client wrapper   | `api.ts` (client-side fetchers)    |
| `IDX` | Barrel / index       | `index.ts` re-exports              |

### 3.2 Syntax Codes (replace AAAK emotion codes)

Syntax codes occupy the same slot as AAAK emotions — `+`-joined, max 4 per line.

| Code   | Meaning                       | Detects / maps to                         |
|--------|-------------------------------|-------------------------------------------|
| `tsx`  | JSX rendering                 | Returns JSX, `<Component />` in source    |
| `hk`   | React hooks                   | `useState`, `useEffect`, `useRef`, `useMemo`, `useCallback` |
| `ftc`  | Data fetching                 | `fetch()`, API calls, `useSWR`, loaders   |
| `st`   | State management              | `useState`, `useReducer`, context state   |
| `eff`  | Side effects                  | `useEffect`, `useLayoutEffect`            |
| `prp`  | Props interface               | Component accepts typed props             |
| `ctx`  | Context usage                 | `useContext`, `createContext`, providers   |
| `frm`  | Form handling                 | `<form>`, `onSubmit`, controlled inputs   |
| `auth` | Authentication                | Auth checks, session, login flows         |
| `cch`  | Caching                       | `cache()`, `revalidate`, `unstable_cache` |
| `ssr`  | Server-side rendering/logic   | Server components, `getServerSideProps`   |
| `mut`  | Data mutation                 | POST/PUT/DELETE, `setState` from user action |
| `qry`  | Query / search / filtering    | URL params, search inputs, filter logic   |
| `val`  | Validation                    | Input validation, schema checks, guards   |
| `err`  | Error handling                | try/catch, error boundaries, fallback UI  |
| `nav`  | Routing / navigation          | `useRouter`, `Link`, redirects            |
| `sty`  | Dynamic styling               | `cn()`, conditional classes, CSS vars     |
| `tbl`  | Table / data display          | `<Table>`, column defs, row rendering     |
| `chrt` | Charts / visualization        | Chart components, D3, Recharts            |
| `mod`  | Modal / dialog                | `<Dialog>`, `<AlertDialog>`, overlays     |
| `sort` | Sorting logic                 | Sort state, `sortData()`, comparators     |
| `flt`  | Filtering logic               | Filter state, predicate functions         |
| `ws`   | WebSocket / realtime          | `WebSocket`, SSE, polling                 |
| `calc` | Computation / algorithm       | Math, aggregation, strategy functions     |
| `anm`  | Animation / transition        | `framer-motion`, CSS transitions          |
| `dl`   | Download / export             | File generation, CSV, blob download       |
| `pag`  | Pagination                    | Page controls, offset/limit               |

### 3.3 Type Shorthands

| Short | Full type                    |
|-------|------------------------------|
| `str` | `string`                     |
| `num` | `number`                     |
| `b`   | `boolean`                    |
| `R<K,V>` | `Record<K,V>`            |
| `T[]` | Array of T                   |
| `T?`  | `T \| null`                  |
| `fn`  | Function                     |
| `void`| `void`                       |
| `json`| JSON object response         |
| `P<T>`| `Promise<T>`                 |

### 3.4 Flags (replace AAAK importance flags)

| Flag      | Meaning                                | Signals                           |
|-----------|----------------------------------------|-----------------------------------|
| `@ENTRY`  | Page entry point                       | `page.tsx`, `layout.tsx`          |
| `@API`    | API boundary                           | `route.ts`, POST/GET handlers     |
| `@SHARE`  | Shared / reusable component            | Used by 3+ consumers              |
| `@PURE`   | Pure function (no side effects)        | No hooks, no fetch, deterministic |
| `@ASYNC`  | Async operation                        | `async function`, `.then()`, `await` |
| `@SSR`    | Server-side only                       | Server component, no `"use client"` |
| `@CSR`    | Client-side only                       | `"use client"` directive          |
| `@GUARD`  | Auth / access guard                    | Auth checks, role gates           |
| `@HEAVY`  | Performance-critical                   | Large datasets, expensive compute |
| `@CORE`   | Core module, widely depended on        | Imported by 5+ files              |
| `@EDGE`   | Edge runtime                           | `runtime = 'edge'`               |
| `@DYN`    | Dynamic / force-dynamic                | `export const dynamic = 'force-dynamic'` |

Flags are `+`-joined. Max 3 per file.

---

## 4. Operators & Symbols

| Symbol  | Meaning                       | Example                                 |
|---------|-------------------------------|-----------------------------------------|
| `\|`    | Field separator               | `app/strat\|page.tsx\|PG`               |
| `+`     | Multi-value conjunction       | `tsx+hk+ftc`, `@ENTRY+@CSR`             |
| `>>`    | Export                        | `>>PageConfig`                          |
| `<<`    | Import                        | `<<react{useState},./api`              |
| `$`     | State variable                | `$loading:b=true`                       |
| `~`     | Effect / lifecycle hook       | `~mount→fetch→$data`                    |
| `→`     | Data flow / transforms        | `fetchPairs→$pairs(buildMarkets)`       |
| `:`     | Type annotation               | `$data:Transaction[]`                   |
| `=`     | Default value                 | `$sort:SortState={col:"pair",dir:"asc"}`|
| `{}`    | Destructured / named imports  | `react{useState,useEffect}`             |
| `<>`    | JSX element / generic         | `<Card><Table rows={data}/>`            |
| `[]`    | Dependency array              | `~[$strategy,$pair]`                    |
| `()`    | Transform / params            | `→$totals(calcTotals)`                  |
| `?`     | Nullable type                 | `$error:str?`                           |
| `,`     | List separator within field   | `$a:str,$b:num`                         |
| `W:`    | Wire (cross-file ref)         | `W:page.tsx→api.ts\|fetchPairs`         |
| `/`     | Path separator                | `app/strat/page.tsx`                    |
| `---`   | Block separator               | Between file blocks                     |

---

## 5. Import Compression

Long import paths are compressed using alias rules:

| Pattern                          | Compressed form        |
|----------------------------------|------------------------|
| `@/components/ui/card`           | `ui{card}`             |
| `@/components/ui/button`         | `ui{btn}`              |
| `@/components/ui/select`         | `ui{select}`           |
| `@/components/ui/skeleton`       | `ui{skeleton}`         |
| `@/components/ui/dialog`         | `ui{dialog}`           |
| `@/components/ui/alert-dialog`   | `ui{alert-dialog}`     |
| `@/components/asset-pair-filter` | `cmp{asset-pair-flt}`  |
| `@/components/badge-led`         | `cmp{badge-led}`       |
| `@/config/types`                 | `cfg/types`            |
| `@/lib/vortex`                   | `lib/vortex`           |
| `@/lib/common/*`                 | `lib/common/*`         |
| `react`                          | `react`                |
| `next/server`                    | `next/server`          |
| `./types`                        | `./types`              |
| `./api`                          | `./api`                |
| `./helpers`                      | `./helpers`            |
| `@radix-ui/react-icons`         | `radix/icons`          |
| `sonner`                         | `sonner`               |

**Rule:** Strip `@/components/ui/` → `ui{}`. Strip `@/components/` → `cmp{}`. Strip `@/` for `lib/`, `config/`. Keep relative and bare module names as-is. Abbreviate known long names (`button` → `btn`, `filter` → `flt`).

---

## 6. Full Examples

### 6.1 Page Component (`app/sumtransactions/page.tsx`)

```
app/sumtransactions|page.tsx|PG
>>PageSumTransactions|<<react{useState,useEffect},ui{card,skeleton,select},./api,./types,./helpers
$data:Transaction[]=[]|$totals:Totals?=null|$sort:SortState|$loading:b=true
~mount→fetchSumTransactions→$data,$totals(calcTotals)
<Card>{$loading?<Skeleton/>:<DataTable rows={sorted} totals/>}|tsx+hk+ftc+tbl+sort|@ENTRY+@CSR
B:FETCH fetchSumTransactions()→$data,$totals(calcTotals),$loading(false)
B:LET sorted=sortData(data,sort)
B:RET <Card><CardContent>{B:JSXCOND $loading?<Skeleton/>:<DataTable rows={sorted} totals={totals}/>}</CardContent></Card>
W:page.tsx→api.ts|fetchSumTransactions
W:page.tsx→helpers.tsx|calcTotals,sortData,buildMarkets
```

### 6.2 API Route (`app/api/orderbook/route.ts`)

```
app/market|route.ts|RT
>>POST:handler|<<next/server{NextResponse},lib/vortex{getClient}
POST /api/orderbook {market:str}→{name,data:{timestamp,bids[],asks[]}}|ftc+val|@API+@ASYNC+@DYN
```

### 6.3 Type Definitions (`app/sumtransactions/types.ts`)

```
app/sumtransactions|types.ts|TP
>>{Transaction,Totals,Market,ConfigResponse,SortColumn,SortState}
Transaction{pair:str,qty:num,price:num,side:str,date:str}
Totals{count:num,volume:num,value:num}
SortState{col:SortColumn,dir:"asc"|"desc"}|@PURE
```

### 6.4 Utility / Helpers (`app/sumtransactions/helpers.tsx`)

```
app/sumtransactions|helpers.tsx|UT
>>{buildMarkets,calcTotals,sortData,SortIndicator,formatPairAsset}
buildMarkets(data:Transaction[])→Market[]
calcTotals(data:Transaction[])→Totals
sortData(data:Transaction[],sort:SortState)→Transaction[]
SortIndicator(props:{col,sort,onSort})→tsx|calc+sort+tsx|@PURE
```

### 6.5 Layout (`app/sumtransactions/layout.tsx`)

```
app/sumtransactions|layout.tsx|LY
>>metadata:{title:"Vortex:Sum Transactions"}|<<next|@ENTRY+@SSR
```

### 6.6 Configuration Page (`app/config/page.tsx`)

```
app/configuration|page.tsx|PG
>>PageConfig|<<react{useState,useEffect},ui{card,btn,input,label,select,skeleton,alert-dialog},cmp{asset-pair-flt,badge-led},cfg/types,radix/icons,sonner
$config:ConfigJson?=null|$error:str?=null|$saving:b=false|$wallets:WalletOption[]=[]
$regenerating:b=false|$loadingColours:b=false|$newExchangeKey:str=""
~mount→fetchConfig→$config,$wallets
<Card><form>{fields,selects,badge-leds}</form><AlertDialog confirm={save}/>|tsx+hk+ftc+frm+mut+mod|@ENTRY+@CSR
```

### 6.7 Strategy Simulator Tab (`app/strat/simulator-tab.tsx`)

```
app/strat|simulator-tab.tsx|CMP
>>SimulatorTab|<<react{useState,useEffect,useRef},./types{AnnealingResult,SimConfig}
$result:AnnealingResult?=null|$cancelRef:ref<b>=false|$paramsLoading:b=true|$strategyParams:R<str,num>={}
~mount→fetch(/api/strat/parameters/${selectedStrategy}/XBTZAR)→$strategyParams
~[$selectedStrategy]→refetch→$strategyParams
<ParamsForm params=$strategyParams/><RunButton/><ResultChart data=$result/>|tsx+hk+ftc+calc+chrt|@CSR+@HEAVY
```

### 6.8 Hook (`lib/common/use-polling.ts`)

```
lib/common|use-polling.ts|HK
>>usePolling(url:str,interval:num)→{data:T?,loading:b,error:str?}
$data:T?=null|$loading:b=true|$error:str?=null
~int(interval)→fetch(url)→$data|hk+ftc+eff|@SHARE
```

### 6.9 Library Module (`lib/strategies/index.ts`)

```
lib/strategies|index.ts|IDX
>>{getStrategy,getDefaultStrategy,listStrategies,getPairStrategyMap}
getStrategy(name:str)→StratFunction|getDefaultStrategy()→StratFunction
listStrategies()→str[]|getPairStrategyMap()→R<str,str>
registry:R<str,StratModule>|calc|@CORE
```

---

## 7. Block Separator & Multi-file Documents

Multiple file blocks are separated by `---`, same as AAAK:

```
app/strat|page.tsx|PG
>>PageStrat|<<react,ui{card,tabs},./run-tab,./simulator-tab,./training-tab
<Tabs><RunTab/><SimulatorTab/><TrainingTab/>|tsx+hk+nav|@ENTRY+@CSR
---
app/strat|run-tab.tsx|CMP
>>RunTab|<<react{useState,useEffect},./types,./api
$mode:RunMode="simulate"|$params:StratParameters={}|$result:RunResult?=null
~[$strategy]→fetchParams→$params
<Select mode/><ParamsGrid/><RunButton/><ResultTable/>|tsx+hk+ftc+tbl+calc|@CSR
---
app/strat|types.ts|TP
>>{RunMode,StratParameters,RunResult,AnnealingResult,SimConfig}
RunMode="simulate"|"historic"
RunResult{totalPnl:num,sharpeRatio:num,maxDrawdownPct:num,totalTrades:num,...}|@PURE
```

---

## 8. Transpilation

### 8.1 VXL → Source Scaffold

Each line type maps to a code generation rule:

| VXL line              | Generates                                      |
|-----------------------|------------------------------------------------|
| Header `PATH\|FILE\|PG` | File path, `"use client"` if `@CSR`           |
| `>>Name`              | `export default function Name() {`             |
| `>>{a,b}`             | `export function a(…) {` + `export function b(…) {` |
| `<<react{useState}`   | `import { useState } from "react";`           |
| `<<ui{card,btn}`      | `import { Card } from "@/components/ui/card";` + `import { Button } from "@/components/ui/button";` |
| `$x:T=v`              | `const [x, setX] = useState<T>(v);`           |
| `$x:ref<T>=v`         | `const x = useRef<T>(v);`                     |
| `~mount→fn→$x`        | `useEffect(() => { fn().then(setX); }, []);`   |
| `~[$dep]→fn→$x`       | `useEffect(() => { fn().then(setX); }, [dep]);`|
| `~int(n)→fn→$x`       | `useEffect(() => { const id = setInterval(…); return () => clearInterval(id); }, []);` |
| `<Card><Table/>`      | JSX return block with nested components        |
| `W:a→b\|fn`           | Import verification / dependency annotation    |
| `Type{f:T,g:T}`       | `interface Type { f: T; g: T; }`              |
| `fn(a:T)→R`           | `export function fn(a: T): R {`               |
| `GET /path→json`      | `export async function GET(req) { … }`        |
| `POST /path {body}→R` | `export async function POST(req) { … }`       |
| `B:LET x=expr`        | `const x = expr;`                              |
| `B:CALL fn(a)`        | `fn(a);`                                        |
| `B:ASSIGN $x(v)`      | `setX(v);`                                      |
| `B:FETCH fn()→$a,$b(tx)` | `.then(res => { setA(res); setB(tx(res)); })` |
| `B:GUARD cond→return` | `if (cond) return;`                             |
| `B:IF cond→{…}`       | `if (cond) { … }`                              |
| `B:RET expr`          | `return expr;`                                  |
| `B:MEMO x=expr,[deps]`| `const x = useMemo(() => expr, [deps]);`       |
| `B:CB fn(p)→{…},[d]`  | `const fn = useCallback((p) => { … }, [d]);`  |
| `B:JSXCOND c?<A/>:<B/>`| `{c ? <A /> : <B />}`                         |
| `B:JSXMAP a→(i)=><C/>`| `{a.map((i) => <C />)}`                        |
| `B:RAW code`          | Verbatim pass-through                           |

### 8.2 Source → VXL (Mining)

Source code is converted to VXL by extracting:

1. **File metadata** → header line (path, name, type code from extension + location)
2. **Import statements** → `<<` with alias compression (§5)
3. **Export declarations** → `>>`
4. **`useState`/`useRef` calls** → `$` state declarations with types
5. **`useEffect` bodies** → `~` effect lines with trigger and target analysis
6. **JSX return** → `<>` compressed tree (top-level structural components only)
7. **Syntax pattern detection** → syntax codes (scan for hooks, fetch, forms, tables, etc.)
8. **Structural analysis** → flags (entry point, SSR/CSR, guard, etc.)
9. **Import/usage cross-refs** → `W:` wire lines

### 8.3 AAAK → VXL Translation

Since AAAK drawers in the `app` wing already contain mined code knowledge, AAAK→VXL maps:

| AAAK field     | VXL field                |
|----------------|--------------------------|
| Entity codes   | File-type code (`PG`, `RT`, `CMP`, …) — inferred from source filename in header |
| Topics         | Import modules + state variable names |
| Key quote      | Export signature or key JSX           |
| Emotions       | Syntax codes (see translation table §3.2) |
| Flags          | VXL flags (see §3.4)   |
| Tunnels        | Wire lines `W:`         |

---

## 9. Grammar (EBNF)

```ebnf
block       = header NL [export_line NL] [state_line NL] {effect_line NL}
              render_line {NL body_line} {NL wire_line} ;
header      = path "|" filename "|" type_code ;
path        = segment {"/" segment} ;
filename    = IDENT "." EXT ;
type_code   = "PG" | "LY" | "RT" | "CMP" | "HK" | "UT" | "TP" | "CFG"
            | "LIB" | "MDW" | "STY" | "CTX" | "TEST" | "API" | "IDX" ;

export_line = exports ["|" imports] ;
exports     = ">>" export_list ;
export_list = name | "{" name {"," name} "}" | method ":" name ;
imports     = "<<" import_item {"," import_item} ;
import_item = module_ref ["{" name {"," name} "}"] ;

state_line  = state_decl {"|" state_decl} ;
state_decl  = "$" IDENT ":" type_expr ["=" value] ;
type_expr   = IDENT ["[]"] ["?"] | "R<" type_expr "," type_expr ">"
            | "ref<" type_expr ">" | "P<" type_expr ">" ;

effect_line = "~" trigger "→" action {"→" target} ;
trigger     = "mount" | "[" "$" IDENT {"," "$" IDENT} "]" | "int(" NUMBER ")" ;
action      = IDENT | "fetch(" path ")" | "refetch" ;
target      = "$" IDENT ["(" transform ")"] ;

render_line = jsx_frag "|" syntax_codes "|" flags ;
jsx_frag    = "<" IDENT {attr | jsx_frag} "/>" | "{" expr "}" ;
syntax_codes= code {"+" code} ;
code        = "tsx" | "hk" | "ftc" | "st" | "eff" | "prp" | "ctx" | "frm"
            | "auth" | "cch" | "ssr" | "mut" | "qry" | "val" | "err" | "nav"
            | "sty" | "tbl" | "chrt" | "mod" | "sort" | "flt" | "ws" | "calc"
            | "anm" | "dl" | "pag" ;
flags       = flag {"+" flag} ;
flag        = "@ENTRY" | "@API" | "@SHARE" | "@PURE" | "@ASYNC" | "@SSR"
            | "@CSR" | "@GUARD" | "@HEAVY" | "@CORE" | "@EDGE" | "@DYN" ;

body_line   = "B:" body_code " " body_args ;
body_code   = "LET" | "CALL" | "ASSIGN" | "AWAIT" | "FETCH" | "AFETCH"
            | "GUARD" | "IF" | "ELIF" | "ELSE" | "RET" | "TERN"
            | "MAP" | "FILTER" | "REDUCE" | "SORT" | "SPREAD"
            | "TRY" | "CATCH" | "FINALLY" | "CB" | "MEMO"
            | "TOAST" | "NAV" | "LOG" | "HANDLE" | "SUBMIT"
            | "DESTRUCT" | "JSXMAP" | "JSXCOND" | "FN" | "END" | "RAW" ;
body_args   = (* pattern-specific, see §2.7.1 *) ;

wire_line   = "W:" filename "→" filename "|" label ;

document    = block {"---" NL block} ;
```

---

## 10. Relationship to AAAK

| Dimension       | AAAK                          | VXL                              |
|-----------------|-------------------------------|----------------------------------|
| Domain          | Narrative knowledge           | Source code structure             |
| Entity codes    | Person names → 3-char codes   | File types → 2-3 char codes      |
| Emotion codes   | `joy`, `fear`, `trust`, …     | `tsx`, `hk`, `ftc`, `tbl`, …     |
| Flags           | `ORIGIN`, `PIVOT`, `DECISION` | `@ENTRY`, `@API`, `@CORE`        |
| Key quote       | Most important sentence       | Export signature / key JSX        |
| Tunnels         | Cross-zettel references       | Cross-file wires (`W:`)          |
| Arc             | Emotional progression         | Data flow (`→` chains)           |
| Compression     | ~30× vs prose                 | ~20× vs source code              |
| Header          | `FILE\|ENTITY\|DATE\|TITLE`   | `PATH\|FILENAME\|TYPE`           |
| Line separator  | `\|`                          | `\|`                             |
| Block separator | `---`                         | `---`                            |

VXL inherits AAAK's core philosophy: pipe-delimited fields, `+`-joined multi-values, symbolic density, and deterministic encoding. It replaces the emotional/narrative vocabulary with a code-structure vocabulary while keeping the same compression architecture.

---

## 11. Design Principles

1. **Developer-native** — Every symbol maps 1:1 to a React/TS/Next.js concept. No learning curve for someone who already reads code.
2. **AAAK-compatible** — Same structural grammar (pipes, pluses, arrows, flags). An agent fluent in AAAK reads VXL immediately.
3. **Scaffold-complete** — A VXL block contains enough information to generate a working file skeleton with correct imports, state, effects, and component structure.
4. **Mine-able** — Source code can be mechanically converted to VXL by static analysis (AST walk + pattern detection).
5. **Composable** — Multi-file blocks concatenate with `---`. A full feature can be described in one VXL document.
6. **Concise** — Target ~20× compression. Every character carries structural meaning. No prose, no comments, no boilerplate.
