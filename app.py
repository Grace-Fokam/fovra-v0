"""Fovra v0 dashboard. Run with: streamlit run app.py"""

import altair as alt
import pandas as pd
import streamlit as st

from controllers import BASELINES
from evaluation import SimulationConfig, compare, merge_for_download
from simulator import MAX_SAFE_TEMP_C, MIN_SAFE_TEMP_C, SCENARIOS
from train_model import train_world_model

st.set_page_config(page_title="Fovra", page_icon="◈", layout="wide")


# The model is trained once and reused. It is never retrained, including in
# the heater degradation scenario.
@st.cache_resource(show_spinner="Training the model...")
def get_model():
    return train_world_model()


@st.cache_data(show_spinner="Running the simulation...")
def get_results(ambient_c: float, process_kw: float, scenario: str, baseline: str):
    model, _ = get_model()
    return compare(SimulationConfig(ambient_c, process_kw, scenario, baseline), model)


if "submitted_conditions" not in st.session_state:
    st.session_state.submitted_conditions = {
        "ambient_c": 20.0,
        "process_kw": 3.0,
        "scenario": "Normal",
        "baseline": "Thermostat",
    }
current = st.session_state.submitted_conditions

with st.sidebar:
    st.markdown("### Try it")
    with st.form("controls"):
        ambient = st.slider(
            "Room temperature (°C)", 10, 35, int(current["ambient_c"]), 1,
            help="A small day/night swing is added on top.",
        )
        demand = st.slider(
            "Production heat demand (kW)", 1.0, 6.0, float(current["process_kw"]), 0.5,
            help="How fast production pulls heat out of the tank.",
        )
        scenario = st.radio(
            "Scenario", SCENARIOS, index=SCENARIOS.index(current["scenario"]),
            help="Both controllers get the exact same day.",
        )
        baseline = st.selectbox(
            "Compare against", BASELINES, index=BASELINES.index(current["baseline"])
        )
        submitted = st.form_submit_button("Run", type="primary", width="stretch")

    if submitted:
        st.session_state.submitted_conditions = {
            "ambient_c": float(ambient),
            "process_kw": float(demand),
            "scenario": scenario,
            "baseline": baseline,
        }

    st.divider()
    st.markdown("**About the simulation**")
    st.caption(
        "24 hours in 5-minute steps. 0–12 kW heater. "
        "The water should stay between 58 and 62°C and starts at 60°C. "
        "The numbers are reasonable guesses, not real equipment."
    )

cfg = SimulationConfig(**st.session_state.submitted_conditions)
model, heldout_mae = get_model()
fovra, baseline_df, fovra_metrics, baseline_metrics = get_results(
    cfg.ambient_c, cfg.process_kw, cfg.scenario, cfg.baseline
)

st.title("Fovra")
st.write(
    "A simulated hot water tank. Fovra learns how it behaves and plans ahead. "
    "Pick something to compare it against in the sidebar."
)

scenario_notes = {
    "Normal": "Demand and room temperature drift a little through the day.",
    "Production surge": "From hour 10 to 14, production needs 2.5 kW more. "
    "Neither controller knows it's coming.",
    "Heater degradation": "From hour 10, the heater only delivers 65% of its power. "
    "Neither controller is told.",
}
st.caption(
    f"{cfg.scenario}: {scenario_notes[cfg.scenario]} "
    f"Room {cfg.ambient_c:.0f}°C, demand {cfg.process_kw:.1f} kW."
)
if cfg.baseline == "Physics MPC":
    st.caption(
        "Physics MPC plans just like Fovra, but uses the tank's equation instead "
        "of learning it. If the lines overlap, that's expected."
    )

savings = (
    100 * (baseline_metrics["energy_kwh"] - fovra_metrics["energy_kwh"])
    / baseline_metrics["energy_kwh"]
    if baseline_metrics["energy_kwh"] > 0
    else 0.0
)

a, b, c, d = st.columns(4)
a.metric("Fovra energy", f"{fovra_metrics['energy_kwh']:.1f} kWh")
b.metric(f"{cfg.baseline} energy", f"{baseline_metrics['energy_kwh']:.1f} kWh")
c.metric("Difference", f"{savings:+.1f}%", help="Positive means Fovra used less.")
d.metric("Fovra out of range", f"{fovra_metrics['minutes_outside']} min")

if fovra_metrics["minutes_outside"] > 0 or baseline_metrics["minutes_outside"] > 0:
    st.warning(
        "At least one controller let the water go out of range. "
        "Saving energy doesn't count for much when that happens."
    )

st.markdown("#### Tank temperature")
temps = pd.DataFrame(
    {
        "Hour": fovra["time_h"],
        "Fovra": fovra["temperature_c"],
        cfg.baseline: baseline_df["temperature_c"],
    }
).melt("Hour", var_name="Controller", value_name="Temperature")
# Zoom the axis to the data and the allowed range, instead of starting at 0,
# so small swings are visible.
y_min = min(MIN_SAFE_TEMP_C, temps["Temperature"].min()) - 0.5
y_max = max(MAX_SAFE_TEMP_C, temps["Temperature"].max()) + 0.5
y_scale = alt.Scale(domain=[y_min, y_max], zero=False)
allowed_range = (
    alt.Chart(pd.DataFrame({"low": [MIN_SAFE_TEMP_C], "high": [MAX_SAFE_TEMP_C]}))
    .mark_rect(color="#2F6FD0", opacity=0.08)
    .encode(y=alt.Y("low:Q", scale=y_scale), y2="high:Q")
)
lines = (
    alt.Chart(temps)
    .mark_line(strokeWidth=2)
    .encode(
        x=alt.X("Hour:Q", title="Hour", scale=alt.Scale(domain=[0, 24])),
        y=alt.Y("Temperature:Q", title="°C", scale=y_scale),
        color=alt.Color(
            "Controller:N",
            scale=alt.Scale(domain=["Fovra", cfg.baseline], range=["#2F6FD0", "#9A9893"]),
            legend=alt.Legend(title=None, orient="bottom"),
        ),
        tooltip=[
            alt.Tooltip("Controller:N"),
            alt.Tooltip("Hour:Q", format=".2f"),
            alt.Tooltip("Temperature:Q", title="°C", format=".2f"),
        ],
    )
)
st.altair_chart(alt.layer(allowed_range, lines).properties(height=330))
st.caption("The shaded band is the 58–62°C range. The axis is zoomed in so small changes show up.")

left, right = st.columns(2)
with left:
    st.markdown("#### Energy used so far")
    st.line_chart(
        pd.DataFrame(
            {
                "Hour": fovra["time_h"],
                "Fovra": fovra["cumulative_energy_kwh"],
                cfg.baseline: baseline_df["cumulative_energy_kwh"],
            }
        ),
        x="Hour", y=["Fovra", cfg.baseline], y_label="kWh", height=270,
    )
with right:
    st.markdown("#### Heater power")
    st.line_chart(
        pd.DataFrame(
            {
                "Hour": fovra["time_h"],
                "Fovra": fovra["heater_kw"],
                cfg.baseline: baseline_df["heater_kw"],
            }
        ),
        x="Hour", y=["Fovra", cfg.baseline], y_label="kW", height=270,
    )


def results_table(rows):
    return pd.DataFrame(
        {
            "Metric": [label for label, _, _ in rows],
            "Fovra": [f"{fovra_metrics[k]:.{d}f}" for _, k, d in rows],
            cfg.baseline: [f"{baseline_metrics[k]:.{d}f}" for _, k, d in rows],
        }
    )


st.markdown("#### Details")
st.dataframe(
    results_table(
        [
            ("Energy (kWh)", "energy_kwh", 2),
            ("Time out of range (min)", "minutes_outside", 0),
            ("Typical miss from 60°C (°C)", "target_rmse_c", 3),
            ("Biggest miss from 60°C (°C)", "worst_target_deviation_c", 2),
            ("Lowest temperature (°C)", "min_temperature_c", 2),
            ("Highest temperature (°C)", "max_temperature_c", 2),
            ("Heater changes", "heater_adjustments", 0),
        ]
    ),
    hide_index=True,
    width="stretch",
)

with st.expander("More numbers"):
    st.dataframe(
        results_table(
            [
                ("How much the temperature varied (°C)", "temperature_std_c", 3),
                ("Furthest out of range (°C)", "max_violation_c", 3),
                ("How far × how long out of range (°C·min)", "violation_degree_minutes", 2),
                ("Total heater movement (kW)", "heater_total_variation_kw", 1),
                ("Time to decide, average (ms)", "decision_mean_ms", 3),
                ("Time to decide, slowest 5% (ms)", "decision_p95_ms", 3),
                ("Time to decide, whole day (ms)", "decision_total_ms", 2),
            ]
        ),
        hide_index=True,
        width="stretch",
    )
    st.caption(
        "Typical miss is the RMSE from 60°C. Time to decide only counts choosing a "
        "heater setting. Repeat runs reuse the first timing, so use benchmark_mpc.py "
        "for fresh numbers. Both planners try hard to stay in range, but it isn't "
        "guaranteed."
    )

with st.expander("How the model works"):
    st.write(
        "Fovra uses a linear regression model trained on 6,000 simulated examples. "
        "It predicts how the water temperature will change over the next 5 minutes. "
        "Every 5 minutes, Fovra tries 625 heater plans for the next 20 minutes, "
        "picks the one that saves the most energy while staying in range, and "
        "applies its first step."
    )
    q1, q2 = st.columns(2)
    q1.metric("Error on test data", f"{heldout_mae:.5f}°C")
    q2.metric("Error in this run", f"{fovra_metrics['one_step_prediction_mae_c']:.3f}°C")
    st.caption(
        "The error is close to zero because the simulator is a simple equation the "
        "model can learn exactly. Real equipment is messier. In the heater degradation "
        "scenario, the model goes wrong on purpose."
    )
    st.line_chart(
        pd.DataFrame(
            {
                "Hour": fovra["time_h"],
                "Predicted": fovra["predicted_next_c"],
                "Actual": fovra["temperature_c"],
            }
        ),
        x="Hour", y=["Predicted", "Actual"], y_label="°C", height=260,
    )

B = cfg.baseline
merged = merge_for_download(fovra, baseline_df, B).drop(columns="baseline_type")
merged = merged.rename(
    columns={
        "time_hours": "Hour",
        "ambient_c": "Room (°C)",
        "process_heat_demand_kw": "Production demand (kW)",
        "actual_heater_efficiency": "Real heater efficiency",
        "fovra_temperature_c": "Fovra temp (°C)",
        "baseline_temperature_c": f"{B} temp (°C)",
        "fovra_heater_kw": "Fovra heater (kW)",
        "baseline_heater_kw": f"{B} heater (kW)",
        "fovra_cumulative_kwh": "Fovra energy so far (kWh)",
        "baseline_cumulative_kwh": f"{B} energy so far (kWh)",
        "fovra_predicted_next_temperature_c": "Fovra predicted temp (°C)",
        "baseline_predicted_next_temperature_c": f"{B} predicted temp (°C)",
        "fovra_prediction_error_c": "Fovra prediction error (°C)",
        "baseline_prediction_error_c": f"{B} prediction error (°C)",
        "fovra_decision_ms": "Fovra time to decide (ms)",
        "baseline_decision_ms": f"{B} time to decide (ms)",
    }
)
with st.expander("Every 5-minute step"):
    st.dataframe(merged, width="stretch", hide_index=True)

st.download_button(
    "Download this run (CSV)",
    data=merged.to_csv(index=False).encode("utf-8"),
    file_name=f"fovra_{cfg.scenario.lower().replace(' ', '_')}.csv",
    mime="text/csv",
)

st.divider()
st.caption(
    "This is one simple simulated system with no real data. "
    "It isn't a tested or safe controller for real equipment."
)
