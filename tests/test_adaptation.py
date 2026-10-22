import numpy as np
import pytest

from adaptive_mpc import RollingMPC
from benchmark_adaptation import (EQUIPMENT, Equipment, capacity_margin,
                                  recovery_minutes, run_case)
from controllers import PhysicsMPC


def test_nominal_models_use_same_optimizer_and_predictions():
    physics = PhysicsMPC()
    for controller in (RollingMPC(), RollingMPC(physics=True)):
        np.testing.assert_array_equal(controller.plans, physics.plans)
        np.testing.assert_allclose(controller.score_plans(60., 20., 2.),
                                   physics.score_plans(60., 20., 2.), atol=1e-10)


@pytest.mark.parametrize('physics', [False, True])
def test_identifies_unseen_equipment_from_completed_transitions(physics):
    controller = RollingMPC(physics=physics)
    plant = Equipment('test', .7, .12, .72)
    rng = np.random.default_rng(9)
    for _ in range(48):
        t, a, d, p = rng.uniform([54.,10.,0.,0.], [66.,30.,4.,12.])
        controller.observe(t,a,d,p,t+plant.delta(t,a,d,p))
    x = rng.uniform([54.,10.,0.,0.], [66.,30.,4.,12.], (50,4))
    np.testing.assert_allclose(controller.predict_delta(*x.T), plant.delta(*x.T), atol=1e-5)
    assert len(controller.window) == 48


def test_updates_are_causal_and_old_observations_expire():
    controller = RollingMPC(window=6)
    before = controller.coef.copy()
    controller.choose(60.,20.,2.)
    np.testing.assert_array_equal(controller.coef, before)
    for i in range(10):
        controller.observe(60.,20.,2.,float(i),60.+i*.01)
    assert len(controller.window) == 6
    assert controller.window[0][0][3] == 4.


def test_suite_is_feasible_even_after_degradation():
    for equipment in EQUIPMENT:
        degraded = Equipment('degraded', equipment.capacity, equipment.loss, equipment.efficiency*.75)
        assert capacity_margin(degraded, 19., 2.4) > 0
        # At zero power, upper boundary cools, and max power warms lower boundary.
        assert degraded.delta(62., 21., 1.6, 0.) < 0
        assert degraded.delta(58., 19., 2.4, 12.) > 0
    with pytest.raises(ValueError):
        Equipment('invalid', 0., .1, 1.)


def test_recovery_handles_delayed_and_censored_cases():
    assert recovery_minutes([57.,57.,60.,60.,60.], change=0, consecutive=3) == 10
    assert recovery_minutes([57.]*5, change=0, consecutive=3) is None
    assert recovery_minutes([60.]*5, change=0, consecutive=3) == 0


def test_short_experiment_is_reproducible_and_reports_all_controllers():
    first = run_case(EQUIPMENT[1], False, 11, steps=12)
    second = run_case(EQUIPMENT[1], False, 11, steps=12)
    assert first == second
    rows, summaries = first
    assert len(rows) == 4*12
    assert len(summaries) == 4
    assert all(r['power_kw'] in (0.,3.,6.,9.,12.) for r in rows)
    assert all(r['prediction_abs_error_c'] >= 0 for r in rows)
    for step in range(12):
        matched = [r for r in rows if r['step'] == step]
        assert len({r['ambient_c'] for r in matched}) == 1
        assert len({r['process_demand_kw'] for r in matched}) == 1
    for summary in summaries:
        own = [r for r in rows if r['controller'] == summary['controller']]
        assert summary['energy_kwh'] == pytest.approx(sum(r['power_kw']/12 for r in own))


def test_model_recovery_metric_is_censored_and_requires_full_hour():
    from benchmark_adaptation import model_recovery_minutes
    assert model_recovery_minutes([.1]*2+[.01]*12, change=0) == 10
    assert model_recovery_minutes([.01]*11, change=0) is None


@pytest.mark.parametrize('physics', [False, True])
def test_estimator_tracks_efficiency_change_after_window_replacement(physics):
    controller = RollingMPC(physics=physics)
    rng = np.random.default_rng(3)
    for efficiency in (1., .65):
        plant = Equipment('changing', 1., .08, efficiency)
        for _ in range(48):
            t,a,d,p = rng.uniform([54.,10.,0.,0.],[66.,30.,4.,12.])
            controller.observe(t,a,d,p,t+plant.delta(t,a,d,p))
        np.testing.assert_allclose(controller.predict_delta(60.,20.,2.,12.),
                                   plant.delta(60.,20.,2.,12.), atol=1e-5)


def test_infeasible_cases_are_rejected():
    with pytest.raises(ValueError, match='capacity-limited'):
        run_case(Equipment('insufficient',1.,.3,.4), False, 11, steps=1)
