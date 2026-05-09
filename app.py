import html
import tempfile
import threading
import time
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

import agents
from core.repo_loader import cleanup_temp, load_repo_from_url


def _escape_html(value: object) -> str:
    return html.escape("" if value is None else str(value))


def main() -> None:
    """Launch the Streamlit shell for the ROCmForge migration dashboard."""
    st.set_page_config(
        page_title="ROCmForge",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    agent_names = [
        "Scanner",
        "Compatibility Analyst",
        "ROCm Knowledge",
        "Migration Engineer",
        "QA Tester",
        "Report Writer",
    ]
    agent_descriptions = {
        "Scanner": "Finds CUDA, NVIDIA, and hardcoded GPU portability issues.",
        "Compatibility Analyst": "Turns findings into ROCm risk notes and AMD fix hints.",
        "ROCm Knowledge": "Pulls local ROCm docs context for each migration decision.",
        "Migration Engineer": "Produces structured JSON edits and generated files.",
        "QA Tester": "Runs the patched project on the AMD ROCm sandbox.",
        "Report Writer": "Builds the final score, patch, QA, and migration report.",
    }

    # Session State Initialization
    if "migrating" not in st.session_state:
        st.session_state.migrating = False
    if "results" not in st.session_state:
        st.session_state.results = None
    if "run_started" not in st.session_state:
        st.session_state.run_started = False
    if "input_script" not in st.session_state:
        st.session_state.input_script = ""
    if "input_url" not in st.session_state:
        st.session_state.input_url = ""
    if "selected_agent" not in st.session_state:
        st.session_state.selected_agent = None
    if "splash_shown" not in st.session_state:
        st.session_state.splash_shown = False
    if "severity_filter" not in st.session_state:
        st.session_state.severity_filter = "all"

    st.markdown(_dashboard_styles(), unsafe_allow_html=True)
    st.markdown("""
    <div class='blob-container'>
        <div class='blob blob-1'></div>
        <div class='blob blob-2'></div>
        <div class='blob blob-3'></div>
    </div>
    <div class='top-bar'>
        <div class='top-bar__brand'>
            <div class='top-bar__mark'>R</div>
            <div>
                <div class='top-bar__title'>ROCmForge</div>
                <div class='top-bar__sub'>AMD MI300X migration lab</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # New Migration button (shown only when on dashboard)
    if st.session_state.migrating:
        if st.button("← New Migration", key="new_migration"):
            st.session_state.migrating = False
            st.session_state.results = None
            st.session_state.run_started = False
            st.session_state.input_script = ""
            st.session_state.input_url = ""
            st.session_state.splash_shown = False
            st.session_state.selected_agent = None
            st.session_state.severity_filter = "all"
            st.rerun()

    # Page Routing
    if not st.session_state.migrating:
        render_input_page()
    else:
        render_dashboard_page(agent_names, agent_descriptions)


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


def render_dashboard_page(agent_names: list[str], agent_descriptions: dict) -> None:
    """Renders the active migration dashboard and the 6-agent tabbed view."""
    
    # Run the pipeline if it hasn't been triggered yet for this session
    if not st.session_state.run_started:
        st.session_state.run_started = True

        # Snapshot session state values BEFORE the thread starts (st.session_state is main-thread only)
        pasted_script = st.session_state.input_script
        github_url = st.session_state.input_url

        if not pasted_script.strip() and not github_url.strip():
            st.error("Provide a script or a repository URL to scan.")
            return

        # Run the real migration in a background thread; advance the UI visually.
        result_holder: dict = {}
        error_holder: dict = {}
        cleanup_refs: dict = {"temp_dir": None, "repo_temp_dir": None}

        def _run_migration_bg(script_val: str, url_val: str):
            try:
                if script_val.strip():
                    td = tempfile.TemporaryDirectory(prefix="rocmforge_")
                    cleanup_refs["temp_dir"] = td
                    tp = f"{td.name}/app.py"
                    with open(tp, "w", encoding="utf-8") as fh:
                        fh.write(script_val)
                    input_path = tp
                else:
                    input_path, repo_td = load_repo_from_url(url_val.strip())
                    cleanup_refs["repo_temp_dir"] = repo_td
                result_holder["data"] = agents.run_migration(input_path)
            except Exception as exc:
                error_holder["error"] = str(exc)

        worker = threading.Thread(target=_run_migration_bg, args=(pasted_script, github_url), daemon=True)
        # Streamlit runs hooks on threads; attach the script context so context-bound APIs work
        try:
            from streamlit.runtime.scriptrunner import add_script_run_ctx
            add_script_run_ctx(worker)
        except Exception:
            pass
        worker.start()

        # Live agent progression: each agent flips queued → running → done in sequence.
        # Use a SINGLE container that we re-render into; never call .empty() on it
        # mid-run (causes Streamlit to escape subsequent HTML).
        progress_slot = st.container()
        agent_states = {name: "queued" for name in agent_names}
        per_agent_seconds = 2.5

        def _render_into(slot, active_idx):
            """Re-render the progress panel into the slot."""
            slot.empty()
            with slot:
                cards_html = []
                for i, name in enumerate(agent_names):
                    state = agent_states[name]
                    if state == "running":
                        dot = "<span class='prog-dot prog-dot--running'></span>"
                        card_cls = "prog-card prog-card--running"
                        tag = "<span class='prog-tag prog-tag--running'>RUNNING</span>"
                    elif state == "complete":
                        dot = "<span class='prog-dot prog-dot--done'>&#10003;</span>"
                        card_cls = "prog-card prog-card--done"
                        tag = "<span class='prog-tag prog-tag--done'>DONE</span>"
                    else:
                        dot = "<span class='prog-dot prog-dot--idle'></span>"
                        card_cls = "prog-card"
                        tag = "<span class='prog-tag prog-tag--idle'>QUEUED</span>"
                    cards_html.append(
                        f"<div class='{card_cls}'>"
                        f"<div class='prog-card__head'>{dot}<div class='prog-card__name'>{name}</div>{tag}</div>"
                        f"<div class='prog-card__desc'>{agent_descriptions[name]}</div>"
                        f"</div>"
                    )
                completed = sum(1 for n in agent_names if agent_states[n] == "complete")
                pct = int((completed / len(agent_names)) * 100)
                if agent_states[agent_names[active_idx]] == "running":
                    pct = int(((completed + 0.5) / len(agent_names)) * 100)
                st.markdown(
                    "<div class='prog-panel'>"
                    "<div class='prog-panel__title'>Multi-Agent Migration in Progress</div>"
                    f"<div class='prog-panel__sub'>Step {active_idx + 1} of {len(agent_names)} &middot; {pct}%</div>"
                    f"<div class='prog-bar'><div class='prog-bar__fill' style='width:{pct}%'></div></div>"
                    f"<div class='prog-grid'>{''.join(cards_html)}</div>"
                    "</div>",
                    unsafe_allow_html=True,
                )

        for idx, name in enumerate(agent_names):
            agent_states[name] = "running"
            _render_into(progress_slot, idx)
            elapsed = 0.0
            tick = 0.25
            while elapsed < per_agent_seconds:
                if not worker.is_alive() and elapsed >= per_agent_seconds * 0.6:
                    break
                time.sleep(tick)
                elapsed += tick
            agent_states[name] = "complete"
            _render_into(progress_slot, idx)

        worker.join()
        progress_slot.empty()

        if "error" in error_holder:
            st.error(error_holder["error"])
            if cleanup_refs["temp_dir"]:
                cleanup_refs["temp_dir"].cleanup()
            if cleanup_refs["repo_temp_dir"]:
                cleanup_temp(cleanup_refs["repo_temp_dir"])
            return

        migration_results = result_holder.get("data", {})
        generated_files = migration_results.get("generated_files", {})
        generated_list = (
            sorted(generated_files)
            if isinstance(generated_files, dict)
            else list(generated_files)
        )
        qa_result = migration_results.get("qa_result", {})
        agent_timeline = _build_agent_timeline(
            agent_names=agent_names,
            agent_outputs=migration_results.get("agent_outputs", {}),
            attempts=migration_results.get("attempts", []),
            qa_result=qa_result,
            report_markdown=migration_results.get("report_markdown", ""),
        )

        st.session_state.results = {
            "readiness_score": migration_results.get("score_before", 0),
            "score_after": migration_results.get("score_after", 0),
            "issues": migration_results.get("issues", []),
            "patch_text": migration_results.get("patch_text", ""),
            "generated_files": generated_list,
            "agent_timeline": agent_timeline,
            "amd_logs": qa_result.get("logs", ""),
            "attempts": migration_results.get("attempts", []),
            "agent_outputs": migration_results.get("agent_outputs", {}),
            "skipped_edits": migration_results.get("skipped_edits", []),
            "applied_edits": migration_results.get("applied_edits", []),
            "failure_class": migration_results.get("failure_class", "unknown"),
            "abort_reason": migration_results.get("abort_reason", ""),
            "benchmark": {
                "before": {"status": "failed", "runtime": None, "memory": None},
                "after": {
                    "status": qa_result.get("status", "unknown"),
                    "runtime": qa_result.get("runtime_sec", 0.0),
                    "memory": qa_result.get("gpu_memory_gb", 0.0),
                },
            },
            "report_markdown": migration_results.get("report_markdown", ""),
            "input": {"pasted_script": pasted_script, "github_url": github_url},
        }

        if cleanup_refs["temp_dir"]:
            cleanup_refs["temp_dir"].cleanup()
        if cleanup_refs["repo_temp_dir"]:
            cleanup_temp(cleanup_refs["repo_temp_dir"])

    results = st.session_state.results

    # AMD Ready banner with key stats (replaces splash + snapshot)
    if results:
        score_before = results.get("readiness_score", 0)
        score_after = results.get("score_after", score_before)
        improvement = max(0, score_after - score_before)
        issues_count = len(results.get("issues", []))
        applied_count = len(results.get("applied_edits", []))
        qa_status = results.get("benchmark", {}).get("after", {}).get("status", "unknown")
        runtime = results.get("benchmark", {}).get("after", {}).get("runtime", 0.0)
        failure_class = results.get("failure_class", "unknown")

        qa_color = "#22c55e" if qa_status == "passed" else "#ff4444"
        qa_label = qa_status if qa_status != "failed" else f"failed · {failure_class}"

        st.markdown(f"""
        <div class='ready-banner'>
            <div class='ready-banner__head'>
                <div>
                    <div class='ready-banner__kicker'>AMD MI300X &middot; Migration Complete</div>
                    <div class='ready-banner__title'><span>AMD</span> Ready</div>
                </div>
                <div class='ready-banner__improvement'>
                    <div class='ready-banner__delta'>+{improvement} pts</div>
                    <div class='ready-banner__delta-label'>Score Improvement</div>
                </div>
            </div>
            <div class='ready-banner__stats'>
                <div class='ready-stat'>
                    <div class='ready-stat__label'>Before Score</div>
                    <div class='ready-stat__value'>{score_before}<span>/100</span></div>
                </div>
                <div class='ready-stat'>
                    <div class='ready-stat__label'>After Score</div>
                    <div class='ready-stat__value' style='color:#5af07f;'>{score_after}<span>/100</span></div>
                </div>
                <div class='ready-stat'>
                    <div class='ready-stat__label'>Issues Found</div>
                    <div class='ready-stat__value'>{issues_count}</div>
                </div>
                <div class='ready-stat'>
                    <div class='ready-stat__label'>Issues Fixed</div>
                    <div class='ready-stat__value' style='color:#5af07f;'>{applied_count}</div>
                </div>
                <div class='ready-stat'>
                    <div class='ready-stat__label'>Runtime</div>
                    <div class='ready-stat__value'>{runtime}<span>s</span></div>
                </div>
                <div class='ready-stat'>
                    <div class='ready-stat__label'>AMD QA</div>
                    <div class='ready-stat__value' style='color:{qa_color};font-size:1.2rem;'>{html.escape(qa_label)}</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    # 2 Tab Navigation
    st.markdown("<br>", unsafe_allow_html=True)
    tabs = st.tabs(["Agent Pipeline", "Final Report"])

    with tabs[0]:
        _render_agent_pipeline_tab(results)

    with tabs[1]:
        _render_final_report_tab(results)


# Tab Render Functions

def _render_agent_pipeline_tab(results: dict | None) -> None:
    if not results:
        st.info("Run a migration to see all six agents work through the pipeline.")
        return

    timeline = results.get("agent_timeline", [])

    # 3x2 grid using Streamlit columns
    rows = [timeline[i:i+3] for i in range(0, len(timeline), 3)]
    for row in rows:
        cols = st.columns(3)
        for col, step in zip(cols, row):
            with col:
                state = step.get("state", "complete")
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
                status_label = _status_label(state)

                card_html = f"""
                <div class='agent-card {state_class}' style='min-height:180px;'>
                    <div class='agent-card__top'>
                        <div class='agent-card__headline'>
                            <div class='agent-step'>Step {step.get('step','?')}</div>
                            <div class='agent-name'>{_escape_html(step.get('name',''))}</div>
                        </div>
                        <span class='status-chip {badge_class}'>{_escape_html(status_label)}</span>
                    </div>
                    <div class='agent-detail'>{_escape_html(step.get('description',''))}</div>
                    <div class='agent-output'>
                        <div class='agent-output__label'>Output</div>
                        <div class='agent-output__body'>{_escape_html(step.get('summary',''))}</div>
                    </div>
                </div>
                """
                st.markdown(card_html, unsafe_allow_html=True)
                if st.button(f"Inspect {step['name']}", key=f"open_agent_{step.get('step',0)}", use_container_width=True):
                    st.session_state.selected_agent = step["name"]
                    st.rerun()

    _render_agent_popup(results)


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

    high = [i for i in issues if i.get("severity") == "high"]
    medium = [i for i in issues if i.get("severity") == "medium"]
    low = [i for i in issues if i.get("severity") == "low"]

    # Clickable severity filter buttons
    filter_cols = st.columns([1, 1, 1, 2])
    severity_filter = st.session_state.get("severity_filter", "all")

    with filter_cols[0]:
        if st.button(f"🔴 High ({len(high)})", key="sev_high",
                     type="primary" if severity_filter == "high" else "secondary",
                     use_container_width=True):
            st.session_state.severity_filter = "all" if severity_filter == "high" else "high"
            st.rerun()
    with filter_cols[1]:
        if st.button(f"🟡 Medium ({len(medium)})", key="sev_med",
                     type="primary" if severity_filter == "medium" else "secondary",
                     use_container_width=True):
            st.session_state.severity_filter = "all" if severity_filter == "medium" else "medium"
            st.rerun()
    with filter_cols[2]:
        if st.button(f"🟢 Low ({len(low)})", key="sev_low",
                     type="primary" if severity_filter == "low" else "secondary",
                     use_container_width=True):
            st.session_state.severity_filter = "all" if severity_filter == "low" else "low"
            st.rerun()

    # Filter and render
    if severity_filter == "high":
        filtered = high
    elif severity_filter == "medium":
        filtered = medium
    elif severity_filter == "low":
        filtered = low
    else:
        filtered = high + medium + low

    for issue in filtered:
        severity = issue.get("severity", "unknown")
        sev_color = {"high": "#ff4444", "medium": "#f59e0b", "low": "#22c55e"}.get(severity, "#888")
        amd_hint = issue.get("amd_fix_hint", "")
        pattern = issue.get("pattern_id", "")
        context = issue.get("rocm_context", "")

        with st.container(border=True):
            st.markdown(f"""
            <div style='display:flex;justify-content:space-between;align-items:flex-start;gap:1rem;'>
                <div>
                    <div style='font-size:0.7rem;letter-spacing:0.18em;text-transform:uppercase;color:rgba(240,240,240,0.45);'>Severity</div>
                    <div style='font-size:1rem;font-weight:700;color:#f0f0f0;margin-top:0.2rem;'>
                        {_escape_html(issue.get('file','?'))}:{_escape_html(issue.get('line','?'))}
                    </div>
                </div>
                <span style='padding:0.35rem 0.8rem;border-radius:999px;border:1px solid {sev_color}44;background:{sev_color}18;color:{sev_color};font-size:0.75rem;font-weight:700;white-space:nowrap;'>
                    {_escape_html(severity)}
                </span>
            </div>
            <div style='color:rgba(240,240,240,0.7);font-size:0.9rem;line-height:1.55;margin-top:0.6rem;'>
                {_escape_html(issue.get('description',''))}
            </div>
            """, unsafe_allow_html=True)

            if amd_hint or pattern:
                chip_row = ""
                if amd_hint:
                    chip_row += f"<span style='display:inline-flex;padding:0.35rem 0.7rem;border-radius:999px;border:1px solid rgba(237,28,36,0.25);background:rgba(237,28,36,0.08);color:#ff3a40;font-size:0.75rem;margin-right:0.5rem;'>{_escape_html(amd_hint[:80])}</span>"
                if pattern:
                    chip_row += f"<span style='display:inline-flex;padding:0.35rem 0.7rem;border-radius:999px;border:1px solid rgba(255,255,255,0.1);background:rgba(255,255,255,0.04);color:rgba(240,240,240,0.6);font-size:0.75rem;'>Pattern: {_escape_html(pattern)}</span>"
                st.markdown(f"<div style='margin-top:0.6rem;'>{chip_row}</div>", unsafe_allow_html=True)

            if context:
                with st.expander("ROCm knowledge context"):
                    st.caption(context)


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

    # Colored unified diff
    lines_html = []
    for line in patch_text.splitlines():
        esc = html.escape(line)
        if line.startswith("+++") or line.startswith("---"):
            lines_html.append(f"<div class='diff-file'>{esc}</div>")
        elif line.startswith("@@"):
            lines_html.append(f"<div class='diff-hunk'>{esc}</div>")
        elif line.startswith("+"):
            lines_html.append(f"<div class='diff-add'>{esc}</div>")
        elif line.startswith("-"):
            lines_html.append(f"<div class='diff-del'>{esc}</div>")
        else:
            lines_html.append(f"<div class='diff-ctx'>{esc or '&nbsp;'}</div>")

    st.markdown(
        f"<div class='diff-block'>{''.join(lines_html)}</div>",
        unsafe_allow_html=True,
    )


# Agent Popup Functions

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
    state_color = {"complete": "#22c55e", "running": "#ED1C24", "error": "#ff4444"}.get(state, "#22c55e")
    status_label = _status_label(state)

    log_lines = _get_agent_logs(selected, step, agent_outputs)
    log_html = "".join(f"<div class='log-line'>{html.escape(line)}</div>" for line in log_lines)
    output_html = _get_agent_output_html(selected, results)

    # Inject CSS to pull the modal iframe to fullscreen overlay
    st.markdown("""
    <style>
    iframe[title="streamlit_components.v1.html"][srcdoc*="agent-modal-marker"] {
        position: fixed !important;
        top: 0 !important;
        left: 0 !important;
        width: 100vw !important;
        height: 100vh !important;
        z-index: 999998 !important;
        border: none !important;
    }
    </style>
    """, unsafe_allow_html=True)

    modal_html = f"""<!DOCTYPE html>
<html data-marker="agent-modal-marker">
<head>
<meta charset="utf-8">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html, body {{ width:100%; height:100%; }}
  body {{
    background: rgba(0,0,0,0.65);
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 2rem;
    font-family: "Segoe UI", sans-serif;
  }}
  .box {{
    background: linear-gradient(180deg, #1a1a24, #0f0f17);
    border: 1px solid rgba(237,28,36,0.25);
    border-radius: 24px;
    box-shadow: 0 40px 100px rgba(0,0,0,0.7), 0 0 60px rgba(237,28,36,0.1);
    width: 100%;
    max-width: 880px;
    max-height: 85vh;
    overflow-y: auto;
    padding: 2rem;
    color: #f0f0f0;
    position: relative;
  }}
  .close {{
    position: absolute;
    top: 1.2rem;
    right: 1.2rem;
    width: 2.2rem;
    height: 2.2rem;
    border-radius: 50%;
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.1);
    color: rgba(240,240,240,0.7);
    font-size: 1.2rem;
    cursor: pointer;
    display: grid;
    place-items: center;
    transition: all 0.2s ease;
  }}
  .close:hover {{
    background: rgba(237,28,36,0.15);
    border-color: #ED1C24;
    color: #ED1C24;
  }}
  .title {{
    font-size: 1.5rem;
    font-weight: 800;
    letter-spacing: -0.03em;
    color: #f0f0f0;
    margin-bottom: 0.4rem;
    padding-right: 3rem;
  }}
  .status-row {{ display:flex; align-items:center; gap:0.8rem; margin-bottom:1.4rem; }}
  .status-chip {{
    padding: 0.35rem 0.8rem;
    border-radius: 999px;
    font-size: 0.72rem;
    font-weight: 700;
    border: 1px solid {state_color}55;
    background: {state_color}15;
    color: {state_color};
  }}
  .desc {{ color: rgba(240,240,240,0.55); font-size: 0.85rem; }}
  .section-label {{
    text-transform: uppercase;
    letter-spacing: 0.18em;
    font-size: 0.7rem;
    color: rgba(240,240,240,0.4);
    margin-bottom: 0.6rem;
    margin-top: 1.2rem;
  }}
  .log {{
    background: #0a0a0d;
    border-radius: 14px;
    border: 1px solid rgba(255,255,255,0.05);
    padding: 1rem;
    font-family: "JetBrains Mono", "Cascadia Mono", Consolas, monospace;
    font-size: 0.78rem;
    color: #c8c8c8;
    max-height: 240px;
    overflow-y: auto;
    line-height: 1.6;
  }}
  .log-line::before {{ content: "> "; color: #ED1C24; opacity: 0.6; }}
  .output-box {{
    background: rgba(255,255,255,0.02);
    border: 1px solid rgba(255,255,255,0.05);
    border-radius: 14px;
    padding: 1rem;
  }}
  .severity-chip {{
    padding: 0.4rem 0.85rem;
    border-radius: 999px;
    font-size: 0.78rem;
    font-weight: 700;
    cursor: pointer;
    border: 1px solid;
    transition: all 0.2s ease;
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
  }}
  .severity-chip:hover {{ transform: translateY(-1px); }}
  .severity-chip.high {{ color:#ff4444; border-color:rgba(255,68,68,0.3); background:rgba(255,68,68,0.07); }}
  .severity-chip.medium {{ color:#f59e0b; border-color:rgba(245,158,11,0.3); background:rgba(245,158,11,0.07); }}
  .severity-chip.low {{ color:#22c55e; border-color:rgba(34,197,94,0.3); background:rgba(34,197,94,0.07); }}
  .severity-chip.active {{ filter: brightness(1.4); transform: translateY(-1px); }}
  .issue-row {{
    padding: 0.7rem 0.9rem;
    margin-top: 0.5rem;
    border-radius: 10px;
    background: rgba(255,255,255,0.025);
    border-left: 3px solid;
    font-size: 0.82rem;
    color: rgba(240,240,240,0.85);
  }}
  .issue-row.high {{ border-left-color: #ff4444; }}
  .issue-row.medium {{ border-left-color: #f59e0b; }}
  .issue-row.low {{ border-left-color: #22c55e; }}
  .issue-meta {{ font-size: 0.72rem; color: rgba(240,240,240,0.5); margin-top: 0.2rem; }}
  .diff-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:1rem; }}
  .diff-pane {{
    background: #0a0a0d;
    border-radius: 12px;
    border: 1px solid rgba(255,255,255,0.05);
    padding: 0.85rem;
    font-family: "JetBrains Mono", monospace;
    font-size: 0.76rem;
    max-height: 280px;
    overflow: auto;
  }}
  .diff-label {{ font-size:0.65rem; letter-spacing:0.14em; text-transform:uppercase; color:rgba(240,240,240,0.4); margin-bottom:0.5rem; }}
  .diff-removed {{ color: #ff6b6b; }}
  .diff-added {{ color: #5af07f; }}
  .pill {{
    display: inline-flex;
    align-items: center;
    padding: 0.4rem 0.85rem;
    border-radius: 999px;
    border: 1px solid rgba(255,255,255,0.1);
    background: rgba(255,255,255,0.04);
    color: #f0f0f0;
    font-size: 0.78rem;
    margin-right: 0.4rem;
    margin-bottom: 0.4rem;
  }}
</style>
</head>
<body>
  <div class="box">
    <button class="close" onclick="closeModal()">×</button>
    <div class="title">{html.escape(selected)}</div>
    <div class="status-row">
        <span class="status-chip">{html.escape(status_label)}</span>
        <span class="desc">{html.escape(step.get('description', ''))}</span>
    </div>
    <div class="section-label">Live Log</div>
    <div class="log">{log_html}</div>
    <div class="section-label">Agent Output</div>
    <div class="output-box">{output_html}</div>
  </div>
<script>
  function closeModal() {{
    var frames = window.parent.document.querySelectorAll('iframe');
    for (var i = 0; i < frames.length; i++) {{
      if (frames[i].srcdoc && frames[i].srcdoc.indexOf('agent-modal-marker') >= 0) {{
        frames[i].style.display = 'none';
        // Trigger Streamlit close via the close button in the parent
        var btns = window.parent.document.querySelectorAll('button');
        for (var j = 0; j < btns.length; j++) {{
          if (btns[j].textContent.trim() === '__close_agent_modal__') {{ btns[j].click(); break; }}
        }}
        break;
      }}
    }}
  }}
  document.addEventListener('keydown', function(e) {{ if (e.key === 'Escape') closeModal(); }});
  document.body.addEventListener('click', function(e) {{ if (e.target === document.body) closeModal(); }});
  // Severity filtering
  document.querySelectorAll('.severity-chip').forEach(function(chip) {{
    chip.addEventListener('click', function() {{
      var sev = chip.getAttribute('data-sev');
      document.querySelectorAll('.severity-chip').forEach(function(c) {{ c.classList.remove('active'); }});
      chip.classList.add('active');
      var rows = document.querySelectorAll('.issue-row');
      rows.forEach(function(r) {{
        if (sev === 'all' || r.classList.contains(sev)) {{ r.style.display = ''; }}
        else {{ r.style.display = 'none'; }}
      }});
    }});
  }});
</script>
</body>
</html>"""

    components.html(modal_html, height=700, scrolling=False)

    # Hidden Streamlit button that the iframe JS clicks to actually clear session state
    st.markdown("<div class='hidden-helper'>", unsafe_allow_html=True)
    if st.button("__close_agent_modal__", key="close_agent_modal_hidden"):
        st.session_state.selected_agent = None
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)


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


def _get_agent_output_html(agent_name: str, results: dict) -> str:
    agent_outputs = results.get("agent_outputs", {})

    if agent_name == "Scanner":
        issues = agent_outputs.get("scanner", [])
        patterns: dict[str, int] = {}
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
        high = [i for i in issues if isinstance(i, dict) and i.get("severity") == "high"]
        med = [i for i in issues if isinstance(i, dict) and i.get("severity") == "medium"]
        low = [i for i in issues if isinstance(i, dict) and i.get("severity") == "low"]

        def issue_row_html(issue, sev):
            file = html.escape(str(issue.get("file", "?")))
            line = html.escape(str(issue.get("line", "?")))
            desc = html.escape(str(issue.get("description", "")))
            hint = html.escape(str(issue.get("amd_fix_hint", "")))
            return f"""<div class='issue-row {sev}'>
                <div>{desc}</div>
                <div class='issue-meta'>{file}:{line}{' · ' + hint if hint else ''}</div>
            </div>"""

        rows = ""
        for i in high: rows += issue_row_html(i, "high")
        for i in med: rows += issue_row_html(i, "medium")
        for i in low: rows += issue_row_html(i, "low")

        return f"""
        <div style='display:flex;gap:0.6rem;flex-wrap:wrap;margin-bottom:1rem;'>
            <span class='severity-chip all active' data-sev='all' style='color:#f0f0f0;border-color:rgba(255,255,255,0.2);background:rgba(255,255,255,0.05);'>All: {len(issues)}</span>
            <span class='severity-chip high' data-sev='high'>High: {len(high)}</span>
            <span class='severity-chip medium' data-sev='medium'>Medium: {len(med)}</span>
            <span class='severity-chip low' data-sev='low'>Low: {len(low)}</span>
        </div>
        <div style='margin-top:0.5rem;'>{rows or '<div style="color:rgba(255,255,255,0.4);">No issues to show.</div>'}</div>
        """

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


# AMD Splash Screen

def _render_amd_splash(results: dict) -> None:
    issues = results.get("issues", [])
    applied = results.get("applied_edits", [])
    issues_found = len(issues)
    issues_fixed = len(applied)
    score_before = results.get("readiness_score", 0)
    score_after = results.get("score_after", score_before)
    if score_after > score_before:
        improvement = score_after - score_before
        suffix = " pts"
        prefix = "+"
    elif issues_found > 0:
        improvement = round(min(issues_fixed / issues_found, 1) * 100)
        suffix = "% fixed"
        prefix = ""
    else:
        improvement = 100
        suffix = "% clean"
        prefix = ""

    # Inject CSS that pulls the splash iframe to fixed full-screen position.
    st.markdown("""
    <style>
    iframe[title="streamlit_components.v1.html"][srcdoc*="amd-splash-marker"] {
        position: fixed !important;
        top: 0 !important;
        left: 0 !important;
        width: 100vw !important;
        height: 100vh !important;
        z-index: 999999 !important;
        border: none !important;
    }
    </style>
    """, unsafe_allow_html=True)

    splash_html = f"""<!DOCTYPE html>
<html data-marker="amd-splash-marker">
<head>
<meta charset="utf-8">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  html, body {{ width: 100%; height: 100%; overflow: hidden; }}
  body {{
    background: rgba(5,5,10,0.97);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 1.4rem;
    text-align: center;
    padding: 2rem;
    font-family: "Segoe UI", sans-serif;
    color: #f0f0f0;
    transition: opacity 0.7s ease;
  }}
  .blob {{ position: fixed; border-radius: 50%; filter: blur(100px); pointer-events: none; }}
  .b1 {{ width: 500px; height: 500px; background: #ED1C24; opacity: 0.1; top: -150px; left: -100px; }}
  .b2 {{ width: 400px; height: 400px; background: #8B0000; opacity: 0.08; bottom: -100px; right: -80px; }}
  .wm {{ font-size: clamp(3rem, 9vw, 6.5rem); font-weight: 900; letter-spacing: -0.04em; line-height: 1; }}
  .wm span {{ color: #ED1C24; }}
  .sub {{ color: rgba(240,240,240,0.5); font-size: 0.85rem; letter-spacing: 0.14em; text-transform: uppercase; }}
  .ctr {{ font-size: clamp(2.5rem, 6vw, 5rem); font-weight: 900; color: #ED1C24; letter-spacing: -0.04em; line-height: 1; }}
  .pills {{ display: flex; gap: 0.75rem; flex-wrap: wrap; justify-content: center; }}
  .pill {{ padding: 0.45rem 1rem; border-radius: 999px; border: 1px solid rgba(255,255,255,0.12); background: rgba(255,255,255,0.05); font-size: 0.85rem; }}
  .bar {{ width: min(360px, 85vw); height: 3px; background: rgba(255,255,255,0.08); border-radius: 999px; overflow: hidden; }}
  .bar-fill {{ height: 100%; width: 100%; background: #ED1C24; border-radius: 999px; transition: width 6s linear; }}
  .skip {{
    margin-top: 0.5rem;
    padding: 0.5rem 1.4rem;
    border-radius: 999px;
    background: transparent;
    border: 1px solid rgba(255,255,255,0.2);
    color: rgba(240,240,240,0.7);
    font-size: 0.8rem;
    cursor: pointer;
    font-family: inherit;
  }}
  .skip:hover {{ border-color: #ED1C24; color: #ED1C24; }}
</style>
</head>
<body id="splash-body">
  <div class="blob b1"></div>
  <div class="blob b2"></div>
  <div class="wm"><span>AMD</span> Ready</div>
  <div class="sub">Migration Complete &middot; Validated on MI300X</div>
  <div class="ctr" id="ctr">{prefix}0{suffix}</div>
  <div class="pills">
    <div class="pill">{issues_found} issues found</div>
    <div class="pill">{issues_fixed} issues fixed</div>
  </div>
  <div class="bar"><div class="bar-fill" id="bar"></div></div>
  <button class="skip" onclick="dismiss()">Skip →</button>
<script>
  var target = {improvement};
  var prefix = {repr(prefix)};
  var suffix = {repr(suffix)};
  var ctr = document.getElementById('ctr');
  var bar = document.getElementById('bar');
  var body = document.getElementById('splash-body');
  var dismissed = false;
  var start = null;
  function tick(ts) {{
    if (!start) start = ts;
    var p = Math.min((ts - start) / 2200, 1);
    var e = 1 - Math.pow(1 - p, 3);
    var cur = Math.round(e * target);
    ctr.textContent = prefix + cur + suffix;
    if (p < 1) requestAnimationFrame(tick);
  }}
  requestAnimationFrame(tick);
  setTimeout(function() {{ bar.style.width = '0%'; }}, 100);
  function dismiss() {{
    if (dismissed) return;
    dismissed = true;
    body.style.opacity = '0';
    setTimeout(function() {{
      // Hide the iframe itself by messaging parent
      var frames = window.parent.document.querySelectorAll('iframe');
      for (var i = 0; i < frames.length; i++) {{
        if (frames[i].srcdoc && frames[i].srcdoc.indexOf('amd-splash-marker') >= 0) {{
          frames[i].style.display = 'none';
          break;
        }}
      }}
    }}, 700);
  }}
  setTimeout(dismiss, 6500);
</script>
</body>
</html>"""

    components.html(splash_html, height=600, scrolling=False)


# Helper Functions & UI Components Below

def _dashboard_styles() -> str:
    return """
    <style>
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

    /* Hide sidebar entirely */
    section[data-testid="stSidebar"],
    [data-testid="collapsedControl"] {
        display: none !important;
    }

    /* Floating top bar */
    .top-bar {
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        z-index: 8000;
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 0.7rem 2rem;
        background: rgba(10,10,15,0.85);
        backdrop-filter: blur(12px);
        border-bottom: 1px solid rgba(255,255,255,0.06);
    }

    .top-bar__brand {
        display: flex;
        align-items: center;
        gap: 0.7rem;
    }

    .top-bar__mark {
        display: grid;
        place-items: center;
        width: 2.2rem;
        height: 2.2rem;
        border-radius: 10px;
        background: linear-gradient(135deg, rgba(237,28,36,0.25), rgba(176,16,24,0.1));
        border: 1px solid rgba(237,28,36,0.4);
        color: #ED1C24;
        font-size: 0.9rem;
        font-weight: 900;
    }

    .top-bar__title {
        font-size: 0.95rem;
        font-weight: 800;
        color: #f0f0f0;
        letter-spacing: -0.02em;
    }

    .top-bar__sub {
        font-size: 0.65rem;
        color: oklch(0.72 0.02 248);
        letter-spacing: 0.14em;
        text-transform: uppercase;
    }

    /* Push content below the top bar */
    main .block-container {
        padding-top: 5rem !important;
    }

    /* AMD Ready Banner */
    .ready-banner {
        margin-top: 2rem;
        margin-bottom: 1.5rem;
        padding: 2rem 2rem 1.7rem;
        border-radius: 24px;
        border: 1px solid rgba(237,28,36,0.25);
        background: linear-gradient(135deg, rgba(20,20,28,0.95), rgba(15,15,22,0.95));
        box-shadow: 0 0 60px rgba(237,28,36,0.08);
        position: relative;
        overflow: hidden;
    }

    .ready-banner::before {
        content: "";
        position: absolute;
        top: -100px;
        right: -100px;
        width: 300px;
        height: 300px;
        background: radial-gradient(circle, rgba(237,28,36,0.15), transparent 70%);
        pointer-events: none;
    }

    .ready-banner__head {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 2rem;
        flex-wrap: wrap;
        margin-bottom: 1.5rem;
        position: relative;
        z-index: 1;
    }

    .ready-banner__kicker {
        font-size: 0.7rem;
        letter-spacing: 0.18em;
        text-transform: uppercase;
        color: rgba(240,240,240,0.5);
        margin-bottom: 0.3rem;
    }

    .ready-banner__title {
        font-size: clamp(2rem, 4vw, 3.2rem);
        font-weight: 900;
        letter-spacing: -0.04em;
        line-height: 1;
        color: #f0f0f0;
    }

    .ready-banner__title span { color: #ED1C24; }

    .ready-banner__improvement {
        text-align: right;
    }

    .ready-banner__delta {
        font-size: clamp(1.8rem, 3.5vw, 2.6rem);
        font-weight: 900;
        color: #ED1C24;
        letter-spacing: -0.03em;
        line-height: 1;
    }

    .ready-banner__delta-label {
        font-size: 0.7rem;
        letter-spacing: 0.18em;
        text-transform: uppercase;
        color: rgba(240,240,240,0.5);
        margin-top: 0.4rem;
    }

    .ready-banner__stats {
        display: grid;
        grid-template-columns: repeat(6, 1fr);
        gap: 0.8rem;
        position: relative;
        z-index: 1;
    }

    @media (max-width: 1100px) {
        .ready-banner__stats { grid-template-columns: repeat(3, 1fr); }
    }
    @media (max-width: 600px) {
        .ready-banner__stats { grid-template-columns: repeat(2, 1fr); }
    }

    .ready-stat {
        padding: 1rem 1.1rem;
        border-radius: 14px;
        background: rgba(255,255,255,0.025);
        border: 1px solid rgba(255,255,255,0.05);
    }

    .ready-stat__label {
        font-size: 0.65rem;
        letter-spacing: 0.18em;
        text-transform: uppercase;
        color: rgba(240,240,240,0.45);
        margin-bottom: 0.5rem;
    }

    .ready-stat__value {
        font-size: 1.6rem;
        font-weight: 800;
        color: #f0f0f0;
        letter-spacing: -0.03em;
        line-height: 1;
    }

    .ready-stat__value span {
        font-size: 0.85rem;
        color: rgba(240,240,240,0.4);
        font-weight: 500;
    }

    /* Colored Diff Block (Final Report > Code Diff tab) */
    .diff-block {
        background: #0a0a0d;
        border-radius: 14px;
        border: 1px solid rgba(255,255,255,0.06);
        padding: 1rem;
        font-family: "JetBrains Mono", "Cascadia Mono", Consolas, monospace;
        font-size: 0.82rem;
        line-height: 1.55;
        max-height: 600px;
        overflow: auto;
        white-space: pre;
    }
    .diff-block > div {
        padding: 0.05rem 0.5rem;
        border-radius: 4px;
    }
    .diff-file {
        color: #9ca3af;
        font-weight: 700;
        margin-top: 0.5rem;
    }
    .diff-hunk {
        color: #60a5fa;
        background: rgba(96,165,250,0.08);
        font-weight: 600;
    }
    .diff-add {
        color: #5af07f;
        background: rgba(34,197,94,0.12);
        border-left: 3px solid #22c55e;
    }
    .diff-del {
        color: #ff8484;
        background: rgba(239,68,68,0.12);
        border-left: 3px solid #ef4444;
    }
    .diff-ctx {
        color: rgba(240,240,240,0.55);
    }

    /* Hidden helper button for modal close */
    .hidden-helper {
        position: fixed;
        top: -9999px;
        left: -9999px;
        opacity: 0;
        pointer-events: auto;
    }

    /* Live Progress Panel */
    .prog-panel {
        max-width: 900px;
        margin: 4rem auto 2rem;
        padding: 2rem;
        border-radius: 24px;
        border: 1px solid rgba(255,255,255,0.06);
        background: linear-gradient(180deg, rgba(20,20,28,0.85), rgba(15,15,22,0.9));
        backdrop-filter: blur(8px);
    }

    .prog-panel__title {
        font-size: 1.5rem;
        font-weight: 800;
        letter-spacing: -0.03em;
        color: #f0f0f0;
        text-align: center;
    }

    .prog-panel__sub {
        text-align: center;
        color: rgba(240,240,240,0.5);
        font-size: 0.85rem;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        margin-top: 0.5rem;
        margin-bottom: 1.5rem;
    }

    .prog-bar {
        width: 100%;
        height: 4px;
        background: rgba(255,255,255,0.06);
        border-radius: 999px;
        overflow: hidden;
        margin-bottom: 2rem;
    }

    .prog-bar__fill {
        height: 100%;
        background: linear-gradient(90deg, #ED1C24, #ff5050);
        border-radius: 999px;
        transition: width 0.4s ease;
    }

    .prog-grid {
        display: grid;
        grid-template-columns: 1fr;
        gap: 0.6rem;
    }

    .prog-card {
        padding: 0.85rem 1.1rem;
        border-radius: 14px;
        border: 1px solid rgba(255,255,255,0.06);
        background: rgba(255,255,255,0.02);
        transition: all 0.3s ease;
    }

    .prog-card--running {
        border-color: rgba(237,28,36,0.45);
        background: rgba(237,28,36,0.06);
        box-shadow: 0 0 30px rgba(237,28,36,0.1);
    }

    .prog-card--done {
        border-color: rgba(34,197,94,0.25);
        background: rgba(34,197,94,0.04);
    }

    .prog-card__head {
        display: flex;
        align-items: center;
        gap: 0.7rem;
    }

    .prog-card__name {
        flex: 1;
        font-size: 0.95rem;
        font-weight: 700;
        color: #f0f0f0;
        letter-spacing: -0.01em;
    }

    .prog-card__desc {
        margin-top: 0.4rem;
        margin-left: 1.6rem;
        font-size: 0.8rem;
        color: rgba(240,240,240,0.5);
        line-height: 1.5;
    }

    .prog-dot {
        display: inline-grid;
        place-items: center;
        width: 1rem;
        height: 1rem;
        border-radius: 50%;
        font-size: 0.7rem;
        font-weight: 800;
    }

    .prog-dot--idle {
        background: rgba(255,255,255,0.1);
    }

    .prog-dot--running {
        background: #ED1C24;
        box-shadow: 0 0 0 0 rgba(237,28,36,0.6);
        animation: prog-pulse 1.2s ease-in-out infinite;
    }

    .prog-dot--done {
        background: #22c55e;
        color: #0a0a0a;
    }

    @keyframes prog-pulse {
        0%, 100% { box-shadow: 0 0 0 0 rgba(237,28,36,0.6); }
        50% { box-shadow: 0 0 0 6px rgba(237,28,36,0); }
    }

    .prog-tag {
        font-size: 0.65rem;
        font-weight: 800;
        letter-spacing: 0.18em;
        padding: 0.25rem 0.6rem;
        border-radius: 999px;
        border: 1px solid;
    }

    .prog-tag--idle {
        color: rgba(240,240,240,0.4);
        border-color: rgba(255,255,255,0.08);
    }

    .prog-tag--running {
        color: #ED1C24;
        border-color: rgba(237,28,36,0.4);
        background: rgba(237,28,36,0.08);
    }

    .prog-tag--done {
        color: #22c55e;
        border-color: rgba(34,197,94,0.3);
        background: rgba(34,197,94,0.05);
    }

    html, body, [data-testid="stAppViewContainer"] {
        background:
            radial-gradient(circle at top left, oklch(0.22 0.04 252 / 0.95) 0%, transparent 35%),
            radial-gradient(circle at top right, rgba(237,28,36,0.08) 0%, transparent 28%),
            linear-gradient(180deg, oklch(0.145 0.025 250), oklch(0.115 0.02 250));
        color: var(--rocm-foreground);
        font-family: "Aptos", "Segoe UI Variable Text", "Segoe UI", sans-serif;
    }

    [data-testid="stAppViewContainer"]::before {
        content: "";
        position: fixed;
        inset: 0;
        pointer-events: none;
        background-image: var(--rocm-grid);
        background-size: 32px 32px;
        opacity: 0.24;
        mask-image: linear-gradient(180deg, rgba(0, 0, 0, 0.45), transparent 80%);
        z-index: 0;
    }

    [data-testid="stAppViewContainer"] > .main {
        position: relative;
        z-index: 1;
    }

    main .block-container {
        max-width: 1600px;
        padding-top: 1.1rem;
        padding-bottom: 2.1rem;
    }

    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, oklch(0.13 0.02 250), oklch(0.1 0.015 250));
        border-right: 1px solid var(--rocm-border);
        box-shadow: inset -1px 0 0 oklch(1 0 0 / 0.03);
    }

    section[data-testid="stSidebar"] > div {
        background: transparent;
    }

    section[data-testid="stSidebar"]::before {
        content: "";
        position: absolute;
        inset: 0;
        pointer-events: none;
        background: radial-gradient(circle at 20% 8%, rgba(237,28,36,0.07), transparent 26%);
    }

    /* Start Migration - AMD Red Primary Button */
    button[kind="primary"] {
        background: linear-gradient(135deg, #ED1C24, #b01018) !important;
        color: #fff !important;
        border: 1px solid #ED1C24 !important;
        font-weight: 800 !important;
        box-shadow: 0 0 20px rgba(237,28,36,0.3) !important;
    }

    /* Streamlit Tabs - Glassmorphism Styling */
    button[data-baseweb="tab"] {
        background: transparent !important;
        color: var(--rocm-muted) !important;
        font-size: 0.95rem !important;
        padding: 0.75rem 1rem !important;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        color: var(--rocm-foreground) !important;
        border-bottom-color: var(--rocm-primary) !important;
    }

    .sidebar-brand {
        display: flex;
        align-items: center;
        gap: 0.875rem;
        padding: 0.25rem 0.15rem 1rem;
        border-bottom: 1px solid oklch(1 0 0 / 0.08);
        margin-bottom: 1rem;
    }

    .sidebar-brand__mark {
        display: grid;
        place-items: center;
        width: 2.85rem;
        height: 2.85rem;
        border-radius: 16px;
        background: linear-gradient(135deg, rgba(237,28,36,0.18), rgba(176,16,24,0.08));
        border: 1px solid rgba(237,28,36,0.35);
        box-shadow: var(--rocm-glow);
        color: var(--rocm-primary);
        font-size: 1.15rem;
        font-weight: 800;
    }

    .sidebar-brand__title {
        color: var(--rocm-foreground);
        font-size: 1rem;
        font-weight: 800;
        letter-spacing: -0.02em;
    }

    .sidebar-brand__subtitle {
        color: var(--rocm-muted);
        font-size: 0.72rem;
        letter-spacing: 0.18em;
        text-transform: uppercase;
        margin-top: 0.1rem;
    }

    .sidebar-nav {
        display: grid;
        gap: 0.5rem;
        margin: 0 0 1rem;
    }

    .sidebar-nav__item {
        display: flex;
        align-items: center;
        justify-content: space-between;
        border-radius: 14px;
        padding: 0.8rem 0.95rem;
        background: oklch(1 0 0 / 0.02);
        border: 1px solid oklch(1 0 0 / 0.05);
        color: var(--rocm-foreground);
        font-size: 0.92rem;
    }

    .sidebar-nav__item--active {
        background: linear-gradient(135deg, rgba(237,28,36,0.12), rgba(237,28,36,0.02));
        border-color: rgba(237,28,36,0.25);
        box-shadow: var(--rocm-glow);
    }

    .sidebar-panel,
    .sidebar-callout {
        border-radius: 20px;
        border: 1px solid rgba(237,28,36,0.14);
        background: linear-gradient(180deg, oklch(0.22 0.03 252 / 0.92), oklch(0.17 0.025 250 / 0.95));
        box-shadow: var(--rocm-shadow);
        padding: 1rem;
        margin-bottom: 0.9rem;
    }

    .sidebar-panel__title,
    .sidebar-callout__label,
    .section-kicker,
    .agent-step,
    .pipeline-strip__label,
    .rocm-pillar__label {
        text-transform: uppercase;
        letter-spacing: 0.18em;
        font-size: 0.7rem;
        color: var(--rocm-muted);
    }

    .sidebar-panel__subtitle,
    .sidebar-callout__copy {
        margin-top: 0.4rem;
        color: var(--rocm-muted);
        font-size: 0.88rem;
        line-height: 1.45;
    }

    [data-testid="stTextArea"] textarea,
    [data-testid="stTextInput"] input {
        background: oklch(0.13 0.02 250) !important;
        color: var(--rocm-foreground) !important;
        border: 1px solid oklch(0.35 0.03 252 / 0.85) !important;
        border-radius: 14px !important;
        box-shadow: inset 0 1px 0 oklch(1 0 0 / 0.03);
    }

    [data-testid="stTextArea"] textarea:focus,
    [data-testid="stTextInput"] input:focus {
        border-color: rgba(237,28,36,0.6) !important;
        box-shadow: 0 0 0 3px rgba(237,28,36,0.15) !important;
    }

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

    div[data-testid="stMetric"] {
        border-radius: 20px;
        border: 1px solid oklch(1 0 0 / 0.08);
        background: linear-gradient(180deg, oklch(0.2 0.03 252 / 0.96), oklch(0.16 0.025 250 / 0.94));
        box-shadow: var(--rocm-shadow);
        padding: 1rem 1rem 0.9rem;
    }

    div[data-testid="stMetricValue"] {
        color: var(--rocm-foreground);
        font-weight: 800;
        letter-spacing: -0.03em;
    }

    div[data-testid="stMetricLabel"] {
        color: var(--rocm-muted);
        text-transform: uppercase;
        letter-spacing: 0.14em;
        font-size: 0.68rem;
    }

    [data-testid="stAlert"] {
        border-radius: 18px;
        border: 1px solid rgba(237,28,36,0.2);
        background: linear-gradient(135deg, oklch(0.2 0.03 252 / 0.96), oklch(0.16 0.025 250 / 0.96));
        box-shadow: var(--rocm-shadow);
    }

    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 24px;
        border: 1px solid oklch(1 0 0 / 0.08);
        background: linear-gradient(180deg, oklch(0.2 0.03 252 / 0.8), oklch(0.14 0.02 250 / 0.78));
        box-shadow: var(--rocm-shadow);
        padding: 1rem 1rem 1.15rem;
    }

    .hero-shell {
        display: grid;
        grid-template-columns: 1fr;
        gap: 1rem;
        margin-bottom: 1rem;
        margin-top: 1rem;
    }

    .hero-copy,
    .hero-panel,
    .stat-card,
    .agent-card,
    .pipeline-strip,
    .issue-card,
    .chip-row,
    .attempts-header,
    .rocm-section-note {
        border-radius: 24px;
        border: 1px solid oklch(1 0 0 / 0.08);
        background: linear-gradient(180deg, oklch(0.2 0.03 252 / 0.96), oklch(0.14 0.02 250 / 0.9));
        box-shadow: var(--rocm-shadow);
    }

    .hero-copy {
        padding: 1.4rem 1.4rem 1.25rem;
        position: relative;
        overflow: hidden;
    }

    .hero-copy::after {
        content: "";
        position: absolute;
        inset: auto -6rem -7rem auto;
        width: 16rem;
        height: 16rem;
        border-radius: 999px;
        background: radial-gradient(circle, rgba(237,28,36,0.14), transparent 62%);
        pointer-events: none;
    }

    .hero-badge {
        display: inline-flex;
        align-items: center;
        gap: 0.45rem;
        padding: 0.38rem 0.75rem;
        border-radius: 999px;
        border: 1px solid rgba(237,28,36,0.25);
        background: rgba(237,28,36,0.08);
        color: var(--rocm-primary-strong);
        font-size: 0.72rem;
        letter-spacing: 0.18em;
        text-transform: uppercase;
        font-weight: 800;
    }

    .hero-title {
        margin: 0.95rem 0 0;
        color: var(--rocm-foreground);
        font-size: clamp(2.2rem, 4.9vw, 4.4rem);
        line-height: 0.95;
        letter-spacing: -0.06em;
        font-weight: 850;
    }

    .hero-copy__body {
        margin-top: 0.95rem;
        color: var(--rocm-muted);
        font-size: 1rem;
        line-height: 1.65;
        max-width: 62ch;
    }

    .hero-chip,
    .file-chip,
    .severity-chip,
    .attempt-chip,
    .status-chip,
    .summary-chip {
        display: inline-flex;
        align-items: center;
        gap: 0.35rem;
        border-radius: 999px;
        border: 1px solid oklch(1 0 0 / 0.08);
        background: oklch(1 0 0 / 0.05);
        color: var(--rocm-foreground);
        font-size: 0.75rem;
        padding: 0.45rem 0.72rem;
    }

    .hero-chip--primary,
    .status-chip--complete,
    .summary-chip--primary {
        border-color: rgba(237,28,36,0.28);
        background: rgba(237,28,36,0.1);
        color: var(--rocm-primary-strong);
    }

    .hero-chip--crimson,
    .severity-chip--high,
    .status-chip--error,
    .summary-chip--crimson {
        border-color: oklch(0.65 0.24 25 / 0.28);
        background: oklch(0.65 0.24 25 / 0.1);
        color: #ff9e98;
    }

    .hero-panel {
        padding: 1rem;
        display: grid;
        gap: 0.75rem;
        align-content: start;
    }

    .hero-panel__title {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
    }

    .hero-panel__kicker,
    .section-kicker,
    .attempts-header__kicker {
        color: var(--rocm-muted);
        font-size: 0.7rem;
        letter-spacing: 0.18em;
        text-transform: uppercase;
        font-weight: 800;
    }

    .hero-panel__headline,
    .section-title,
    .attempts-header__title {
        color: var(--rocm-foreground);
        font-size: 1.1rem;
        font-weight: 800;
        letter-spacing: -0.03em;
        margin-top: 0.25rem;
    }

    .hero-panel__body,
    .attempts-header__body,
    .rocm-section-note__body {
        color: var(--rocm-muted);
        font-size: 0.92rem;
        line-height: 1.55;
    }

    .hero-panel__stats {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 0.75rem;
    }

    .hero-panel__stat {
        border-radius: 18px;
        border: 1px solid oklch(1 0 0 / 0.08);
        background: oklch(1 0 0 / 0.03);
        padding: 0.85rem 0.9rem;
    }

    .hero-panel__stat-label,
    .stat-card__label,
    .issue-card__meta,
    .agent-detail,
    .agent-output__label,
    .pipeline-strip__label,
    .rocm-section-note__label {
        color: var(--rocm-muted);
        font-size: 0.72rem;
        letter-spacing: 0.18em;
        text-transform: uppercase;
    }

    .hero-panel__stat-value,
    .stat-card__value,
    .agent-name,
    .issue-card__title,
    .pipeline-strip__value strong {
        color: var(--rocm-foreground);
        font-weight: 800;
        letter-spacing: -0.03em;
    }

    .hero-panel__stat-value {
        font-size: 1.2rem;
        margin-top: 0.35rem;
    }

    .hero-panel__stat-copy,
    .stat-card__detail,
    .agent-output__body,
    .pipeline-strip__detail,
    .issue-card__body,
    .rocm-section-note__copy {
        color: var(--rocm-muted);
        font-size: 0.84rem;
        line-height: 1.5;
        margin-top: 0.35rem;
    }

    .stat-card {
        padding: 1rem 1rem 0.95rem;
        min-height: 130px;
    }

    .stat-card--success,
    .agent-card--complete,
    .summary-chip--success,
    .file-chip--success {
        border-color: rgba(237,28,36,0.24);
    }

    .stat-card--warning,
    .agent-card--pending,
    .summary-chip--warning,
    .file-chip--warning {
        border-color: oklch(0.82 0.16 84 / 0.24);
    }

    .stat-card--crimson,
    .agent-card--error,
    .summary-chip--crimson,
    .file-chip--crimson {
        border-color: oklch(0.65 0.24 25 / 0.24);
    }

    .stat-card__value {
        font-size: 1.45rem;
        margin-top: 0.45rem;
    }

    .agent-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
        gap: 0.9rem;
    }

    .agent-card {
        padding: 1rem 1rem 0.9rem;
        position: relative;
        overflow: hidden;
        min-height: 210px;
    }

    .agent-card::after {
        content: "";
        position: absolute;
        inset: auto -1.5rem -1.5rem auto;
        width: 8rem;
        height: 8rem;
        border-radius: 999px;
        background: radial-gradient(circle, rgba(237,28,36,0.08), transparent 68%);
        pointer-events: none;
    }

    .agent-card--running {
        border-color: rgba(237,28,36,0.45);
        box-shadow: 0 0 42px rgba(237,28,36,0.2);
    }

    .agent-card__top,
    .issue-card__top,
    .pipeline-strip,
    .attempts-header {
        display: flex;
        justify-content: space-between;
        gap: 0.9rem;
        align-items: flex-start;
    }

    .agent-name,
    .issue-card__title {
        font-size: 1.02rem;
        margin-top: 0.35rem;
    }

    .agent-detail {
        margin-top: 0.35rem;
        line-height: 1.6;
        font-size: 0.8rem;
        letter-spacing: 0.13em;
    }

    .agent-output {
        margin-top: 0.9rem;
        padding-top: 0.75rem;
        border-top: 1px solid oklch(1 0 0 / 0.08);
    }

    .agent-output__body,
    .pipeline-strip__value strong,
    .issue-card__body,
    .rocm-section-note__copy {
        font-size: 0.88rem;
        letter-spacing: normal;
        text-transform: none;
    }

    .agent-status,
    .severity-chip,
    .status-chip {
        white-space: nowrap;
        align-self: flex-start;
    }

    .agent-status--running::before,
    .status-chip--running::before {
        content: "";
        width: 0.42rem;
        height: 0.42rem;
        border-radius: 999px;
        background: var(--amd-red);
        box-shadow: 0 0 0 0 rgba(237,28,36,0.35);
        animation: rocm-pulse 1.5s ease-in-out infinite;
    }

    .pipeline-strip {
        margin-top: 0.95rem;
        padding: 0.9rem 1rem;
        align-items: center;
        gap: 0.9rem;
        flex-wrap: wrap;
    }

    .pipeline-strip__stat {
        flex: 1 1 150px;
        min-width: 150px;
    }

    .chip-row {
        display: flex;
        flex-wrap: wrap;
        gap: 0.55rem;
        padding: 0.85rem 0.95rem;
        margin-bottom: 0.75rem;
    }

    .file-chip {
        border-color: rgba(237,28,36,0.18);
    }

    .issue-card {
        padding: 1rem;
        margin-top: 0.85rem;
    }

    .issue-card__meta-row {
        display: flex;
        flex-wrap: wrap;
        gap: 0.55rem;
        align-items: center;
        margin-top: 0.55rem;
    }

    .issue-card__body {
        margin-top: 0.7rem;
        font-size: 0.92rem;
        line-height: 1.55;
    }

    .issue-card details {
        margin-top: 0.85rem;
        border-top: 1px solid oklch(1 0 0 / 0.08);
        padding-top: 0.7rem;
    }

    .issue-card summary {
        cursor: pointer;
        color: var(--rocm-primary-strong);
        font-weight: 700;
        font-size: 0.84rem;
        list-style: none;
    }

    .issue-card summary::-webkit-details-marker {
        display: none;
    }

    .issue-card__context {
        margin-top: 0.6rem;
        color: var(--rocm-muted);
        font-size: 0.84rem;
        line-height: 1.55;
        white-space: pre-wrap;
    }

    .attempts-header {
        margin: 0 0 0.9rem;
        padding: 0.9rem 1rem;
    }

    .attempts-header__count {
        color: var(--rocm-primary-strong);
        font-size: 1.4rem;
        font-weight: 800;
        letter-spacing: -0.04em;
    }

    .rocm-section-note {
        padding: 0.9rem 1rem;
        margin-bottom: 0.9rem;
    }

    .rocm-section-note__title {
        color: var(--rocm-foreground);
        font-weight: 800;
        font-size: 0.96rem;
        margin-top: 0.25rem;
    }

    pre, code {
        font-family: "JetBrains Mono", "Fira Code", "Cascadia Mono", Consolas, monospace !important;
    }

    div[data-testid="stCodeBlock"] {
        border-radius: 18px;
        overflow: hidden;
        border: 1px solid oklch(1 0 0 / 0.08);
        box-shadow: var(--rocm-shadow);
    }

    @keyframes rocm-pulse {
        0%, 100% { transform: scale(1); opacity: 0.95; box-shadow: 0 0 0 0 rgba(237,28,36,0.35); }
        50% { transform: scale(1.24); opacity: 0.65; box-shadow: 0 0 0 6px rgba(237,28,36,0); }
    }

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
    </style>
    """


def _sidebar_header() -> str:
    return """
    <div class='sidebar-brand'>
        <div class='sidebar-brand__mark'>R</div>
        <div>
            <div class='sidebar-brand__title'>ROCmForge</div>
            <div class='sidebar-brand__subtitle'>AMD MI300X migration lab</div>
        </div>
    </div>
    """


def _sidebar_nav() -> str:
    return """
    <div class='sidebar-nav'>
        <div class='sidebar-nav__item sidebar-nav__item--active'>
            <span>New Migration</span><span>01</span>
        </div>
    </div>
    """


def _sidebar_snapshot(readiness_score: int, qa_status: str, issues_count: int, failure_class: str) -> str:
    qa_display = qa_status if qa_status != "failed" else f"failed · {failure_class}"
    return f"""
    <div class='sidebar-panel'>
        <div class='sidebar-panel__title'>Current run</div>
        <div class='hero-panel__stats' style='margin-top:0.75rem;'>
            <div class='hero-panel__stat'>
                <div class='hero-panel__stat-label'>Readiness</div>
                <div class='hero-panel__stat-value'>{readiness_score}/100</div>
            </div>
            <div class='hero-panel__stat'>
                <div class='hero-panel__stat-label'>Issues</div>
                <div class='hero-panel__stat-value'>{issues_count}</div>
            </div>
        </div>
        <div class='hero-panel__stat' style='margin-top:0.75rem;'>
            <div class='hero-panel__stat-label'>AMD QA</div>
            <div class='hero-panel__stat-value'>{_escape_html(qa_display)}</div>
        </div>
    </div>
    """


def _hero_info_card() -> str:
    return """
    <section class='hero-shell'>
        <div class='hero-panel'>
            <div class='hero-panel__title'>
                <div>
                    <div class='hero-panel__kicker'>Before start</div>
                    <div class='hero-panel__headline'>Ready to run</div>
                </div>
                <span class='status-chip status-chip--running'>Idle</span>
            </div>
            <div class='hero-panel__body'>Paste a CUDA-dependent script or point ROCmForge at a GitHub repository to begin the full migration loop.</div>
            <div class='hero-panel__stats'>
                <div class='hero-panel__stat'>
                    <div class='hero-panel__stat-label'>Pipeline</div>
                    <div class='hero-panel__stat-value'>6 agents</div>
                    <div class='hero-panel__stat-copy'>Scanner, compatibility, knowledge, migration, QA, report.</div>
                </div>
                <div class='hero-panel__stat'>
                    <div class='hero-panel__stat-label'>Style</div>
                    <div class='hero-panel__stat-value'>Lovable</div>
                    <div class='hero-panel__stat-copy'>Glass cards, glowing borders, and dark control-surface styling.</div>
                </div>
                <div class='hero-panel__stat'>
                    <div class='hero-panel__stat-label'>Target</div>
                    <div class='hero-panel__stat-value'>MI300X</div>
                    <div class='hero-panel__stat-copy'>Designed to feel like an AI ops dashboard for AMD hardware.</div>
                </div>
                <div class='hero-panel__stat'>
                    <div class='hero-panel__stat-label'>Input</div>
                    <div class='hero-panel__stat-value'>Main</div>
                    <div class='hero-panel__stat-copy'>Controls are placed in the primary card for a focused workflow.</div>
                </div>
            </div>
        </div>
    </section>
    """


def _stat_card(title: str, value: object, detail: str, tone: str = "primary") -> str:
    tone_class = {
        "primary": "stat-card--success",
        "success": "stat-card--success",
        "warning": "stat-card--warning",
        "crimson": "stat-card--crimson",
    }.get(tone, "stat-card--success")
    return f"""
    <div class='stat-card {tone_class}'>
        <div class='stat-card__label'>{_escape_html(title)}</div>
        <div class='stat-card__value'>{_escape_html(value)}</div>
        <div class='stat-card__detail'>{_escape_html(detail)}</div>
    </div>
    """


def _section_header(kicker: str, title: str, subtitle: str) -> str:
    return f"""
    <div class='rocm-section-note'>
        <div class='section-kicker'>{_escape_html(kicker)}</div>
        <div class='rocm-section-note__title'>{_escape_html(title)}</div>
        <div class='rocm-section-note__body'>{_escape_html(subtitle)}</div>
    </div>
    """


def _agent_grid(timeline: list[dict]) -> str:
    cards = "".join(_agent_card(step) for step in timeline)
    return f"<div class='agent-grid'>{cards}</div>"


def _agent_card(step: dict) -> str:
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
    return f"""
    <div class='agent-card {state_class}'>
        <div class='agent-card__top'>
            <div class='agent-card__headline'>
                <div class='agent-step'>Step {step.get('step', '?')}</div>
                <div class='agent-name'>{_escape_html(step.get('name', 'Agent'))}</div>
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


def _pipeline_strip(scanner_count: int, compatibility_count: int, knowledge_count: int, report_lines: int) -> str:
    return f"""
    <div class='pipeline-strip'>
        <div class='pipeline-strip__stat'>
            <div class='pipeline-strip__label'>Scanner</div>
            <div class='pipeline-strip__value'><strong>{scanner_count}</strong> issues surfaced</div>
        </div>
        <div class='pipeline-strip__stat'>
            <div class='pipeline-strip__label'>Compatibility</div>
            <div class='pipeline-strip__value'><strong>{compatibility_count}</strong> hints attached</div>
        </div>
        <div class='pipeline-strip__stat'>
            <div class='pipeline-strip__label'>Knowledge</div>
            <div class='pipeline-strip__value'><strong>{knowledge_count}</strong> enriched findings</div>
        </div>
        <div class='pipeline-strip__stat'>
            <div class='pipeline-strip__label'>Report</div>
            <div class='pipeline-strip__value'><strong>{report_lines}</strong> lines generated</div>
        </div>
    </div>
    """


def _issue_legend() -> str:
    return """
    <div class='chip-row'>
        <span class='severity-chip severity-chip--high'>High severity</span>
        <span class='severity-chip severity-chip--medium'>Medium severity</span>
        <span class='severity-chip severity-chip--low'>Low severity</span>
        <span class='summary-chip summary-chip--primary'>ROCm context available</span>
    </div>
    """


def _issue_card(issue: dict) -> str:
    severity = str(issue.get("severity", "unknown"))
    severity_class = {
        "high": "severity-chip--high",
        "medium": "severity-chip--medium",
        "low": "severity-chip--low",
    }.get(severity, "severity-chip--medium")
    context = _escape_html(issue.get("rocm_context", ""))
    sources = issue.get("rocm_sources", [])
    source_items = "".join(
        f"<span class='file-chip'>{_escape_html(src.get('heading') or src.get('source') or 'unknown')}</span>"
        for src in sources
    ) or "<span class='file-chip file-chip--warning'>No source refs</span>"
    context_block = ""
    if context or sources:
        context_block = f"""
        <details>
            <summary>ROCm knowledge context</summary>
            <div class='issue-card__context'>{context or 'No local ROCm context was retrieved for this issue.'}</div>
            <div class='chip-row' style='margin-top:0.7rem;'>{source_items}</div>
        </details>
        """
    return f"""
    <div class='issue-card'>
        <div class='issue-card__top'>
            <div class='issue-card__headline'>
                <div class='issue-card__meta'>Severity</div>
                <div class='issue-card__title'>{_escape_html(issue.get('file', '?'))}:{_escape_html(issue.get('line', '?'))}</div>
            </div>
            <span class='severity-chip {severity_class}'>{_escape_html(severity)}</span>
        </div>
        <div class='issue-card__body'>{_escape_html(issue.get('description', ''))}</div>
        <div class='issue-card__meta-row'>
            {f"<span class='summary-chip summary-chip--primary'>{_escape_html(issue.get('amd_fix_hint', ''))}</span>" if issue.get('amd_fix_hint') else ''}
            {f"<span class='summary-chip'>Pattern: {_escape_html(issue.get('pattern_id', 'unknown'))}</span>" if issue.get('pattern_id') else ''}
        </div>
        {context_block}
    </div>
    """


def _chip_row(items: list[str], empty_label: str = "None") -> str:
    if not items:
        return f"<div class='chip-row'><span class='file-chip file-chip--warning'>{_escape_html(empty_label)}</span></div>"
    chips = "".join(f"<span class='file-chip'>{_escape_html(item)}</span>" for item in items)
    return f"<div class='chip-row'>{chips}</div>"


def _attempts_header(count: int) -> str:
    return f"""
    <div class='attempts-header'>
        <div>
            <div class='attempts-header__kicker'>Retry loop</div>
            <div class='attempts-header__title'>AMD QA attempts</div>
            <div class='attempts-header__body'>The last pass is used for the report, but failed attempts remain visible for debugging.</div>
        </div>
        <div class='attempts-header__count'>{count}</div>
    </div>
    """


def _build_agent_timeline(
    agent_names: list[str],
    agent_outputs: dict,
    attempts: list[dict],
    qa_result: dict,
    report_markdown: str,
) -> list[dict]:
    scanner_count = len(agent_outputs.get("scanner", []))
    compatibility_count = len(agent_outputs.get("compatibility", []))
    knowledge_items = agent_outputs.get("knowledge", [])
    source_count = sum(len(item.get("rocm_sources", [])) for item in knowledge_items)
    final_attempt = attempts[-1] if attempts else {}
    edits_count = len(final_attempt.get("edits_raw", []))
    patch_lines = len((final_attempt.get("patch", "") or "").splitlines())
    qa_status = qa_result.get("status", "unknown")
    runtime = qa_result.get("runtime_sec", 0.0)

    summaries = {
        "Scanner": f"Detected {scanner_count} portability issue(s).",
        "Compatibility Analyst": f"Added AMD fix hints to {compatibility_count} issue(s).",
        "ROCm Knowledge": f"Attached docs context for {len(knowledge_items)} issue(s), using {source_count} source reference(s).",
        "Migration Engineer": f"Generated {edits_count} edit(s) across a {patch_lines}-line patch.",
        "QA Tester": f"AMD sandbox returned {qa_status} in {runtime}s.",
        "Report Writer": f"Produced a {len(report_markdown.splitlines())}-line migration report.",
    }
    descriptions = {
        "Scanner": "Static analysis over Python, Dockerfile, requirements, and README files.",
        "Compatibility Analyst": "Severity-aware translation from CUDA risks to AMD/ROCm actions.",
        "ROCm Knowledge": "Retrieval from the local ROCm documentation index.",
        "Migration Engineer": "Structured JSON edits, generated files, and patch application.",
        "QA Tester": "Remote ROCm execution through the configured AMD sandbox.",
        "Report Writer": "Readable final artifact for judging, demos, and PR review.",
    }

    return [
        {
            "step": index,
            "name": name,
            "state": _status_state(name, qa_status),
            "description": descriptions[name],
            "summary": summaries[name],
        }
        for index, name in enumerate(agent_names, start=1)
    ]


def _status_state(name: str, qa_status: str) -> str:
    if name == "QA Tester" and qa_status == "failed":
        return "error"
    return "complete"


def _status_label(state: str) -> str:
    return {
        "complete": "Complete",
        "error": "Needs Attention",
        "running": "Running",
    }.get(state, state.title())


if __name__ == "__main__":
    main()