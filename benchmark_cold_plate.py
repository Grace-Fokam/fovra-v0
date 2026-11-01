"""Reproduce cold-plate geometry screening, with a hidden finite-grid reference."""

import argparse
from dataclasses import asdict, replace
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import time

import numpy as np
import pandas as pd

from cold_plate import ColdPlateCase, ColdPlateDesign, evaluate_design
from cold_plate_search import INITIAL_SAMPLES, METHODS, best_verified, candidate_designs, run_search

DEFAULT_SEEDS = (11, 22, 33, 44, 55, 66)


def experiments():
    all_designs = candidate_designs()
    return [
        (ColdPlateCase(), all_designs),
        (ColdPlateCase(name="higher_load", heat_w=150), all_designs),
        (ColdPlateCase(name="warm_inlet", inlet_c=30), all_designs),
        (ColdPlateCase(name="fixed_flow_geometry"), [d for d in all_designs if d.flow_lpm == 0.2]),
    ]


def pareto_flags(rows):
    """Nondominated simulated peak temperature and pump power, feasible only."""
    feasible = [r for r in rows if r["feasible"]]
    return [r["feasible"] and not any(
        x["peak_base_c"] <= r["peak_base_c"] and x["pump_w"] <= r["pump_w"]
        and (x["peak_base_c"] < r["peak_base_c"] or x["pump_w"] < r["pump_w"])
        for x in feasible) for r in rows]


def run_benchmark(output, seeds=DEFAULT_SEEDS, budget=32, specs=None):
    specs = experiments() if specs is None else specs
    if not specs or not seeds or len(set(seeds)) != len(seeds):
        raise ValueError("Provide nonempty experiments and distinct seeds")
    grids, trials, summaries, timings, sensitivity, references, winners = [], [], [], [], [], [], []
    for case_id, (case, designs) in enumerate(specs):
        # Compute the exhaustive reference independently. Searches below make real
        # calls, not table lookups. The optimizer never receives this oracle table.
        t0 = time.perf_counter()
        grid = [{**evaluate_design(case, d), "candidate_id": i}
                for i, d in enumerate(designs)]
        timings.append({"case_id": case_id, "method": "grid", "seed": None,
                        "elapsed_s": time.perf_counter()-t0, "evaluations": len(grid)})
        for row, flag in zip(grid, pareto_flags(grid)):
            grids.append({"case_id": case_id, "case": case.name, **row, "pareto": flag})
        oracle = best_verified(grid)
        references.append({"case_id": case_id, "case": case.name,
                           **evaluate_design(case, ColdPlateDesign())})
        if oracle:
            winners.append({"case_id": case_id, "case": asdict(case),
                            "design": asdict(designs[oracle["candidate_id"]]), "result": oracle})
            for h_factor, loss_k in ((0.7, 2.), (1., 2.), (1.3, 2.), (1., 0.), (1., 5.)):
                sensitivity.append({"case_id": case_id, "case": case.name,
                                    "heat_transfer_multiplier": h_factor, "minor_loss_k": loss_k,
                                    **evaluate_design(replace(case, heat_transfer_multiplier=h_factor,
                                                              minor_loss_k=loss_k),
                                                      designs[oracle["candidate_id"]])})
        for seed in seeds:
            for method in METHODS:
                observed = run_search(case, method, budget=budget, seed=seed, designs=designs)
                timings.append({"case_id": case_id, "method": method, "seed": seed,
                                "elapsed_s": observed[-1]["elapsed_s"], "evaluations": budget})
                best = best_verified(observed)
                for row in observed:
                    row.pop("elapsed_s")  # Deterministic scientific files, timing separate.
                    row["gap_to_grid_w"] = (row["best_pump_w_so_far"]-oracle["pump_w"]
                                            if oracle and row["best_pump_w_so_far"] is not None else None)
                    trials.append({"case_id": case_id, "case": case.name, **row})
                near = [r["evaluation"] for r in observed if oracle and r["feasible"]
                        and r["pump_w"] <= 1.05*oracle["pump_w"]]
                first = [r["evaluation"] for r in observed if r["feasible"]]
                summaries.append({
                    "case_id": case_id, "case": case.name, "method": method, "seed": seed,
                    "simulator_evaluations": len(observed), "grid_evaluations_separate": len(grid),
                    "feasible_observations": len(first), "first_feasible_evaluation": min(first) if first else None,
                    "first_within_5pct_grid_evaluation": min(near) if near else None,
                    "found_feasible": best is not None, "grid_has_feasible": oracle is not None,
                    "best_candidate_id": best["candidate_id"] if best else None,
                    **{f"best_{key}": best[key] if best else None for key in
                       ("peak_base_c", "thermal_resistance_k_w", "pressure_pa", "pump_w", "pump_kwh", "pump_cost")},
                    "grid_best_pump_w": oracle["pump_w"] if oracle else None,
                    "relative_gap_to_grid": (best["pump_w"]/oracle["pump_w"]-1) if best and oracle else None,
                })
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    summary = pd.DataFrame(summaries)
    for name, rows in (("grid", grids), ("search_trials", trials), ("search_summary", summaries),
                       ("timings", timings), ("sensitivity", sensitivity), ("reference_design", references)):
        pd.DataFrame(rows).to_csv(output / f"{name}.csv", index=False)
    (output / "grid_winners.json").write_text(json.dumps(winners, indent=2, allow_nan=False)+"\n")
    paired = []
    for (case_id, seed), part in summary.groupby(["case_id", "seed"]):
        a = part[part.method == "surrogate"].iloc[0]
        r = part[part.method == "random"].iloc[0]
        if not a.found_feasible and not r.found_feasible:
            outcome = "neither_feasible"
        elif not a.found_feasible:
            outcome = "loss"
        elif not r.found_feasible:
            outcome = "win"
        elif np.isclose(a.best_pump_w, r.best_pump_w, rtol=1e-9, atol=1e-12):
            outcome = "tie"
        else:
            outcome = "win" if a.best_pump_w < r.best_pump_w else "loss"
        paired.append({"case_id": case_id, "case": a["case"], "seed": seed, "surrogate_outcome": outcome})
    pd.DataFrame(paired).to_csv(output / "paired_comparison.csv", index=False)
    root = Path(__file__).resolve().parent
    sources = ("cold_plate.py", "cold_plate_search.py", "benchmark_cold_plate.py")
    metadata = {
        "scope": "Unvalidated reduced-order cold-plate coupon model. No hardware or general AI advantage claim.",
        "objective": "Minimize plate-only pump electric power subject to geometry, correlation-domain, temperature and pressure constraints.",
        "budget": budget, "seeds": list(seeds), "shared_initial_samples": INITIAL_SAMPLES,
        "surrogate": {"trees": 64, "exploration_every_post_initial_queries": 5,
                      "targets_standardized_from_observed_samples_only": True},
        "experiments": [{"case": asdict(c), "candidate_count": len(ds),
                         "designs": [asdict(d) for d in ds]} for c, ds in specs],
        "oracle_evaluations": sum(len(ds) for _, ds in specs),
        "search_evaluations": len(specs)*len(seeds)*len(METHODS)*budget,
        "extra_sensitivity_evaluations": len(sensitivity), "extra_reference_evaluations": len(references),
        "oracle_policy": "Separate exhaustive finite grids, never passed to search. Searches call simulator directly.",
        "python": platform.python_version(),
        "packages": {p: importlib.metadata.version(p) for p in ("numpy", "pandas", "scipy", "scikit-learn", "joblib", "threadpoolctl")},
        "source_sha256": {name: hashlib.sha256((root/name).read_bytes()).hexdigest() for name in sources},
    }
    (output / "metadata.json").write_text(json.dumps(metadata, indent=2, allow_nan=False)+"\n")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="results/cold_plate")
    parser.add_argument("--budget", type=int, default=32)
    parser.add_argument("--seeds", type=int, nargs="+", default=DEFAULT_SEEDS)
    args = parser.parse_args()
    frame = run_benchmark(args.output, seeds=args.seeds, budget=args.budget)
    print(frame.groupby(["case", "method"])[["found_feasible", "relative_gap_to_grid"]].mean().to_string())
