"""Fovra dashboard for simulated data-center cooling."""

import streamlit as st

from cooling_view import render_cooling


st.set_page_config(page_title="Fovra | Cooling Research", page_icon="◈", layout="wide")
render_cooling()
