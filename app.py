def main() -> None:
    """Launch the Streamlit shell for the ROCmForge migration dashboard."""
    import streamlit as st
    import plotly.graph_objects as go
    import tempfile

    import agents
    from core.repo_loader import cleanup_temp, load_repo_from_url

    st.set_page_config(page_title="ROCmForge", layout="wide")

    st.title("ROCmForge")
    st.caption("Proof-backed AMD/ROCm migration lab.")
    st.markdown(
        """
        <style>
        .agent-card {
            border: 1px solid rgba(148, 163, 184, 0.35);
            border-radius: 8px;
            padding: 14px 16px;
            min-height: 142px;
            background: rgba(255, 255, 255, 0.02);
        }
        .agent-step {
            color: #64748B;
            font-size: 12px;
            font-weight: 700;
            letter-spacing: 0;
            text-transform: uppercase;
        }
        .agent-name {
            font-size: 17px;
            font-weight: 700;
            margin: 4px 0 8px 0;
        }
        .agent-detail {
            color: #475569;
            font-size: 14px;
            line-height: 1.35;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.subheader("Input")
        pasted_script = st.text_area(
            "Paste a Python script",
            height=220,
            placeholder="Paste a minimal CUDA-dependent script here...",
        )
        github_url = st.text_input(
            "GitHub URL",
            placeholder="https://github.com/user/repo",
        )
        start_migration = st.button("Start Migration", type="primary")

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

    if "results" not in st.session_state:
        st.session_state.results = None

    if start_migration:
        st.session_state.results = None
        status_container = st.container()
        status_blocks = {
            name: status_container.status(
                name,
                state="running",
                expanded=False,
            )
            for name in agent_names
        }
        for name, block in status_blocks.items():
            block.write(agent_descriptions[name])
        temp_dir = None
        repo_temp_dir = None
        try:
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
    if results:
        top_cols = st.columns(4)
        top_cols[0].metric("Before Score", f"{results['readiness_score']}/100")
        top_cols[1].metric("After Score", f"{results.get('score_after', 0)}/100")
        top_cols[2].metric("Issues Found", len(results.get("issues", [])))
        top_cols[3].metric("AMD QA", results.get("benchmark", {}).get("after", {}).get("status", "unknown"))

    tabs = st.tabs(
        [
            "Input",
            "Agent Pipeline",
            "Scan Results",
            "Migration Patch",
            "AMD Test",
            "Benchmark",
            "Final Report",
        ]
    )

    with tabs[0]:
        st.subheader("Input")
        if results:
            st.code(results["input"]["pasted_script"] or "(no script provided)")
            if results["input"]["github_url"]:
                st.write(f"Repo: {results['input']['github_url']}")
            else:
                st.write("Repo: (none)")
        else:
            st.info("Click Start Migration to populate results.")

    with tabs[1]:
        st.subheader("Agent Pipeline")
        if results:
            timeline = results.get("agent_timeline", [])
            for row_start in range(0, len(timeline), 3):
                cols = st.columns(3)
                for col, step in zip(cols, timeline[row_start : row_start + 3]):
                    with col:
                        state = step.get("state", "complete")
                        label = _status_label(state)
                        st.markdown(
                            f"""
                            <div class="agent-card">
                                <div class="agent-step">Step {step.get('step', '?')} - {label}</div>
                                <div class="agent-name">{step.get('name', 'Agent')}</div>
                                <div class="agent-detail">{step.get('description', '')}</div>
                                <hr>
                                <div class="agent-detail"><strong>Output:</strong> {step.get('summary', '')}</div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
            st.divider()
            with st.expander("Raw agent outputs"):
                agent_outputs = results.get("agent_outputs", {})
                st.json(agent_outputs)
        else:
            st.info("Run a migration to see all six agents work through the pipeline.")

    with tabs[2]:
        st.subheader("Scan Results")
        if results:
            st.markdown(
                f"## AMD Readiness Score: {results['readiness_score']}/100"
            )
            for issue in results["issues"]:
                severity = issue["severity"]
                badge_color = {
                    "high": "#ED1C24",
                    "medium": "#F59E0B",
                    "low": "#10B981",
                }.get(severity, "#6B7280")
                with st.container(border=True):
                    st.markdown(
                        f"<span style='background:{badge_color};color:white;"
                        "padding:4px 10px;border-radius:999px;font-size:12px;"
                        "font-weight:600;text-transform:uppercase;'>"
                        f"{severity}</span>",
                        unsafe_allow_html=True,
                    )
                    st.write(f"{issue['file']}:{issue['line']}")
                    st.write(issue["description"])
                    if issue.get("amd_fix_hint"):
                        st.caption(f"AMD fix: {issue['amd_fix_hint']}")
                    if issue.get("rocm_context"):
                        with st.expander("ROCm knowledge context"):
                            st.write(issue["rocm_context"])
                            sources = issue.get("rocm_sources", [])
                            if sources:
                                st.write("Sources")
                                for source in sources:
                                    label = source.get("heading") or source.get("source") or "unknown"
                                    st.write(f"- {label}")
        else:
            st.info("No scan results yet.")

    with tabs[3]:
        st.subheader("Migration Patch")
        if results:
            st.code(results["patch_text"], language="diff")
            st.write("Generated files")
            st.write(", ".join(results["generated_files"]))
        else:
            st.info("No patch generated yet.")

    with tabs[4]:
        st.subheader("AMD Test")
        if results:
            status_blocks = []
            for step in results["agent_timeline"]:
                status_blocks.append(
                    st.status(step["name"], state=step["state"], expanded=False)
                )
            st.text_area("Logs", value=results["amd_logs"], height=200)
            attempts = results.get("attempts", [])
            if attempts:
                st.write("Attempts")
                for attempt in attempts:
                    qa_result = attempt.get("qa_result", {})
                    label = (
                        f"Attempt {attempt.get('attempt', '?')} - "
                        f"{qa_result.get('status', 'unknown')}"
                    )
                    with st.expander(label, expanded=qa_result.get("status") == "failed"):
                        st.code(attempt.get("patch", "") or "(no patch)", language="diff")
                        st.text_area(
                            "QA logs",
                            value=qa_result.get("logs", ""),
                            height=160,
                            key=f"qa_logs_attempt_{attempt.get('attempt', '?')}",
                        )
        else:
            st.info("No AMD test results yet.")

    with tabs[5]:
        st.subheader("Benchmark")
        if results:
            before = results["benchmark"]["before"]
            after = results["benchmark"]["after"]
            fig = go.Figure(
                data=[
                    go.Bar(
                        name="Before",
                        x=["Runtime (s)", "GPU Memory (GB)"],
                        y=[0 if before["runtime"] is None else before["runtime"],
                           0 if before["memory"] is None else before["memory"]],
                        marker_color="#9CA3AF",
                    ),
                    go.Bar(
                        name="After",
                        x=["Runtime (s)", "GPU Memory (GB)"],
                        y=[after["runtime"], after["memory"]],
                        marker_color="#ED1C24",
                    ),
                ]
            )
            fig.update_layout(barmode="group", height=360)
            st.plotly_chart(fig, width="stretch")

            metric_cols = st.columns(3)
            metric_cols[0].metric("Before", "Failed")
            metric_cols[1].metric("After", f"{after['runtime']}s")
            metric_cols[2].metric("GPU Memory", f"{after['memory']} GB")
        else:
            st.info("No benchmark data yet.")

    with tabs[6]:
        st.subheader("Final Report")
        if results:
            st.markdown(results["report_markdown"])
            st.download_button(
                "Download migration_report.md",
                data=results["report_markdown"],
                file_name="migration_report.md",
            )
        else:
            st.info("No report generated yet.")


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
