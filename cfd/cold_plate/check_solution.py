"""Check solver-exported integral metrics. Blank templates are never results."""

import argparse
import csv
import json
import math
from pathlib import Path

FIELDS = ["case_id", "physics_variant", "mesh_level", "cell_count", "solver_version",
          "mass_in_kg_s", "mass_out_kg_s", "heater_w", "dissipation_w",
          "enthalpy_gain_w", "other_outward_heat_w", "interface_solid_to_fluid_w",
          "interface_fluid_from_solid_w", "inlet_k", "outlet_bulk_k", "base_max_k",
          "base_mean_k", "p_in_area_pa", "p_out_area_pa", "pressure_gradient_pa_m",
          "last_window_temperature_drift_k", "last_window_pressure_drift_fraction"]


def grid_convergence(coarse, medium, fine, ratio=2.0):
    """Equal-ratio Richardson/GCI with a three-grid safety factor of 1.25.

    Use positive temperature rise, resistance or pressure drop, not Celsius.
    Only monotonic converging sequences are accepted.
    """
    if not all(math.isfinite(v) for v in [coarse, medium, fine, ratio]) or ratio <= 1:
        raise ValueError("Finite values and refinement ratio > 1 required")
    a, b = coarse-medium, medium-fine
    if a*b <= 0 or abs(a) <= abs(b) or fine <= 0:
        raise ValueError("No usable monotonic convergence. Refine or investigate.")
    p = math.log(abs(a/b)) / math.log(ratio)
    extrapolated = fine + (fine-medium)/(ratio**p-1)
    bound = 1.25*abs(fine-medium)/(ratio**p-1)
    return {"observed_order": p, "extrapolated": extrapolated,
            "fine_gci_absolute": bound, "fine_gci_percent": 100*bound/abs(fine),
            "note": "Three-grid estimate, not independent proof of asymptotic behavior. Check a fourth grid if uncertain."}


def assess(row):
    for name in FIELDS:
        if name not in row or row[name] == "":
            raise ValueError(f"Missing measured/exported field: {name}")
    numeric = {key: float(row[key]) for key in FIELDS[3:] if key != "solver_version"}
    if not all(math.isfinite(v) for v in numeric.values()):
        raise ValueError("All solution metrics must be finite")
    if numeric["mass_in_kg_s"] <= 0 or numeric["mass_out_kg_s"] <= 0 or numeric["heater_w"] <= 0:
        raise ValueError("Mass rates and imposed heat must be positive magnitudes")
    if numeric["cell_count"] <= 0 or not numeric["cell_count"].is_integer():
        raise ValueError("Positive integer cell count required")
    if numeric["dissipation_w"] < 0:
        raise ValueError("Dissipation must be nonnegative and match the energy equation")
    qin = numeric["heater_w"] + numeric["dissipation_w"]
    mass_error = abs(numeric["mass_out_kg_s"]-numeric["mass_in_kg_s"])/numeric["mass_in_kg_s"]
    heat_error = abs(numeric["enthalpy_gain_w"]+numeric["other_outward_heat_w"]-qin)/qin
    interface_error = abs(numeric["interface_solid_to_fluid_w"]-numeric["interface_fluid_from_solid_w"])/numeric["heater_w"]
    dp = numeric["p_in_area_pa"]-numeric["p_out_area_pa"]
    checks = {"mass_balance": mass_error <= .001, "heat_balance": heat_error <= .005,
              "interface_balance": interface_error <= .001,
              "temperature_stationarity": abs(numeric["last_window_temperature_drift_k"]) <= .01,
              "pressure_stationarity": abs(numeric["last_window_pressure_drift_fraction"]) <= .001,
              "positive_pressure_drop": dp > 0}
    return {"case_id": row["case_id"], "checks": checks,
            "integral_checks_pass": all(checks.values()),
            "mass_error_fraction": mass_error, "heat_error_fraction": heat_error,
            "interface_error_fraction": interface_error, "channel_end_pressure_drop_pa": dp,
            "base_temperature_rise_k": numeric["base_max_k"]-numeric["inlet_k"],
            "thermal_resistance_k_w": (numeric["base_max_k"]-numeric["inlet_k"])/numeric["heater_w"],
            "scope": "Integral checks only. Requires mesh, discretization, boundary and engineering review."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path)
    parser.add_argument("--write-template", type=Path)
    args = parser.parse_args()
    if bool(args.results) == bool(args.write_template):
        parser.error("Choose exactly one of --results or --write-template")
    if args.write_template:
        args.write_template.parent.mkdir(parents=True, exist_ok=True)
        with args.write_template.open("w", newline="") as stream:
            csv.writer(stream, lineterminator="\n").writerow(FIELDS)
    else:
        with args.results.open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        if not rows:
            raise SystemExit("No solver results. Template is empty.")
        reports = [assess(row) for row in rows]
        print(json.dumps(reports, indent=2, allow_nan=False))
        raise SystemExit(0 if all(r["integral_checks_pass"] for r in reports) else 1)
