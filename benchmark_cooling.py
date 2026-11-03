"""Reproduce the illustrative cooling and equal-budget search experiments."""

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import platform

import numpy as np
import pandas as pd
import sklearn

from cooling import CLIMATES, CoolingCase, evaluate_design, pareto_mask
from cooling_search import METHODS, best_verified, candidate_designs, run_search


def run_benchmark(output, cases=None, seeds=(11, 22, 33), budget=12, water_budget_l=4000.0):
    cases = cases if cases is not None else [
        CoolingCase(climate=climate, surge=surge)
        for climate in CLIMATES for surge in (False, True)
    ]
    grid_parts, trial_parts, summaries = [], [], []
    for case_id, case in enumerate(cases):
        # Full-grid truth is used ONLY for verification and the oracle comparison.
        # run_search sees one chosen result at a time, never this table.
        truth = {d.name: evaluate_design(case, d) for d in candidate_designs()}
        grid = pd.DataFrame(truth.values())
        grid["pareto"] = pareto_mask(grid)
        grid_parts.append(grid.assign(case_id=case_id))
        oracle = best_verified(grid, water_budget_l)
        for seed in seeds:
            for method in METHODS:
                trials = run_search(case, method, budget, water_budget_l, seed,
                                    evaluator=lambda d: truth[d.name])
                trial_parts.append(trials.assign(case_id=case_id))
                best = best_verified(trials, water_budget_l)
                summaries.append({
                    "case_id": case_id, **asdict(case), "method": method, "seed": seed,
                    "simulations_observed": budget, "oracle_simulations": len(grid),
                    "water_budget_l": water_budget_l,
                    "found_feasible": best is not None,
                    "best_design": best["design"] if best else None,
                    "best_cooling_kwh": best["cooling_kwh"] if best else None,
                    "best_makeup_l": best["makeup_l"] if best else None,
                    "oracle_cooling_kwh": oracle["cooling_kwh"] if oracle else None,
                    "gap_to_grid_kwh": best["cooling_kwh"] - oracle["cooling_kwh"]
                    if best is not None and oracle is not None else None,
                })
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    pd.concat(grid_parts, ignore_index=True).to_csv(output / "grid.csv", index=False)
    pd.concat(trial_parts, ignore_index=True).to_csv(output / "search_trials.csv", index=False)
    summary = pd.DataFrame(summaries)
    summary.to_csv(output / "search_summary.csv", index=False)
    root = Path(__file__).resolve().parent
    metadata = {
        "scope": "Synthetic cooling exploration. No equipment validation or demonstrated ML advantage.",
        "cases": [asdict(c) for c in cases], "seeds": list(seeds), "budget": budget,
        "water_budget_l": water_budget_l, "candidate_count": len(candidate_designs()),
        "initial_shared_samples": 6,
        "objective": "Minimize cooling electricity subject to thermal checks and makeup-water budget.",
        "oracle": "Full 35-design grid, hidden from both search methods. Precomputed simulations are replayed one chosen result at a time. No speedup claim.",
        "python": platform.python_version(), "numpy": np.__version__,
        "pandas": pd.__version__, "scikit_learn": sklearn.__version__,
        "source_sha256": {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                          for name in ("cooling.py", "cooling_search.py", "benchmark_cooling.py")},
    }
    (output / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="results/cooling")
    parser.add_argument("--budget", type=int, default=12)
    parser.add_argument("--water-budget-l", type=float, default=4000.0)
    args = parser.parse_args()
    results = run_benchmark(args.output, budget=args.budget, water_budget_l=args.water_budget_l)
    print(results[["climate", "surge", "method", "seed", "found_feasible", "gap_to_grid_kwh"]].to_string(index=False))
