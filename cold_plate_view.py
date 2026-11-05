"""Interactive component design and recorded cold-plate search results."""

from dataclasses import asdict, fields
import json

import altair as alt
import pandas as pd
import streamlit as st

from cold_plate import ColdPlateCase, ColdPlateDesign, evaluate_design
from cold_plate_explorer import (
    CASE_LABELS, METHOD_LABELS, VIOLATIONS, budget_snapshot, comparison_results,
    geometry_svg, load_recorded_results, paired_outcomes,
)

COLORS = ["#0d8c89", "#d97b38"]
DOC_URL = "https://github.com/Grace-Fokam/fovra-v0/blob/main/docs/cold-plate.md"


@st.cache_data(show_spinner=False)
def recorded_results():
    return load_recorded_results()


def _load_design(design):
    for key, value in asdict(design).items():
        st.session_state[f"cp_{key}"] = value


def _case_changed():
    # A fixed-flow study must not silently retain the previous flow setting.
    if st.session_state.cp_case == "fixed_flow_geometry":
        st.session_state.cp_flow_lpm = 0.2


def _controls(data):
    cases = {e["case"]["name"]: ColdPlateCase(**e["case"])
             for e in data["metadata"]["experiments"]}
    with st.sidebar:
        st.markdown("### Operating case")
        name = st.selectbox("Illustrative requirements", list(cases), key="cp_case",
                            format_func=CASE_LABELS.get, on_change=_case_changed)
        case = cases[name]
        case_id = list(cases).index(name)
        winner = next(w for w in data["winners"] if w["case_id"] == case_id)
        st.caption(f"Base ≤{case.max_base_c:g}°C · Δp ≤{case.max_pressure_pa/1000:g} kPa · "
                   f"plate pump ≤{case.max_pump_w:g} W")
        st.markdown("### Channel geometry")
        a, b = st.columns(2)
        a.button("Grid best", key="cp_reset_grid", on_click=_load_design,
                 args=(ColdPlateDesign(**winner["design"]),), width="stretch")
        b.button("Reference", key="cp_reset_reference", on_click=_load_design,
                 args=(ColdPlateDesign(),), width="stretch")
        defaults = ColdPlateDesign(**winner["design"])
        for field in fields(ColdPlateDesign):
            st.session_state.setdefault(f"cp_{field.name}", getattr(defaults, field.name))
        if name == "fixed_flow_geometry":
            st.session_state.cp_flow_lpm = 0.2
        width = st.select_slider("Channel width (mm)", [0.2, 0.3, 0.5, 0.8], key="cp_width_mm")
        depth = st.select_slider("Channel depth (mm)", [0.8, 1.2, 1.8], key="cp_depth_mm")
        web = st.select_slider("Web thickness (mm)", [0.2, 0.4, 0.8], key="cp_web_mm")
        base = st.select_slider("Base thickness (mm)", [1.0, 2.0], key="cp_base_mm")
        st.markdown("### Material & coolant")
        conductivity = st.selectbox("Solid conductivity", [167.0, 390.0], key="cp_conductivity_w_mk",
            format_func=lambda k: f"{'Aluminum-like' if k == 167 else 'Copper-like'} · {k:g} W/(m·K)",
            help="Illustrative conductivity values, not certified alloys. No material cost penalty.")
        flow = st.select_slider("Total water flow (L/min)", [0.05, 0.1, 0.2, 0.4, 0.8],
                                key="cp_flow_lpm", disabled=name == "fixed_flow_geometry")
        st.caption("100 × 50 mm coupon · 1 mm cover. Controls use the recorded search values. "
                   "Some combinations fall outside the geometry rules.")
    return case_id, case, ColdPlateDesign(width, depth, web, base, flow, conductivity), winner


def _metrics(result):
    specifications = [("Peak base proxy", "peak_base_c", "°C", 3),
                      ("Pressure drop", "pressure_pa", "Pa", 3),
                      ("Plate-only pump", "pump_w", "mW", 3),
                      ("Thermal resistance", "thermal_resistance_k_w", "K/W", 4)]
    for column, (label, key, unit, digits) in zip(st.columns(4), specifications):
        value = result.get(key)
        if value is not None and key == "pump_w":
            value *= 1000
        column.metric(label, "—" if value is None else f"{value:,.{digits}f} {unit}", border=True)


def _status(case, result):
    if result["feasible"]:
        st.success("Passes this model's geometry, correlation-domain and operating checks. Hardware validation is still required.")
    elif not result["geometry_ok"]:
        st.error("Geometry outside model rules. Thermal and hydraulic outputs are unavailable.")
    elif not result["domain_ok"]:
        st.warning("Outside the model's correlation domain. Values below are diagnostics, not supported performance predictions.")
    else:
        st.warning("Within the correlation domain, but fails an operating limit.")
    for reason in result["violations"].split(";"):
        if reason:
            st.caption("• " + VIOLATIONS.get(reason, reason))
    with st.expander("Constraint details & diagnostics", expanded=False):
        if not result["geometry_ok"]:
            st.write("Correct the geometry to calculate the operating and correlation checks.")
            return
        checks = [
            ("Peak base proxy", result["peak_base_c"], case.max_base_c, "°C"),
            ("Pressure drop", result["pressure_pa"], case.max_pressure_pa, "Pa"),
            ("Plate-only pump electricity", result["pump_w"], case.max_pump_w, "W"),
            ("Reynolds number", result["reynolds"], 2000, "–"),
            ("Hydrodynamic entry / channel length", result["hydrodynamic_entry_fraction"], 0.1, "–"),
            ("Thermal entry / channel length", result["thermal_entry_fraction"], 1.0, "–"),
            ("Outlet water", result["outlet_c"], 40.0, "°C"),
        ]
        st.dataframe(pd.DataFrame([{"Check": label, "Value": value, "Maximum": limit,
                                   "Unit": unit, "Status": "Pass" if value <= limit else "Fail"}
                                  for label, value, limit, unit in checks]),
                     hide_index=True, width="stretch")
        st.caption(f"Inlet water {case.inlet_c:g}°C (minimum 20°C). "
                   f"Outlet {result['outlet_c']:.3f}°C · channel velocity {result['velocity_m_s']:.4f} m/s · "
                   f"fin efficiency {result['fin_efficiency']:.3f}.")


def _display_comparison(frame):
    display = frame.reindex(columns=["design", "width_mm", "depth_mm", "web_mm", "base_mm",
        "conductivity_w_mk", "flow_lpm", "channel_count", "peak_base_c", "pressure_pa",
        "pump_w", "feasible", "domain_ok", "violations"]).copy()
    display["pump_w"] *= 1000
    display["Status"] = frame.apply(lambda r: "Model feasible" if r.feasible else
        "Invalid geometry" if not r.geometry_ok else "Outside model domain" if not r.domain_ok else
        "Operating limit failed", axis=1)
    display = display.drop(columns=["feasible", "domain_ok"]).rename(columns={
        "design": "Design", "width_mm": "Width (mm)", "depth_mm": "Depth (mm)",
        "web_mm": "Web (mm)", "base_mm": "Base (mm)", "conductivity_w_mk": "k (W/m·K)",
        "flow_lpm": "Flow (L/min)", "channel_count": "Channels", "peak_base_c": "Base proxy (°C)",
        "pressure_pa": "Δp (Pa)", "pump_w": "Pump (mW)", "violations": "Failed checks"})
    st.dataframe(display.round(4), hide_index=True, width="stretch")


def _design_studio(case, design, winner):
    result = evaluate_design(case, design)
    _status(case, result)
    _metrics(result)
    st.caption("Base temperature is not chip junction temperature. Pump power covers the plate only, at 40% efficiency.")
    drawing = geometry_svg(case, design, result)
    if drawing:
        st.image(drawing, width="stretch")
    else:
        st.info("Geometry preview withheld until the dimensions pass the model's geometry checks.")
    st.caption(f"Uniform {case.heat_w:g} W heat load over 50 cm² "
               f"({case.heat_w/50:g} W/cm²). Water enters at {case.inlet_c:g}°C. "
               "This illustrative coupon does not represent a high-power GPU or its hotspots.")

    st.markdown("### Compare design choices")
    st.write("Pin a design, adjust a parameter, and compare all candidates under the same operating case.")
    pins = st.session_state.setdefault("cp_pins", [])
    left, right, _ = st.columns([1, 1, 2])
    if left.button("Pin current design", key="cp_pin", disabled=design in pins or len(pins) >= 3,
                   width="stretch"):
        pins.append(design)
        st.rerun()
    if right.button("Clear pinned designs", key="cp_clear", disabled=not pins, width="stretch"):
        st.session_state.cp_pins = []
        st.rerun()
    st.caption("Up to three pins, retained for this session. Changing case re-evaluates every design. "
               "The fixed-flow case applies 0.2 L/min to all comparisons.")
    designs = [("Current design", design), ("Arbitrary reference", ColdPlateDesign()),
               ("Recorded grid best", ColdPlateDesign(**winner["design"]))]
    designs += [(f"Pinned {i+1}", item) for i, item in enumerate(pins)]
    frame = comparison_results(case, designs)
    _display_comparison(frame)
    valid = frame[frame.geometry_ok].copy()
    valid["Status"] = valid.apply(lambda r: "Model feasible" if r.feasible else "Diagnostic / infeasible", axis=1)
    if not valid.empty:
        st.altair_chart(alt.Chart(valid).mark_point(size=180, filled=True).encode(
            x=alt.X("pressure_pa:Q", title="Pressure drop (Pa)", scale=alt.Scale(type="log")),
            y=alt.Y("peak_base_c:Q", title="Peak base proxy (°C)", scale=alt.Scale(zero=False)),
            color=alt.Color("design:N", title="Design"), shape=alt.Shape("Status:N", title=None),
            tooltip=["design:N", "Status:N", "flow_lpm:Q", "peak_base_c:Q", "pressure_pa:Q", "pump_w:Q"],
        ).properties(height=230), use_container_width=True)
    st.caption("The reference is an arbitrary geometry, not a commercial product. Grid best means lowest "
               "feasible plate-only pump electricity within the recorded finite grid, not lowest temperature.")
    a, b = st.columns(2)
    a.download_button("Download comparison CSV", frame.to_csv(index=False),
                      "fovra_cold_plate_comparison.csv", "text/csv", key="cp_comparison_download")
    payload = {"scope": "Unvalidated reduced-order simulation, not hardware performance",
               "case": asdict(case), "design": asdict(design), "result": result}
    b.download_button("Download current design JSON", json.dumps(payload, indent=2, allow_nan=False),
                      "fovra_cold_plate_design.json", "application/json", key="cp_design_download")


def _search_chart(trace, winner, budget, metadata):
    trace = trace.copy()
    trace["Method"] = trace.method.map(METHOD_LABELS)
    trace["pump_mw"] = trace.best_pump_w_so_far * 1000
    colors = alt.Scale(domain=list(METHOD_LABELS.values()), range=COLORS)
    line = alt.Chart(trace).mark_line(interpolate="step-after", point=True).encode(
        x=alt.X("evaluation:Q", title="Simulator evaluations per method",
                scale=alt.Scale(domain=[1, metadata["budget"]]), axis=alt.Axis(tickMinStep=1)),
        y=alt.Y("pump_mw:Q", title="Best feasible plate pump (mW) · lower is better",
                scale=alt.Scale(type="log")),
        color=alt.Color("Method:N", scale=colors, title=None),
        tooltip=["Method:N", "evaluation:Q", alt.Tooltip("pump_mw:Q", format=".4f")])
    oracle = alt.Chart(pd.DataFrame({"pump_mw": [winner["result"]["pump_w"]*1000]})).mark_rule(
        color="#52677b", strokeDash=[6, 4]).encode(y="pump_mw:Q")
    initial = alt.Chart(pd.DataFrame({"evaluation": [metadata["shared_initial_samples"]]})).mark_rule(
        color="#9ca9b3", strokeDash=[2, 4]).encode(x="evaluation:Q")
    st.altair_chart((line + oracle + initial).properties(height=310), use_container_width=True)
    st.caption(f"Showing the first {budget} evaluations of a recorded {metadata['budget']}-call run, "
               f"including failures and {metadata['shared_initial_samples']} shared initial designs. "
               "Blank values mean no feasible design yet. Horizontal dashed line: separate exhaustive-grid best. "
               "Vertical dotted line: end of shared initialization. Logarithmic pump axis.")


def _tradeoff_chart(data, case_id, case, snapshot):
    grid = data["grid"][data["grid"].case_id == case_id].copy()
    grid["Status"] = grid.apply(lambda r: "Model feasible" if r.feasible else
        "Outside model domain" if not r.domain_ok else "Operating limit failed", axis=1)
    show_failures = st.checkbox("Include infeasible diagnostic points", key="cp_show_failures")
    points = grid[grid.geometry_ok & (True if show_failures else grid.feasible)]
    chart = alt.Chart(points).mark_circle(size=40, opacity=0.45).encode(
        x=alt.X("pressure_pa:Q", title="Pressure drop (Pa) · logarithmic", scale=alt.Scale(type="log")),
        y=alt.Y("peak_base_c:Q", title="Peak base proxy (°C)", scale=alt.Scale(zero=False)),
        color=alt.Color("Status:N", title=None, scale=alt.Scale(
            domain=["Model feasible", "Outside model domain", "Operating limit failed"],
            range=["#93b5c4", "#c9a89c", "#cb6b5c"])),
        tooltip=["candidate_id:Q", "Status:N", "width_mm:Q", "depth_mm:Q", "flow_lpm:Q",
                 "peak_base_c:Q", "pressure_pa:Q", "pump_w:Q", "violations:N"])
    best = snapshot[snapshot.found_feasible].copy()
    best["Method"] = best.method.map(METHOD_LABELS)
    selected = alt.Chart(best).mark_point(size=190, filled=True, stroke="#102738", strokeWidth=1).encode(
        x="pressure_pa:Q", y="peak_base_c:Q", color=alt.Color("Method:N", title=None,
        scale=alt.Scale(domain=list(METHOD_LABELS.values()), range=COLORS)),
        shape=alt.Shape("Method:N", legend=None),
        tooltip=["Method:N", "candidate_id:Q", "peak_base_c:Q", "pressure_pa:Q", "pump_w:Q"])
    thermal_limit = alt.Chart(pd.DataFrame({"limit": [case.max_base_c]})).mark_rule(
        color="#b65745", strokeDash=[5, 4]).encode(y="limit:Q")
    pressure_limit = alt.Chart(pd.DataFrame({"limit": [case.max_pressure_pa]})).mark_rule(
        color="#b65745", strokeDash=[5, 4]).encode(x="limit:Q")
    st.altair_chart((chart + selected + thermal_limit + pressure_limit).resolve_scale(color="independent").properties(
        height=330), use_container_width=True)
    st.caption(f"{len(grid)} recorded grid candidates, {int(grid.feasible.sum())} model-feasible. "
               "Large symbols: best feasible result for each method at the selected seed and budget. "
               "Dashed lines: operating limits. Pressure and temperature alone do not determine feasibility. "
               "The stored Pareto flag concerns temperature versus pump power, so it is not used as a pressure frontier.")


def _recorded_search(data, case_id, case, winner):
    metadata = data["metadata"]
    st.markdown("### Search the design space")
    st.write("Recorded experiment · minimize plate-only pump electricity while satisfying all model checks.")
    st.info("The controls below replay saved simulations. Geometry and material edits do not rerun this experiment. "
            "Use the operating-case selector to switch the recorded dataset.")
    a, b = st.columns([1, 3])
    seed = a.selectbox("Recorded seed", metadata["seeds"], key="cp_seed")
    budget = b.slider("Replay evaluation budget per method", 1, metadata["budget"],
                       metadata["budget"], key="cp_budget")
    snapshot = budget_snapshot(data["search_trials"], case_id, budget)
    selected = snapshot[snapshot.seed == seed]
    for col, (_, row) in zip(st.columns(2), selected.sort_values("method").iterrows()):
        with col:
            value = f"{row.pump_w*1000:.4f} mW" if row.found_feasible else "No feasible design"
            st.metric(METHOD_LABELS[row.method], value, border=True)
            st.caption(f"{int(row.evaluations)} calls · {int(row.feasible_observations)} feasible observations")
    trials = data["search_trials"]
    trace = trials[(trials.case_id == case_id) & (trials.seed == seed) & (trials.evaluation <= budget)]
    _search_chart(trace, winner, budget, metadata)
    st.markdown("#### Temperature & pressure tradeoffs")
    _tradeoff_chart(data, case_id, case, selected)
    st.markdown("#### Check all seeds")
    outcomes = paired_outcomes(snapshot)
    st.write(f"At {budget} evaluations, across {len(metadata['seeds'])} seeds in this case: "
             f"**{outcomes.get('win', 0)} surrogate wins · {outcomes.get('tie', 0)} ties · "
             f"{outcomes.get('loss', 0)} losses · {outcomes.get('neither_feasible', 0)} neither feasible**.")
    table = snapshot.copy()
    table["Method"] = table.method.map(METHOD_LABELS)
    table["Best pump (mW)"] = table.pump_w * 1000
    table["Gap to grid (%)"] = (table.pump_w / winner["result"]["pump_w"] - 1) * 100
    st.dataframe(table[["seed", "Method", "evaluations", "feasible_observations", "found_feasible",
                        "candidate_id", "Best pump (mW)", "Gap to grid (%)"]].round(4),
                 hide_index=True, width="stretch")
    st.caption("Relative gaps divide by very small pump values. Missing results stay missing, not zero.")
    totals = data["paired_comparison"].surrogate_outcome.value_counts()
    st.write(f"Full recorded benchmark: **{totals.get('win', 0)} wins, {totals.get('tie', 0)} ties, "
             f"{totals.get('loss', 0)} losses** across {len(data['paired_comparison'])} matched comparisons "
             f"at {metadata['budget']} calls per method.")
    timings = data["timings"].groupby("method").agg(
        runs=("elapsed_s", "size"), calls=("evaluations", "sum"), elapsed_s=("elapsed_s", "sum")).reset_index()
    timings["Method"] = timings.method.map({**METHOD_LABELS, "grid": "Exhaustive grid"})
    st.markdown("#### Evaluation efficiency is not runtime speed")
    st.dataframe(timings[["Method", "runs", "calls", "elapsed_s"]].rename(columns={
        "runs": "Recorded runs", "calls": "Simulator calls", "elapsed_s": "Total recorded time (s)"
    }).round(3), hide_index=True, width="stretch")
    st.caption("Full runs across all four cases, independent of the replay slider. Search timings include model fitting. "
               "The exhaustive grid was much faster on this cheap simulator. These machine-specific timings do not show an AI speedup.")
    st.warning("Six fixed seeds are an initial benchmark. Higher-load and warm-inlet outcomes are nearly redundant. "
               "This is not a held-out statistical result, CFD validation, or measured hardware performance.")
    st.download_button("Download displayed search trials (CSV)", trace.to_csv(index=False),
                       "fovra_cold_plate_search_prefix.csv", "text/csv", key="cp_trials_download")


def _model_notes(data):
    st.markdown("### What the model can tell us")
    st.write("A reduced-order model screens straight rectangular channels under uniform heating. "
             "Every live design calls the same evaluate_design function used by the research benchmark. "
             "Recorded search points are simulator evaluations, not random-forest predictions.")
    st.markdown("""
- **Geometry:** 100 × 50 mm coupon, equal parallel flow, three heated channel walls and an insulated lid.
- **Physics:** fully developed laminar rectangular-duct correlations, fin efficiency and base conduction. Water properties are fixed at approximate room-temperature values.
- **Feasibility:** chosen geometry rules, a correlation envelope, and illustrative temperature, pressure and pump limits. Passing is not manufacturing approval.
- **Omissions:** headers, flow maldistribution, heat spreading, chip/package/TIM resistance, hotspots, roughness, tolerances, leakage, sealing and long-term reliability.
- **Next evidence:** real component requirements, conjugate CFD with mesh and conservation checks, then fabricated parts and repeatable bench measurements.
""")
    st.info("No CFD, fabricated components or laboratory measurements are included. Conductivity has no cost penalty, "
            "and thin bases/webs have no structural penalty. The grid often selects these boundaries.")
    st.markdown(f"[Read the equations, assumptions and research results]({DOC_URL})")
    st.markdown("[Reproduce the recorded results](https://github.com/Grace-Fokam/fovra-v0/blob/main/docs/cold-plate-reproducibility.md)")
    with st.expander("Recorded run provenance"):
        metadata = data["metadata"]
        st.json({key: metadata[key] for key in ("objective", "budget", "seeds", "shared_initial_samples",
                                               "python", "packages", "source_sha256")})


def render_cold_plate():
    st.markdown('''<style>
    .cp-hero {padding:28px 32px;border-radius:16px;background:linear-gradient(115deg,#102738,#164e57);color:#f7fbfc;margin-bottom:22px}
    .cp-hero .eyebrow {font-size:12px;letter-spacing:2px;color:#80ddd5;font-weight:700}
    .cp-hero h1 {color:#f7fbfc;font-size:36px;letter-spacing:-1px;padding:10px 0}
    .cp-hero p {color:#d9e8ed;margin:0;max-width:760px}
    @media(max-width:640px) {.cp-hero {padding:20px}.cp-hero h1 {font-size:27px}}
    </style><div class="cp-hero"><div class="eyebrow">FOVRA / COMPONENT RESEARCH</div>
    <h1>Explore the geometry of cooling.</h1>
    <p>Shape a liquid cold plate. Examine the tradeoffs. See how a learned search chooses its next design.</p></div>''', unsafe_allow_html=True)
    st.caption("SIMULATION ONLY · Unvalidated reduced-order research. No experimentally validated hardware performance.")
    try:
        data = recorded_results()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        st.error(f"The recorded cold-plate files could not be loaded: {exc}")
        st.info("Restore results/cold_plate from the repository. The data-center cooling view remains available.")
        return
    case_id, case, design, winner = _controls(data)
    view = st.radio("Component workspace", ["Design studio", "Recorded search", "Model & evidence"],
                    horizontal=True, key="cp_view", label_visibility="collapsed")
    if view == "Design studio":
        _design_studio(case, design, winner)
    elif view == "Recorded search":
        _recorded_search(data, case_id, case, winner)
    else:
        _model_notes(data)
