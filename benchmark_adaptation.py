"""Matched, feasible synthetic adaptation experiment. Run as a standalone CLI."""
import argparse
from dataclasses import asdict, dataclass, replace
import json
import hashlib
from pathlib import Path
import platform

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from adaptive_mpc import RollingMPC
from controllers import LearnedMPC, PhysicsMPC
from simulator import STEP_HOURS, MIN_SAFE_TEMP_C, MAX_SAFE_TEMP_C
from train_model import train_world_model


@dataclass(frozen=True)
class Equipment:
    name: str
    capacity: float
    loss: float
    efficiency: float

    def __post_init__(self):
        if self.capacity <= 0 or self.loss < 0 or not 0 < self.efficiency <= 1:
            raise ValueError("invalid physical equipment parameters")

    def delta(self, temp, ambient, demand, power):
        return STEP_HOURS * (self.efficiency*np.asarray(power)
                             - self.loss*(np.asarray(temp)-ambient)-demand)/self.capacity


# Only nominal equipment is in the fixed model's training data.
EQUIPMENT = (Equipment('nominal', 1., .08, 1.),
             Equipment('unseen_small', .65, .11, .90),
             Equipment('unseen_large', 1.6, .05, .85))
CHANGE_STEP = 120
STEPS = 288


def capacity_margin(equipment, ambient, demand):
    """Positive heat margin at upper safety limit is a sufficient static check."""
    return 12*equipment.efficiency-equipment.loss*(MAX_SAFE_TEMP_C-ambient)-demand


def recovery_minutes(temperatures, change=CHANGE_STEP, consecutive=12):
    """First full hour within safety band after change, or None if censored."""
    safe = (np.asarray(temperatures) >= MIN_SAFE_TEMP_C) & (np.asarray(temperatures) <= MAX_SAFE_TEMP_C)
    for start in range(change, len(safe)-consecutive+1):
        if safe[start:start+consecutive].all():
            return (start-change)*5
    return None


def model_recovery_minutes(errors, change=CHANGE_STEP, threshold=.02, consecutive=12):
    """First hour of common-probe MAE <= .02 C/step, or censored None."""
    for start in range(change, len(errors)-consecutive+1):
        if np.all(np.asarray(errors[start:start+consecutive]) <= threshold):
            return (start-change)*5
    return None


def run_case(equipment, degradation, seed, steps=STEPS):
    model, _ = train_world_model(seed)
    controllers = {'fixed_learned': LearnedMPC(model), 'fixed_physics': PhysicsMPC(),
                   'adaptive_learned': RollingMPC(), 'adaptive_physics': RollingMPC(physics=True)}
    # Same exogenous series in each closed loop, independently of controller.
    rng = np.random.default_rng(seed)
    ambient = 20 + np.sin(np.arange(steps)*2*np.pi/288)
    demand = 2.0 + .3*np.sin(np.arange(steps)*2*np.pi/72) + rng.uniform(-.1,.1,steps)
    rows, summaries = [], []
    for name, controller in controllers.items():
        temp = 60.
        trajectory = []
        for step in range(steps):
            plant = replace(equipment, efficiency=equipment.efficiency*.75) if degradation and step >= CHANGE_STEP else equipment
            margin = capacity_margin(plant, ambient[step], demand[step])
            if margin <= 0:
                raise ValueError('capacity-limited case must not enter feasible suite')
            power = controller.choose(temp, ambient[step], demand[step])
            predicted = float(np.asarray(controller.predict_delta(temp, ambient[step], demand[step], power)).item())
            actual = float(plant.delta(temp, ambient[step], demand[step], power))
            next_temp = temp + actual
            # Common probe grid isolates model error from the visited trajectory.
            probe_t, probe_p = np.meshgrid([58.,60.,62.], [0.,3.,6.,9.,12.])
            probe_error = np.mean(np.abs(controller.predict_delta(probe_t.ravel(), ambient[step], demand[step], probe_p.ravel())
                                        - plant.delta(probe_t.ravel(), ambient[step], demand[step], probe_p.ravel())))
            rows.append(dict(equipment=equipment.name, degradation=degradation, seed=seed,
                             controller=name, step=step, temperature_c=next_temp, power_kw=power,
                             ambient_c=float(ambient[step]), process_demand_kw=float(demand[step]),
                             prediction_abs_error_c=abs(actual-predicted), probe_mae_c=float(probe_error),
                             capacity_margin_kw=margin))
            trajectory.append(next_temp)
            # Update after scoring prediction and applying action, never before.
            if isinstance(controller, RollingMPC):
                controller.observe(temp, ambient[step], demand[step], power, next_temp)
            temp = next_temp
        own = rows[-steps:]
        after = own[CHANGE_STEP:]
        summaries.append(dict(equipment=equipment.name, degradation=degradation, seed=seed, controller=name,
                              energy_kwh=sum(r['power_kw']*STEP_HOURS for r in own),
                              violation_minutes=sum(not MIN_SAFE_TEMP_C <= t <= MAX_SAFE_TEMP_C for t in trajectory)*5,
                              target_rmse_c=float(np.sqrt(np.mean((np.asarray(trajectory)-60.)**2))),
                              model_recovery_minutes=model_recovery_minutes([r['probe_mae_c'] for r in own]) if degradation else None,
                              prediction_mae_c=np.mean([r['prediction_abs_error_c'] for r in own]),
                              post_change_mae_c=np.mean([r['prediction_abs_error_c'] for r in after]) if after else None,
                              post_change_probe_mae_c=np.mean([r['probe_mae_c'] for r in after]) if after else None,
                              recovery_minutes=recovery_minutes(trajectory) if degradation else None))
    return rows, summaries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('results/adaptation'))
    args = parser.parse_args()
    rows, summaries = [], []
    with threadpool_limits(limits=1):
        for equipment in EQUIPMENT:
            for degradation in (False, True):
                for seed in (11,22,33):
                    r, s = run_case(equipment, degradation, seed)
                    rows.extend(r)
                    summaries.extend(s)
    args.output.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(args.output/'trajectories.csv', index=False, float_format='%.10g')
    frame = pd.DataFrame(summaries)
    frame.to_csv(args.output/'summary.csv', index=False, float_format='%.10g')
    fixed = frame[frame.controller=='fixed_learned'].set_index(['equipment','degradation','seed'])
    paired = frame[frame.controller!='fixed_learned'].set_index(['equipment','degradation','seed'])
    for metric in ('energy_kwh','violation_minutes','post_change_mae_c','post_change_probe_mae_c'):
        paired[metric+'_minus_fixed_learned'] = paired[metric].to_numpy()-fixed[metric].reindex(paired.index).to_numpy()
    paired.to_csv(args.output/'paired.csv', float_format='%.10g')
    learned = frame[frame.controller=='adaptive_learned'].set_index(['equipment','degradation','seed'])
    physical = frame[frame.controller=='adaptive_physics'].set_index(['equipment','degradation','seed'])
    differences = learned.select_dtypes(include='number')-physical.select_dtypes(include='number')
    differences.to_csv(args.output/'adaptive_learned_minus_physics.csv', float_format='%.10g')
    import sklearn
    metadata = dict(base_commit='d28674c3ead95c63dc16b1cdc6c0a65568778c17', seeds=[11,22,33],
                    equipment=[asdict(e) for e in EQUIPMENT], change_step=CHANGE_STEP,
                    steps=STEPS, window=48, ridge=1e-6, python=platform.python_version(),
                    numpy=np.__version__, pandas=pd.__version__, sklearn=sklearn.__version__)
    import scipy
    metadata['scipy'] = scipy.__version__
    metadata['source_sha256'] = {p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
                                 for p in ('adaptive_mpc.py','benchmark_adaptation.py',
                                           'controllers.py','simulator.py','train_model.py')}
    metadata['trajectory_sha256'] = hashlib.sha256((args.output/'trajectories.csv').read_bytes()).hexdigest()
    metadata['protocol'] = dict(observations=['temperature','ambient','process demand','past applied power'],
                                degradation_multiplier=.75, change_disclosed=False,
                                model_recovery_threshold_c=.02, recovery_consecutive_steps=12,
                                sensor_noise=False)
    (args.output/'metadata.json').write_text(json.dumps(metadata, indent=2)+'\n')
    print(frame.groupby('controller').mean(numeric_only=True).to_string())


if __name__ == '__main__':
    main()
