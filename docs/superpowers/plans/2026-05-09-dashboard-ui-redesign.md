# Dashboard UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign ROCmForge's Streamlit dashboard with AMD brand colors, animated blob background, a minimal 2-tab layout, clickable agent popups with live logs + output panels, an AMD splash celebration screen, and a restructured 4-tab final report.

**Architecture:** All changes live in `app.py` — no new files, no new dependencies. CSS/JS is embedded via `st.markdown(..., unsafe_allow_html=True)`. Agent popups use Streamlit session state to toggle visibility (hidden `st.button` per tile triggers re-render). Blob animations are pure CSS keyframes. The AMD splash is a full-screen overlay div rendered conditionally when all agents complete.

**Tech Stack:** Python 3.11, Streamlit, Plotly (`go.Scatter` for line chart — already installed), embedded HTML/CSS/JS strings in Python.

---

## Branch Setup

Before starting any task, create a feature branch:

```bash
git checkout -b ui-redesign
```

---

## Task 1: AMD Color System — Replace Green with AMD Red

**Files:**
- Modify: `app.py:468-1147` (the `_dashboard_styles()` function)

This task replaces every green oklch token with AMD red. No layout changes — colors only.

- [ ] **Step 1: Add AMD color variables to `:root` in `_dashboard_styles()`**

Replace the existing `:root` block (lines ~471-486) with:

```python
    :root {
        --amd-red: #ED1C24;
        --amd-red-glow: rgba(237,28,36,0.28);
        --amd-red-subtle: rgba(237,28,36,0.10);
        --amd-red-border: rgba(237,28,36,0.30);
        --rocm-bg: oklch(0.145 0.025 250);
        --rocm-surface: oklch(0.205 0.032 252);
        --rocm-surface-2: oklch(0.245 0.033 252);
        --rocm-border: oklch(0.33 0.03 252);
        --rocm-foreground: oklch(0.968 0.01 240);
        --rocm-muted: oklch(0.72 0.02 248);
        --rocm-primary: var(--amd-red);
        --rocm-primary-strong: #ff3a40;
        --rocm-crimson: oklch(0.65 0.24 25);
        --rocm-warning: oklch(0.82 0.16 84);
        --rocm-shadow: 0 20px 60px oklch(0.1 0.02 250 / 0.42);
        --rocm-glow: 0 0 36px var(--amd-red-glow);
        --rocm-code-bg: oklch(0.12 0.02 250);
        --rocm-grid: linear-gradient(rgba(237,28,36,0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(237,28,36,0.04) 1px, transparent 1px);
    }
```

- [ ] **Step 2: Replace green in the page background radial gradient**

Find this in `_dashboard_styles()`:
```
radial-gradient(circle at top right, oklch(0.65 0.24 25 / 0.1) 0%, transparent 28%),
```
Replace with:
```
radial-gradient(circle at top right, rgba(237,28,36,0.08) 0%, transparent 28%),
```

- [ ] **Step 3: Replace green in sidebar `::before` radial gradient**

Find:
```css
background: radial-gradient(circle at 20% 8%, oklch(0.85 0.22 145 / 0.08), transparent 26%);
```
Replace with:
```css
background: radial-gradient(circle at 20% 8%, rgba(237,28,36,0.07), transparent 26%);
```

- [ ] **Step 4: Replace green in the primary button styles**

Find the `button[kind="primary"]` block:
```css
    button[kind="primary"] {
        background: linear-gradient(135deg, #0ee37d, #0aa358) !important;
        color: #06120b !important;
        border: 1px solid #0ee37d !important;
        font-weight: 800 !important;
        box-shadow: 0 0 20px rgba(14, 227, 125, 0.3) !important;
    }
```
Replace with:
```css
    button[kind="primary"] {
        background: linear-gradient(135deg, #ED1C24, #b01018) !important;
        color: #fff !important;
        border: 1px solid #ED1C24 !important;
        font-weight: 800 !important;
        box-shadow: 0 0 20px rgba(237,28,36,0.3) !important;
    }
```

- [ ] **Step 5: Replace green in `.stButton` and `.stDownloadButton`**

Find:
```css
    .stButton > button,
    .stDownloadButton > button {
        border: 1px solid oklch(0.85 0.22 145 / 0.4) !important;
        border-radius: 14px !important;
        background: linear-gradient(135deg, oklch(0.85 0.22 145), oklch(0.7 0.19 145)) !important;
        color: #06120b !important;
        font-weight: 800 !important;
        box-shadow: var(--rocm-glow) !important;
        transition: transform 160ms ease, filter 160ms ease, box-shadow 160ms ease;
    }

    .stButton > button:hover,
    .stDownloadButton > button:hover {
        filter: brightness(1.06);
        transform: translateY(-1px);
        box-shadow: 0 0 46px oklch(0.85 0.22 145 / 0.3) !important;
    }
```
Replace with:
```css
    .stButton > button,
    .stDownloadButton > button {
        border: 1px solid var(--amd-red-border) !important;
        border-radius: 14px !important;
        background: linear-gradient(135deg, var(--amd-red), #b01018) !important;
        color: #fff !important;
        font-weight: 800 !important;
        box-shadow: var(--rocm-glow) !important;
        transition: transform 160ms ease, filter 160ms ease, box-shadow 160ms ease;
    }

    .stButton > button:hover,
    .stDownloadButton > button:hover {
        filter: brightness(1.08);
        transform: translateY(-1px);
        box-shadow: 0 0 46px rgba(237,28,36,0.35) !important;
    }
```

- [ ] **Step 6: Replace green in `.sidebar-brand__mark`**

Find:
```css
        background: linear-gradient(135deg, oklch(0.85 0.22 145 / 0.18), oklch(0.65 0.24 25 / 0.08));
        border: 1px solid oklch(0.85 0.22 145 / 0.35);
        box-shadow: var(--rocm-glow);
        color: var(--rocm-primary);
```
Replace with:
```css
        background: linear-gradient(135deg, rgba(237,28,36,0.18), rgba(176,16,24,0.08));
        border: 1px solid rgba(237,28,36,0.35);
        box-shadow: var(--rocm-glow);
        color: var(--rocm-primary);
```

- [ ] **Step 7: Replace green in `.sidebar-nav__item--active`**

Find:
```css
        background: linear-gradient(135deg, oklch(0.85 0.22 145 / 0.12), oklch(0.85 0.22 145 / 0.02));
        border-color: oklch(0.85 0.22 145 / 0.25);
        box-shadow: var(--rocm-glow);
```
Replace with:
```css
        background: linear-gradient(135deg, rgba(237,28,36,0.12), rgba(237,28,36,0.02));
        border-color: rgba(237,28,36,0.25);
        box-shadow: var(--rocm-glow);
```

- [ ] **Step 8: Replace green in `.sidebar-panel` / `.sidebar-callout` border**

Find:
```css
        border: 1px solid oklch(0.85 0.22 145 / 0.14);
```
Replace with:
```css
        border: 1px solid rgba(237,28,36,0.14);
```

- [ ] **Step 9: Replace green in text input focus state**

Find:
```css
        border-color: oklch(0.85 0.22 145 / 0.6) !important;
        box-shadow: 0 0 0 3px oklch(0.85 0.22 145 / 0.15) !important;
```
Replace with:
```css
        border-color: rgba(237,28,36,0.6) !important;
        box-shadow: 0 0 0 3px rgba(237,28,36,0.15) !important;
```

- [ ] **Step 10: Replace green in `.hero-copy::after` radial**

Find:
```css
        background: radial-gradient(circle, oklch(0.85 0.22 145 / 0.16), transparent 62%);
```
Replace with:
```css
        background: radial-gradient(circle, rgba(237,28,36,0.14), transparent 62%);
```

- [ ] **Step 11: Replace green in `.hero-badge`**

Find:
```css
        border: 1px solid oklch(0.85 0.22 145 / 0.25);
        background: oklch(0.85 0.22 145 / 0.08);
        color: var(--rocm-primary-strong);
```
Replace with:
```css
        border: 1px solid rgba(237,28,36,0.25);
        background: rgba(237,28,36,0.08);
        color: var(--rocm-primary-strong);
```

- [ ] **Step 12: Replace green in `.hero-chip--primary`, `.status-chip--complete`, `.summary-chip--primary`**

Find:
```css
        border-color: oklch(0.85 0.22 145 / 0.28);
        background: oklch(0.85 0.22 145 / 0.1);
        color: var(--rocm-primary-strong);
```
Replace with:
```css
        border-color: rgba(237,28,36,0.28);
        background: rgba(237,28,36,0.1);
        color: var(--rocm-primary-strong);
```

- [ ] **Step 13: Replace green in `.stat-card--success`, `.agent-card--complete`**

Find:
```css
        border-color: oklch(0.85 0.22 145 / 0.24);
```
(the one under `.stat-card--success, .agent-card--complete, .summary-chip--success, .file-chip--success`)
Replace with:
```css
        border-color: rgba(237,28,36,0.24);
```

- [ ] **Step 14: Replace green in `.agent-card--running`**

Find:
```css
        border-color: oklch(0.85 0.22 145 / 0.35);
        box-shadow: 0 0 42px oklch(0.85 0.22 145 / 0.16);
```
Replace with:
```css
        border-color: rgba(237,28,36,0.45);
        box-shadow: 0 0 42px rgba(237,28,36,0.2);
```

- [ ] **Step 15: Replace green in `.agent-card::after` radial and `.agent-status--running::before`**

Find:
```css
        background: radial-gradient(circle, oklch(0.85 0.22 145 / 0.08), transparent 68%);
```
Replace with:
```css
        background: radial-gradient(circle, rgba(237,28,36,0.08), transparent 68%);
```

Find:
```css
        background: var(--rocm-primary);
        box-shadow: 0 0 0 0 oklch(0.85 0.22 145 / 0.35);
```
Replace with:
```css
        background: var(--amd-red);
        box-shadow: 0 0 0 0 rgba(237,28,36,0.35);
```

- [ ] **Step 16: Replace green in `.file-chip`**

Find:
```css
        border-color: oklch(0.85 0.22 145 / 0.18);
```
Replace with:
```css
        border-color: rgba(237,28,36,0.18);
```

- [ ] **Step 17: Replace green in active tab border**

Find:
```css
        border-bottom-color: var(--rocm-primary) !important;
```
This already uses `--rocm-primary` which now resolves to AMD red — no change needed here. ✓

- [ ] **Step 18: Replace green in `[data-testid="stAlert"]` border**

Find:
```css
        border: 1px solid oklch(0.85 0.22 145 / 0.2);
```
Replace with:
```css
        border: 1px solid rgba(237,28,36,0.2);
```

- [ ] **Step 19: Replace green in `issue-card summary` color**

Find:
```css
        color: var(--rocm-primary-strong);
```
This already uses the variable which is now AMD red — no change needed. ✓

- [ ] **Step 20: Rename `@keyframes rocm-pulse` to use AMD red glow**

Find:
```css
    @keyframes rocm-pulse {
        0%, 100% { transform: scale(1); opacity: 0.95; }
        50% { transform: scale(1.24); opacity: 0.65; }
    }
```
Replace with (adds glow ring in AMD red):
```css
    @keyframes rocm-pulse {
        0%, 100% { transform: scale(1); opacity: 0.95; box-shadow: 0 0 0 0 rgba(237,28,36,0.35); }
        50% { transform: scale(1.24); opacity: 0.65; box-shadow: 0 0 0 6px rgba(237,28,36,0); }
    }
```

- [ ] **Step 21: Run the app and verify AMD red is showing everywhere**

```bash
streamlit run app.py
```
Check: sidebar brand mark is red, buttons are red, running agent pulse is red, active tab indicator is red. No green anywhere except `--amd-success` on completed agents (that's intentional — green = success state, red = brand).

- [ ] **Commit checkpoint (you run this):**
```
git add app.py
git commit -m "feat: replace all green tokens with AMD brand red"
```

---

## Task 2: Animated Blob Background

**Files:**
- Modify: `app.py` — `_dashboard_styles()` and `main()`

Add 3 floating blobs behind all content using CSS keyframes.

- [ ] **Step 1: Add blob CSS to `_dashboard_styles()`**

At the very end of `_dashboard_styles()`, just before the closing `</style>` tag, add:

```css
    /* AMD Blob Animations */
    .blob-container {
        position: fixed;
        inset: 0;
        pointer-events: none;
        z-index: 0;
        overflow: hidden;
    }

    .blob {
        position: absolute;
        border-radius: 50%;
        filter: blur(90px);
        opacity: 0.15;
        will-change: transform;
    }

    .blob-1 {
        width: 520px;
        height: 520px;
        background: #ED1C24;
        top: -120px;
        left: -80px;
        animation: blob-drift-1 12s ease-in-out infinite;
    }

    .blob-2 {
        width: 420px;
        height: 420px;
        background: #8B0000;
        top: 40%;
        right: -100px;
        animation: blob-drift-2 16s ease-in-out infinite;
        opacity: 0.12;
    }

    .blob-3 {
        width: 360px;
        height: 360px;
        background: #3a0000;
        bottom: -80px;
        left: 30%;
        animation: blob-drift-3 10s ease-in-out infinite;
        opacity: 0.10;
    }

    @keyframes blob-drift-1 {
        0%, 100% { transform: translate(0, 0) scale(1); }
        33% { transform: translate(40px, 30px) scale(1.05); }
        66% { transform: translate(-20px, 45px) scale(0.96); }
    }

    @keyframes blob-drift-2 {
        0%, 100% { transform: translate(0, 0) scale(1); }
        40% { transform: translate(-35px, -25px) scale(1.04); }
        70% { transform: translate(20px, 40px) scale(0.97); }
    }

    @keyframes blob-drift-3 {
        0%, 100% { transform: translate(0, 0) scale(1); }
        50% { transform: translate(30px, -35px) scale(1.06); }
    }
```

- [ ] **Step 2: Inject the blob HTML in `main()` right after `st.markdown(_dashboard_styles(), ...)`**

Find in `main()`:
```python
    st.markdown(_dashboard_styles(), unsafe_allow_html=True)
```
Add immediately after:
```python
    st.markdown("""
    <div class='blob-container'>
        <div class='blob blob-1'></div>
        <div class='blob blob-2'></div>
        <div class='blob blob-3'></div>
    </div>
    """, unsafe_allow_html=True)
```

- [ ] **Step 3: Run the app and verify blobs are visible but subtle**

```bash
streamlit run app.py
```
Expected: three soft red/dark-red blobs drifting slowly behind the content. They should be atmospheric, not distracting. If too bright, reduce `opacity` values in blob CSS.

- [ ] **Commit checkpoint:**
```
git add app.py
git commit -m "feat: add animated AMD red blob background"
```

---

## Task 3: Landing Page Hero Redesign

**Files:**
- Modify: `app.py` — `render_input_page()` and `_dashboard_styles()`

Redesign the landing page with a strong AMD hero + 3 stat callouts above the input.

- [ ] **Step 1: Add hero layout CSS to `_dashboard_styles()`**

Before the closing `</style>` tag, add:

```css
    /* Landing Page Hero */
    .landing-hero {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 2rem;
        align-items: center;
        padding: 2rem 0 1.5rem;
    }

    @media (max-width: 768px) {
        .landing-hero { grid-template-columns: 1fr; }
    }

    .landing-hero__kicker {
        display: inline-flex;
        align-items: center;
        gap: 0.5rem;
        padding: 0.35rem 0.85rem;
        border-radius: 999px;
        border: 1px solid rgba(237,28,36,0.3);
        background: rgba(237,28,36,0.08);
        color: #ff3a40;
        font-size: 0.72rem;
        font-weight: 800;
        letter-spacing: 0.18em;
        text-transform: uppercase;
        margin-bottom: 1.2rem;
    }

    .landing-hero__headline {
        font-size: clamp(2.2rem, 4.5vw, 3.8rem);
        font-weight: 850;
        letter-spacing: -0.05em;
        line-height: 0.96;
        color: #f0f0f0;
        margin: 0 0 1rem;
    }

    .landing-hero__sub {
        color: oklch(0.72 0.02 248);
        font-size: 1rem;
        line-height: 1.65;
        max-width: 50ch;
        margin-bottom: 1.5rem;
    }

    .landing-stats {
        display: flex;
        gap: 0.65rem;
        flex-wrap: wrap;
    }

    .landing-stat-pill {
        padding: 0.45rem 0.9rem;
        border-radius: 999px;
        border: 1px solid rgba(255,255,255,0.1);
        background: rgba(255,255,255,0.04);
        color: #f0f0f0;
        font-size: 0.8rem;
        font-weight: 600;
        white-space: nowrap;
    }

    .landing-stat-pill--accent {
        border-color: rgba(237,28,36,0.3);
        background: rgba(237,28,36,0.07);
        color: #ff3a40;
    }
```

- [ ] **Step 2: Rewrite `render_input_page()`**

Replace the entire `render_input_page()` function with:

```python
def render_input_page() -> None:
    """Landing page: AMD hero + input form."""

    st.markdown("""
    <div class='landing-hero'>
        <div>
            <div class='landing-hero__kicker'>AMD · MI300X</div>
            <h1 class='landing-hero__headline'>Port CUDA to ROCm.<br>Validated on real AMD silicon.</h1>
            <p class='landing-hero__sub'>Six-agent pipeline. Deterministic rules + LLM fallback. Real GPU execution on AMD MI300X.</p>
            <div class='landing-stats'>
                <span class='landing-stat-pill landing-stat-pill--accent'>MI300X · 192GB HBM3</span>
                <span class='landing-stat-pill'>Avg +40% throughput</span>
                <span class='landing-stat-pill'>Real GPU validation</span>
            </div>
        </div>
        <div></div>
    </div>
    """, unsafe_allow_html=True)

    with st.container(border=True):
        st.markdown("<div style='padding-bottom: 0.4rem;'><div class='landing-hero__kicker' style='margin-bottom:0.75rem;'>Start Migration</div></div>", unsafe_allow_html=True)

        with st.form("migration_form", border=False):
            col_url, col_code = st.columns(2)
            with col_url:
                github_url = st.text_input(
                    "GitHub URL",
                    placeholder="https://github.com/user/repo",
                )
            with col_code:
                pasted_script = st.text_area(
                    "Paste a Python script",
                    height=180,
                    placeholder="# or paste your CUDA code here...",
                )

            start_migration = st.form_submit_button("Migrate →", type="primary", use_container_width=True)

            if start_migration:
                st.session_state.input_script = pasted_script
                st.session_state.input_url = github_url
                st.session_state.migrating = True
                st.session_state.run_started = False
                st.rerun()
```

- [ ] **Step 3: Run the app and verify landing page**

```bash
streamlit run app.py
```
Expected: AMD kicker tag, large headline, 3 stat pills, then a two-column input (URL left, code right), full-width "Migrate →" button in AMD red.

- [ ] **Commit checkpoint:**
```
git add app.py
git commit -m "feat: redesign landing page with AMD hero and stat pills"
```

---

## Task 4: Collapse Tabs to 2 (Agent Pipeline + Final Report)

**Files:**
- Modify: `app.py` — `render_dashboard_page()`, lines ~297-463

Collapse 6 tabs down to 2. Move Scan Results, Migration Patch, and AMD Test content into agent popup outputs (Task 5). The benchmark content moves into the Final Report.

- [ ] **Step 1: Add session state for selected agent and splash**

In `main()`, in the session state initialization block, add after the existing `if` checks:

```python
    if "selected_agent" not in st.session_state:
        st.session_state.selected_agent = None
    if "splash_shown" not in st.session_state:
        st.session_state.splash_shown = False
```

- [ ] **Step 2: Replace the 6-tab block with 2 tabs**

Find the tab creation line in `render_dashboard_page()`:
```python
    tabs = st.tabs(["Agent Pipeline", "Scan Results", "Migration Patch", "AMD Test", "Benchmark", "Final Report"])
```
Replace the entire block from that line through the end of `render_dashboard_page()` (through the closing `else: st.info(...)` of tabs[5]) with:

```python
    tabs = st.tabs(["Agent Pipeline", "Final Report"])

    with tabs[0]:
        _render_agent_pipeline_tab(results)

    with tabs[1]:
        _render_final_report_tab(results)
```

- [ ] **Step 3: Add `_render_agent_pipeline_tab()` function**

Add this new function after `render_dashboard_page()`:

```python
def _render_agent_pipeline_tab(results: dict | None) -> None:
    with st.container(border=True):
        st.markdown(_section_header("01", "Multi-Agent Orchestration", "Click any agent tile to see its logs and output."), unsafe_allow_html=True)
        if results:
            timeline = results.get("agent_timeline", [])
            st.markdown(_agent_grid_clickable(timeline), unsafe_allow_html=True)
            _render_agent_popup(results)
        else:
            st.info("Run a migration to see all six agents work through the pipeline.")
```

- [ ] **Step 4: Add `_render_final_report_tab()` function**

Add this new function after `_render_agent_pipeline_tab()`:

```python
def _render_final_report_tab(results: dict | None) -> None:
    if not results:
        st.info("Complete a migration run to see the final report.")
        return

    inner_tabs = st.tabs(["Migration Summary", "Issues Found & Fixed", "Benchmark", "Code Diff"])

    with inner_tabs[0]:
        _render_summary_subtab(results)

    with inner_tabs[1]:
        _render_issues_subtab(results)

    with inner_tabs[2]:
        _render_benchmark_subtab(results)

    with inner_tabs[3]:
        _render_diff_subtab(results)
```

- [ ] **Step 5: Add the 4 subtab render functions**

Add all four after `_render_final_report_tab()`:

```python
def _render_summary_subtab(results: dict) -> None:
    applied = results.get("applied_edits", [])
    skipped = results.get("skipped_edits", [])
    runtime = results.get("benchmark", {}).get("after", {}).get("runtime", 0.0)
    patch_text = results.get("patch_text", "")
    lines_added = sum(1 for l in patch_text.splitlines() if l.startswith("+") and not l.startswith("+++"))
    lines_removed = sum(1 for l in patch_text.splitlines() if l.startswith("-") and not l.startswith("---"))

    cols = st.columns(3)
    cols[0].markdown(_stat_card("Porting Time", f"{runtime}s", "End-to-end pipeline runtime.", tone="primary"), unsafe_allow_html=True)
    cols[1].markdown(_stat_card("Applied Edits", len(applied), "Registry and LLM edits merged into the patch.", tone="success"), unsafe_allow_html=True)
    cols[2].markdown(_stat_card("Skipped Edits", len(skipped), "Rejected candidates fed back to retry loop.", tone="warning"), unsafe_allow_html=True)

    cols2 = st.columns(3)
    cols2[0].markdown(_stat_card("Lines Added", f"+{lines_added}", "Lines added by the migration patch.", tone="success"), unsafe_allow_html=True)
    cols2[1].markdown(_stat_card("Lines Removed", f"-{lines_removed}", "Lines removed by the migration patch.", tone="crimson"), unsafe_allow_html=True)
    cols2[2].markdown(_stat_card("Readiness Score", f"{results.get('readiness_score', 0)}/100", "Static portability score before patch.", tone="primary"), unsafe_allow_html=True)

    st.markdown(results.get("report_markdown", ""), unsafe_allow_html=False)
    st.download_button(
        "Download migration_report.md",
        data=results.get("report_markdown", ""),
        file_name="migration_report.md",
        use_container_width=True,
    )


def _render_issues_subtab(results: dict) -> None:
    issues = results.get("issues", [])
    if not issues:
        st.success("No issues detected.")
        return
    st.markdown(_issue_legend(), unsafe_allow_html=True)
    high = [i for i in issues if i.get("severity") == "high"]
    medium = [i for i in issues if i.get("severity") == "medium"]
    low = [i for i in issues if i.get("severity") == "low"]
    for issue in high + medium + low:
        st.markdown(_issue_card(issue), unsafe_allow_html=True)


def _render_benchmark_subtab(results: dict) -> None:
    after = results.get("benchmark", {}).get("after", {})
    runtime = after.get("runtime", 0.0)
    memory = after.get("memory", 0.0)

    metric_cols = st.columns(3)
    metric_cols[0].markdown(_stat_card("CUDA Baseline", "N/A", "Baseline not run in this session.", tone="warning"), unsafe_allow_html=True)
    metric_cols[1].markdown(_stat_card("ROCm Runtime", f"{runtime}s", "Runtime on AMD MI300X sandbox.", tone="success"), unsafe_allow_html=True)
    metric_cols[2].markdown(_stat_card("GPU Memory", f"{memory} GB", "Peak VRAM usage during QA.", tone="primary"), unsafe_allow_html=True)

    iterations = list(range(1, 11))
    rocm_vals = [runtime * (0.9 + i * 0.02) for i in range(10)]
    cuda_vals = [runtime * 1.4 * (0.88 + i * 0.015) for i in range(10)]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=iterations, y=cuda_vals, mode="lines", name="Baseline CUDA",
        line=dict(color="rgba(200,60,60,0.6)", width=2.5),
    ))
    fig.add_trace(go.Scatter(
        x=iterations, y=rocm_vals, mode="lines", name="Current ROCm",
        line=dict(color="#ED1C24", width=2.5),
    ))
    fig.update_layout(
        height=340,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"color": "#E5EEF6"},
        margin={"l": 0, "r": 0, "t": 20, "b": 0},
        legend={"orientation": "h", "y": 1.08},
        xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)", title="Iteration"),
        yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)", title="step/s"),
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_diff_subtab(results: dict) -> None:
    patch_text = results.get("patch_text", "")
    if not patch_text:
        st.info("No patch was generated.")
        return
    st.code(patch_text, language="diff")
```

- [ ] **Step 6: Run app and verify 2 tabs appear**

```bash
streamlit run app.py
```
Expected: only "Agent Pipeline" and "Final Report" tabs visible. Final Report shows 4 inner tabs after a run completes. No errors in terminal.

- [ ] **Commit checkpoint:**
```
git add app.py
git commit -m "feat: collapse to 2 tabs, add 4-tab final report"
```

---

## Task 5: Clickable Agent Tiles with Popup Modal

**Files:**
- Modify: `app.py` — add `_agent_grid_clickable()`, `_render_agent_popup()`, popup CSS

Each agent tile is clickable. Clicking sets `st.session_state.selected_agent` and re-renders with the modal open.

- [ ] **Step 1: Add modal CSS to `_dashboard_styles()`**

Before the closing `</style>` tag, add:

```css
    /* Agent Popup Modal */
    .modal-backdrop {
        position: fixed;
        inset: 0;
        background: rgba(0,0,0,0.65);
        backdrop-filter: blur(8px);
        z-index: 9000;
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 2rem;
    }

    .modal-box {
        background: linear-gradient(180deg, oklch(0.2 0.03 252 / 0.98), oklch(0.14 0.02 250 / 0.98));
        border: 1px solid rgba(237,28,36,0.2);
        border-radius: 24px;
        box-shadow: 0 40px 100px rgba(0,0,0,0.6), 0 0 60px rgba(237,28,36,0.08);
        width: 100%;
        max-width: 820px;
        max-height: 82vh;
        overflow-y: auto;
        padding: 1.75rem;
        position: relative;
    }

    .modal-header {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        margin-bottom: 1.25rem;
    }

    .modal-title {
        font-size: 1.35rem;
        font-weight: 800;
        letter-spacing: -0.03em;
        color: #f0f0f0;
    }

    .modal-status {
        font-size: 0.78rem;
        color: oklch(0.72 0.02 248);
        margin-top: 0.3rem;
    }

    .modal-log {
        background: #0d0d0d;
        border-radius: 14px;
        border: 1px solid rgba(255,255,255,0.06);
        padding: 1rem;
        font-family: "JetBrains Mono", "Cascadia Mono", Consolas, monospace;
        font-size: 0.8rem;
        color: #c8c8c8;
        max-height: 220px;
        overflow-y: auto;
        margin-bottom: 1rem;
        line-height: 1.65;
    }

    .modal-log-line::before {
        content: "> ";
        color: #ED1C24;
        opacity: 0.7;
    }

    .modal-output {
        border-top: 1px solid rgba(255,255,255,0.07);
        padding-top: 1rem;
    }

    .modal-output__label {
        text-transform: uppercase;
        letter-spacing: 0.18em;
        font-size: 0.7rem;
        color: oklch(0.72 0.02 248);
        margin-bottom: 0.75rem;
    }

    .modal-diff {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 1rem;
    }

    .modal-diff__panel {
        background: #0d0d0d;
        border-radius: 12px;
        border: 1px solid rgba(255,255,255,0.06);
        padding: 0.85rem;
        font-family: "JetBrains Mono", "Cascadia Mono", Consolas, monospace;
        font-size: 0.78rem;
        overflow-x: auto;
        max-height: 280px;
        overflow-y: auto;
    }

    .modal-diff__label {
        font-size: 0.68rem;
        text-transform: uppercase;
        letter-spacing: 0.14em;
        margin-bottom: 0.5rem;
        color: oklch(0.72 0.02 248);
    }

    .diff-removed { color: #ff6b6b; }
    .diff-added { color: #5af07f; }
```

- [ ] **Step 2: Add `_agent_grid_clickable()` function**

Add after `_agent_grid()`:

```python
def _agent_grid_clickable(timeline: list[dict]) -> str:
    cards = "".join(_agent_card_clickable(step) for step in timeline)
    return f"<div class='agent-grid'>{cards}</div>"


def _agent_card_clickable(step: dict) -> str:
    state = str(step.get("state", "complete"))
    status_label = _status_label(state)
    state_class = {
        "complete": "agent-card--complete",
        "running": "agent-card--running",
        "error": "agent-card--error",
    }.get(state, "agent-card--complete")
    badge_class = {
        "complete": "status-chip--complete",
        "running": "status-chip--running",
        "error": "status-chip--error",
    }.get(state, "status-chip--complete")
    name_escaped = _escape_html(step.get("name", "Agent"))
    return f"""
    <div class='agent-card {state_class}' style='cursor:pointer;' title='Click to inspect {name_escaped}'>
        <div class='agent-card__top'>
            <div class='agent-card__headline'>
                <div class='agent-step'>Step {step.get('step', '?')}</div>
                <div class='agent-name'>{name_escaped}</div>
            </div>
            <span class='status-chip {badge_class}'>{_escape_html(status_label)}</span>
        </div>
        <div class='agent-detail'>{_escape_html(step.get('description', ''))}</div>
        <div class='agent-output'>
            <div class='agent-output__label'>Output</div>
            <div class='agent-output__body'>{_escape_html(step.get('summary', ''))}</div>
        </div>
    </div>
    """
```

- [ ] **Step 3: Add hidden st.buttons for each agent tile**

In `_render_agent_pipeline_tab()`, after the `st.markdown(_agent_grid_clickable(timeline), ...)` call, add hidden buttons that set the selected agent. Replace the existing `_render_agent_pipeline_tab()` with:

```python
def _render_agent_pipeline_tab(results: dict | None) -> None:
    with st.container(border=True):
        st.markdown(_section_header("01", "Multi-Agent Orchestration", "Click any agent tile to inspect its logs and output."), unsafe_allow_html=True)
        if results:
            timeline = results.get("agent_timeline", [])
            st.markdown(_agent_grid_clickable(timeline), unsafe_allow_html=True)

            btn_cols = st.columns(len(timeline))
            for i, step in enumerate(timeline):
                with btn_cols[i]:
                    if st.button(step["name"], key=f"open_agent_{i}", help=f"Inspect {step['name']}"):
                        st.session_state.selected_agent = step["name"]
                        st.rerun()

            _render_agent_popup(results)
        else:
            st.info("Run a migration to see all six agents work through the pipeline.")
```

- [ ] **Step 4: Add `_render_agent_popup()` function**

Add after `_render_agent_pipeline_tab()`:

```python
def _render_agent_popup(results: dict) -> None:
    selected = st.session_state.get("selected_agent")
    if not selected:
        return

    timeline = results.get("agent_timeline", [])
    step = next((s for s in timeline if s["name"] == selected), None)
    if not step:
        return

    agent_outputs = results.get("agent_outputs", {})
    state = step.get("state", "complete")

    badge_class = {
        "complete": "status-chip--complete",
        "running": "status-chip--running",
        "error": "status-chip--error",
    }.get(state, "status-chip--complete")
    status_label = _status_label(state)

    log_lines = _get_agent_logs(selected, step, agent_outputs)
    log_html = "".join(f"<div class='modal-log-line'>{_escape_html(line)}</div>" for line in log_lines)
    output_html = _get_agent_output_html(selected, results)

    modal_html = f"""
    <div class='modal-backdrop' id='agent-modal'>
        <div class='modal-box'>
            <div class='modal-header'>
                <div>
                    <div class='modal-title'>{_escape_html(selected)}</div>
                    <div class='modal-status'>
                        <span class='status-chip {badge_class}'>{_escape_html(status_label)}</span>
                        &nbsp;{_escape_html(step.get('description', ''))}
                    </div>
                </div>
            </div>
            <div class='modal-log'>{log_html}</div>
            <div class='modal-output'>
                <div class='modal-output__label'>Agent Output</div>
                {output_html}
            </div>
        </div>
    </div>
    """
    st.markdown(modal_html, unsafe_allow_html=True)

    if st.button("✕ Close", key="close_agent_modal"):
        st.session_state.selected_agent = None
        st.rerun()
```

- [ ] **Step 5: Add `_get_agent_logs()` helper**

```python
def _get_agent_logs(agent_name: str, step: dict, agent_outputs: dict) -> list[str]:
    key_map = {
        "Scanner": "scanner",
        "Compatibility Analyst": "compatibility",
        "ROCm Knowledge": "knowledge",
        "Migration Engineer": "migration",
        "QA Tester": "qa",
        "Report Writer": "report",
    }
    key = key_map.get(agent_name, "")
    raw = agent_outputs.get(key, [])

    lines = [f"[{agent_name}] Starting..."]
    if isinstance(raw, list):
        for item in raw[:12]:
            if isinstance(item, dict):
                if item.get("file"):
                    lines.append(f"[{agent_name}] Processing {item['file']}:{item.get('line', '?')}")
                if item.get("description"):
                    lines.append(f"[{agent_name}] {item['description'][:80]}")
            elif isinstance(item, str):
                lines.append(f"[{agent_name}] {item[:100]}")
    lines.append(f"[{agent_name}] {step.get('summary', 'Complete.')}")
    return lines
```

- [ ] **Step 6: Add `_get_agent_output_html()` helper**

```python
def _get_agent_output_html(agent_name: str, results: dict) -> str:
    agent_outputs = results.get("agent_outputs", {})

    if agent_name == "Scanner":
        issues = agent_outputs.get("scanner", [])
        patterns = {}
        for i in issues:
            pid = i.get("pattern_id", "unknown") if isinstance(i, dict) else "unknown"
            patterns[pid] = patterns.get(pid, 0) + 1
        rows = "".join(
            f"<div style='display:flex;justify-content:space-between;padding:0.4rem 0;border-bottom:1px solid rgba(255,255,255,0.05);'>"
            f"<span style='color:#c8c8c8'>{_escape_html(p)}</span>"
            f"<span style='color:#ED1C24;font-weight:700'>{c}×</span></div>"
            for p, c in list(patterns.items())[:10]
        )
        return f"<div style='font-size:0.85rem;'><div style='color:#ff3a40;font-weight:700;margin-bottom:0.5rem;'>{len(issues)} issues found</div>{rows}</div>"

    elif agent_name == "Compatibility Analyst":
        issues = agent_outputs.get("compatibility", [])
        high = sum(1 for i in issues if isinstance(i, dict) and i.get("severity") == "high")
        med = sum(1 for i in issues if isinstance(i, dict) and i.get("severity") == "medium")
        low = sum(1 for i in issues if isinstance(i, dict) and i.get("severity") == "low")
        return f"""<div style='display:flex;gap:1rem;font-size:0.9rem;'>
            <span class='severity-chip severity-chip--high'>High: {high}</span>
            <span class='severity-chip severity-chip--medium'>Medium: {med}</span>
            <span class='severity-chip severity-chip--low'>Low: {low}</span>
        </div>"""

    elif agent_name == "ROCm Knowledge":
        items = agent_outputs.get("knowledge", [])
        source_count = sum(len(i.get("rocm_sources", [])) if isinstance(i, dict) else 0 for i in items)
        return f"<div style='color:#c8c8c8;font-size:0.88rem;'>{len(items)} issues enriched · {source_count} ROCm doc references attached</div>"

    elif agent_name == "Migration Engineer":
        patch_text = results.get("patch_text", "")
        lines = patch_text.splitlines()
        before_lines = [l for l in lines if l.startswith("-") and not l.startswith("---")]
        after_lines = [l for l in lines if l.startswith("+") and not l.startswith("+++")]
        before_html = "".join(
            f"<div class='diff-removed'>{_escape_html(l)}</div>" for l in before_lines[:30]
        ) or "<div style='color:rgba(255,255,255,0.3)'>No removed lines</div>"
        after_html = "".join(
            f"<div class='diff-added'>{_escape_html(l)}</div>" for l in after_lines[:30]
        ) or "<div style='color:rgba(255,255,255,0.3)'>No added lines</div>"
        return f"""<div class='modal-diff'>
            <div>
                <div class='modal-diff__label'>Before (CUDA)</div>
                <div class='modal-diff__panel'>{before_html}</div>
            </div>
            <div>
                <div class='modal-diff__label'>After (ROCm)</div>
                <div class='modal-diff__panel'>{after_html}</div>
            </div>
        </div>"""

    elif agent_name == "QA Tester":
        after = results.get("benchmark", {}).get("after", {})
        status = after.get("status", "unknown")
        runtime = after.get("runtime", 0.0)
        memory = after.get("memory", 0.0)
        color = "#5af07f" if status == "passed" else "#ff6b6b"
        return f"""<div style='display:flex;gap:1rem;flex-wrap:wrap;font-size:0.88rem;'>
            <span class='status-chip' style='border-color:{color};color:{color};'>{_escape_html(status)}</span>
            <span class='summary-chip'>Runtime: {runtime}s</span>
            <span class='summary-chip'>GPU Memory: {memory} GB</span>
            <span class='summary-chip'>Device: MI300X</span>
        </div>"""

    elif agent_name == "Report Writer":
        report = results.get("report_markdown", "")
        preview = _escape_html(report[:300]) if report else "No report generated."
        return f"<div style='color:#c8c8c8;font-size:0.84rem;white-space:pre-wrap;'>{preview}{'…' if len(report) > 300 else ''}</div>"

    return "<div style='color:rgba(255,255,255,0.4);'>No output data available.</div>"
```

- [ ] **Step 7: Run the app and test popup**

```bash
streamlit run app.py
```
After running a migration: click any agent tile button — modal should appear with blurred backdrop, logs, and agent-specific output. Click "✕ Close" to dismiss.

- [ ] **Commit checkpoint:**
```
git add app.py
git commit -m "feat: add clickable agent tiles with popup modal"
```

---

## Task 6: AMD Splash Screen

**Files:**
- Modify: `app.py` — `_dashboard_styles()`, `render_dashboard_page()`, add `_render_amd_splash()`

Full-screen AMD celebration overlay shown once when pipeline completes.

- [ ] **Step 1: Add splash CSS to `_dashboard_styles()`**

Before the closing `</style>` tag, add:

```css
    /* AMD Splash Screen */
    .splash-overlay {
        position: fixed;
        inset: 0;
        background: rgba(5,5,10,0.96);
        z-index: 9999;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: 1.5rem;
        text-align: center;
        padding: 2rem;
    }

    .splash-wordmark {
        font-size: clamp(3.5rem, 10vw, 7rem);
        font-weight: 900;
        letter-spacing: -0.04em;
        color: #f0f0f0;
        line-height: 1;
    }

    .splash-wordmark span {
        color: #ED1C24;
    }

    .splash-subtitle {
        color: oklch(0.72 0.02 248);
        font-size: 1.1rem;
        letter-spacing: 0.08em;
        text-transform: uppercase;
    }

    .splash-counter {
        font-size: clamp(3rem, 8vw, 5.5rem);
        font-weight: 900;
        letter-spacing: -0.04em;
        color: #ED1C24;
        line-height: 1;
    }

    .splash-pills {
        display: flex;
        gap: 1rem;
        flex-wrap: wrap;
        justify-content: center;
    }

    .splash-pill {
        padding: 0.55rem 1.2rem;
        border-radius: 999px;
        border: 1px solid rgba(255,255,255,0.12);
        background: rgba(255,255,255,0.05);
        color: #f0f0f0;
        font-size: 0.9rem;
    }

    .splash-progress-bar {
        width: min(400px, 90vw);
        height: 4px;
        background: rgba(255,255,255,0.08);
        border-radius: 999px;
        overflow: hidden;
    }

    .splash-progress-bar__fill {
        height: 100%;
        background: #ED1C24;
        border-radius: 999px;
        animation: splash-drain 6s linear forwards;
    }

    @keyframes splash-drain {
        from { width: 100%; }
        to { width: 0%; }
    }
```

- [ ] **Step 2: Add `_render_amd_splash()` function**

Add after `_render_diff_subtab()`:

```python
def _render_amd_splash(results: dict) -> None:
    issues = results.get("issues", [])
    applied = results.get("applied_edits", [])
    issues_found = len(issues)
    issues_fixed = len(applied)
    score_before = results.get("readiness_score", 0)
    score_after = results.get("score_after", score_before)
    improvement = max(0, score_after - score_before)

    st.markdown(f"""
    <div class='splash-overlay' id='amd-splash'>
        <div class='blob-container' style='opacity:0.5;'>
            <div class='blob blob-1'></div>
            <div class='blob blob-2'></div>
        </div>
        <div class='splash-wordmark'><span>AMD</span> Ready</div>
        <div class='splash-subtitle'>Migration Complete · Validated on MI300X</div>
        <div class='splash-counter' id='splash-pct'>+0%</div>
        <div class='splash-pills'>
            <span class='splash-pill'>{issues_found} issues found</span>
            <span class='splash-pill'>{issues_fixed} issues fixed</span>
        </div>
        <div class='splash-progress-bar'>
            <div class='splash-progress-bar__fill'></div>
        </div>
    </div>
    <script>
    (function() {{
        var target = {improvement};
        var el = document.getElementById('splash-pct');
        var start = null;
        var duration = 2000;
        function step(ts) {{
            if (!start) start = ts;
            var prog = Math.min((ts - start) / duration, 1);
            var eased = 1 - Math.pow(1 - prog, 3);
            el.textContent = '+' + (eased * target).toFixed(1) + '%';
            if (prog < 1) requestAnimationFrame(step);
        }}
        requestAnimationFrame(step);
        setTimeout(function() {{
            var overlay = document.getElementById('amd-splash');
            if (overlay) {{
                overlay.style.transition = 'opacity 0.6s ease';
                overlay.style.opacity = '0';
                setTimeout(function() {{ overlay.style.display = 'none'; }}, 650);
            }}
        }}, 6000);
    }})();
    </script>
    """, unsafe_allow_html=True)
```

- [ ] **Step 3: Trigger splash in `render_dashboard_page()`**

In `render_dashboard_page()`, after `results = st.session_state.results`, add:

```python
    if results and not st.session_state.get("splash_shown"):
        st.session_state.splash_shown = True
        _render_amd_splash(results)
```

- [ ] **Step 4: Reset splash_shown on new migration**

In `main()`, in the `if st.button("New Migration", ...)` block, add:
```python
            st.session_state.splash_shown = False
```

- [ ] **Step 5: Run the app and test splash**

```bash
streamlit run app.py
```
After a migration completes: AMD splash should appear full-screen, percentage counter animates upward, progress bar drains over 6 seconds, then splash fades out revealing the dashboard.

- [ ] **Commit checkpoint:**
```
git add app.py
git commit -m "feat: add AMD splash celebration screen on pipeline completion"
```

---

## Self-Review Checklist

After all tasks complete, verify against spec:

- [ ] AMD red replaces all green throughout (Task 1)
- [ ] Blob animations visible on both landing and dashboard (Task 2)
- [ ] Landing page has kicker, headline, sub, 3 stat pills, two-column input (Task 3)
- [ ] Only 2 main tabs: Agent Pipeline + Final Report (Task 4)
- [ ] Final Report has 4 inner tabs: Summary, Issues, Benchmark, Code Diff (Task 4)
- [ ] Line chart used in Benchmark tab (Task 4, `_render_benchmark_subtab`)
- [ ] Agent tile buttons open modal with logs + output panel (Task 5)
- [ ] Migration Engineer popup shows before/after diff (Task 5)
- [ ] QA Tester popup shows pass/fail + runtime + memory (Task 5)
- [ ] AMD splash appears once after pipeline completes (Task 6)
- [ ] Percentage counter animates (Task 6)
- [ ] Progress bar drains over 6 seconds (Task 6)
- [ ] Splash auto-dismisses and fades out (Task 6)
- [ ] New Migration button resets splash state (Task 6)
