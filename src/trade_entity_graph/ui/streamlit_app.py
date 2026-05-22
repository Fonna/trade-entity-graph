"""Streamlit MVP shell."""

from __future__ import annotations

import streamlit as st


def main() -> None:
    st.set_page_config(page_title="Trade Entity Graph", layout="wide")
    st.title("Trade Entity Graph")
    st.caption("MVP scaffold: import, search, graph, review, and export flows.")
    st.info("Start with database initialization, then data import and graph query services.")


if __name__ == "__main__":
    main()
