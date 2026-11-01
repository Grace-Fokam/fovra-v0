"""Independent physical identities, model guardrails, and search-budget integrity."""

from dataclasses import replace
import json
from math import pi, tanh

import numpy as np
import pandas as pd
import pytest

from cold_plate import ColdPlateCase, ColdPlateDesign, evaluate_design, rectangular_correlations
from cold_plate_search import INITIAL_SAMPLES, METHODS, best_verified, candidate_designs, run_search
from benchmark_cold_plate import pareto_flags, run_benchmark


@pytest.mark.parametrize("aspect", [0.1, 0.25, 0.5, 1.0])
def test_darcy_correlation_against_rectangular_duct_series(aspect):
    # Exact fully developed rectangular Poiseuille solution, independently of
    # the polynomial: Q = a*b^3/(12 mu L) * series_factor * dp, a >= b.
    factor = 1 - 192*aspect/pi**5*sum(
        tanh(n*pi/(2*aspect))/n**5 for n in range(1, 400, 2))
    expected_po = 96/(factor*(1+aspect)**2)
    po, _ = rectangular_correlations(aspect)
    assert po == pytest.approx(expected_po, rel=0.0007)


def test_square_and_parallel_plate_limits():
    po, nu = rectangular_correlations(1)
    assert po == pytest.approx(56.908, rel=0.0003)
    assert nu == pytest.approx(3.549285)
    po, nu = rectangular_correlations(1e-8)
    assert po == pytest.approx(96, rel=1e-7)
    assert nu == pytest.approx(8.235, rel=1e-7)
    with pytest.raises(ValueError):
        rectangular_correlations(2)


def test_mass_heat_work_and_unit_balances():
    case, d = ColdPlateCase(), ColdPlateDesign()
    r = evaluate_design(case, d)
    q = d.flow_lpm/60000
    assert r["feasible"]
    assert r["velocity_m_s"]*r["channel_count"]*d.width_mm*d.depth_mm/1e6 == pytest.approx(q)
    assert (r["outlet_c"]-case.inlet_c)*case.rho_kg_m3*q*case.cp_j_kgk == pytest.approx(case.heat_w+r["hydraulic_w"])
    assert r["pressure_pa"] == pytest.approx(r["friction_pressure_pa"]+r["minor_pressure_pa"])
    assert r["pump_w"]*case.pump_efficiency == pytest.approx(r["pressure_pa"]*q)
    assert r["pump_kwh"] == pytest.approx(r["pump_w"]*24/1000)
    assert r["pump_cost"] == pytest.approx(r["pump_kwh"]*case.electricity_per_kwh)
    assert r["heat_removed_kwh"] == pytest.approx(2.4)
    assert 0 < r["fin_efficiency"] <= 1
    assert r["peak_base_c"] > r["outlet_c"] > case.inlet_c


def test_laminar_flow_scalings_and_material_tradeoff():
    case, design = ColdPlateCase(), ColdPlateDesign()
    a = evaluate_design(case, design)
    b = evaluate_design(case, replace(design, flow_lpm=design.flow_lpm*2))
    assert b["friction_pressure_pa"] == pytest.approx(2*a["friction_pressure_pa"])
    assert b["minor_pressure_pa"] == pytest.approx(4*a["minor_pressure_pa"])
    assert b["peak_base_c"] < a["peak_base_c"]
    low_k = evaluate_design(case, replace(design, conductivity_w_mk=167))
    assert low_k["peak_base_c"] > a["peak_base_c"]
    assert low_k["pressure_pa"] == a["pressure_pa"]
    less_h = evaluate_design(replace(case, heat_transfer_multiplier=0.7), design)
    assert less_h["peak_base_c"] > a["peak_base_c"]


@pytest.mark.parametrize("kwargs,reason", [
    ({"width_mm": 0.1}, "minimum_feature"), ({"depth_mm": 0.2}, "channel_aspect"),
    ({"depth_mm": 3., "width_mm": 0.8, "base_mm": 2.}, "stack_height"),
    ({"width_mm": 50., "depth_mm": 50.}, "channel_count"),
])
def test_invalid_geometry_has_no_fabricated_results(kwargs, reason):
    r = evaluate_design(ColdPlateCase(), replace(ColdPlateDesign(), **kwargs))
    assert not r["geometry_ok"] and not r["feasible"]
    assert reason in r["violations"]
    assert "peak_base_c" not in r


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), True])
def test_invalid_design_numbers_raise(value):
    with pytest.raises(ValueError):
        evaluate_design(ColdPlateCase(), ColdPlateDesign(flow_lpm=value))


@pytest.mark.parametrize("kwargs", [{"cover_mm": 0.1}, {"edge_mm": 0.1}])
def test_cover_and_edge_must_also_respect_minimum_feature(kwargs):
    r = evaluate_design(replace(ColdPlateCase(), **kwargs), ColdPlateDesign())
    assert not r["geometry_ok"] and "minimum_feature" in r["violations"]


@pytest.mark.parametrize("kwargs", [{"pump_efficiency": 1.1}, {"minor_loss_k": -1},
                                      {"heat_w": float("nan")}, {"max_base_c": 20}])
def test_invalid_case_numbers_raise(kwargs):
    with pytest.raises(ValueError):
        evaluate_design(replace(ColdPlateCase(), **kwargs), ColdPlateDesign())


def test_outside_correlation_and_operating_limits_is_infeasible():
    fast = evaluate_design(ColdPlateCase(), ColdPlateDesign(flow_lpm=10))
    assert not fast["domain_ok"] and not fast["feasible"]
    assert "nonlaminar" in fast["violations"]
    assert "thermal_entry_at_outlet" in fast["violations"]
    for case, reason in [(ColdPlateCase(max_pressure_pa=1), "pressure_drop"),
                         (ColdPlateCase(max_pump_w=1e-6), "pump_power"),
                         (ColdPlateCase(max_base_c=26), "base_temperature"),
                         (ColdPlateCase(inlet_c=15), "constant_property_envelope")]:
        r = evaluate_design(case, ColdPlateDesign())
        assert not r["feasible"] and reason in r["violations"]


def test_candidate_geometry_really_changes_and_fits():
    designs = candidate_designs()
    assert len(designs) == len(set(designs)) == 660
    assert len({d.width_mm for d in designs}) == 4
    for d in designs:
        r = evaluate_design(ColdPlateCase(), d)
        assert r["geometry_ok"]
        assert r["active_width_mm"] <= 48+1e-10
        assert r["active_width_mm"] + d.width_mm+d.web_mm > 48


def test_equal_budget_shared_start_actual_calls_and_reproducibility():
    histories = []
    for method in METHODS:
        calls = []
        def evaluate(d):
            calls.append(d)
            return evaluate_design(ColdPlateCase(), d)
        rows = run_search(ColdPlateCase(), method, budget=14, seed=22, evaluator=evaluate)
        assert len(calls) == len(set(calls)) == len(rows) == 14
        assert [candidate_designs()[r["candidate_id"]] for r in rows] == calls
        again = run_search(ColdPlateCase(), method, budget=14, seed=22)
        for a, b in zip(rows, again):
            a.pop("elapsed_s")
            b.pop("elapsed_s")
            assert a == b
        histories.append(rows)
    assert [r["candidate_id"] for r in histories[0][:INITIAL_SAMPLES]] == [r["candidate_id"] for r in histories[1][:INITIAL_SAMPLES]]
    assert histories[1][12]["selection_policy"] == "random"


def test_no_feasible_result_never_falls_back_to_invalid_design():
    case = ColdPlateCase(max_base_c=25.01)
    for method in METHODS:
        rows = run_search(case, method, budget=10)
        assert best_verified(rows) is None
        assert all(r["best_pump_w_so_far"] is None for r in rows)


def test_geometry_failures_still_consume_queries():
    designs = [ColdPlateDesign(width_mm=0.01+i*0.001) for i in range(8)]
    rows = run_search(ColdPlateCase(), "surrogate", budget=8, designs=designs)
    assert len(rows) == 8
    assert not any(r["geometry_ok"] for r in rows)
    assert best_verified(rows) is None


@pytest.mark.parametrize("budget", [True, 2, 661, 8.5])
def test_invalid_budget(budget):
    with pytest.raises(ValueError):
        run_search(ColdPlateCase(), "surrogate", budget=budget)


def test_exhaustive_small_budget_finds_same_best_and_exports_counts(tmp_path):
    designs = [replace(ColdPlateDesign(), flow_lpm=x) for x in np.linspace(.1, .3, 10)]
    specs = [(ColdPlateCase(), designs)]
    frame = run_benchmark(tmp_path, specs=specs, seeds=(11,), budget=10)
    assert frame.relative_gap_to_grid.eq(0).all()
    assert frame.simulator_evaluations.eq(10).all()
    traces = pd.read_csv(tmp_path/"search_trials.csv")
    assert len(traces) == 20 and "elapsed_s" not in traces
    meta = json.loads((tmp_path/"metadata.json").read_text())
    assert meta["oracle_evaluations"] == 10 and meta["search_evaluations"] == 20
    assert meta["extra_sensitivity_evaluations"] == 5
    assert len(json.loads((tmp_path/"grid_winners.json").read_text())) == 1


def test_pareto_never_includes_infeasible_or_dominated():
    rows = [{"peak_base_c": t, "pump_w": p, "feasible": f}
            for t, p, f in [(30, 1, True), (31, 2, True), (35, .5, True), (20, .1, False)]]
    assert pareto_flags(rows) == [True, False, True, False]
