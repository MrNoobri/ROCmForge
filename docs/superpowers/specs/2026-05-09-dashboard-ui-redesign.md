# ROCmForge Dashboard UI Redesign

**Date:** 2026-05-09  
**Status:** Approved  
**Approach:** Streamlit-native (Option A) — embedded HTML/CSS/JS via `st.markdown()` and `st.components.v1.html()`

---

## 1. Color System

Replace all existing `--rocm-primary` green (oklch lime) with AMD brand red throughout.

| Token | Value | Usage |
|---|---|---|
| `--amd-red` | `#ED1C24` | Primary accent, active states, borders, CTAs |
| `--amd-red-glow` | `rgba(237,28,36,0.35)` | Box-shadow glow on running agents, hover states |
| `--amd-dark` | `#0a0a0f` | Page background |
| `--amd-surface` | `rgba(255,255,255,0.04)` | Card/tile background |
| `--amd-surface-hover` | `rgba(255,255,255,0.07)` | Card hover state |
| `--amd-text` | `#f0f0f0` | Primary text |
| `--amd-muted` | `rgba(240,240,240,0.45)` | Secondary/muted text |
| `--amd-success` | `#22c55e` | Completed agent check, QA pass |
| `--amd-border` | `rgba(255,255,255,0.08)` | Subtle card borders |

All existing oklch green references in `_dashboard_styles()` are replaced with the above tokens.

---

## 2. Landing Page

### 2a. Animated Blob Background
- 3 large blobs rendered as `position: fixed` divs behind all content
- Colors: `--amd-red` (blob 1), a darker crimson `#8B0000` (blob 2), and near-black `#1a0000` (blob 3)
- Each blob: `border-radius: 50%`, `filter: blur(80px)`, `opacity: 0.18`
- CSS keyframe `@keyframes blob-drift` — translates X/Y ±40px, scales 0.95–1.05, over 8–14s with different `animation-duration` and `animation-delay` per blob so they feel independent
- Blobs sit at `z-index: 0`; all content at `z-index: 1`

### 2b. Hero Section (above the fold)
Layout: two-column grid, left = text, right = empty (blobs visible through it)

**Left column:**
- Kicker tag: `AMD · MI300X` in small caps, AMD red
- H1 headline: "Port CUDA to ROCm. Validated on real AMD silicon."
- Subheadline: "Six-agent pipeline. Deterministic rules + LLM fallback. Real GPU execution."
- 3 stat callouts in a horizontal row (pill-shaped cards):
  - "MI300X · 192GB HBM3"
  - "Avg +40% throughput"  
  - "Real GPU validation"

### 2c. Input Area (directly below hero, same page)
- Section label: "Start Migration" in AMD red
- Two-column layout:
  - Left: GitHub repo URL text input with placeholder "https://github.com/org/repo"
  - Right: Code textarea with placeholder "# or paste your CUDA code here"
- "Migrate →" button below both inputs, full width, AMD red background, white text, subtle hover glow

---

## 3. Agent Pipeline Page

### 3a. Progress Bar
- 3-step stepper: Input Repo → Multi-Agent Flow → Benchmark Diff
- Active step uses AMD red; completed steps use `--amd-success` green; future steps grey
- Thin connecting lines between steps

### 3b. Tab Bar
Two tabs only:
- **Agent Pipeline** — active during run
- **Final Report** — disabled (greyed, non-clickable) until all agents complete; unlocks and auto-activates when pipeline finishes

### 3c. Agent Grid (3×2)
Six agent tiles in a CSS grid (`grid-template-columns: repeat(3, 1fr)`):
1. Code Analyzer
2. Compatibility Agent  
3. Knowledge Agent
4. Migration Engineer
5. QA Tester
6. Report Agent

**Tile states:**

| State | Visual |
|---|---|
| `queued` | Grey border, grey circle icon, muted text, "Queued" label |
| `waiting` | Grey border, grey circle icon, italic label "Waiting for [blocking agent name]..." |
| `running` | AMD red pulsing border (`box-shadow` keyframe `amd-pulse`), spinning indicator, "Running..." |
| `complete` | Solid `--amd-success` border, green checkmark, completion summary line |
| `error` | Red border, X icon, error summary line |

Each tile is `cursor: pointer` and opens the agent popup on click.

### 3d. Agent Popup (Modal)

Triggered by clicking any agent tile. Implemented via a hidden `<div>` with `position: fixed; z-index: 9999` toggled visible via injected JS + Streamlit session state.

**Backdrop:** `position: fixed; inset: 0; backdrop-filter: blur(8px); background: rgba(0,0,0,0.6)`

**Modal structure (3 zones):**

**Zone 1 — Header:**
- Agent name (large), status badge (pill: Running/Complete/Waiting/Error in appropriate color)
- If `waiting`: "Waiting for: [Agent Name]" shown in muted text below status
- Close button (×) top-right

**Zone 2 — Live Log Stream:**
- Scrollable terminal-style div, monospace font, dark background (`#0d0d0d`), AMD red cursor blink
- Each log line prefixed with `> ` 
- Auto-scrolls to bottom as lines are added
- Max height ~40% of modal

**Zone 3 — Output Panel (agent-specific):**

| Agent | Output Panel Content |
|---|---|
| Code Analyzer | Issue count, list of pattern types found (e.g. "14 × torch.cuda calls", "3 × custom .cu kernels") |
| Compatibility Agent | Risk breakdown: High/Medium/Low counts with severity pills |
| Knowledge Agent | Number of ROCm doc chunks retrieved, list of topics covered |
| Migration Engineer | Before/After code diff: two side-by-side panels with syntax highlighting, added lines in green, removed in red |
| QA Tester | Pass/Fail badge, runtime (seconds), GPU memory used (GB), MI300X device name |
| Report Agent | Preview of report summary (first ~200 chars), artifact count |

Click outside modal or press Escape to close.

---

## 4. AMD Splash Screen

Triggered automatically when all 6 agents reach `complete` state. Implemented as a full-screen overlay div injected via `st.components.v1.html()`.

**Layout (centered vertically and horizontally):**
1. "AMD" wordmark in large bold white text with red underline accent
2. "Migration Complete" subtitle in muted text
3. Animated percentage counter: ticks from `0%` to actual improvement value (e.g. `+40.4%`) over 2 seconds using `requestAnimationFrame` JS counter
4. Two stat pills below counter:
   - "X issues found"
   - "Y issues fixed"
5. Countdown progress bar at bottom of modal: drains left-to-right over 6 seconds, AMD red fill
6. "View Report →" button to dismiss early

**Behavior:**
- Auto-dismisses after 6 seconds
- On dismiss (timer or button): overlay fades out, Final Report tab becomes active and auto-selects

**Background:** Same blob animations as landing page for visual continuity, but at reduced opacity (0.12)

---

## 5. Final Report Page

Activated after splash dismisses. Two-level tab structure:

**Outer tabs (reuses existing tab bar):**
- Agent Pipeline (now inactive)
- **Final Report** (now active)

**Inner tabs (4 tabs within Final Report):**

### Tab 1 — Migration Summary
Cards in a 2×2 grid:
- Porting Time (seconds, end-to-end)
- Files Touched (count)
- Lines Changed (+added / -removed)
- Call Conversions (e.g. "14 torch.cuda → torch.hip")
- Custom Kernels Ported (X/Y)
- Overall Readiness Score (percentage, AMD red progress ring)

### Tab 2 — Issues Found & Fixed
Each issue rendered as its own card:
- Header: severity badge + file path + line number
- Body: "Found" description, "Applied Fix" description
- Expandable before/after code snippet (collapsed by default, expand on click)
- Cards sorted by severity (High → Medium → Low)

### Tab 3 — Benchmark
- Two stat callouts side by side: CUDA AVG (red, muted) and ROCm AVG (AMD red, bright)
- Delta callout: `ROCm Δ +X%` in a highlighted box (AMD red background)
- **Line chart** (Plotly `go.Scatter` with `mode='lines'`):
  - X-axis: iteration number
  - Y-axis: step/s
  - Two lines: "Baseline CUDA" (grey/muted red) and "Current ROCm" (AMD red)
  - Chart background dark, grid lines subtle
- Toggle buttons: "Iteration Speed" / "Memory Usage (VRAM)"

### Tab 4 — Code Diff
- File selector dropdown if multiple files were touched
- Full diff view: unified diff format, line numbers shown
- Removed lines: red background tint
- Added lines: green background tint
- Monospace font, scrollable, syntax highlighted

---

## 6. Implementation Notes

### Popup Strategy
Streamlit doesn't natively support modals. Approach:
- Store `selected_agent` in `st.session_state`
- Render the modal HTML/CSS/JS unconditionally but hidden (`display: none`)
- When `selected_agent` is set, re-render with `display: block`
- JS `postMessage` from `st.components.v1.html()` back to Streamlit not needed — clicking tiles sets session state via a hidden `st.button` per tile, triggering a re-render with the modal visible

### Blob Animations
Pure CSS, no JS required. Three `<div class="blob blob-N">` elements inside a fixed container injected once via `st.markdown(..., unsafe_allow_html=True)` at page load. CSS keyframes handle all motion.

### Line Chart
Replace existing `go.Bar` with `go.Scatter(mode='lines', line=dict(width=2.5))` in the benchmark section. Both series on the same figure. Use `fig.update_layout` for dark background matching the design system.

### AMD Color Audit
All occurrences of oklch lime green in `_dashboard_styles()` replaced with AMD red tokens. Specifically:
- `oklch(0.85 0.22 145)` → `#ED1C24`
- `oklch(0.65 0.24 25)` → keep as-is (this is already the crimson/red family)
- Any `#22c55e` or similar greens used for "success" states stay green (they're status indicators, not brand color)

---

## 7. Files Changed

| File | Change |
|---|---|
| `app.py` | All changes — color tokens, landing page, agent tiles, popup modal, splash screen, final report tabs, line chart |

No new files needed. All UI lives in `app.py` consistent with existing architecture.
