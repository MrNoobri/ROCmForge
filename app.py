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
        "Code Analyzer",
        "ROCm Knowledge",
        "Migration Engineer",
        "QA Tester",
        "Benchmark",
        "Report",
    ]

    if "results" not in st.session_state:
        st.session_state.results = None

    if start_migration:
        st.session_state.results = None
        status_container = st.container()
        status_blocks = {
            name: status_container.status(name, state="running", expanded=False)
            for name in agent_names
        }
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

            for name in agent_names:
                status_blocks[name].update(state="complete")

            generated_files = migration_results.get("generated_files", {})
            generated_list = (
                sorted(generated_files)
                if isinstance(generated_files, dict)
                else list(generated_files)
            )
            qa_result = migration_results.get("qa_result", {})
            st.session_state.results = {
                "readiness_score": migration_results.get("score_before", 0),
                "issues": migration_results.get("issues", []),
                "patch_text": migration_results.get("patch_text", ""),
                "generated_files": generated_list,
                "agent_timeline": [
                    {"name": name, "state": "complete"}
                    for name in agent_names
                ],
                "amd_logs": qa_result.get("logs", ""),
                "attempts": migration_results.get("attempts", []),
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
    tabs = st.tabs(
        [
            "Input",
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
        else:
            st.info("No scan results yet.")

    with tabs[2]:
        st.subheader("Migration Patch")
        if results:
            st.code(results["patch_text"], language="diff")
            st.write("Generated files")
            st.write(", ".join(results["generated_files"]))
        else:
            st.info("No patch generated yet.")

    with tabs[3]:
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

    with tabs[4]:
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
            st.plotly_chart(fig, use_container_width=True)

            metric_cols = st.columns(3)
            metric_cols[0].metric("Before", "Failed")
            metric_cols[1].metric("After", f"{after['runtime']}s")
            metric_cols[2].metric("GPU Memory", f"{after['memory']} GB")
        else:
            st.info("No benchmark data yet.")

    with tabs[5]:
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


main()
