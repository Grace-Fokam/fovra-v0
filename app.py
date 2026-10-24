"""Fovra v0 | An interactive synthetic physical-systems controller demo.

Run locally with: streamlit run app.py
"""

import pandas as pd
import streamlit as st

from controllers import BASELINES
from evaluation import SimulationConfig, compare, merge_for_download
from simulator import MAX_SAFE_TEMP_C, MIN_SAFE_TEMP_C, SCENARIOS
from train_model import train_world_model

st.set_page_config(
    page_title="Fovra | Physical Systems Intelligence",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Each sidebar submission triggers a new matched comparison. The fitted model
# is unchanged across scenarios, including the equipment-degradation scenario.
@st.cache_resource(show_spinner="Training the prediction model...")
def get_model():
    return train_world_model()


@st.cache_data(show_spinner="Running matched simulations...")
def get_results(ambient_c: float, process_kw: float, scenario: str, baseline: str):
    model, _ = get_model()
    config = SimulationConfig(ambient_c, process_kw, scenario, baseline)
    return compare(config, model)


if "submitted_conditions" not in st.session_state:
    st.session_state.submitted_conditions = {
        "ambient_c": 20.0,
        "process_kw": 3.0,
        "scenario": "Normal",
        "baseline": "Thermostat",
    }

with st.sidebar:
    st.markdown("### FOVRA / SIMULATION")
    st.caption("Change inputs, then run the experiment.")
    with st.form("controls"):
        ambient = st.slider(
            "Surrounding temperature (°C)",
            min_value=10,
            max_value=35,
            value=int(st.session_state.submitted_conditions["ambient_c"]),
            step=1,
            help="Baseline outdoor temperature; the simulator adds a small day/night cycle.",
        )
        demand = st.slider(
            "Production heat demand (kW)",
            min_value=1.0,
            max_value=6.0,
            value=float(st.session_state.submitted_conditions["process_kw"]),
            step=0.5,
            help="Baseline rate at which production removes heat from the tank.",
        )
        scenario = st.radio(
            "Operating scenario",
            SCENARIOS,
            index=SCENARIOS.index(st.session_state.submitted_conditions["scenario"]),
            help="The same disturbance affects both controllers in each run.",
        )
        baseline = st.selectbox(
            "Compare Fovra against",
            BASELINES,
            index=BASELINES.index(
                st.session_state.submitted_conditions["baseline"]
            ),
        )
        submitted = st.form_submit_button("Run simulation", type="primary", width="stretch")

    if submitted:
        st.session_state.submitted_conditions = {
            "ambient_c": float(ambient),
            "process_kw": float(demand),
            "scenario": scenario,
            "baseline": baseline,
        }

    st.divider()
    st.caption("SIMULATOR ASSUMPTIONS")
    st.markdown("**Duration:** 24 hours  ")
    st.markdown("**Time step:** 5 minutes  ")
    st.markdown("**Heater:** 0–12 kW electric input  ")
    st.markdown("**Operating band:** 58–62°C  ")
    st.markdown("**Starting water temperature:** 60°C")
    st.caption("Illustrative physics only. Not validated against real industrial equipment.")

config_values = st.session_state.submitted_conditions
cfg = SimulationConfig(**config_values)
model, heldout_mae = get_model()
fovra, baseline_df, fovra_metrics, baseline_metrics = get_results(
    cfg.ambient_c, cfg.process_kw, cfg.scenario, cfg.baseline
)

st.title("Fovra")
st.caption("PHYSICAL SYSTEMS INTELLIGENCE  /  SYNTHETIC CONTROL LAB")
st.info(
    "**Simulation, not a field trial.** Every number below is calculated from a "
    "simplified virtual heating system. Fovra uses a trained ML prediction model "
    "and a model-predictive controller."
)

st.subheader("Current simulation state")
a, b, c = st.columns(3)
with a:
    st.metric("Final tank temperature", f"{fovra['temperature_c'].iloc[-1]:.2f}°C")
with b:
    st.metric("Final heater command", f"{fovra['heater_kw'].iloc[-1]:.1f} kW")
with c:
    st.metric("Allowed temperature band", "58–62°C")

st.caption(
    f"**Scenario:** {cfg.scenario} · **Ambient baseline:** {cfg.ambient_c:.0f}°C "
    f"· **Demand baseline:** {cfg.process_kw:.1f} kW · **Comparator:** {cfg.baseline}"
)
if cfg.scenario == "Production surge":
    st.caption("At hour 10–14, production demand increases by 2.5 kW. Neither controller receives advance notice.")
elif cfg.scenario == "Heater degradation":
    st.caption("Starting at hour 10, only 65% of electric heater input reaches the water as heat. "
               "Neither MPC is told about this change or updated to reflect it.")
else:
    st.caption("Normal operating conditions include varying production demand and a small ambient-temperature cycle.")

if cfg.baseline == "Physics MPC":
    st.caption(
        "Matched MPCs: same 625 plans, 20-minute horizon, objective and current observations. "
        "Physics MPC uses the nominal heat-balance equation. Both hold current demand and "
        "ambient temperature constant in their forecasts, and assume nominal efficiency. "
        "Overlapping curves are expected when the learned model recovers that equation."
    )

st.subheader("Controller comparison · 24 hours")
savings = (
    100 * (baseline_metrics["energy_kwh"] - fovra_metrics["energy_kwh"])
    / baseline_metrics["energy_kwh"]
    if baseline_metrics["energy_kwh"] > 0
    else 0.0
)

a, b, c, d = st.columns(4)
with a:
    st.metric("Fovra electricity", f"{fovra_metrics['energy_kwh']:.1f} kWh")
with b:
    st.metric(f"{cfg.baseline} electricity", f"{baseline_metrics['energy_kwh']:.1f} kWh")
with c:
    st.metric("Electricity difference", f"{savings:+.1f}%", help="Positive means Fovra uses less electricity. Negative means it uses more.")
with d:
    st.metric("Fovra outside allowed band", f"{fovra_metrics['minutes_outside']} min")

if (fovra_metrics["minutes_outside"] > 0 or baseline_metrics["minutes_outside"] > 0):
    st.warning(
        "At least one controller left the required temperature band. "
        "Lower electricity use alone is not evidence of better performance."
    )

# All chart values below come from the comparison dataframes (not mock data).
merged = merge_for_download(fovra, baseline_df, cfg.baseline)
plot_temp = pd.DataFrame(
    {
        "Time (hours)": fovra["time_h"],
        "Fovra": fovra["temperature_c"],
        cfg.baseline: baseline_df["temperature_c"],
        "Lower limit": MIN_SAFE_TEMP_C,
        "Upper limit": MAX_SAFE_TEMP_C,
    }
)

st.markdown("#### Tank temperature")
st.line_chart(
    plot_temp,
    x="Time (hours)",
    y=["Fovra", cfg.baseline, "Lower limit", "Upper limit"],
    x_label="Time (hours)",
    y_label="Temperature (°C)",
    height=330,
)

left, right = st.columns(2)
with left:
    st.markdown("#### Cumulative electricity")
    plot_energy = pd.DataFrame(
        {
            "Time (hours)": fovra["time_h"],
            "Fovra": fovra["cumulative_energy_kwh"],
            cfg.baseline: baseline_df["cumulative_energy_kwh"],
        }
    )
    st.line_chart(plot_energy, x="Time (hours)", y=["Fovra", cfg.baseline],
                  y_label="Electricity (kWh)", height=270)
with right:
    st.markdown("#### Commanded heater power")
    plot_power = pd.DataFrame(
        {
            "Time (hours)": fovra["time_h"],
            "Fovra": fovra["heater_kw"],
            cfg.baseline: baseline_df["heater_kw"],
        }
    )
    st.line_chart(plot_power, x="Time (hours)", y=["Fovra", cfg.baseline],
                  y_label="Input power (kW)", height=270)

st.markdown("#### Detailed outcomes")
metric_rows = [
    ("Electricity consumption (kWh)", "energy_kwh", 2),
    ("Time outside 58–62°C (minutes)", "minutes_outside", 0),
    ("Temperature RMSE from 60°C (°C)", "target_rmse_c", 3),
    ("Temperature standard deviation (°C)", "temperature_std_c", 3),
    ("Worst deviation from 60°C (°C)", "worst_target_deviation_c", 2),
    ("Maximum band violation (°C)", "max_violation_c", 3),
    ("Integrated band violation (°C·min)", "violation_degree_minutes", 2),
    ("Minimum temperature (°C)", "min_temperature_c", 2),
    ("Maximum temperature (°C)", "max_temperature_c", 2),
    ("Heater power adjustments", "heater_adjustments", 0),
    ("Total heater power variation (kW)", "heater_total_variation_kw", 1),
    ("Mean decision computation (ms)", "decision_mean_ms", 3),
    ("95th percentile decision computation (ms)", "decision_p95_ms", 3),
    ("Total decision computation (ms)", "decision_total_ms", 2),
]
comparison_table = pd.DataFrame(
    {
        "Metric": [label for label, _, _ in metric_rows],
        # Format per row so integer metrics don't display as "0.00".
        "Fovra": [f"{fovra_metrics[key]:.{digits}f}" for _, key, digits in metric_rows],
        cfg.baseline: [f"{baseline_metrics[key]:.{digits}f}" for _, key, digits in metric_rows],
    }
)
st.dataframe(comparison_table, hide_index=True, width="stretch")
st.caption(
    "Timing measures controller decisions only, excluding training, plant simulation and charts. "
    "Cached results retain timing from the original run. For repeated timing measurements, "
    "run benchmark_mpc.py. Power adjustments exclude the initial command from the off state. "
    "Temperature limits are soft penalties in both MPCs, not guaranteed hard constraints."
)

with st.expander("How the ML model works / prediction accuracy", expanded=False):
    st.write(
        "The model is **scikit-learn linear regression** trained on 6,000 synthetic "
        "examples from the nominal heater simulator. It predicts the five-minute "
        "change in water temperature from current temperature, surrounding "
        "temperature, production demand, and commanded heater power."
    )
    q1, q2 = st.columns(2)
    with q1:
        st.metric("Held-out synthetic MAE", f"{heldout_mae:.5f}°C")
    with q2:
        st.metric("This scenario's one-step MAE", f"{fovra_metrics['one_step_prediction_mae_c']:.3f}°C")
    st.caption(
        "The near-zero nominal MAE is expected because the simple training simulator "
        "uses a linear equation. It is not evidence of physical-world accuracy, "
        "novelty, or generalization. Degradation creates a deliberately hidden "
        "difference between the learned model and the simulated plant."
    )
    st.line_chart(
        pd.DataFrame(
            {
                "Time (hours)": fovra["time_h"],
                "Predicted next temperature": fovra["predicted_next_c"],
                "Actual next temperature": fovra["temperature_c"],
            }
        ),
        x="Time (hours)",
        y=["Predicted next temperature", "Actual next temperature"],
        height=260,
    )

with st.expander("See the simulated records", expanded=False):
    st.dataframe(merged, width="stretch", hide_index=True)

st.download_button(
    "Download this comparison as CSV",
    data=merged.to_csv(index=False).encode("utf-8"),
    file_name=f"fovra_{cfg.scenario.lower().replace(' ', '_')}_comparison.csv",
    mime="text/csv",
    width="stretch",
)

st.divider()
st.caption(
    "LIMITATIONS · Single simplified thermal system · No real sensor or plant data · "
    "Linear training dynamics · Approximate candidate-action MPC · "
    "No guaranteed safe control · Not an industrial deployment."
)
