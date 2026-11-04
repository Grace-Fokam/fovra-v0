"""Streamlit dashboard for the simulated data-center cooling experiment."""

import altair as alt
import pandas as pd
import streamlit as st

from cooling import CLIMATES, LIMIT_C, CoolingCase, compare_cooling, pareto_mask
from cooling_search import METHODS, best_verified, compare_search


@st.cache_data(show_spinner="Comparing cooling options...")
def get_cooling_results(case, size, trigger):
    return compare_cooling(case, size, trigger)


@st.cache_data(show_spinner="Testing settings in the simulator...")
def get_search_results(case, budget, water_budget, seed):
    return compare_search(case, budget, water_budget, seed)


def render_cooling():
    st.title("Cooling exploration")
    st.write("Compare ways to cool a simulated data center and see the electricity and water tradeoffs.")
    st.caption("Early research. The equipment and weather are illustrative.")
    with st.sidebar:
        st.markdown("### Cooling conditions")
        climate = st.selectbox("Climate", list(CLIMATES), index=1, key="cool_climate")
        load = st.slider("Base IT load (kW)", 20, 150, 80, 10, key="cool_load")
        surge = st.checkbox("Add a midday workload surge", key="cool_surge")
        size = st.select_slider("Cooler size", [0.6, 0.8, 1.0, 1.2, 1.5, 1.8, 2.0],
                                value=1.0, key="cool_size",
                                help="Relative heat-exchanger size. Bigger coolers have bigger fans.")
        trigger = st.select_slider("Start evaporative assist above fan fraction",
                                   [0.35, 0.55, 0.75, 1.0], value=1.0, key="cool_trigger",
                                   help="Lower values switch to water sooner. Below this fan setting, dry cooling is used if it can hit the target.")
        with st.expander("Cost and emissions assumptions"):
            carbon = st.number_input("Grid emissions (kg CO₂e/kWh)", 0.0, 2.0, 0.4, 0.05,
                                     key="cool_carbon")
            electricity = st.number_input("Electricity price ($/kWh)", 0.0, 2.0, 0.12, 0.01,
                                          key="cool_price")
            water_price = st.number_input("Water price ($/m³)", 0.0, 50.0, 2.0, 0.5,
                                          key="cool_water_price")
        st.caption("Simulates 24 hours. Both options get the same IT load and weather, and the workload is never reduced.")

    case = CoolingCase(climate, float(load), surge, carbon, electricity, water_price)
    summary, traces = get_cooling_results(case, size, trigger)
    st.markdown("#### Same workload, two cooling options")
    for column, (_, result) in zip(st.columns(2), summary.iterrows()):
        with column:
            st.subheader(result["mode"])
            st.metric("Cooling electricity", f"{result.cooling_kwh:.1f} kWh")
            st.metric("Makeup water", f"{result.makeup_l:,.0f} L")
            st.caption(f"Evaporated: {result.evaporated_l:,.0f} L · Peak coolant: {result.peak_coolant_c:.1f}°C")
            if result.thermal_ok:
                st.success("Passes the modeled temperature and end-of-day heat checks.")
            else:
                st.warning("Fails the modeled thermal checks, so low electricity use here doesn't count.")

    st.caption("Makeup water is evaporation plus blowdown. The dry cooler uses no onsite water in this model.")
    display = summary[["mode", "it_kwh", "cooling_kwh", "makeup_l", "evaporated_l",
                       "cooling_carbon_kg", "cooling_utility_cost", "peak_coolant_c",
                       "over_limit_minutes", "stored_heat_kwh"]].rename(columns={
        "mode": "Option", "it_kwh": "IT electricity (kWh)",
        "cooling_kwh": "Cooling electricity (kWh)", "makeup_l": "Makeup water (L)",
        "evaporated_l": "Evaporated water (L)", "cooling_carbon_kg": "Cooling emissions (kg CO₂e)",
        "cooling_utility_cost": "Cooling utility cost ($)", "peak_coolant_c": "Peak coolant (°C)",
        "over_limit_minutes": "Intervals over limit (min)", "stored_heat_kwh": "Heat left in loop (kWh)",
    })
    st.dataframe(display.round(2), hide_index=True, width="stretch")
    st.caption("Emissions cover cooling electricity only, and cost covers cooling electricity and makeup water. These aren't full facility or lifecycle totals.")

    st.markdown("#### Coolant temperature")
    lines = alt.Chart(traces).mark_line().encode(
        x=alt.X("time_h:Q", title="Hour"),
        y=alt.Y("coolant_c:Q", title="Bulk coolant (°C)", scale=alt.Scale(zero=False)),
        color=alt.Color("mode:N", title=None),
        tooltip=["mode:N", alt.Tooltip("time_h:Q", format=".2f"),
                 alt.Tooltip("coolant_c:Q", format=".2f")],
    )
    limit = alt.Chart(pd.DataFrame({"limit": [LIMIT_C]})).mark_rule(
        color="#C44B40", strokeDash=[5, 4]
    ).encode(y="limit:Q")
    st.altair_chart((lines + limit).properties(height=280))
    st.caption("Red line: illustrative 35°C coolant limit (not server inlet air or chip temperature).")
    a, b = st.columns(2)
    with a:
        st.line_chart(traces.pivot(index="time_h", columns="mode", values="cumulative_cooling_kwh"),
                      x_label="Hour", y_label="Cooling electricity (kWh)")
    with b:
        st.line_chart(traces.pivot(index="time_h", columns="mode", values="cumulative_makeup_l"),
                      x_label="Hour", y_label="Makeup water (L)")
    st.download_button("Download cooling results (CSV)", summary.to_csv(index=False),
                       "fovra_cooling_summary.csv", "text/csv", key="cool_summary_download")
    st.download_button("Download every cooling step (CSV)", traces.to_csv(index=False),
                       "fovra_cooling_steps.csv", "text/csv", key="cool_trace_download")

    st.divider()
    st.markdown("#### Test AI screening")
    st.write("A small model learns from finished simulations and suggests the next setting to try. See how it compares with random search on the same number of simulations.")
    st.caption("Searches 35 combinations of cooler type, size, and assist trigger, using the climate and workload above. Every reported result comes from the simulator.")
    a, b, c = st.columns(3)
    budget = a.selectbox("Simulations per method", [8, 12, 18, 24], index=1, key="cool_search_budget")
    water_budget = b.number_input("Maximum makeup water (L/day)", 0.0, 20000.0, 4000.0,
                                  250.0, key="cool_water_budget")
    seed = c.selectbox("Search seed", [11, 22, 33], key="cool_seed")
    request = (case, budget, water_budget, seed)
    if st.button("Run AI comparison", key="cool_search_run"):
        st.session_state.cool_search_result = (request, get_search_results(*request))
    stored = st.session_state.get("cool_search_result")
    if stored is not None and stored[0] == request:
        searches = stored[1]
        rows = []
        for method in METHODS:
            best = best_verified(searches[searches.method == method], water_budget)
            rows.append({"Method": method, "Simulations": budget,
                         "Best tested setting": best["design"] if best else "No feasible setting found",
                         "Cooling electricity (kWh)": best["cooling_kwh"] if best else None,
                         "Makeup water (L)": best["makeup_l"] if best else None})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        points = searches.drop_duplicates("candidate_id").copy()
        points["Tradeoff frontier"] = pareto_mask(points)
        st.altair_chart(alt.Chart(points).mark_circle(size=90).encode(
            x=alt.X("makeup_l:Q", title="Makeup water (L)"),
            y=alt.Y("cooling_kwh:Q", title="Cooling electricity (kWh)", scale=alt.Scale(zero=False)),
            color=alt.Color("thermal_ok:N", title="Thermal checks passed"),
            shape="Tradeoff frontier:N",
            tooltip=["design:N", "cooling_kwh:Q", "makeup_l:Q", "peak_coolant_c:Q"],
        ).properties(height=260))
        st.caption("Best = lowest cooling electricity among tested settings that pass the water and thermal checks. The frontier shows electricity/water tradeoffs among tested settings that pass. It ignores equipment cost and doesn't prove an AI advantage.")
        st.download_button("Download search trials (CSV)", searches.to_csv(index=False),
                           "fovra_cooling_search.csv", "text/csv", key="cool_search_download")
    elif stored is not None:
        st.info("Conditions changed. Run AI comparison again to update the results.")

    with st.expander("What this model assumes"):
        st.write("A warm-water loop takes in heat from the IT load and pump, and a fan rejects it to outdoor air. Evaporative assist can reject heat at a lower temperature, but uses water.")
        st.write("The fan follows a simple physics rule. AI is only used to screen settings in the optional search. It doesn't control a real data center or design hardware.")
        st.write("The loop starts at 32°C. To pass, it can't go over 35°C and can't end the day with more than 0.5 kWh of extra heat. Failing designs keep running at full load so overheating stays visible.")
        st.write("It leaves out chillers, chip temperatures, equipment failures, capital cost, embodied carbon, and water used to generate electricity. The wet model treats all rejected heat as evaporation. Validating it would need real equipment data.")
        st.markdown("[Equations, assumptions, and benchmark instructions](https://github.com/Grace-Fokam/fovra-v0/blob/ce12821da8b12acd26e2963cbdfab2f8cd0a2e53/docs/cooling-experiment.md)")
