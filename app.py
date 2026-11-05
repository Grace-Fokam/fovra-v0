"""Fovra's interactive component-design and data-center cooling research."""

import streamlit as st

from cold_plate_view import render_cold_plate
from cooling_view import render_cooling


st.set_page_config(page_title="Fovra | Cooling Research", page_icon="◈", layout="wide")
with st.sidebar:
    st.markdown("## ◈ Fovra")
    st.caption("DESIGN RESEARCH / v0")
    view = st.radio("Research view", ["Component design", "Data-center cooling"], key="research_view")
    st.divider()

if view == "Component design":
    render_cold_plate()
else:
    render_cooling()
