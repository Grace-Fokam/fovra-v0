"""Export liquid-water properties for an explicitly assumed absolute pressure."""

import argparse
import csv
import json
from pathlib import Path

import CoolProp
from CoolProp.CoolProp import PhaseSI, PropsSI


def export(path, pressure_pa=101325.0, start_c=20, stop_c=60):
    if not 0 < pressure_pa or not 0 <= start_c < stop_c <= 90:
        raise ValueError("Require positive absolute pressure and 0 <= start < stop <= 90 C")
    rows = []
    for temperature_c in range(start_c, stop_c+1):
        temperature_k = temperature_c + 273.15
        if PhaseSI("T", temperature_k, "P", pressure_pa, "HEOS::Water") != "liquid":
            raise ValueError("Requested table includes a non-liquid state")
        row = {"temperature_k": temperature_k, "absolute_pressure_pa": pressure_pa}
        for name, prop in [("rho_kg_m3", "Dmass"), ("mu_pa_s", "VISCOSITY"),
                           ("cp_j_kgk", "Cpmass"), ("k_w_mk", "CONDUCTIVITY"),
                           ("h_j_kg", "Hmass")]:
            row[name] = PropsSI(prop, "T", temperature_k, "P", pressure_pa, "HEOS::Water")
        rows.append(row)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys(), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    path.with_suffix(".json").write_text(json.dumps({
        "backend": "HEOS::Water", "CoolProp_version": CoolProp.__version__,
        "CoolProp_git_revision": CoolProp.__gitrevision__,
        "absolute_pressure_pa": pressure_pa,
        "pressure_status": "Analyst sensitivity assumption, not a partner requirement",
        "range_c": [start_c, stop_c], "spacing_k": 1,
        "interpolation": "Piecewise linear. No extrapolation. Verify midpoint errors before use.",
        "fluid_status": "Pure water assumption. Not a glycol or inhibitor blend specification.",
        "references": ["https://coolprop.org/fluid_properties/fluids/Water.html",
                       "https://coolprop.org/coolprop/HighLevelAPI.html"]}, indent=2)+"\n")
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pressure-pa", type=float, default=101325.0)
    parser.add_argument("--start-c", type=int, default=20)
    parser.add_argument("--stop-c", type=int, default=60)
    args = parser.parse_args()
    export(args.output, args.pressure_pa, args.start_c, args.stop_c)
