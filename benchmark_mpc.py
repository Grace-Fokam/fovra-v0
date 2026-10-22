"""Reproduce matched MPC trials, including conventional feedback baselines.

Run: python benchmark_mpc.py --output results/mpc_comparison
Deterministic behavior metrics are separate from hardware-dependent timings.
"""

import argparse
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
from time import perf_counter

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from controllers import make_controller
from evaluation import SimulationConfig, merge_for_download, run_controller, summarize
from simulator import SCENARIOS
from train_model import train_world_model

PROFILES = {"default": (20., 3.), "cold_high": (10., 6.), "warm_low": (35., 1.)}
CONTROLLERS = ("Fovra", "Physics MPC", "Thermostat", "PI controller")
DEFAULT_SEEDS = (20261020, 20261021, 20261022)


def run_benchmark(output: Path, seeds=DEFAULT_SEEDS, repeats=3):
    if repeats < 1 or not seeds:
        raise ValueError("At least one seed and one repeat are required")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    rows, pairs, training = [], [], []
    # Limit native math-library threading for comparable small-array timings.
    with threadpool_limits(limits=1):
        for seed_index, seed in enumerate(seeds):
            start = perf_counter()
            model, heldout_mae = train_world_model(seed)
            training.append({"seed": seed, "heldout_mae_c": heldout_mae,
                             "training_and_validation_seconds": perf_counter() - start})
            # Warm disposable controllers, then start every trial from fresh
            # state. This does not advance the evaluated controller or plant.
            for name in CONTROLLERS:
                warm = make_controller(name, model)
                for _ in range(5):
                    warm.choose(60., 20., 3.)
            for profile_index, (profile, (ambient, demand)) in enumerate(PROFILES.items()):
                for scenario_index, scenario in enumerate(SCENARIOS):
                    config = SimulationConfig(ambient, demand, scenario, "Physics MPC")
                    for repeat in range(repeats):
                        # Rotate ordering to reduce systematic first-run bias.
                        offset = (seed_index + profile_index + scenario_index + repeat) % len(CONTROLLERS)
                        order = CONTROLLERS[offset:] + CONTROLLERS[:offset]
                        frames = {}
                        for position, name in enumerate(order):
                            frame = run_controller(name, config, model)
                            frames[name] = frame
                            rows.append({
                                "seed": seed, "profile": profile, "scenario": scenario,
                                "ambient_c": ambient, "process_kw": demand,
                                "repeat": repeat, "run_position": position,
                                "controller": name, **summarize(frame),
                            })
                        if repeat == 0:
                            learned, physics = frames["Fovra"], frames["Physics MPC"]
                            lm, pm = summarize(learned), summarize(physics)
                            pairs.append({
                                "seed": seed, "profile": profile, "scenario": scenario,
                                "action_mismatches": int(np.count_nonzero(
                                    np.abs(learned.heater_kw - physics.heater_kw) > 1e-9)),
                                "max_temperature_gap_c": float(np.max(np.abs(
                                    learned.temperature_c - physics.temperature_c))),
                                **{f"delta_{key}": lm[key] - pm[key] for key in (
                                    "energy_kwh", "target_rmse_c", "temperature_std_c",
                                    "minutes_outside", "max_violation_c", "violation_degree_minutes",
                                    "heater_adjustments", "heater_total_variation_kw",
                                )},
                            })
                            if seed_index == 0 and profile == "default":
                                filename = scenario.lower().replace(" ", "_") + ".csv"
                                merge_for_download(learned, physics, "Physics MPC").to_csv(
                                    output / filename, index=False, float_format="%.12g"
                                )

    measurements = pd.DataFrame(rows)
    paired = pd.DataFrame(pairs)
    # Stable ordering makes non-timing columns easy to compare across reruns.
    measurements = measurements.sort_values(["seed", "profile", "scenario", "repeat", "controller"])
    measurements.to_csv(output / "measurements.csv", index=False, float_format="%.12g")
    paired.to_csv(output / "paired_differences.csv", index=False, float_format="%.12g")
    root = Path(__file__).resolve().parent
    sources = ("controllers.py", "evaluation.py", "simulator.py", "train_model.py", "benchmark_mpc.py")
    metadata = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(), "platform": platform.platform(),
        "machine": platform.machine(), "processor": platform.processor(),
        "versions": {name: version(name) for name in (
            "numpy", "pandas", "scipy", "scikit-learn", "joblib", "threadpoolctl", "streamlit", "pytest"
        )},
        "source_sha256": {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in sources},
        "seeds": list(seeds), "profiles": PROFILES, "scenarios": list(SCENARIOS),
        "repeats": repeats, "controllers": list(CONTROLLERS), "native_thread_limit": 1,
        "warmup_decisions_per_controller_per_seed": 5,
        "timing_scope": "perf_counter_ns around choose only; excludes training, diagnostics, simulation and UI",
        "training": training,
        "interpretation": "Seeds resample noiseless nominal training data, not independent plants or noisy days. "
                          "Repeats measure runtime variability, not statistical evidence of generalization.",
    }
    (output / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {len(measurements)} controller-days and {len(paired)} distinct MPC pairs to {output}")
    print(f"Action mismatches: {paired.action_mismatches.sum()}")
    print(f"Largest temperature gap: {paired.max_temperature_gap_c.max():.12g} °C")
    default = measurements[(measurements.profile == "default") & (measurements.seed == seeds[0]) & (measurements.repeat == 0)]
    print(default[["scenario", "controller", "energy_kwh", "target_rmse_c", "minutes_outside", "heater_adjustments"]].to_string(index=False))
    print("Median of per-day mean decision times (ms), across all recorded trials:")
    print(measurements.groupby("controller").decision_mean_ms.median().to_string())
    return measurements, paired


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("results/mpc_comparison"))
    parser.add_argument("--seeds", type=int, nargs="+", default=list(DEFAULT_SEEDS))
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    run_benchmark(args.output, args.seeds, args.repeats)


if __name__ == "__main__":
    main()
