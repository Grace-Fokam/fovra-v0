"""Equal-query-budget random and random-forest searches of channel geometry."""

from dataclasses import astuple
from itertools import product
from math import isfinite
import time

import numpy as np
from sklearn.ensemble import RandomForestRegressor

from cold_plate import ColdPlateDesign, evaluate_design, validate_case

METHODS = ("random", "surrogate")
INITIAL_SAMPLES = 8
# Model raw observable responses, not a hidden oracle or composite ground truth.
TARGETS = ("peak_base_c", "pressure_pa", "pump_w", "outlet_c",
           "reynolds", "hydrodynamic_entry_fraction", "thermal_entry_fraction")


def candidate_designs():
    return [ColdPlateDesign(*values) for values in product(
        (0.2, 0.3, 0.5, 0.8), (0.8, 1.2, 1.8), (0.2, 0.4, 0.8),
        (1.0, 2.0), (0.05, 0.1, 0.2, 0.4, 0.8), (167.0, 390.0))
        if 1 <= values[1]/values[0] <= 6]


def best_verified(records):
    valid = [r for r in records if r["feasible"]]
    return min(valid, key=lambda r: (r["pump_w"], r["peak_base_c"], r["candidate_id"])) if valid else None


def predicted_rank(prediction, case):
    peak, pressure, pump, outlet, re, hydro, thermal = prediction
    ratios = (max(0., (peak-case.max_base_c)/(case.max_base_c-case.inlet_c)),
              max(0., pressure/case.max_pressure_pa-1), max(0., pump/case.max_pump_w-1),
              max(0., (outlet-40)/20), max(0., re/2000-1),
              max(0., hydro/0.1-1), max(0., thermal-1))
    violation = sum(ratios)
    return (violation > 0, violation, pump, peak)


def run_search(case, method, budget=32, seed=11, designs=None, evaluator=None):
    """Only requested evaluations are visible. Every request consumes one query.

    Identical eight-point initialization. Surrogate uses a deterministic random
    exploration query every fifth post-initial query, otherwise greedy predicted
    feasibility then pump power. Tree spread is not treated as calibrated error.
    """
    validate_case(case)
    designs = candidate_designs() if designs is None else list(designs)
    if method not in METHODS or isinstance(budget, bool) or not isinstance(budget, int):
        raise ValueError("Unknown method or noninteger budget")
    if not INITIAL_SAMPLES <= budget <= len(designs) or len(set(designs)) != len(designs):
        raise ValueError("Budget must cover initialization and fit unique candidates")
    evaluate = evaluator if evaluator is not None else lambda d: evaluate_design(case, d)
    order = np.random.default_rng(seed).permutation(len(designs)).tolist()
    features = np.array([astuple(d) for d in designs])
    selected, records = [], []
    start = time.perf_counter()
    for iteration in range(budget):
        remaining = [i for i in order if i not in selected]
        usable = [j for j, r in enumerate(records)
                  if all(isfinite(r.get(key, float("nan"))) for key in TARGETS)]
        choice = remaining[0]
        policy = "random"
        if (method == "surrogate" and iteration >= INITIAL_SAMPLES
                and (iteration-INITIAL_SAMPLES+1) % 5 != 0 and len(usable) >= 2):
            model = RandomForestRegressor(n_estimators=64, min_samples_leaf=1,
                                          random_state=seed, n_jobs=1)
            # Separate output scales avoid pressure dominating multi-output tree splits.
            y = np.array([[records[j][key] for key in TARGETS] for j in usable])
            scale = np.maximum(np.std(y, axis=0), 1e-9)
            center = np.mean(y, axis=0)
            model.fit(features[[selected[j] for j in usable]], (y-center)/scale)
            pred = model.predict(features[remaining])*scale+center
            index = min(range(len(remaining)), key=lambda j: (predicted_rank(pred[j], case), remaining[j]))
            choice, policy = remaining[index], "surrogate"
        result = dict(evaluate(designs[choice]))
        result.update({"candidate_id": choice, "method": method, "seed": seed,
                       "evaluation": iteration+1, "selection_policy": policy})
        records.append(result)
        selected.append(choice)
        best = best_verified(records)
        result["best_pump_w_so_far"] = best["pump_w"] if best else None
        result["elapsed_s"] = time.perf_counter()-start
    return records
