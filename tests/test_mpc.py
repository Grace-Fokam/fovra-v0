"""Independent optimizer checks, matched trials and observation-boundary tests."""

from itertools import product

import numpy as np
import pandas as pd
import pytest

import evaluation
from controllers import LearnedMPC, PhysicsMPC, make_controller
from evaluation import SimulationConfig, compare, merge_for_download, run_controller, summarize
from simulator import SCENARIOS, STEP_HOURS, next_step, operating_conditions
from train_model import train_world_model


@pytest.fixture(scope="module")
def model():
    return train_world_model()[0]


def test_nominal_physics_prediction_and_actuator_clipping():
    controller = PhysicsMPC()
    assert float(controller.predict_next_temperature(60, 20, 3, 8)) == pytest.approx(60.15)
    for power in (-100, 0, 3, 6, 9, 12, 900):
        assert controller.predict_next_temperature(61, 10, 5, power) == pytest.approx(
            next_step(61, 10, 5, power)[0]
        )
    # The baseline is usable without a trained ML artifact.
    assert isinstance(make_controller("Physics MPC"), PhysicsMPC)


def _reference_cost(plan, temperature, ambient, demand, previous):
    """Scalar oracle, independent of the vectorized optimizer implementation."""
    cost = 0.0
    for power in plan:
        temperature, electricity = next_step(temperature, ambient, demand, power)
        cost += electricity + 9 * (temperature - 60) ** 2
        cost += 500 * (max(58 - temperature, 0) ** 2 + max(temperature - 62, 0) ** 2)
        cost += 0.006 * (power - previous) ** 2
        previous = power
    return cost


@pytest.mark.parametrize("state", [(60, 20, 3, 0), (57, 10, 8.5, 12), (63, 35, 1, 6)])
def test_same_grid_cost_forecast_and_first_action_as_scalar_oracle(model, state):
    temperature, ambient, demand, previous = state
    expected_plans = np.array(list(product((0, 3, 6, 9, 12), repeat=4)))
    expected_costs = np.array([
        _reference_cost(plan, temperature, ambient, demand, previous)
        for plan in expected_plans
    ])
    for controller in (PhysicsMPC(), LearnedMPC(model)):
        np.testing.assert_array_equal(controller.plans, expected_plans)
        assert controller.plan_count == 625
        controller.previous_kw = previous
        scores = controller.score_plans(temperature, ambient, demand)
        np.testing.assert_allclose(scores, expected_costs, rtol=1e-10, atol=1e-10)
        assert controller.previous_kw == previous  # Scoring must not change state.
        action = controller.choose(temperature, ambient, demand)
        assert action == expected_plans[np.argmin(expected_costs), 0]
        assert controller.previous_kw == action


def test_predictor_sees_persistence_forecast_only():
    class RecordingModel:
        def __init__(self):
            self.inputs = []

        def predict(self, x):
            self.inputs.append(x.copy())
            return np.zeros(len(x))

    predictor = RecordingModel()
    LearnedMPC(predictor).choose(59.8, 17.5, 4.2)
    assert len(predictor.inputs) == 4
    for x in predictor.inputs:
        assert x.shape == (625, 4)
        np.testing.assert_array_equal(x[:, 1], 17.5)
        np.testing.assert_array_equal(x[:, 2], 4.2)


@pytest.mark.parametrize("name", ["Physics MPC", "Fovra"])
def test_runner_exposes_only_current_observations(monkeypatch, model, name):
    controller = make_controller(name, model)
    choose = controller.choose
    conditions_seen = []
    observations = []

    def conditions(step, *args):
        assert step == len(conditions_seen)
        result = operating_conditions(step, *args)
        conditions_seen.append(result)
        return result

    def observe(*args, **kwargs):
        # No future conditions generated, no timestamp, efficiency or scenario
        # passed into either optimizer. Only three current scalar observations.
        assert len(conditions_seen) == len(observations) + 1
        assert len(args) == 3 and not kwargs
        assert args[1:] == (conditions_seen[-1].ambient_c, conditions_seen[-1].process_kw)
        observations.append(args)
        return choose(*args)

    controller.choose = observe
    monkeypatch.setattr(evaluation, "make_controller", lambda *args: controller)
    monkeypatch.setattr(evaluation, "operating_conditions", conditions)
    result = run_controller(name, SimulationConfig(scenario="Heater degradation"), model)
    np.testing.assert_allclose(np.array(observations)[:, 0], result.temperature_before_c)
    assert conditions_seen[-1].heater_efficiency == 0.65


@pytest.mark.parametrize("name", ["Physics MPC", "Fovra"])
def test_hidden_degradation_and_future_surge_are_not_anticipated(model, name):
    normal = run_controller(name, SimulationConfig(), model)
    surge = run_controller(name, SimulationConfig(scenario="Production surge"), model)
    degraded = run_controller(name, SimulationConfig(scenario="Heater degradation"), model)
    # Step 120 is the first affected transition (10:00 to 10:05).
    np.testing.assert_array_equal(normal.heater_kw.iloc[:120], surge.heater_kw.iloc[:120])
    np.testing.assert_array_equal(normal.heater_kw.iloc[:121], degraded.heater_kw.iloc[:121])
    assert degraded.prediction_error_c.iloc[120] < -0.1
    expected_error = -0.35 * degraded.heater_kw.iloc[120:] * STEP_HOURS
    np.testing.assert_allclose(degraded.prediction_error_c.iloc[120:], expected_error, atol=1e-12)


@pytest.mark.parametrize("scenario", SCENARIOS)
@pytest.mark.parametrize("ambient,demand", [(20, 3), (10, 6), (35, 1)])
def test_matched_mpcs_recover_same_closed_loop_behavior(model, scenario, ambient, demand):
    fovra, physics, fm, pm = compare(SimulationConfig(ambient, demand, scenario, "Physics MPC"), model)
    # Do not equate timing: it is a measured, nondeterministic quantity.
    for field in ("heater_kw", "temperature_c", "ambient_c", "process_kw", "heater_efficiency"):
        np.testing.assert_array_equal(fovra[field], physics[field])
    assert fm["energy_kwh"] == pm["energy_kwh"]
    assert fm["minutes_outside"] == pm["minutes_outside"]
    assert fm["heater_adjustments"] == pm["heater_adjustments"]
    for frame in (fovra, physics):
        np.testing.assert_allclose(frame.interval_energy_kwh, frame.heater_kw * STEP_HOURS)
        assert np.isfinite(frame.decision_ms).all() and frame.decision_ms.ge(0).all()
    exported = merge_for_download(fovra, physics, "Physics MPC")
    np.testing.assert_array_equal(exported.baseline_predicted_next_temperature_c, physics.predicted_next_c)
    np.testing.assert_array_equal(exported.baseline_decision_ms, physics.decision_ms)


@pytest.mark.parametrize("seed", [20261021, 20261022])
def test_nominal_equivalence_is_not_specific_to_one_training_seed(seed):
    model, _ = train_world_model(seed)
    rng = np.random.default_rng(42)
    states = rng.uniform([54, 8, 0, 0], [66, 40, 9, 12], (100, 4))
    learned, physics = LearnedMPC(model), PhysicsMPC()
    np.testing.assert_allclose(learned.predict_delta(*states.T), physics.predict_delta(*states.T), atol=1e-12)


def test_metric_definitions_with_known_trajectory():
    frame = pd.DataFrame({
        "temperature_c": [57., 60., 63.],
        "heater_kw": [0., 3., 3.],
        "interval_energy_kwh": [0., .25, .25],
        "prediction_error_c": [-1., 0., 1.],
        "decision_ms": [1., 2., 3.],
    })
    result = summarize(frame)
    assert result["energy_kwh"] == .5
    assert result["minutes_outside"] == 10
    assert result["target_rmse_c"] == pytest.approx(np.sqrt(6))
    assert result["temperature_std_c"] == pytest.approx(np.sqrt(6))
    assert result["max_violation_c"] == 1
    assert result["violation_degree_minutes"] == 10
    assert result["heater_adjustments"] == 1
    assert result["heater_total_variation_kw"] == 3
    assert result["one_step_prediction_mae_c"] == pytest.approx(2/3)
    assert result["decision_mean_ms"] == 2
    assert result["decision_p95_ms"] == pytest.approx(2.9)
    assert result["decision_total_ms"] == 6


def test_original_default_learned_results_are_preserved(model):
    for scenario, expected_kwh in zip(SCENARIOS, [148.75, 158.75, 194.0]):
        frame = run_controller("Fovra", SimulationConfig(scenario=scenario), model)
        assert summarize(frame)["energy_kwh"] == expected_kwh
