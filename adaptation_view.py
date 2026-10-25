"""Read-only explorer for the committed adaptation benchmark."""
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

LOGGER = logging.getLogger(__name__)
RESULTS = Path(__file__).resolve().parent / "results" / "adaptation" / "summary.csv"
CONTROLLERS = {
    "fixed_learned": "Fixed learned MPC",
    "fixed_physics": "Fixed physics MPC",
    "adaptive_learned": "Adaptive learned MPC",
    "adaptive_physics": "Adaptive physics MPC",
}
METRICS = {
    "target_rmse_c": "Tracking RMSE (°C)",
    "prediction_mae_c": "Full-day prediction MAE (°C/step)",
    "post_change_mae_c": "Hours 10–24 prediction MAE (°C/step)",
    "post_change_probe_mae_c": "Hours 10–24 common-probe MAE (°C/step)",
    "energy_kwh": "Electricity (kWh/day)",
    "violation_minutes": "Temperature violations (min/day)",
}


def load_results(path=RESULTS):
    """Reject incomplete or ambiguous comparisons instead of silently averaging."""
    frame = pd.read_csv(path)
    keys = ["equipment", "degradation", "seed", "controller"]
    required = keys + list(METRICS)
    if not set(required).issubset(frame.columns):
        raise ValueError("Missing required experiment columns")
    if frame.duplicated(keys).any():
        raise ValueError("Duplicate case/controller records")
    expected = pd.MultiIndex.from_product([
        ["nominal", "unseen_small", "unseen_large"], [False, True],
        [11, 22, 33], list(CONTROLLERS),
    ], names=keys)
    if set(frame.set_index(keys).index) != set(expected):
        raise ValueError("Expected all 72 matched case/controller records")
    numeric = frame[list(METRICS)]
    if numeric.isna().any().any() or not (np.isfinite(numeric.to_numpy()).all() and (numeric >= 0).all().all()):
        raise ValueError("Invalid experiment metrics")
    return frame


def select_results(frame, equipment, degradation, seeds, controllers):
    return frame.loc[
        frame.equipment.isin(equipment) & frame.degradation.eq(degradation)
        & frame.seed.isin(seeds) & frame.controller.isin(controllers)
    ].copy()


def render_adaptation():
    st.title("Adaptation experiment")
    st.write("Can updating a model help when equipment changes? Compare four controllers on the same recorded simulated days.")
    st.warning(
        "Research prototype: conventional adaptive physics remains competitive. "
        "These are synthetic, linear, noiseless systems. No real-world energy savings "
        "or advantage unique to machine learning has been demonstrated. "
        "Adaptive controllers use slightly more electricity in the degraded cases."
    )
    st.info("Precomputed experiments · results/adaptation/summary.csv · 72 records, 18 matched cases. Changing filters does not run a simulation.")
    try:
        frame = load_results()
    except (OSError, ValueError, TypeError):
        LOGGER.exception("Unable to read or validate recorded adaptation results")
        st.error("Recorded adaptation results are unavailable. Please contact the maintainer.")
        return
    equipment = st.multiselect("Equipment configurations", ["nominal", "unseen_small", "unseen_large"], default=["nominal", "unseen_small", "unseen_large"])
    condition = st.radio("Equipment condition", ["Degraded", "Unchanged"], horizontal=True)
    seeds = st.multiselect("Operating-condition seeds", [11, 22, 33], default=[11, 22, 33])
    controllers = st.multiselect("Controllers", list(CONTROLLERS), default=list(CONTROLLERS), format_func=CONTROLLERS.get)
    st.caption("Nominal: capacity 1.00 kWh/°C, loss 0.08 kW/°C, efficiency 1.00. Unseen small: 0.65, 0.11, 0.90. Unseen large: 1.60, 0.05, 0.85. Only nominal equipment is used in fixed-model training.")
    selected = select_results(frame, equipment, condition == "Degraded", seeds, controllers)
    if selected.empty:
        st.info("Select at least one equipment configuration, seed, and controller.")
        return
    count = len(equipment) * len(seeds)
    st.caption(f"Equal-weight means over {count} matched cases per controller. Seeds repeat operating conditions on three synthetic plants, not independent real installations.")
    st.write("Degraded equipment loses 25% of its initial heater efficiency at hour 10, without notifying controllers. Unchanged equipment keeps its initial efficiency.")
    means = selected.groupby("controller", sort=False)[list(METRICS)].mean().reindex(controllers)
    means.index = means.index.map(CONTROLLERS)
    means.index.name = "Controller"
    st.dataframe(means.rename(columns=METRICS), width="stretch")
    metric = st.selectbox("Chart metric", list(METRICS), format_func=METRICS.get)
    st.bar_chart(means[[metric]].rename(columns=METRICS), horizontal=True)
    st.caption("Lower is better for each metric, but lower tracking or prediction error does not imply lower electricity use. Tracking RMSE measures deviation from 60°C. Violations count time outside 58–62°C. Temperature limits use soft penalties, not guaranteed safety constraints.")
    st.caption("Prediction MAE is scored before model updates on each controller’s own trajectory. Common-probe MAE uses the same 15 temperature/power probes for every controller. Hours 10–24 means the post-change window in degraded runs and the same time window in unchanged runs. Energy, tracking RMSE, and violations cover all 24 hours.")
    with st.expander("Per-case recorded results"):
        st.dataframe(selected, hide_index=True, width="stretch")
        st.download_button("Download selected recorded results", selected.to_csv(index=False), "adaptation-selection.csv", "text/csv")
    st.markdown("[Experimental methodology and limitations](https://github.com/Grace-Fokam/fovra-v0/blob/main/docs/adaptation-results.md)")
    st.caption("Trajectories are not included in this read-only view. The benchmark CLI generates trajectories.csv offline, and CI retains it as an artifact. No newly executed simulations are mixed with these recorded metrics.")
