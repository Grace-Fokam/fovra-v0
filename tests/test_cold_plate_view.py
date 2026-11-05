"""UI integration checks against the simulator and recorded scientific results."""

from pathlib import Path
import xml.etree.ElementTree as ET

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from cold_plate import ColdPlateCase, ColdPlateDesign, evaluate_design
from cold_plate_explorer import (
    budget_snapshot, comparison_results, geometry_svg, load_recorded_results, paired_outcomes,
)

APP = str(Path(__file__).resolve().parents[1] / "app.py")


@pytest.fixture(scope="module")
def recorded():
    return load_recorded_results()


def app():
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    return at


def comparison_table(at):
    return next(d.value for d in at.dataframe if "Design" in d.value.columns)


def test_default_and_edited_design_match_simulator():
    at = app()
    assert at.radio(key="research_view").value == "Component design"
    assert at.metric[0].value == "41.386 °C"
    assert at.metric[1].value == "56.471 Pa"
    at.button(key="cp_reset_reference").click().run()
    at.selectbox(key="cp_conductivity_w_mk").set_value(167.0)
    at.select_slider(key="cp_flow_lpm").set_value(0.4).run()
    expected = evaluate_design(ColdPlateCase(), ColdPlateDesign(flow_lpm=0.4, conductivity_w_mk=167))
    assert not at.exception
    assert at.metric[0].value == f"{expected['peak_base_c']:,.3f} °C"
    assert at.metric[1].value == f"{expected['pressure_pa']:,.3f} Pa"
    assert comparison_table(at).iloc[0]["k (W/m·K)"] == 167
    assert len(at.get("download_button")) == 2


def test_invalid_geometry_has_no_invented_physics_and_recovers():
    at = app()
    at.select_slider(key="cp_width_mm").set_value(0.2).run()
    assert not at.exception
    assert all(m.value == "—" for m in at.metric)
    assert any("Geometry outside model rules" in e.value for e in at.error)
    assert comparison_table(at).iloc[0]["Status"] == "Invalid geometry"
    at.button(key="cp_reset_grid").click().run()
    assert not at.exception
    assert at.metric[0].value == "41.386 °C"
    assert not at.error


def test_domain_failures_remain_visible():
    at = app()
    at.select_slider(key="cp_flow_lpm").set_value(0.8).run()
    assert not at.exception
    assert any("Outside the model's correlation domain" in w.value for w in at.warning)
    assert any("entry length" in c.value for c in at.caption)
    assert comparison_table(at).iloc[0]["Status"] == "Outside model domain"
    at.select_slider(key="cp_flow_lpm").set_value(0.05).run()
    assert any("outlet ≤40°C" in c.value for c in at.caption)


def test_pins_recomputed_for_new_case_and_fixed_flow():
    at = app()
    at.button(key="cp_pin").click().run()
    at.select_slider(key="cp_flow_lpm").set_value(0.4).run()
    table = comparison_table(at)
    assert table.set_index("Design").loc["Pinned 1", "Flow (L/min)"] == 0.1
    at.selectbox(key="cp_case").set_value("higher_load").run()
    expected = evaluate_design(ColdPlateCase(heat_w=150), ColdPlateDesign(
        width_mm=0.8, depth_mm=1.8, web_mm=0.2, flow_lpm=0.1))
    table = comparison_table(at).set_index("Design")
    assert table.loc["Pinned 1", "Base proxy (°C)"] == round(expected["peak_base_c"], 4)
    at.selectbox(key="cp_case").set_value("fixed_flow_geometry").run()
    assert not at.exception
    assert at.select_slider(key="cp_flow_lpm").disabled
    assert comparison_table(at)["Flow (L/min)"].eq(0.2).all()
    at.button(key="cp_clear").click().run()
    assert len(comparison_table(at)) == 3


def test_recorded_views_switch_cases_seeds_and_budget(recorded):
    at = app()
    at.radio(key="cp_view").set_value("Recorded search").run()
    for experiment in recorded["metadata"]["experiments"]:
        at.selectbox(key="cp_case").set_value(experiment["case"]["name"])
        at.selectbox(key="cp_seed").set_value(22)
        at.slider(key="cp_budget").set_value(8).run()
        assert not at.exception
        assert at.metric[0].value == at.metric[1].value
        table = at.dataframe[0].value
        assert table.evaluations.eq(8).all()
        assert len(table) == 12
    at.checkbox(key="cp_show_failures").check().run()
    at.slider(key="cp_budget").set_value(32).run()
    assert not at.exception
    assert at.dataframe[0].value.evaluations.eq(32).all()
    at.radio(key="cp_view").set_value("Model & evidence").run()
    assert not at.exception
    assert any("No CFD" in item.value for item in at.info)
    at.radio(key="research_view").set_value("Data-center cooling").run()
    assert not at.exception
    assert at.title[0].value == "Cooling exploration"
    at.radio(key="research_view").set_value("Component design").run()
    assert not at.exception


def test_full_budget_reconstructs_recorded_summaries_and_pairs(recorded):
    for case_id in range(4):
        snap = budget_snapshot(recorded["search_trials"], case_id, 32)
        summary = recorded["search_summary"].query("case_id == @case_id")
        joined = snap.merge(summary, on=["seed", "method"])
        assert joined.pump_w.tolist() == pytest.approx(joined.best_pump_w.tolist())
        assert (joined.candidate_id == joined.best_candidate_id).all()
        expected = recorded["paired_comparison"].query("case_id == @case_id").surrogate_outcome.value_counts().to_dict()
        assert paired_outcomes(snap) == expected
        initial = budget_snapshot(recorded["search_trials"], case_id, 8)
        assert paired_outcomes(initial) == {"tie": 6}


def test_budget_never_looks_ahead_and_keeps_missing_results(recorded):
    trials = recorded["search_trials"].copy()
    trials.loc[trials.evaluation <= 8, "feasible"] = False
    early = budget_snapshot(trials, 0, 8)
    assert not early.found_feasible.any()
    assert early.pump_w.isna().all()
    assert paired_outcomes(early) == {"neither_feasible": 6}
    later = budget_snapshot(trials, 0, 32)
    assert later.found_feasible.all()


def test_every_grid_winner_matches_live_comparisons(recorded):
    for winner in recorded["winners"]:
        case = ColdPlateCase(**winner["case"])
        design = ColdPlateDesign(**winner["design"])
        frame = comparison_results(case, [("winner", design)])
        for key in ("peak_base_c", "pressure_pa", "pump_w", "thermal_resistance_k_w"):
            assert frame.iloc[0][key] == pytest.approx(winner["result"][key], rel=1e-12)
        assert frame.iloc[0].feasible
        assert frame.iloc[0].heat_w == case.heat_w
        assert frame.iloc[0].inlet_c == case.inlet_c


def test_geometry_draws_correct_count_and_does_not_show_invalid_shapes():
    case, design = ColdPlateCase(), ColdPlateDesign()
    result = evaluate_design(case, design)
    root = ET.fromstring(geometry_svg(case, design, result))
    channels = [r for r in root.iter("{http://www.w3.org/2000/svg}rect") if r.get("class") == "channel"]
    assert len(channels) == result["channel_count"] + 3
    assert float(channels[0].get("height")) == pytest.approx(design.width_mm * 5.4)
    invalid = ColdPlateDesign(width_mm=0.2, depth_mm=1.8)
    assert geometry_svg(case, invalid, evaluate_design(case, invalid)) is None


def test_loading_is_read_only_and_independent_of_working_directory(recorded, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    loaded = load_recorded_results()
    pd.testing.assert_frame_equal(loaded["grid"], recorded["grid"])
    assert not list(tmp_path.iterdir())
    with pytest.raises(OSError):
        load_recorded_results(tmp_path)
