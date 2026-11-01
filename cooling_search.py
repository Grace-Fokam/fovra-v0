"""Budgeted surrogate screening, with simulator verification of every result."""

from math import isfinite

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

from cooling import CoolingDesign, LIMIT_C, TARGET_C, evaluate_design

TARGETS = ["cooling_kwh", "makeup_l", "peak_coolant_c", "end_coolant_c"]
METHODS = ("Random search", "AI screening")
INITIAL_SAMPLES = 6


def candidate_designs():
    designs = []
    for size in (0.6, 0.8, 1.0, 1.2, 1.5, 1.8, 2.0):
        designs.append(CoolingDesign("Dry cooler", size))
        designs.extend(CoolingDesign("Evaporative assist", size, trigger)
                       for trigger in (0.35, 0.55, 0.75, 1.0))
    return designs


def feasible_mask(frame, water_budget_l):
    return frame.thermal_ok & (frame.makeup_l <= water_budget_l + 1e-8)


def best_verified(frame, water_budget_l):
    valid = frame[feasible_mask(frame, water_budget_l)]
    if valid.empty:
        return None
    return valid.sort_values(["cooling_kwh", "makeup_l", "design"]).iloc[0].to_dict()


def run_search(case, method, budget=12, water_budget_l=4000.0, seed=11, evaluator=None):
    """Same candidate set, budget, and initial samples for both methods.

    The optional evaluator is only called for the chosen candidate. An oracle
    table, if used by the offline benchmark, is never exposed to the model.
    """
    designs = candidate_designs()
    if method not in METHODS:
        raise ValueError("Unknown search method")
    if not isinstance(budget, int) or not INITIAL_SAMPLES <= budget <= len(designs):
        raise ValueError("Budget must be an integer between 6 and 35")
    if not isfinite(water_budget_l) or water_budget_l < 0:
        raise ValueError("Water budget must be finite and nonnegative")
    evaluate = evaluator if evaluator is not None else lambda d: evaluate_design(case, d)
    order = np.random.default_rng(seed).permutation(len(designs)).tolist()
    features = np.array([[float(d.mode == "Evaporative assist"), d.size, d.wet_trigger]
                         for d in designs])
    selected, records = [], []
    for iteration in range(budget):
        unseen = [i for i in order if i not in selected]
        if method == "Random search" or iteration < INITIAL_SAMPLES:
            choice = unseen[0]
        else:
            # New fit uses this search's completed simulations only.
            model = RandomForestRegressor(n_estimators=64, random_state=seed, n_jobs=1)
            model.fit(features[selected], pd.DataFrame(records)[TARGETS])
            predictions = model.predict(features[unseen])

            def rank(j):
                energy, water, peak, end = predictions[j]
                violations = (max(0.0, peak - LIMIT_C),
                              max(0.0, end - (TARGET_C + 0.1)),
                              max(0.0, water - water_budget_l))
                # Prefer predicted feasible designs, then lower electricity.
                # Infeasible estimates use lexicographic constraint violations.
                return (any(v > 0 for v in violations), *violations, energy, unseen[j])

            choice = unseen[min(range(len(unseen)), key=rank)]
        result = dict(evaluate(designs[choice]))
        records.append({**result, "method": method, "seed": seed,
                        "evaluation": iteration + 1, "candidate_id": choice,
                        "water_budget_l": water_budget_l})
        selected.append(choice)
    frame = pd.DataFrame(records)
    frame["within_budget"] = feasible_mask(frame, water_budget_l)
    return frame


def compare_search(case, budget=12, water_budget_l=4000.0, seed=11):
    return pd.concat([run_search(case, method, budget, water_budget_l, seed)
                      for method in METHODS], ignore_index=True)
