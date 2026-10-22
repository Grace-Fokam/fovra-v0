import math

import numpy as np

from controllers import LearnedMPC, Thermostat
from evaluation import SimulationConfig, compare
from simulator import (
    MAX_HEATER_KW,
    STEP_HOURS,
    STEPS_PER_DAY,
    next_step,
    operating_conditions,
)
from train_model import train_world_model


def test_original_five_minute_physics_example():
    t, e = next_step(60.0, 20.0, 3.0, 8.0)
    assert math.isclose(t, 60.15)
    assert math.isclose(e, 8 * STEP_HOURS)


def test_command_is_clamped():
    _, high = next_step(60.0, 20.0, 3.0, 900)
    _, low = next_step(60.0, 20.0, 3.0, -100)
    assert math.isclose(high, MAX_HEATER_KW * STEP_HOURS)
    assert low == 0


def test_surge_is_observed_only_in_window():
    before = operating_conditions(9 * 12, 20, 3, "Production surge")
    during = operating_conditions(11 * 12, 20, 3, "Production surge")
    normal = operating_conditions(11 * 12, 20, 3, "Normal")
    assert math.isclose(before.process_kw, operating_conditions(9 * 12, 20, 3, "Normal").process_kw)
    assert math.isclose(during.process_kw - normal.process_kw, 2.5)


def test_degradation_wastes_heat_not_electricity():
    nominal_t, nominal_kwh = next_step(60, 20, 3, 8, 1.0)
    degraded_t, degraded_kwh = next_step(60, 20, 3, 8, 0.65)
    assert degraded_t < nominal_t
    assert nominal_kwh == degraded_kwh
    assert operating_conditions(11 * 12, 20, 3, "Heater degradation").heater_efficiency == 0.65


def test_train_predict_and_run_comparisons():
    model, mae = train_world_model()
    assert mae < 1e-8  # Expected because simulator is an exact linear equation.
    ctrl = LearnedMPC(model)
    assert ctrl.choose(60, 20, 3) in (0, 3, 6, 9, 12)

    cfg = SimulationConfig(20, 3, "Normal", "Thermostat")
    fovra, baseline, fstats, bstats = compare(cfg, model)
    assert len(fovra) == len(baseline) == STEPS_PER_DAY
    assert fstats["energy_kwh"] > 0
    assert bstats["energy_kwh"] > 0
    assert np.allclose(fovra["ambient_c"], baseline["ambient_c"])
    assert np.allclose(fovra["process_kw"], baseline["process_kw"])


def test_slider_and_scenarios_affect_results():
    model, _ = train_world_model()
    low, _, _, _ = compare(SimulationConfig(10, 2, "Normal", "Thermostat"), model)
    high, _, _, _ = compare(SimulationConfig(35, 6, "Normal", "Thermostat"), model)
    assert not np.allclose(low["temperature_c"], high["temperature_c"])

    normal, _, _, _ = compare(SimulationConfig(20, 3, "Normal", "Thermostat"), model)
    surge, _, _, _ = compare(SimulationConfig(20, 3, "Production surge", "Thermostat"), model)
    degraded, _, _, _ = compare(SimulationConfig(20, 3, "Heater degradation", "Thermostat"), model)
    assert not np.allclose(normal["temperature_c"], surge["temperature_c"])
    assert not np.allclose(normal["temperature_c"], degraded["temperature_c"])


def test_pi_baseline_is_supported():
    model, _ = train_world_model()
    a, b, fa, fb = compare(SimulationConfig(20, 3, "Normal", "PI controller"), model)
    assert len(a) == len(b) == STEPS_PER_DAY
    assert fa["energy_kwh"] >= 0 and fb["energy_kwh"] >= 0
