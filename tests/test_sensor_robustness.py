import json

import numpy as np
import pandas as pd
import pytest

from adaptive_mpc import RollingMPC
from benchmark_adaptation import EQUIPMENT, model_recovery_minutes, run_case as original_case
import benchmark_sensor_robustness as bench


@pytest.mark.parametrize('sigma,bias', [(-1., 0.), (np.nan, 0.), (np.inf, 0.), (0., np.inf)])
def test_sensor_validation(sigma, bias):
    with pytest.raises(ValueError):
        bench.Sensor('invalid', sigma, bias)


def test_sensor_stream_reproducible_independent_and_prefix_stable():
    sensor = bench.Sensor('test', .5, 1.)
    first = bench.sensor_errors(sensor, 11, 30)
    np.testing.assert_array_equal(first, bench.sensor_errors(sensor, 11, 30))
    np.testing.assert_array_equal(first[:11], bench.sensor_errors(sensor, 11, 10))
    assert not np.array_equal(first, bench.sensor_errors(sensor, 22, 30))
    np.testing.assert_allclose(first - 1., .5 * bench.sensor_errors(bench.Sensor('unit', 1.), 11, 30))
    before = bench.exogenous_series(11, 30)
    bench.sensor_errors(sensor, 11, 100)
    for a, b in zip(before, bench.exogenous_series(11, 30)):
        np.testing.assert_array_equal(a, b)


def test_sensor_distribution_and_differenced_observation_noise():
    errors = bench.sensor_errors(bench.Sensor('test', .5, 1.), 11, 20000)
    assert errors.mean() == pytest.approx(1., abs=.015)
    assert errors.std() == pytest.approx(.5, abs=.015)
    differences = np.diff(errors)
    assert differences.std() == pytest.approx(np.sqrt(2) * .5, abs=.02)
    # Shared endpoint errors create negative lag-one correlation in delta targets.
    assert np.corrcoef(differences[:-1], differences[1:])[0, 1] == pytest.approx(-.5, abs=.025)


def test_clean_control_reproduces_original_actions_and_physical_states():
    original, _ = original_case(EQUIPMENT[1], False, 11, steps=16)
    new, _ = bench.run_case(EQUIPMENT[1], False, 11, bench.Sensor('clean'), steps=16)
    for old, row in zip(original, new):
        assert row['controller'] == old['controller']
        assert row['power_kw'] == old['power_kw']
        assert row['next_true_temperature_c'] == old['temperature_c']
        assert row['next_observed_temperature_c'] == old['temperature_c']
        assert abs(row['forecast_true_error_c']) == pytest.approx(old['prediction_abs_error_c'])


def test_case_reproducibility_and_matched_protocol():
    args = (EQUIPMENT[1], True, 11, bench.Sensor('noisy', .5, -1.))
    first = bench.run_case(*args, steps=24, change_step=12)
    assert first == bench.run_case(*args, steps=24, change_step=12)
    rows, summaries = first
    assert len(rows) == 4 * 24
    assert len(summaries) == 4
    for step in range(24):
        matched = [r for r in rows if r['step'] == step]
        for key in ('sensor_error_c', 'next_sensor_error_c', 'ambient_c', 'process_demand_kw'):
            assert len({r[key] for r in matched}) == 1
    for name in {r['controller'] for r in rows}:
        own = [r for r in rows if r['controller'] == name]
        for a, b in zip(own, own[1:]):
            assert a['next_observed_temperature_c'] == b['observed_temperature_c']
            assert a['next_sensor_error_c'] == b['sensor_error_c']


def test_sensor_errors_never_enter_physics_with_fixed_actions(monkeypatch):
    class ConstantController:
        def choose(self, *args):
            return 6.

        def predict_delta(self, temp, *args):
            return np.zeros_like(temp)

    monkeypatch.setattr(bench, 'make_controllers', lambda seed: {'constant': ConstantController()})
    clean, _ = bench.run_case(EQUIPMENT[0], True, 11, bench.Sensor('clean'), 20, 10)
    noisy, _ = bench.run_case(EQUIPMENT[0], True, 11, bench.Sensor('test', 1., 2.), 20, 10)
    for a, b in zip(clean, noisy):
        for key in ('true_temperature_c', 'next_true_temperature_c', 'power_kw',
                    'ambient_c', 'process_demand_kw'):
            assert a[key] == b[key]
        assert a['observed_temperature_c'] != b['observed_temperature_c']


@pytest.mark.parametrize('physics', [False, True])
def test_only_completed_noisy_transitions_reach_updates(monkeypatch, physics):
    class Spy(RollingMPC):
        def __init__(self):
            super().__init__(physics=physics)
            self.seen = []
            self.coefficients_at_choose = []
            self.coefficients_after_update = []

        def choose(self, *args):
            before = self.coef.copy()
            result = super().choose(*args)
            np.testing.assert_array_equal(before, self.coef)
            self.coefficients_at_choose.append(before)
            return result

        def observe(self, *args):
            self.seen.append(args)
            super().observe(*args)
            self.coefficients_after_update.append(self.coef.copy())

    controller = Spy()
    monkeypatch.setattr(bench, 'make_controllers', lambda seed: {'spy': controller})
    rows, _ = bench.run_case(EQUIPMENT[1], True, 11, bench.Sensor('noisy', .5, 1.), 20, 10)
    for step, (row, observed) in enumerate(zip(rows, controller.seen)):
        expected = (row['observed_temperature_c'], row['ambient_c'],
                    row['process_demand_kw'], row['power_kw'], row['next_observed_temperature_c'])
        assert observed == expected
        assert observed[0] != row['true_temperature_c']
        assert observed[-1] != row['next_true_temperature_c']
        # Forecast was scored with coefficients BEFORE this transition's fit.
        features = controller.features(*expected[:-1])
        forecast = expected[0] + features @ controller.coefficients_at_choose[step]
        assert row['predicted_next_temperature_c'] == pytest.approx(forecast)
        if step:
            np.testing.assert_array_equal(controller.coefficients_at_choose[step],
                                          controller.coefficients_after_update[step - 1])
    for (features, target), observed in zip(controller.window, controller.seen):
        np.testing.assert_array_equal(features, controller.features(*observed[:-1]))
        assert target == observed[-1] - observed[0]
    assert not np.array_equal(controller.prior, controller.coef)


def test_future_observations_cannot_change_past_actions_or_models(monkeypatch):
    args = (EQUIPMENT[1], True, 11, bench.Sensor('noisy', .5))
    original, _ = bench.run_case(*args, steps=24, change_step=12)
    real_errors = bench.sensor_errors

    def changed_future(sensor, seed, steps):
        errors = real_errors(sensor, seed, steps)
        errors[16:] += 5.
        return errors

    monkeypatch.setattr(bench, 'sensor_errors', changed_future)
    changed, _ = bench.run_case(*args, steps=24, change_step=12)
    for a, b in zip(original, changed):
        if a['step'] < 15:
            assert a == b
        if a['step'] == 15:
            # Next sensor reading differs, but this action/prediction/model precedes it.
            for key in ('power_kw', 'predicted_next_temperature_c', 'probe_mae_c'):
                assert a[key] == b[key]


def test_fixed_models_do_not_change_after_noisy_rollout(monkeypatch):
    controllers = bench.make_controllers(11)
    before = {name: c.predict_delta(bench.PROBE_T, 20., 2., bench.PROBE_P).copy()
              for name, c in controllers.items()}
    monkeypatch.setattr(bench, 'make_controllers', lambda seed: controllers)
    bench.run_case(EQUIPMENT[1], True, 11, bench.Sensor('noisy', .5), 20, 10)
    for name in ('fixed_learned', 'fixed_physics'):
        np.testing.assert_array_equal(before[name], controllers[name].predict_delta(
            bench.PROBE_T, 20., 2., bench.PROBE_P))


def test_metrics_use_true_states_and_distinguish_forecast_targets():
    rows = [dict(next_true_temperature_c=t, next_observed_temperature_c=60.,
                 forecast_true_error_c=2., forecast_observed_error_c=.5,
                 probe_mae_c=.1, power_kw=6.) for t in [57., 58., 62., 63.]]
    result = bench.summarize(rows, True, 0)
    assert result['target_rmse_c'] == pytest.approx(np.sqrt(6.5))
    assert result['energy_kwh'] == 2.
    assert result['violation_minutes'] == 10
    assert result['violation_degree_minutes'] == 10.
    assert result['max_excursion_c'] == 1.
    assert result['forecast_true_rmse_c'] == 2.
    assert result['forecast_observed_rmse_c'] == .5
    assert result['model_recovery_minutes'] is None
    assert result['model_recovery_status'] == 'censored'
    assert result['final_hour_probe_mae_c'] is None


def test_recovery_requires_full_hour_and_keeps_censoring_explicit():
    assert model_recovery_minutes([.1] * 2 + [.01] * 12, change=0) == 10
    assert model_recovery_minutes([.01] * 11, change=0) is None
    rows = [dict(next_true_temperature_c=60., forecast_true_error_c=0.,
                 forecast_observed_error_c=0., probe_mae_c=.01, power_kw=6.)] * 12
    assert bench.summarize(rows, True, 0)['model_recovery_status'] == 'recovered'
    assert bench.summarize(rows, False, 0)['model_recovery_status'] == 'not_applicable'


def test_full_artifacts_are_reproducible_and_pair_by_case(tmp_path):
    sensors = [bench.Sensor('clean'), bench.Sensor('noise', .5)]
    a, b = tmp_path / 'a', tmp_path / 'b'
    first = bench.run_benchmark(a, [11], sensors, steps=8, change_step=4)
    second = bench.run_benchmark(b, [11], sensors, steps=8, change_step=4)
    pd.testing.assert_frame_equal(first, second)
    for path in a.iterdir():
        assert path.read_bytes() == (b / path.name).read_bytes()
    metadata = json.loads((a / 'metadata.json').read_text())
    assert metadata['paired_cases'] == 12
    assert metadata['controller_runs'] == 48
    for name, digest in metadata['artifact_sha256'].items():
        assert bench._sha256(a / name) == digest
    pairs = pd.read_csv(a / 'paired.csv')
    assert len(pairs) == 48
    assert not any('recovery_minutes_difference' in c for c in pairs.columns)
    indexed = first.set_index(bench.CASE_KEYS + ['controller'])
    for _, row in pairs.iterrows():
        left, right = row['contrast'].split('_minus_')
        key = tuple(row[k] for k in bench.CASE_KEYS)
        expected = indexed.loc[key + (left,), 'energy_kwh'] - indexed.loc[key + (right,), 'energy_kwh']
        assert row['energy_kwh_difference'] == pytest.approx(expected)
    effects = bench.noise_effects(first)
    for _, row in effects.iterrows():
        key = (row.equipment, row.degradation, row.seed)
        expected = (indexed.loc[key + (row.sensor, row.controller), 'target_rmse_c']
                    - indexed.loc[key + ('clean', row.controller), 'target_rmse_c'])
        assert row.target_rmse_c_minus_clean == pytest.approx(expected)


def test_original_output_locations_are_protected():
    from pathlib import Path
    root = Path(bench.__file__).parent
    for relative in ('results/adaptation', 'results/mpc_comparison/subdir'):
        with pytest.raises(ValueError, match='original experiment'):
            bench.run_benchmark(root / relative)


@pytest.mark.parametrize('seeds,sensors,steps,change', [
    ([], [bench.Sensor('clean')], 8, 4),
    ([11, 11], [bench.Sensor('clean')], 8, 4),
    ([-1], [bench.Sensor('clean')], 8, 4),
    ([11], [bench.Sensor('noise', .5)], 8, 4),
    ([11], [bench.Sensor('clean')], 8, 8),
])
def test_invalid_protocols_are_rejected(tmp_path, seeds, sensors, steps, change):
    with pytest.raises(ValueError):
        bench.run_benchmark(tmp_path, seeds, sensors, steps, change)
