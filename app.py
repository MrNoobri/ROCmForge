def main() -> None:
    """Launch the Streamlit shell for the ROCmForge migration dashboard."""
    import streamlit as st

    st.set_page_config(page_title="ROCmForge", layout="wide")
    st.title("ROCmForge")
    st.caption("Proof-backed AMD/ROCm migration lab.")
    st.info("Phase 0 scaffold is ready. The interactive workflow arrives in later phases.")


main()
