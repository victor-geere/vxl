# Hilbert Maze — Specification

Single-file HTML/CSS/JS application. No external dependencies beyond the Google Fonts CDN. Output: `hilbert.html`.

---

## 1. Overview

An interactive Hilbert curve maze rendered on an HTML5 Canvas. Each cell is labelled with an alphanumeric coordinate (column letter + row number). The Hilbert curve defines the maze structure; random paths through the curve are overlaid and selectable. Users control the curve order, canvas scale, number of paths, and which path is highlighted. A scrollable path table below the canvas shows each path's step-by-step directions and cell names. A reset button regenerates paths.

---

## 2. Visual Design

### Design Language

Neomorphic ("neumorphic") design system throughout. Background and surfaces share a single matte colour; depth is expressed through paired light/dark directional shadows rather than borders.

### Design Tokens

```css
--neo-bg:            #e0e5ec  /* page + surface background */
--neo-text:          #2c3e50  /* primary text */
--neo-shadow-light:  #ffffff  /* highlight shadow */
--neo-shadow-dark:   #c0c5ce  /* depth shadow */
--neo-accent:        #3498db  /* blue accent */
--neo-accent-secondary: #2ecc71 /* green accent */
--muted-foreground:  #6b7280  /* secondary text */
--border:            #b0bec5  /* dividers */
```

Font: **Inter** (loaded from Google Fonts), fallback system sans-serif stack.

### Layout

- `body`: flex column, centered, `padding: 32px 16px`, `background: var(--neo-bg)`
- All content inside `.app-col`: flex column, `max-width: 95vw`, `gap: 24px`
- Three rows stacked vertically: `.controls`, `.canvas-wrap`, `#table-wrap`

### Neomorphic Component Classes

| Class | Shadow pattern | Usage |
|---|---|---|
| `.neo-card` | `9/9/16px` outer dark+light pair | `#path-card` |
| `.neo-card-inset` | `6/6/12px` inset dark+light pair | `.canvas-wrap`, `#table-wrap` |
| `.neo-button` | `6/6/12px` outer; inset on `:active` | Reset button |

### Canvas Element

- The `<canvas>` has no border and square corners (`border-radius: 0`)
- The canvas background is filled with `#e0e5ec` on each render

### Color Palette

| Element | Color | Notes |
|---|---|---|
| Page + canvas background | `#e0e5ec` | Same colour — canvas blends into page |
| Grid lines | `#c0c5ce` | 1px |
| Cell labels | `#6b7280` | Top-left of each cell |
| Hilbert curve | `#e0e5ec` | Invisible — same as background |
| Hilbert curve endpoints | `#3498db` | Blue filled circle at `d=0` and `d=4^n−1` |
| Paths (unselected) | `rgba(52,152,219,0.6)` | 3px, alpha 0.8 |
| Selected path | `#FF6600` | 3.5px, fully opaque |
| Entry markers | Same as path color | Dot at boundary + line to cell center |
| Terminus dot (selected path only) | `#FF6600` | Filled circle at path end cell |

---

## 3. Grid & Cell Labels

### Grid

- Slider `n` (order, 1–6) sets dimensions: `2^n × 2^n` cells
- Base canvas size: `gridDim = round(512 × scale)`. Cell size: `cs = gridDim / 2^n`
- **1-cell padding** on all four sides of the grid. Total canvas dimension: `dim = gridDim + 2 × cs`
- Canvas background filled solid `#e0e5ec`; grid lines drawn inside the padding area
- Outer boundary drawn edge-by-edge; segments are omitted for entry openings

### Cell Naming

- **Columns** (x-axis, left→right): `A`, `B`, … `Z`, `AA`, `AB`, … (spreadsheet-style)
- **Rows** (y-axis, top→bottom): `1`, `2`, … `2^n`
- Internal Hilbert y-coordinate (`hy`) has `hy=0` at the bottom, `hy=2^n−1` at the top
- Row number in label = `2^n − hy` (so bottom cell gets the highest row number)
- Format: column letters immediately followed by row number. E.g. `A1` (top-left), `H8` (bottom-right of 8×8)
- Labels placed in the **top-left** corner of each cell with an 8% inset
- Font: Inter 500, `min(24, max(6, cs × 0.28))px`; label skipped if it would exceed 85% of cell width

---

## 4. Hilbert Curve

### Algorithm

- Iterative `d2xy(order, d)` — linear index `d` (0 to `4^n − 1`) → `{x, y}`
- Inverse `xy2d(order, x, y)` — coordinates → linear index
- Standard bit-rotation algorithm; no recursion
- `hy=0` is at the bottom of the canvas (bottom row)

### Rendering

- Stroke color `#e0e5ec` — same as background, making the curve **invisible** (structure only)
- `lineWidth: 2`, `lineJoin: 'round'`, `lineCap: 'round'`
- **Blue dots** (`#3498db`, radius `max(4, cs × 0.13)`) drawn at the start (`d=0`) and end (`d=4^n−1`) of the curve

---

## 5. Maze Interpretation

### Wall Rules

- Every cell has 4 walls (N, S, E, W)
- For consecutive cells `d` and `d+1` in the Hilbert sequence, the shared wall is **removed** (passage)
- All other walls remain, including the outer boundary
- Result: a perfect maze with exactly 2 dead ends — `d=0` and `d=4^n−1`

### Visualization

- Walls are implied by the grid lines; passages are implied by the curve
- Entry openings are shown by omitting the corresponding outer-boundary segment when drawing the grid
- The Hilbert curve itself is not visually drawn; paths follow its structure

---

## 6. Path Generation

### Entry Point Selection

1. Collect all edge cells (top row, bottom row, left col, right col), deduplicated — total `4 × 2^n − 4`
2. Shuffle the full edge-cell list
3. Pick up to `desired` cells in order; for each, call `pickWall(x, y, gs)` which randomly selects one of the cell's outer walls (corner cells may have 2 options)
4. Find that cell's Hilbert index via `xy2d(order, x, y)`
5. Choose a random direction along the curve: toward `d=0` (negative) or toward `d=4^n−1` (positive)
6. Collect all curve cells from the entry cell to the chosen endpoint

### Path Filtering & Sorting

After generating raw paths, apply in order:
1. **Filter**: discard paths with fewer than 3 cells (step count < 2)
2. **Sort**: ascending by path length (shortest first)
3. **Cap**: keep at most 8 paths

The `Paths` slider controls how many raw candidates are attempted before filtering. After filtering, the actual count may be lower.

### Rendering

- Draw each path as connected line segments through cell centers
- **Unselected paths**: `rgba(52,152,219,0.6)`, 3px, `globalAlpha 0.8`
- **Selected path**: `#FF6600`, 3.5px, fully opaque, drawn last (on top of unselected)
- **Straight-through segments** (cells where the path runs straight — same x or same y for three consecutive cells): drawn as **dashed** (`[dash, dash]` where `dash = max(3, cs × 0.15)`)
- **Turning segments**: drawn as solid lines

### Entry Markers

For each path, at the entry cell:
- Compute boundary point `(bx, by)`: midpoint of the opened wall segment (half a cell-size from the cell center toward the open wall)
- Draw a **filled circle** at `(bx, by)`, radius `max(3, cs × 0.1)`, color matches path
- Draw a **line** from `(bx, by)` to the entry cell center

### Terminus Marker

- For the **selected path only**: draw an orange filled circle (`#FF6600`, radius `mr × 1.2`) at the center of the last cell in the path
- No terminus marker for unselected paths

---

## 7. Controls

Horizontal wrapping row above the canvas, styled as a neomorphic inset.

| Control | Element | Range | Default | Label format | Effect |
|---|---|---|---|---|---|
| Order | `input[range]` | 1–6 | 3 | `"Order: 3 (8×8)"` | Regenerate curve + paths + table |
| Scale | `input[range]` | 0.5–3.0 (step 0.1) | 1.0 | `"Scale: 1.0×"` | Resize canvas, repaint only |
| Paths | `input[range]` | 1–20 | 5 | `"Paths: 5"` (actual count after filter) | Regenerate paths, filter, sort, cap |
| Selected | `input[range]` | 1–n | 1 | `"Selected: 1"` | Highlight nth path, repaint |
| Reset | `button.neo-button` | — | — | "Reset" | Regenerate paths + entries |

**Scale slider**: HTML attribute `min=5, max=30, value=10`; internal value divided by 10 to get `scale` in [0.5, 3.0].

**Label updates**: all labels update in real time on each slider input event. The `Paths` label shows the actual number of paths retained after filtering, not the slider value. The `Selected` slider max is clamped to the actual path count.

---

## 8. State & Event Flow

### State Object

```js
const S = {
  order:   3,    // curve order; grid is 2^order × 2^order
  scale:   1.0,  // canvas scale multiplier
  selPath: 1,    // 1-indexed selected path
  curve:   [],   // [{x, y}, …] in Hilbert order, length 4^order
  paths:   [],   // [[{x, y}, …], …] after filter/sort/cap
  entries: [],   // [{x, y, wall}, …] parallel to paths
};
const BASE = 512;          // base canvas pixels before scale
const MAX_TABLE_COLS = 150; // truncation limit
```

### Event → Action

| Event | Action |
|---|---|
| Order change | `regenerateAll()`: rebuild curve, regeneratePaths, render |
| Scale change | update `S.scale`, `updateLabels()`, `render()` |
| Paths change | `regeneratePaths()`: new paths, filter, sort, cap, render |
| Selected change | update `S.selPath`, `updateLabels()`, `render()` |
| Reset | `regenerateAll()` |

### Paint Cycle (back to front)

1. Fill canvas `#e0e5ec`
2. `drawGrid` — grid lines + boundary with entry gaps
3. `drawLabels` — cell names top-left of each cell
4. `drawCurve` — invisible stroke + blue endpoint dots
5. `drawPaths` — unselected (blue) paths, then selected (orange) path
6. `drawMarkers` — entry line+dot per path; orange terminus dot for selected path
7. `buildTable` — rebuild DOM path table

After `buildTable`, JS sets `#path-card` width to match `#maze-card` (canvas dim + 32px for maze-card padding).

---

## 9. Layout

```
.app-col
├── .controls            (neo inset: 4/4/8px)
├── .canvas-wrap         (neo-card-inset + flex row)
│   ├── #maze-card       (flat-carved: outer 1px border + subtle inset shadow, inline style)
│   │   └── canvas        (no border, no border-radius)
│   └── #path-card       (neo-card, empty, width = maze-card width)
└── #table-wrap           (neo-card-inset, max-height 420px, overflow: auto)
    └── #ptable
```

**`#maze-card`**: styled with inline `style` — `background: var(--neo-bg)`, a 1px solid border, and a subtle box-shadow. No CSS class.

**`#path-card`**: empty at runtime — the `buildPathCard()` function is defined but not called. Width is set in JS to equal the maze-card width (canvas dimension + 32px to account for maze-card's 16px padding on each side).

**`.canvas-wrap`** overrides `.neo-card-inset` to add `display: flex; flex-direction: row; gap: 20px; padding: 20px`.

---

## 10. Path Table

A scrollable HTML table in `#table-wrap` rebuilt on every render.

### Structure

Each path occupies **two rows**:
- **Row 1 — Directions**: `—` (em-dash U+2014) for the first cell, then N/E/S/W for each subsequent step
- **Row 2 — Cell names**: alphanumeric name of each cell visited

Row header (`<th>`, `rowSpan=2`): `"Path N"` or `"Path N (total)"` if truncated.

### Truncation

Paths longer than `MAX_TABLE_COLS` (150) are truncated: show first 75 cells + `…` + last 75 cells.

### Styling

- Selected path rows: `class="sel"` → light orange background (`#FFF3E6` cells, `#FFE8CC` header)
- Path separator: `class="sep"` on first row of each path after the first → `border-top: 2px solid var(--border)`
- `#ptable th` is `position: sticky; left: 0` so path labels stay visible while scrolling horizontally
- Table scrolls horizontally for long paths; `#table-wrap` cap at 420px height with vertical overflow

### Direction Computation

For consecutive Hilbert coordinates `(x1, y1)` → `(x2, y2)`:
- `x2 > x1` → `E`
- `x2 < x1` → `W`
- `y2 > y1` → `N` (Hilbert y increases upward on canvas)
- `y2 < y1` → `S`

---

## 11. Design Decisions

| Decision | Rationale |
|---|---|
| Single order slider (not independent X/Y) | Hilbert curve requires a square `2^n × 2^n` grid. Independent axes would leave cells unreachable. |
| Canvas over SVG | Up to 64×64 = 4096 cells at order 6. Canvas handles bulk painting efficiently; SVG would create thousands of DOM elements. |
| Curve rendered invisible (same color as background) | The curve's structure is implied by the paths; the visible curve would visually clutter the maze. Blue endpoint dots mark the two dead ends. |
| Paths follow curve in a random direction | Produces visual variety in path lengths. Entry cells near the middle of the curve can traverse toward either dead end. |
| Alphanumeric cell names | Column-letter + row-number (A1, B2, …) are immediately readable and map naturally to the path table. Familiar spreadsheet convention. |
| Dashed straight-through segments | Visually distinguishes segments where the path runs straight versus where it turns, making the maze structure more legible. |
| Path filtering and cap | Paths shorter than 3 steps and the longest paths are excluded to keep the table readable and paths meaningfully long. |
| 1-cell padding on canvas | Provides visual breathing room around the grid and space for entry markers outside the boundary. |
| Base canvas size 512px | Comfortable default. Scale slider [0.5×–3.0×] covers small screens to large monitors. |
| Neomorphic design | Consistent with the project's styleguide (styleguide.html). Uses paired directional shadows on a shared background rather than borders. |

---

## 12. Verification

1. Open `hilbert.html` in a browser — grid renders on `#e0e5ec` background with cell labels in the top-left of each cell
2. Canvas background matches page background; grid blends naturally
3. Blue dots appear at the Hilbert curve start (`d=0`) and end (`d=4^n−1`) positions
4. Order slider: grid, labels, curve dots, paths, and path table all regenerate; label shows `"Order: N (M×M)"`
5. Scale slider: canvas resizes smoothly, cell size and padding scale proportionally
6. Paths slider: `"Paths: N"` reflects the actual count after filter/sort/cap (not the raw slider value)
7. Selector slider max clamps to actual path count; changing it repaints paths without regenerating
8. Reset button regenerates new random paths; curve structure unchanged
9. Straight-through segments of each path appear dashed; turning segments solid
10. Orange entry dot and orange line visible for selected path; blue for unselected
11. Orange terminus dot at the last cell of the selected path only
12. Path table rows for selected path have light orange background
13. Long paths truncate with `…` in the table at 150 columns
14. `#path-card` is empty and the same width as `#maze-card`
15. Order 6 (64×64, 4096 cells) renders without noticeable lag

