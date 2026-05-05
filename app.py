def main() -> None:
    """Launch the Streamlit shell for the ROCmForge migration dashboard."""
    import streamlit as st
    import plotly.graph_objects as go

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

    mock_results = {
        "readiness_score": 38,
        "issues": [
            {
                "severity": "high",
                "file": "Dockerfile",
                "line": 1,
                "description": "Base image uses NVIDIA CUDA runtime.",
            },
            {
                "severity": "high",
                "file": "requirements.txt",
                "line": 3,
                "description": "CUDA-only dependency: bitsandbytes.",
            },
            {
                "severity": "medium",
                "file": "app.py",
                "line": 14,
                "description": "Detected torch.cuda.set_device usage.",
            },
            {
                "severity": "medium",
                "file": "app.py",
                "line": 22,
                "description": "Detected .cuda() call on model/tensor.",
            },
            {
                "severity": "low",
                "file": "README.md",
                "line": 5,
                "description": "README references NVIDIA CUDA Toolkit.",
            },
        ],
        "patch_text": """diff --git a/Dockerfile b/Dockerfile.rocm
index 8e3f0aa..d7b1b77 100644
--- a/Dockerfile
+++ b/Dockerfile.rocm
@@ -1,6 +1,7 @@
-FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04
+FROM rocm/pytorch:rocm6.0_ubuntu22.04_py3.11_pytorch
 WORKDIR /app
 COPY . /app
 RUN pip install -r requirements.txt
+RUN python -c \"import torch; print(torch.version.hip)\"
 CMD [\"python\", \"app.py\"]
""",
        "generated_files": ["Dockerfile.rocm", "rocm_setup.md"],
        "agent_timeline": [
            {"name": "Code Analyzer", "state": "complete"},
            {"name": "ROCm Knowledge", "state": "complete"},
            {"name": "Migration Engineer", "state": "complete"},
            {"name": "QA Tester", "state": "running"},
            {"name": "Benchmark", "state": "pending"},
            {"name": "Report", "state": "pending"},
        ],
        "amd_logs": """[qa] starting validation
[qa] parsed app.py ok
[qa] sandbox run queued
[qa] waiting for GPU availability...
""",
        "benchmark": {
            "before": {"status": "failed", "runtime": None, "memory": None},
            "after": {"status": "passed", "runtime": 8.4, "memory": 6.2},
        },
        "report_markdown": """
# ROCmForge Migration Report

## Summary
The scan detected CUDA-specific dependencies and usage patterns that prevent
execution on AMD GPUs. A ROCm-compatible base image and dependency replacements
were proposed, and the project was validated with a mocked AMD sandbox run.

## Key Findings
- Dockerfile uses an NVIDIA CUDA base image.
- bitsandbytes is CUDA-only and must be replaced.
- Direct CUDA calls (.cuda, torch.cuda.set_device) are present.

## Recommendations
1. Switch to ROCm base images for container builds.
2. Replace bitsandbytes with Optimum-AMD or native PyTorch modules.
3. Validate on AMD hardware with ROCm and PyTorch ROCm builds.

## Next Steps
Run the patched project on an AMD MI300X sandbox to confirm performance
and update the README with ROCm installation steps.
""",
    }

    if "results" not in st.session_state:
        st.session_state.results = None

    if start_migration:
        st.session_state.results = {
            **mock_results,
            "input": {"pasted_script": pasted_script, "github_url": github_url},
        }

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
