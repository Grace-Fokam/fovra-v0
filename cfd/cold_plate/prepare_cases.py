"""Select recorded rows and export SI inputs without running a CFD solver."""

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from cold_plate import ColdPlateCase, ColdPlateDesign, evaluate_design

SOURCE_COMMIT = "3e088831d50f8c65281bc6e84482700395a1c1a7"
PINNED_SHA256 = {
    "results/cold_plate/grid.csv": "ab9605e2a6fb99095a78ba0c107910f7ccce96d64b5c18c50481e9c321377677",
    "results/cold_plate/grid_winners.json": "47d2e4feb08bd3356d791e893a3900a101fcfe61e7e2c1a98fece8ed774fcfbe",
    "cold_plate.py": "60f12b3aad7f69eb4facf2dd0edf44a5643b60547ba0ac8d408185ac2097eb87",
    "docs/cold-plate.md": "4489dff488c2fce41fe7127e497b73d9e120df31b09cf789573e05aa8c8b9330",
}
SELECTION = [
    ("N0_nominal", 603, "Nominal grid winner and primary verification case"),
    ("G1_narrow", 423, "Narrower channels, count changes at fixed footprint and total flow"),
    ("G2_shallow", 543, "Shallower channels at fixed width, webs and total flow"),
    ("G3_thicker_web", 623, "Thicker webs and fewer channels at fixed footprint"),
    ("G4_thicker_base", 613, "Base conduction and spreading sensitivity"),
    ("M1_lower_conductivity", 602, "Material-property sensitivity without changing geometry"),
    ("F1_double_flow", 605, "Flow-only control, same geometry as the fixed-flow winner"),
]
DESIGN_KEYS = tuple(ColdPlateDesign.__dataclass_fields__)
METRICS = ["peak_base_c", "outlet_c", "pressure_pa", "friction_pressure_pa",
           "minor_pressure_pa", "thermal_resistance_k_w", "reynolds", "hydraulic_w"]


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def prepare(output, root=ROOT):
    for path, expected in PINNED_SHA256.items():
        if hashlib.sha256((root/path).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Source changed: {path}. Review provenance and selection before updating pins.")
    winners = json.loads((root / "results/cold_plate/grid_winners.json").read_text())
    nominal = next(r for r in winners if r["case"]["name"] == "nominal")
    case = nominal["case"]
    with (root / "results/cold_plate/grid.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    output = Path(output)
    records = []
    for name, candidate, reason in SELECTION:
        matches = [(line, r) for line, r in enumerate(rows, 2)
                   if r["case"] == "nominal" and int(r["candidate_id"]) == candidate]
        if len(matches) != 1:
            raise ValueError(f"Expected one recorded nominal candidate {candidate}")
        line, row = matches[0]
        design = {key: float(row[key]) for key in DESIGN_KEYS}
        calculated = evaluate_design(ColdPlateCase(**case), ColdPlateDesign(**design))
        for key in METRICS:
            if abs(calculated[key] - float(row[key])) > 1e-9 * max(1, abs(calculated[key])):
                raise ValueError(f"Recorded result mismatch: {name}/{key}")
        if name == "N0_nominal" and design != nominal["design"]:
            raise ValueError("Nominal selection no longer matches grid_winners.json")
        n = calculated["channel_count"]
        L, W = case["length_mm"] / 1000, case["plate_width_mm"] / 1000
        w, d, s, t = [design[k] / 1000 for k in
                       ("width_mm", "depth_mm", "web_mm", "base_mm")]
        margin = (W - n*w - (n-1)*s) / 2
        qv = design["flow_lpm"] / 60000
        spec = {
            "schema_version": 1, "case_id": name,
            "status": "Prepared geometry and analytical inputs only. CFD not performed.",
            "provenance": {"repository": "Grace-Fokam/fovra-v0", "commit": SOURCE_COMMIT,
                           "path": "results/cold_plate/grid.csv", "csv_line": line,
                           "recorded_case": "nominal", "candidate_id": candidate},
            "selection_reason": reason, "recorded_case": case, "recorded_design": design,
            "geometry_m": {"length": L, "width": W, "channel_width": w,
                           "channel_depth": d, "web": s, "base": t, "side_margin": margin,
                           "channel_count": n, "modeled_height": t+d,
                           "screening_cover_thickness_not_meshed": case["cover_mm"]/1000},
            "solid": {"conductivity_w_mk": design["conductivity_w_mk"],
                      "isotropic": True, "alloy": None, "density_kg_m3": None,
                      "cp_j_kgk": None},
            "fluid_constant": {"rho_kg_m3": case["rho_kg_m3"], "mu_pa_s": case["mu_pa_s"],
                               "cp_j_kgk": case["cp_j_kgk"], "k_w_mk": case["coolant_k_w_mk"]},
            "boundary_inputs": {"heat_w": case["heat_w"], "heat_flux_w_m2": case["heat_w"]/(L*W),
                                "inlet_k": case["inlet_c"]+273.15, "total_flow_m3_s": qv,
                                "channel_flow_m3_s": qv/n, "inlet_velocity_m_s": qv/(n*w*d),
                                "total_mass_flow_kg_s": qv*case["rho_kg_m3"],
                                "outlet_gauge_pressure_pa": 0},
            "idealizations": {"lid": "zero-thickness, no-slip, adiabatic wall",
                               "heat_source": "uniform flux over entire underside",
                               "inlet": "uniform axial velocity imposed on every channel mouth",
                               "outer_solid": "adiabatic except heated underside",
                               "gravity": "omitted in baseline", "roughness": "smooth walls",
                               "viscous_heating": "off in baseline, explicit sensitivity only"},
            "unknown_partner_inputs": {key: None for key in
                ["headers", "ports", "seal_geometry", "lid_material_and_bond", "heat_map",
                 "chip_contact_footprint", "interface_resistance", "coolant_composition",
                 "operating_absolute_pressure", "surface_roughness", "tolerances", "orientation"]},
            "analytical": {"fluid_volume_m3": n*L*w*d,
                           "solid_volume_m3": L*W*(t+d)-n*L*w*d,
                           "inlet_area_m2": n*w*d, "heater_area_m2": L*W,
                           "interface_area_m2": n*L*(w+2*d),
                           "roof_area_m2": n*L*w,
                           "outlet_c_no_viscous_heating": case["inlet_c"]+case["heat_w"]/(case["rho_kg_m3"]*qv*case["cp_j_kgk"])},
            "recorded_reduced_order": {key: float(row[key]) for key in METRICS},
            "cfd_results": None,
        }
        write_json(output / "cases" / f"{name}.json", spec)
        records.append({"case_id": name, "candidate_id": candidate, **design,
                        "channel_count": n, **spec["recorded_reduced_order"], "reason": reason})
    with (output / "comparison_set.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=records[0].keys(), lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)
    write_json(output / "source_manifest.json", {
        "commit": SOURCE_COMMIT,
        "files": PINNED_SHA256,
        "selection": SELECTION,
    })
    return records


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "cfd/cold_plate/inputs")
    args = parser.parse_args()
    print(json.dumps(prepare(args.output), indent=2))
