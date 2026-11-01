"""Physical accounting, matched conditions, feasibility, and search integrity."""

import json

import numpy as np
import pandas as pd
import pytest

from cooling import (
    CAPACITY_KWH_PER_C, CLIMATES, CYCLES_OF_CONCENTRATION, LATENT_KWH_PER_L,
    LIMIT_C, MODES, STEP_HOURS, TARGET_C, CoolingCase, CoolingDesign,
    advance_temperature, compare_cooling, evaluate_design, pareto_mask, simulate_cooling,
    summarize_cooling,
)
from cooling_search import METHODS, best_verified, candidate_designs, compare_search, run_search


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("climate", CLIMATES)
def test_heat_and_electricity_balance(mode, climate):
    frame = simulate_cooling(CoolingCase(climate=climate, surge=True), CoolingDesign(mode))
    stored = CAPACITY_KWH_PER_C * (frame.coolant_c - frame.temperature_before_c)
    input_heat = (frame.it_kw + frame.pump_kw) * STEP_HOURS
    removed_heat = frame.heat_rejected_kw * STEP_HOURS
    np.testing.assert_allclose(stored, input_heat - removed_heat, atol=1e-11)
    np.testing.assert_allclose(frame.cooling_kwh, (frame.pump_kw + frame.fan_kw) * STEP_HOURS)
    assert frame.heat_rejected_kw.ge(0).all()
    assert frame.fan_fraction.between(0, 1).all()
    assert np.isfinite(frame.select_dtypes(include="number")).all().all()
    summary = summarize_cooling(frame, CoolingCase(climate=climate, surge=True), CoolingDesign(mode))
    # Whole five-minute intervals must not lose a minute to float truncation.
    expected_intervals = ((frame.temperature_before_c > LIMIT_C + 1e-8)
                          | (frame.coolant_c > LIMIT_C + 1e-8)).sum()
    assert summary["over_limit_minutes"] == 5 * expected_intervals


@pytest.mark.parametrize("temp,sink,heat,ua", [(32, 20, 80, 12), (20, 35, 100, 24), (32, 20, 0, 12)])
def test_exact_temperature_step_and_no_overshoot(temp, sink, heat, ua):
    end, removed = advance_temperature(temp, sink, heat, ua, hours=2)
    halfway, first_heat = advance_temperature(temp, sink, heat, ua, hours=1)
    subdivided, second_heat = advance_temperature(halfway, sink, heat, ua, hours=1)
    assert end == pytest.approx(subdivided)
    assert removed * 2 == pytest.approx(first_heat + second_heat)
    assert end >= min(temp, sink)
    assert advance_temperature(32, 40, 0, 12) == (32, 0)
    assert advance_temperature(32, 20, 60, 0)[0] == pytest.approx(33)


def test_matched_workload_and_overheating_are_visible():
    summary, trace = compare_cooling(CoolingCase(surge=True))
    dry, wet = [trace[trace["mode"] == mode].reset_index(drop=True) for mode in MODES]
    pd.testing.assert_frame_equal(dry[["it_kw", "dry_bulb_c", "wet_bulb_c"]],
                                  wet[["it_kw", "dry_bulb_c", "wet_bulb_c"]])
    assert summary.it_kwh.nunique() == 1
    assert dry.coolant_c.max() > LIMIT_C
    assert not summary.iloc[0].thermal_ok
    assert summary.iloc[0].over_limit_minutes > 0
    assert summary.iloc[0].makeup_l == 0
    assert wet.makeup_l.sum() > 0


def test_water_cost_and_carbon_boundaries():
    case = CoolingCase(carbon_kg_per_kwh=0.25, electricity_per_kwh=0.2, water_per_m3=3)
    design = CoolingDesign("Evaporative assist")
    frame = simulate_cooling(case, design)
    np.testing.assert_allclose(frame.evaporated_l,
                              frame.heat_rejected_kw * STEP_HOURS / LATENT_KWH_PER_L * frame.wet_active)
    np.testing.assert_allclose(frame.blowdown_l, frame.evaporated_l / (CYCLES_OF_CONCENTRATION - 1))
    np.testing.assert_allclose(frame.makeup_l, frame.blowdown_l + frame.evaporated_l)
    result = evaluate_design(case, design)
    assert result["cooling_carbon_kg"] == pytest.approx(result["cooling_kwh"] * 0.25)
    assert result["cooling_utility_cost"] == pytest.approx(result["cooling_kwh"] * 0.2 + result["makeup_l"] / 1000 * 3)
    assert result["stored_heat_kwh"] == pytest.approx(CAPACITY_KWH_PER_C * (frame.coolant_c.iloc[-1] - TARGET_C))


def test_cool_climate_uses_dry_mode_for_both_options():
    summary, traces = compare_cooling(CoolingCase(climate="Cool"))
    assert summary.makeup_l.eq(0).all()
    assert summary.thermal_ok.all()
    assert summary.cooling_kwh.nunique() == 1
    assert not traces.wet_active.any()


def test_pareto_excludes_overheated_cheaper_design():
    frame = pd.DataFrame({"cooling_kwh": [1, 3, 2, 4], "makeup_l": [0, 0, 2, 3],
                          "thermal_ok": [False, True, True, True]})
    assert pareto_mask(frame).tolist() == [False, True, True, False]


def test_equal_budget_shared_start_and_verified_outputs():
    case = CoolingCase()
    trials = compare_search(case, budget=8, water_budget_l=4000, seed=22)
    random, ai = [trials[trials.method == method] for method in METHODS]
    assert len(random) == len(ai) == 8
    assert random.candidate_id.nunique() == ai.candidate_id.nunique() == 8
    assert random.candidate_id.iloc[:6].tolist() == ai.candidate_id.iloc[:6].tolist()
    for row in ai.itertuples():
        verified = evaluate_design(case, candidate_designs()[row.candidate_id])
        assert row.cooling_kwh == verified["cooling_kwh"]
        assert row.makeup_l == verified["makeup_l"]
        assert row.thermal_ok == verified["thermal_ok"]
    best = best_verified(trials, 4000)
    if best:
        assert best["thermal_ok"] and best["makeup_l"] <= 4000
    pd.testing.assert_frame_equal(ai.reset_index(drop=True), run_search(case, METHODS[1], 8, 4000, 22))


def test_impossible_water_budget_does_not_manufacture_a_winner():
    results = compare_search(CoolingCase(), budget=8, water_budget_l=0)
    assert best_verified(results, 0) is None


def test_invalid_inputs_rejected():
    for kwargs in ({"load_kw": float("nan")}, {"carbon_kg_per_kwh": -1}, {"climate": "unknown"}):
        with pytest.raises(ValueError):
            CoolingCase(**kwargs)
    with pytest.raises(ValueError):
        CoolingDesign(size=0)
    with pytest.raises(ValueError):
        run_search(CoolingCase(), METHODS[0], budget=36)


def test_offline_benchmark_keeps_oracle_separate_and_exports(tmp_path):
    from benchmark_cooling import run_benchmark
    summary = run_benchmark(tmp_path, cases=[CoolingCase(climate="Cool")], seeds=[11], budget=6)
    trials = pd.read_csv(tmp_path / "search_trials.csv")
    assert len(pd.read_csv(tmp_path / "grid.csv")) == 35
    assert len(trials) == 12
    assert summary.simulations_observed.eq(6).all()
    assert summary.gap_to_grid_kwh.ge(-1e-9).all()
    metadata = json.loads((tmp_path / "metadata.json").read_text())
    assert metadata["budget"] == 6
    assert len(metadata["source_sha256"]) == 3
