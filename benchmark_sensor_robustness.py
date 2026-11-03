"""Matched sensor-noise experiments, separate from the original adaptation suite.

Only the evaluation harness sees latent temperature or sensor errors. Controllers
receive y[t] = x[t] + bias + sigma*z[t], and learn from completed (y[t], y[t+1])
transitions. No filtering, bias correction, or estimator retuning is introduced.
"""

import argparse
from dataclasses import asdict, dataclass, replace
import gzip
import hashlib
import io
import json
from pathlib import Path
import platform

import numpy as np
import pandas as pd
import scipy
import sklearn
from threadpoolctl import threadpool_limits

from adaptive_mpc import RollingMPC
from benchmark_adaptation import (
    CHANGE_STEP, EQUIPMENT, STEPS, capacity_margin, model_recovery_minutes,
)
from controllers import LearnedMPC, PhysicsMPC
from simulator import (
    MAX_SAFE_TEMP_C, MIN_SAFE_TEMP_C, START_TEMP_C, STEP_HOURS,
    STEP_MINUTES, TARGET_TEMP_C,
)
from train_model import train_world_model

BASE_COMMIT = '2c8b2d4c9ad1455cfc801cb9ba21f2680ae6811e'
SEEDS = (11, 22, 33)
SENSOR_STREAM = 0x53454E53
RECOVERY_THRESHOLD_C = .02
RECOVERY_CONSECUTIVE = 12
PROBE_T, PROBE_P = (x.ravel() for x in np.meshgrid(
    [58., 60., 62.], [0., 3., 6., 9., 12.]))
CASE_KEYS = ['equipment', 'degradation', 'seed', 'sensor']
METRICS = (
    'target_rmse_c', 'energy_kwh', 'violation_minutes',
    'violation_degree_minutes', 'max_excursion_c',
    'forecast_true_rmse_c', 'forecast_observed_rmse_c',
    'probe_mae_c', 'post_change_probe_mae_c', 'final_hour_probe_mae_c',
)
CONTRASTS = (
    ('adaptive_learned', 'adaptive_physics'),
    ('adaptive_learned', 'fixed_learned'),
    ('adaptive_physics', 'fixed_physics'),
    ('fixed_learned', 'fixed_physics'),
)


@dataclass(frozen=True)
class Sensor:
    name: str
    noise_std_c: float = 0.
    bias_c: float = 0.

    def __post_init__(self):
        if (not self.name or not np.isfinite(self.noise_std_c)
                or self.noise_std_c < 0 or not np.isfinite(self.bias_c)):
            raise ValueError('sensor needs a name, finite bias and nonnegative finite noise')


# Illustrative stress levels, not specifications of any industrial sensor.
SENSORS = (
    Sensor('clean'), Sensor('noise_0p1', .1), Sensor('noise_0p5', .5),
    Sensor('noise_1p0', 1.), Sensor('bias_plus_1', bias_c=1.),
    Sensor('bias_minus_1', bias_c=-1.),
    Sensor('noise_0p5_bias_plus_1', .5, 1.),
    Sensor('noise_0p5_bias_minus_1', .5, -1.),
)


def exogenous_series(seed, steps):
    """Retain the original physical disturbances, independent of sensor draws."""
    rng = np.random.default_rng(seed)
    time = np.arange(steps)
    ambient = 20 + np.sin(time * 2 * np.pi / 288)
    demand = 2 + .3 * np.sin(time * 2 * np.pi / 72) + rng.uniform(-.1, .1, steps)
    return ambient, demand


def sensor_errors(sensor, seed, steps):
    """One sample per state, including x[0] and x[steps].

    A separate PCG64 stream cannot perturb process demand or training data.
    Common z draws are reused across controllers and scaled across noise levels.
    """
    rng = np.random.default_rng(np.random.SeedSequence([seed, SENSOR_STREAM]))
    return sensor.bias_c + sensor.noise_std_c * rng.standard_normal(steps + 1)


def make_controllers(seed):
    # Same clean nominal commissioning/training assumptions as the original suite.
    # Degraded/unseen equipment, future observations and sensor parameters are hidden.
    model, _ = train_world_model(seed)
    return {
        'fixed_learned': LearnedMPC(model), 'fixed_physics': PhysicsMPC(),
        'adaptive_learned': RollingMPC(),
        'adaptive_physics': RollingMPC(physics=True),
    }


def summarize(rows, degradation, change_step):
    temperature = np.array([r['next_true_temperature_c'] for r in rows])
    excursion = (np.maximum(MIN_SAFE_TEMP_C - temperature, 0.)
                 + np.maximum(temperature - MAX_SAFE_TEMP_C, 0.))
    probes = np.array([r['probe_mae_c'] for r in rows])
    recovery = (model_recovery_minutes(probes, change=change_step,
                                      threshold=RECOVERY_THRESHOLD_C,
                                      consecutive=RECOVERY_CONSECUTIVE)
                if degradation else None)
    return {
        'target_rmse_c': float(np.sqrt(np.mean((temperature - TARGET_TEMP_C)**2))),
        'energy_kwh': sum(r['power_kw'] * STEP_HOURS for r in rows),
        'violation_minutes': int(np.count_nonzero(excursion) * STEP_MINUTES),
        'violation_degree_minutes': float(excursion.sum() * STEP_MINUTES),
        'max_excursion_c': float(excursion.max()),
        'forecast_true_rmse_c': float(np.sqrt(np.mean([
            r['forecast_true_error_c']**2 for r in rows]))),
        'forecast_observed_rmse_c': float(np.sqrt(np.mean([
            r['forecast_observed_error_c']**2 for r in rows]))),
        'probe_mae_c': float(probes.mean()),
        'post_change_probe_mae_c': float(probes[change_step:].mean()) if degradation else None,
        'final_hour_probe_mae_c': float(probes[-RECOVERY_CONSECUTIVE:].mean())
        if len(probes) >= RECOVERY_CONSECUTIVE else None,
        'model_recovery_minutes': recovery,
        'model_recovery_status': ('not_applicable' if not degradation else
                                  'censored' if recovery is None else 'recovered'),
        'recovery_followup_minutes': (len(rows) - change_step) * STEP_MINUTES
        if degradation else None,
    }


def run_case(equipment, degradation, seed, sensor, steps=STEPS, change_step=CHANGE_STEP):
    if steps < 1 or change_step < 0 or (degradation and change_step >= steps):
        raise ValueError('need positive steps and an in-run change for degraded cases')
    ambient, demand = exogenous_series(seed, steps)
    errors = sensor_errors(sensor, seed, steps)
    controllers = make_controllers(seed)
    rows, summaries = [], []
    for name, controller in controllers.items():
        identity = dict(equipment=equipment.name, degradation=degradation, seed=seed,
                        sensor=sensor.name, noise_std_c=sensor.noise_std_c,
                        bias_c=sensor.bias_c, controller=name)
        true_temp = START_TEMP_C
        observed_temp = true_temp + errors[0]
        own = []
        for step in range(steps):
            plant = (replace(equipment, efficiency=equipment.efficiency * .75)
                     if degradation and step >= change_step else equipment)
            margin = capacity_margin(plant, ambient[step], demand[step])
            if margin <= 0:
                raise ValueError('capacity-limited case must not enter feasible suite')
            # Choose and forecast using only the current observation and completed history.
            power = controller.choose(observed_temp, ambient[step], demand[step])
            forecast = observed_temp + float(np.asarray(controller.predict_delta(
                observed_temp, ambient[step], demand[step], power)).item())
            # Oracle-only diagnostic at a fixed, shared grid. Never used for updates/actions.
            probe_error = float(np.mean(np.abs(
                controller.predict_delta(PROBE_T, 20., 2., PROBE_P)
                - plant.delta(PROBE_T, 20., 2., PROBE_P))))
            next_true = true_temp + float(plant.delta(
                true_temp, ambient[step], demand[step], power))
            next_observed = next_true + errors[step + 1]
            own.append(dict(
                **identity, step=step, true_temperature_c=float(true_temp),
                observed_temperature_c=float(observed_temp),
                next_true_temperature_c=float(next_true),
                next_observed_temperature_c=float(next_observed),
                sensor_error_c=float(errors[step]),
                next_sensor_error_c=float(errors[step + 1]), power_kw=power,
                ambient_c=float(ambient[step]), process_demand_kw=float(demand[step]),
                predicted_next_temperature_c=float(forecast),
                forecast_true_error_c=float(forecast - next_true),
                forecast_observed_error_c=float(forecast - next_observed),
                probe_mae_c=probe_error, capacity_margin_kw=float(margin),
            ))
            # The endpoint observation is reused as the next transition's start.
            # Both regressors AND targets are noisy. Never pass true_temp/next_true here.
            if isinstance(controller, RollingMPC):
                controller.observe(observed_temp, ambient[step], demand[step], power,
                                   next_observed)
            true_temp, observed_temp = next_true, next_observed
        rows.extend(own)
        summaries.append(dict(**identity, **summarize(own, degradation, change_step)))
    return rows, summaries


def paired_differences(summary):
    """Within-case contrasts. Do not subtract censored recovery times."""
    parts = []
    for left, right in CONTRASTS:
        a = summary[summary.controller == left].set_index(CASE_KEYS)
        b = summary[summary.controller == right].set_index(CASE_KEYS)
        difference = a[list(METRICS)] - b[list(METRICS)]
        difference.columns = [m + '_difference' for m in METRICS]
        difference['contrast'] = left + '_minus_' + right
        difference['left_recovery_status'] = a.model_recovery_status
        difference['right_recovery_status'] = b.model_recovery_status
        parts.append(difference.reset_index())
    return pd.concat(parts, ignore_index=True)


def noise_effects(summary):
    """Each controller against its own matched clean-sensor control."""
    keys = ['equipment', 'degradation', 'seed', 'controller']
    clean = summary[summary.sensor == 'clean'].set_index(keys)
    noisy = summary[summary.sensor != 'clean'].set_index(keys)
    result = noisy[['sensor']].copy()
    for metric in METRICS:
        result[metric + '_minus_clean'] = (noisy[metric].to_numpy(dtype=float)
                                          - clean[metric].reindex(noisy.index).to_numpy(dtype=float))
    return result.reset_index()


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_benchmark(output, seeds=SEEDS, sensors=SENSORS, steps=STEPS, change_step=CHANGE_STEP):
    output = Path(output).resolve()
    root = Path(__file__).resolve().parent
    for preserved in (root / 'results/adaptation', root / 'results/mpc_comparison'):
        if output == preserved or preserved in output.parents:
            raise ValueError('output must not overwrite original experiment results')
    seeds, sensors = tuple(seeds), tuple(sensors)
    if (not seeds or len(set(seeds)) != len(seeds) or any(s < 0 for s in seeds)
            or not sensors or len({s.name for s in sensors}) != len(sensors)
            or Sensor('clean') not in sensors):
        raise ValueError('need distinct nonnegative seeds, distinct sensors and clean control')
    if not 0 <= change_step < steps:
        raise ValueError('change_step must be inside the run')
    # Each run writes complete files, with deterministic order/float formatting/gzip.
    output.mkdir(parents=True, exist_ok=True)
    summaries = []
    trace_path = output / 'trajectories.csv.gz'
    with threadpool_limits(limits=1), trace_path.open('wb') as raw:
        with gzip.GzipFile(filename='', fileobj=raw, mode='wb', mtime=0) as compressed:
            with io.TextIOWrapper(compressed, encoding='utf-8', newline='') as stream:
                first = True
                for equipment in EQUIPMENT:
                    for degradation in (False, True):
                        for seed in seeds:
                            for sensor in sensors:
                                rows, results = run_case(equipment, degradation, seed, sensor,
                                                         steps, change_step)
                                pd.DataFrame(rows).to_csv(stream, index=False, header=first,
                                                          float_format='%.12g')
                                first = False
                                summaries.extend(results)
    summary = pd.DataFrame(summaries)
    summary.to_csv(output / 'summary.csv', index=False, float_format='%.12g')
    paired_differences(summary).to_csv(output / 'paired.csv', index=False, float_format='%.12g')
    noise_effects(summary).to_csv(output / 'noise_effects.csv', index=False, float_format='%.12g')
    sources = ('benchmark_sensor_robustness.py', 'benchmark_adaptation.py',
               'adaptive_mpc.py', 'controllers.py', 'simulator.py', 'train_model.py')
    metadata = dict(
        schema_version=1, base_commit=BASE_COMMIT, seeds=list(seeds),
        sensors=[asdict(s) for s in sensors], equipment=[asdict(e) for e in EQUIPMENT],
        steps=steps, change_step=change_step, step_minutes=STEP_MINUTES,
        controller_runs=len(summary), paired_cases=len(summary) // 4,
        versions=dict(python=platform.python_version(), numpy=np.__version__,
                      pandas=pd.__version__, scipy=scipy.__version__, sklearn=sklearn.__version__),
        protocol=dict(
            sensor_equation='y[t] = x[t] + bias + sigma*z[t], z iid standard normal',
            sensor_seed_sequence=['seed', SENSOR_STREAM], rng='PCG64',
            observations=['noisy temperature', 'exact current ambient',
                          'exact current process demand', 'past applied power'],
            common_sensor_errors=True, shared_transition_endpoints=True,
            bias_active_from_initial_observation=True,
            training='original clean nominal commissioning data',
            scoring='before observing completed transition',
            model_window=48, ridge=1e-6, degradation_multiplier=.75,
            change_disclosed=False, sensor_parameters_disclosed=False,
            probe=dict(temperatures_c=[58., 60., 62.], powers_kw=[0., 3., 6., 9., 12.],
                       ambient_c=20., demand_kw=2., oracle_only=True),
            recovery_threshold_c=RECOVERY_THRESHOLD_C,
            recovery_consecutive_steps=RECOVERY_CONSECUTIVE,
            recovery_time='start of first qualifying hour, confirmed 60 minutes later',
            censored_recovery='blank time with explicit censored status',
            physical_metrics='post-action true state, five-minute sampled band violations',
        ),
        source_sha256={name: _sha256(root / name) for name in sources},
        artifact_sha256={name: _sha256(output / name) for name in
                         ('summary.csv', 'paired.csv', 'noise_effects.csv', 'trajectories.csv.gz')},
    )
    (output / 'metadata.json').write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('results/sensor_robustness'))
    parser.add_argument('--seeds', nargs='+', type=int, default=list(SEEDS))
    parser.add_argument('--sensors', nargs='+', choices=[s.name for s in SENSORS],
                        default=[s.name for s in SENSORS])
    parser.add_argument('--steps', type=int, default=STEPS)
    parser.add_argument('--change-step', type=int, default=CHANGE_STEP)
    args = parser.parse_args()
    selected = [s for s in SENSORS if s.name in args.sensors]
    if SENSORS[0] not in selected:
        parser.error('--sensors must include clean as a matched control')
    summary = run_benchmark(args.output, args.seeds, selected, args.steps, args.change_step)
    print(summary.groupby(['sensor', 'controller'])[
        ['target_rmse_c', 'energy_kwh', 'violation_minutes', 'forecast_true_rmse_c']
    ].mean().to_string())


if __name__ == '__main__':
    main()
