import html
import tempfile
import plotly.graph_objects as go
import streamlit as st

import agents
from core.repo_loader import cleanup_temp, load_repo_from_url


def _escape_html(value: object) -> str:
    return html.escape("" if value is None else str(value))


def main() -> None:
    """Launch the Streamlit shell for the ROCmForge migration dashboard."""
    st.set_page_config(
        page_title="ROCmForge",
        layout="wide",
        initial_sidebar_state="expanded",
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

    st.markdown(_dashboard_styles(), unsafe_allow_html=True)

    # Sidebar Navigation & Snapshot
    with st.sidebar:
        st.markdown(_sidebar_header(), unsafe_allow_html=True)
        st.markdown(_sidebar_nav(), unsafe_allow_html=True)
        
        # Action to reset and start a new migration
        if st.button("New Migration", key="new_migration"):
            st.session_state.migrating = False
            st.session_state.results = None
            st.session_state.run_started = False
            st.session_state.input_script = ""
            st.session_state.input_url = ""
            st.rerun()

        if st.session_state.results:
            sidebar_results = st.session_state.results
            qa_status = sidebar_results.get("benchmark", {}).get("after", {}).get("status", "unknown")
            failure_class = sidebar_results.get("failure_class", "unknown")
            st.markdown(
                _sidebar_snapshot(
                    readiness_score=sidebar_results.get("readiness_score", 0),
                    qa_status=qa_status,
                    issues_count=len(sidebar_results.get("issues", [])),
                    failure_class=failure_class,
                ),
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                "<div class='sidebar-callout'>"
                "<div class='sidebar-callout__label'>MI300X ready</div>"
                "<div class='sidebar-callout__copy'>The migration pipeline will scan, patch, and benchmark the input after you press Start Migration.</div>"
                "</div>",
                unsafe_allow_html=True,
            )

    # Page Routing
    if not st.session_state.migrating:
        render_input_page()
    else:
        render_dashboard_page(agent_names, agent_descriptions)


def render_input_page() -> None:
    """Renders the initial landing page with the Main Input Card and Info Card."""
    
    # 1. Main Card (Inputs)
    with st.container(border=True):
        st.markdown("""
        <div style="padding-bottom: 0.5rem;">
            <div class='hero-badge'>CUDA → ROCm · Multi-agent orchestration</div>
            <h1 class='hero-title'>High-end AMD migration ops for CUDA projects.</h1>
            <div class='hero-copy__body' style='margin-bottom: 1rem;'>
                ROCmForge turns a repository or script into a proof-backed migration package with scan findings, compatibility hints, local ROCm context, patch generation, AMD QA, and a final markdown report.
            </div>
        </div>
        """, unsafe_allow_html=True)

        with st.form("migration_form", border=False):
            pasted_script = st.text_area(
                "Paste a Python script",
                height=240,
                placeholder="Paste a minimal CUDA-dependent script here...",
            )
            github_url = st.text_input(
                "GitHub URL",
                placeholder="https://github.com/user/repo",
            )
            
            # The type="primary" flag triggers our new custom green CSS
            start_migration = st.form_submit_button("Start Migration", type="primary")

            if start_migration:
                st.session_state.input_script = pasted_script
                st.session_state.input_url = github_url
                st.session_state.migrating = True
                st.session_state.run_started = False
                st.rerun()

    # 2. Info Card (Moved below the main card as requested)
    st.markdown(_hero_info_card(), unsafe_allow_html=True)


def render_dashboard_page(agent_names: list[str], agent_descriptions: dict) -> None:
    """Renders the active migration dashboard and the 6-agent tabbed view."""
    
    # Run the pipeline if it hasn't been triggered yet for this session
    if not st.session_state.run_started:
        st.session_state.run_started = True
        
        run_status_placeholder = st.empty()
        status_container = run_status_placeholder.container()
        status_blocks = {
            name: status_container.status(name, state="running", expanded=False)
            for name in agent_names
        }
        for name, block in status_blocks.items():
            block.write(agent_descriptions[name])

        temp_dir = None
        repo_temp_dir = None
        try:
            pasted_script = st.session_state.input_script
            github_url = st.session_state.input_url

            if not pasted_script.strip() and not github_url.strip():
                raise ValueError("Provide a script or a repository URL to scan.")

            if pasted_script.strip():
                temp_dir = tempfile.TemporaryDirectory(prefix="rocmforge_")
                temp_path = f"{temp_dir.name}/app.py"
                with open(temp_path, "w", encoding="utf-8") as handle:
                    handle.write(pasted_script)
                input_path = temp_path
            else:
                input_path, repo_temp_dir = load_repo_from_url(github_url.strip())

            with st.spinner("Running migration agents..."):
                migration_results = agents.run_migration(input_path)

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
            for step in agent_timeline:
                status_blocks[step["name"]].update(state=step["state"])
            
            # Clear the loading blocks
            run_status_placeholder.empty()

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
        except Exception as exc:
            status_blocks[agent_names[0]].update(state="error")
            st.error(str(exc))
        finally:
            if temp_dir is not None:
                temp_dir.cleanup()
            if repo_temp_dir is not None:
                cleanup_temp(repo_temp_dir)

    results = st.session_state.results

    # Full-width Migration output snapshot
    with st.container(border=True):
        st.markdown(_section_header("00", "Migration output snapshot", "Latest run artifacts and shortlog."), unsafe_allow_html=True)
        if results:
            runtime = results.get("benchmark", {}).get("after", {}).get("runtime", 0.0)
            issues_count = len(results.get("issues", []))
            artifacts = len(results.get("generated_files", []))
            st.markdown(
                f"""
                <div class='hero-panel hero-panel--full' style='margin-bottom: 1rem;'>
                    <div class='hero-panel__title'>
                        <div>
                            <div class='hero-panel__kicker'>Live posture</div>
                            <div class='hero-panel__headline'>Migration output snapshot</div>
                        </div>
                        <span class='status-chip status-chip--complete'>Connected</span>
                    </div>
                    <div class='hero-panel__body'>A concise snapshot of the last migration run including readiness, issues, runtime, and generated artifacts.</div>
                    <div class='hero-panel__stats'>
                        <div class='hero-panel__stat'>
                            <div class='hero-panel__stat-label'>Readiness</div>
                            <div class='hero-panel__stat-value'>{results.get('readiness_score', 0)}/100</div>
                        </div>
                        <div class='hero-panel__stat'>
                            <div class='hero-panel__stat-label'>Issues</div>
                            <div class='hero-panel__stat-value'>{issues_count}</div>
                        </div>
                        <div class='hero-panel__stat'>
                            <div class='hero-panel__stat-label'>Runtime</div>
                            <div class='hero-panel__stat-value'>{runtime}s</div>
                        </div>
                        <div class='hero-panel__stat'>
                            <div class='hero-panel__stat-label'>Artifacts</div>
                            <div class='hero-panel__stat-value'>{artifacts}</div>
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            qa_status = results.get("benchmark", {}).get("after", {}).get("status", "unknown")
            failure_class = results.get("failure_class", "unknown")

            summary_cols = st.columns(4)
            summary_cols[0].markdown(
                _stat_card("Before Score", f"{results['readiness_score']}/100", "Static portability score before the patch.", tone="success"),
                unsafe_allow_html=True,
            )
            summary_cols[1].markdown(
                _stat_card("After Score", f"{results.get('score_after', 0)}/100", "Post-migration posture after QA and retry loops.", tone="primary"),
                unsafe_allow_html=True,
            )
            summary_cols[2].markdown(
                _stat_card("Issues Found", issues_count, "Detected CUDA, NVIDIA, and portability blockers.", tone="warning"),
                unsafe_allow_html=True,
            )
            
            qa_label = qa_status
            if qa_status == "failed" and failure_class in ("app_bug", "environment"):
                qa_label = f"{qa_status} ({failure_class})"
            summary_cols[3].markdown(
                _stat_card("AMD QA", qa_label, "Sandbox execution result for the patched project.", tone="crimson" if qa_status == "failed" else "primary"),
                unsafe_allow_html=True,
            )
        else:
            st.info("No migration output yet.")

    # 6 Tab Navigation
    st.markdown("<br>", unsafe_allow_html=True)
    tabs = st.tabs(["Agent Pipeline", "Scan Results", "Migration Patch", "AMD Test", "Benchmark", "Final Report"])

    with tabs[0]:
        with st.container(border=True):
            st.markdown(_section_header("01", "Agent Pipeline", "The six-agent backend, remapped into Lovable-style performance cards."), unsafe_allow_html=True)
            if results:
                timeline = results.get("agent_timeline", [])
                st.markdown(_agent_grid(timeline), unsafe_allow_html=True)
                st.markdown(
                    _pipeline_strip(
                        scanner_count=len(results.get("agent_outputs", {}).get("scanner", [])),
                        compatibility_count=len(results.get("agent_outputs", {}).get("compatibility", [])),
                        knowledge_count=len(results.get("agent_outputs", {}).get("knowledge", [])),
                        report_lines=len(results.get("report_markdown", "").splitlines()),
                    ),
                    unsafe_allow_html=True,
                )
                with st.expander("Raw agent outputs"):
                    st.json(results.get("agent_outputs", {}))
            else:
                st.info("Run a migration to see all six agents work through the pipeline.")

    with tabs[1]:
        with st.container(border=True):
            st.markdown(_section_header("02", "Scan Results", "High-signal findings with ROCm context and fix hints."), unsafe_allow_html=True)
            if results:
                issues = results.get("issues", [])
                if issues:
                    st.markdown(_issue_legend(), unsafe_allow_html=True)
                    for issue in issues:
                        st.markdown(_issue_card(issue), unsafe_allow_html=True)
                else:
                    st.success("No scan issues were detected.")
            else:
                st.info("No scan results yet.")

    with tabs[2]:
        with st.container(border=True):
            st.markdown(_section_header("03", "Migration Patch", "Diff output, generated files, and edit retry evidence."), unsafe_allow_html=True)
            if results:
                applied = results.get("applied_edits", [])
                skipped = results.get("skipped_edits", [])
                patch_cols = st.columns(2)
                patch_cols[0].markdown(
                    _stat_card("Applied edits", len(applied), "Registry and LLM edits that made it into the patch.", tone="primary"),
                    unsafe_allow_html=True,
                )
                patch_cols[1].markdown(
                    _stat_card("Skipped edits", len(skipped), "Rejected patch candidates fed back into retry loops.", tone="warning"),
                    unsafe_allow_html=True,
                )
                st.markdown(_chip_row(results.get("generated_files", []), empty_label="No generated files"), unsafe_allow_html=True)
                st.code(results["patch_text"] or "(no patch)", language="diff")

                if skipped:
                    st.warning(f"{len(skipped)} edit(s) could not be applied. These were fed back to the LLM on retry.")
                    with st.expander("Skipped edits", expanded=False):
                        for edit in skipped:
                            st.markdown(f"**{edit.get('file', '?')}** — `{edit.get('reason', 'unknown')}`")
                            st.caption(edit.get("detail", ""))
                            st.caption(f"rationale: {edit.get('rationale', '')}")
                            st.code(
                                f"# original_block\n{edit.get('original_block', '')}\n\n"
                                f"# replacement_block\n{edit.get('replacement_block', '')}",
                                language="python",
                            )
                if applied:
                    with st.expander(f"Applied edits ({len(applied)})", expanded=False):
                        for edit in applied:
                            match_kind = edit.get("match", "exact")
                            st.markdown(f"**{edit.get('file', '?')}** — match: `{match_kind}`")
                            st.caption(edit.get("rationale", ""))
            else:
                st.info("No patch generated yet.")

    with tabs[3]:
        with st.container(border=True):
            st.markdown(_section_header("04", "AMD Test", "The sandbox trace, retry attempts, and runtime diagnostics."), unsafe_allow_html=True)
            if results:
                qa_status = results.get("benchmark", {}).get("after", {}).get("status", "unknown")
                runtime = results.get("benchmark", {}).get("after", {}).get("runtime", 0.0)
                test_cols = st.columns(3)
                test_cols[0].markdown(_stat_card("Sandbox status", qa_status, "Final execution state reported by the AMD test harness.", tone="primary"), unsafe_allow_html=True)
                test_cols[1].markdown(_stat_card("Runtime", f"{runtime}s", "Measured runtime from the last QA pass.", tone="success"), unsafe_allow_html=True)
                test_cols[2].markdown(_stat_card("Failure class", results.get("failure_class", "unknown"), "How the retry loop classified the remaining failure.", tone="crimson" if results.get("failure_class") == "cuda_relevant" else "primary"), unsafe_allow_html=True)

                st.text_area("Logs", value=results["amd_logs"], height=220)
                attempts = results.get("attempts", [])
                if attempts:
                    st.markdown(_attempts_header(len(attempts)), unsafe_allow_html=True)
                    for attempt in attempts:
                        qa_result = attempt.get("qa_result", {})
                        label = f"Attempt {attempt.get('attempt', '?')} - {qa_result.get('status', 'unknown')}"
                        with st.expander(label, expanded=qa_result.get("status") == "failed"):
                            det = attempt.get("deterministic_edit_count", 0)
                            llm = attempt.get("llm_edit_count", 0)
                            skipped = attempt.get("skipped_edits", [])
                            st.caption(f"Deterministic edits: {det}  |  LLM edits: {llm}  |  Skipped: {len(skipped)}")
                            st.code(attempt.get("patch", "") or "(no patch)", language="diff")
                            if skipped:
                                with st.expander("Skipped edits this attempt", expanded=False):
                                    for edit in skipped:
                                        st.write(f"- `{edit.get('reason', '?')}` in {edit.get('file', '?')}: {edit.get('detail', '')}")
                            st.text_area(
                                "QA logs",
                                value=qa_result.get("logs", ""),
                                height=160,
                                key=f"qa_logs_attempt_{attempt.get('attempt', '?')}",
                            )
            else:
                st.info("No AMD test results yet.")

    with tabs[4]:
        with st.container(border=True):
            st.markdown(_section_header("05", "Benchmark", "Baseline versus patched performance for runtime and memory."), unsafe_allow_html=True)
            if results:
                before = results["benchmark"]["before"]
                after = results["benchmark"]["after"]
                fig = go.Figure(
                    data=[
                        go.Bar(
                            name="Before",
                            x=["Runtime (s)", "GPU Memory (GB)"],
                            y=[0 if before["runtime"] is None else before["runtime"], 0 if before["memory"] is None else before["memory"]],
                            marker_color="#8b93a7",
                        ),
                        go.Bar(
                            name="After",
                            x=["Runtime (s)", "GPU Memory (GB)"],
                            y=[after["runtime"], after["memory"]],
                            marker_color="#0ee37d",
                        ),
                    ]
                )
                fig.update_layout(
                    barmode="group",
                    height=360,
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font={"color": "#E5EEF6"},
                    margin={"l": 0, "r": 0, "t": 20, "b": 0},
                    legend={"orientation": "h", "y": 1.08},
                )
                st.plotly_chart(fig, use_container_width=True)

                metric_cols = st.columns(3)
                metric_cols[0].markdown(_stat_card("Before", "Failed", "Baseline execution state before the patch.", tone="warning"), unsafe_allow_html=True)
                metric_cols[1].markdown(_stat_card("After", f"{after['runtime']}s", "Runtime reported by the ROCm sandbox.", tone="success"), unsafe_allow_html=True)
                metric_cols[2].markdown(_stat_card("GPU Memory", f"{after['memory']} GB", "Peak memory usage from the last QA pass.", tone="primary"), unsafe_allow_html=True)
            else:
                st.info("No benchmark data yet.")

    with tabs[5]:
        with st.container(border=True):
            st.markdown(_section_header("06", "Final Report", "The markdown artifact used for judging, demos, and PR review."), unsafe_allow_html=True)
            if results:
                st.markdown(results["report_markdown"])
                st.download_button(
                    "Download migration_report.md",
                    data=results["report_markdown"],
                    file_name="migration_report.md",
                    use_container_width=True,
                )
            else:
                st.info("No report generated yet.")


# Helper Functions & UI Components Below

def _dashboard_styles() -> str:
    return """
    <style>
    :root {
        --rocm-bg: oklch(0.145 0.025 250);
        --rocm-surface: oklch(0.205 0.032 252);
        --rocm-surface-2: oklch(0.245 0.033 252);
        --rocm-border: oklch(0.33 0.03 252);
        --rocm-foreground: oklch(0.968 0.01 240);
        --rocm-muted: oklch(0.72 0.02 248);
        --rocm-primary: oklch(0.85 0.22 145);
        --rocm-primary-strong: oklch(0.9 0.19 145);
        --rocm-crimson: oklch(0.65 0.24 25);
        --rocm-warning: oklch(0.82 0.16 84);
        --rocm-shadow: 0 20px 60px oklch(0.1 0.02 250 / 0.42);
        --rocm-glow: 0 0 36px oklch(0.85 0.22 145 / 0.24);
        --rocm-code-bg: oklch(0.12 0.02 250);
        --rocm-grid: linear-gradient(oklch(0.85 0.22 145 / 0.035) 1px, transparent 1px), linear-gradient(90deg, oklch(0.85 0.22 145 / 0.035) 1px, transparent 1px);
    }

    html, body, [data-testid="stAppViewContainer"] {
        background:
            radial-gradient(circle at top left, oklch(0.22 0.04 252 / 0.95) 0%, transparent 35%),
            radial-gradient(circle at top right, oklch(0.65 0.24 25 / 0.1) 0%, transparent 28%),
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
        background: radial-gradient(circle at 20% 8%, oklch(0.85 0.22 145 / 0.08), transparent 26%);
    }

    /* Start Migration - Custom Green Primary Button */
    button[kind="primary"] {
        background: linear-gradient(135deg, #0ee37d, #0aa358) !important;
        color: #06120b !important;
        border: 1px solid #0ee37d !important;
        font-weight: 800 !important;
        box-shadow: 0 0 20px rgba(14, 227, 125, 0.3) !important;
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
        background: linear-gradient(135deg, oklch(0.85 0.22 145 / 0.18), oklch(0.65 0.24 25 / 0.08));
        border: 1px solid oklch(0.85 0.22 145 / 0.35);
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
        background: linear-gradient(135deg, oklch(0.85 0.22 145 / 0.12), oklch(0.85 0.22 145 / 0.02));
        border-color: oklch(0.85 0.22 145 / 0.25);
        box-shadow: var(--rocm-glow);
    }

    .sidebar-panel,
    .sidebar-callout {
        border-radius: 20px;
        border: 1px solid oklch(0.85 0.22 145 / 0.14);
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
        border-color: oklch(0.85 0.22 145 / 0.6) !important;
        box-shadow: 0 0 0 3px oklch(0.85 0.22 145 / 0.15) !important;
    }

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
        border: 1px solid oklch(0.85 0.22 145 / 0.2);
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
        background: radial-gradient(circle, oklch(0.85 0.22 145 / 0.16), transparent 62%);
        pointer-events: none;
    }

    .hero-badge {
        display: inline-flex;
        align-items: center;
        gap: 0.45rem;
        padding: 0.38rem 0.75rem;
        border-radius: 999px;
        border: 1px solid oklch(0.85 0.22 145 / 0.25);
        background: oklch(0.85 0.22 145 / 0.08);
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
        border-color: oklch(0.85 0.22 145 / 0.28);
        background: oklch(0.85 0.22 145 / 0.1);
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
        border-color: oklch(0.85 0.22 145 / 0.24);
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
        background: radial-gradient(circle, oklch(0.85 0.22 145 / 0.08), transparent 68%);
        pointer-events: none;
    }

    .agent-card--running {
        border-color: oklch(0.85 0.22 145 / 0.35);
        box-shadow: 0 0 42px oklch(0.85 0.22 145 / 0.16);
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
        background: var(--rocm-primary);
        box-shadow: 0 0 0 0 oklch(0.85 0.22 145 / 0.35);
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
        border-color: oklch(0.85 0.22 145 / 0.18);
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
        0%, 100% { transform: scale(1); opacity: 0.95; }
        50% { transform: scale(1.24); opacity: 0.65; }
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