"""Presentation helpers for the cold-plate model and immutable experiment files."""

from dataclasses import asdict, replace
import json
from math import isclose
from pathlib import Path

import pandas as pd

from cold_plate import ColdPlateDesign, evaluate_design
from cold_plate_search import best_verified

RESULTS_DIR = Path(__file__).resolve().parent / "results" / "cold_plate"
METHOD_LABELS = {"random": "Random search", "surrogate": "Surrogate-assisted search"}
CASE_LABELS = {
    "nominal": "Nominal · 100 W / 25°C",
    "higher_load": "Higher load · 150 W / 25°C",
    "warm_inlet": "Warm inlet · 100 W / 30°C",
    "fixed_flow_geometry": "Fixed flow · 100 W / 25°C / 0.2 L/min",
}
VIOLATIONS = {
    "minimum_feature": "A feature is below the model's 0.2 mm minimum.",
    "channel_aspect": "Channel depth / width must be between 1 and 6.",
    "stack_height": "Base + channel + cover exceeds the 5 mm height limit.",
    "channel_count": "Fewer than two parallel channels fit.",
    "nonlaminar": "Reynolds number exceeds the model's 2,000 laminar cutoff.",
    "hydrodynamic_entry": "Hydrodynamic entry length exceeds 10% of channel length.",
    "thermal_entry_at_outlet": "Thermal entry length exceeds channel length.",
    "constant_property_envelope": "Fixed water properties require inlet ≥20°C and outlet ≤40°C.",
    "base_temperature": "Modeled peak base temperature exceeds the operating limit.",
    "pressure_drop": "Modeled pressure drop exceeds the operating limit.",
    "pump_power": "Modeled plate-only pump electricity exceeds the operating limit.",
}


def load_recorded_results(directory=RESULTS_DIR):
    """Read only. Paths are anchored to this module, independent of launch cwd."""
    directory = Path(directory)
    metadata = json.loads((directory / "metadata.json").read_text())
    winners = json.loads((directory / "grid_winners.json").read_text())
    data = {name: pd.read_csv(directory / f"{name}.csv") for name in
            ("grid", "search_trials", "search_summary", "paired_comparison", "timings")}
    required = {
        "grid": {"case_id", "candidate_id", "geometry_ok", "domain_ok", "feasible",
                 "peak_base_c", "pressure_pa", "pump_w"},
        "search_trials": {"case_id", "seed", "method", "evaluation", "feasible",
                          "candidate_id", "peak_base_c", "pressure_pa", "pump_w", "best_pump_w_so_far"},
        "search_summary": {"case_id", "seed", "method", "best_pump_w"},
        "paired_comparison": {"surrogate_outcome"},
        "timings": {"case_id", "method", "elapsed_s", "evaluations"},
    }
    for name, columns in required.items():
        if data[name].empty or not columns.issubset(data[name].columns):
            raise ValueError(f"Recorded {name} is empty or missing required columns")
    if not metadata["experiments"] or not winners or metadata["budget"] < 1:
        raise ValueError("Recorded experiment metadata is incomplete")
    return {**data, "metadata": metadata, "winners": winners}


def comparison_results(case, designs):
    """Reevaluate every design at the same case; fixed-flow means exactly 0.2 L/min."""
    rows = []
    for label, design in designs:
        if case.name == "fixed_flow_geometry":
            design = replace(design, flow_lpm=0.2)
        rows.append({"design": label, "case": case.name, **asdict(case),
                     **evaluate_design(case, design)})
    return pd.DataFrame(rows)


def budget_snapshot(trials, case_id, budget):
    """Best simulator-verified candidate per method/seed at a trace prefix."""
    selected = trials[(trials.case_id == case_id) & (trials.evaluation <= budget)]
    rows = []
    for (seed, method), part in selected.groupby(["seed", "method"], sort=True):
        best = best_verified(part.to_dict("records"))
        rows.append({"seed": seed, "method": method, "evaluations": len(part),
                     "feasible_observations": int(part.feasible.sum()),
                     "found_feasible": best is not None,
                     **{key: best[key] if best else None for key in
                        ("candidate_id", "peak_base_c", "pressure_pa", "pump_w")}})
    return pd.DataFrame(rows)


def paired_outcomes(snapshot):
    outcomes = []
    for _, part in snapshot.groupby("seed"):
        by_method = part.set_index("method")
        a, r = by_method.loc["surrogate"], by_method.loc["random"]
        if not a.found_feasible and not r.found_feasible:
            outcome = "neither_feasible"
        elif not a.found_feasible:
            outcome = "loss"
        elif not r.found_feasible:
            outcome = "win"
        elif isclose(a.pump_w, r.pump_w, rel_tol=1e-9, abs_tol=1e-12):
            outcome = "tie"
        else:
            outcome = "win" if a.pump_w < r.pump_w else "loss"
        outcomes.append(outcome)
    return pd.Series(outcomes).value_counts().to_dict()


def geometry_svg(case, design, result):
    """Dimensioned geometry only. Color is categorical, never a thermal field."""
    if not result["geometry_ok"]:
        return None
    count = result["channel_count"]
    margin = (case.plate_width_mm - result["active_width_mm"]) / 2
    scale = 5.4
    x, y = 70, 95
    length, width = case.length_mm * scale, case.plate_width_mm * scale
    channels = "".join(
        f'<rect class="channel" x="{x}" y="{y+(margin+i*(design.width_mm+design.web_mm))*scale:.3f}" '
        f'width="{length}" height="{design.width_mm*scale:.3f}"/>' for i in range(count)
    )
    # A three-channel periodic detail, enlarged equally in both axes.
    pitch = design.width_mm + design.web_mm
    detail_width = 3 * design.width_mm + 4 * design.web_mm
    height = design.base_mm + design.depth_mm + case.cover_mm
    zoom = min(225 / detail_width, 165 / height)
    dx, dy = 720, 140
    cavities = "".join(
        f'<rect class="channel" x="{dx+(design.web_mm+i*pitch)*zoom:.3f}" '
        f'y="{dy+case.cover_mm*zoom:.3f}" width="{design.width_mm*zoom:.3f}" '
        f'height="{design.depth_mm*zoom:.3f}"/>' for i in range(3)
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 455" role="img" aria-labelledby="title desc">
<title id="title">Cold-plate plan and enlarged channel section</title>
<desc id="desc">{count} parallel channels, each {design.width_mm:g} mm wide and {design.depth_mm:g} mm deep.
Plate {case.length_mm:g} by {case.plate_width_mm:g} mm. Base {design.base_mm:g} mm. Web {design.web_mm:g} mm.
Geometry only, no simulated temperature field.</desc>
<style>text{{font-family:Arial,sans-serif;fill:#cbd5e1;font-size:13px}} .label{{fill:#f8fafc;font-size:16px;font-weight:600}}
.channel{{fill:#40c6c4}} .dim{{stroke:#899eb1;stroke-width:1;fill:none}}</style>
<rect width="1000" height="455" rx="18" fill="#102738"/>
<text x="35" y="35" class="label">01 / PLAN VIEW</text><text x="680" y="35" class="label">02 / CHANNEL SECTION</text>
<text x="35" y="57">Cover removed · geometry to scale</text><text x="680" y="57">Three-channel detail · enlarged to scale</text>
<rect x="{x}" y="{y}" width="{length}" height="{width}" fill="#b7c7d2"/>{channels}
<path class="dim" d="M {x} 79 V 70 H {x+length} V 79"/>
<text x="{x+length/2}" y="66" text-anchor="middle">{case.length_mm:g} mm</text>
<path class="dim" d="M 55 {y} H 46 V {y+width} H 55"/>
<text x="30" y="{y+width/2}" text-anchor="middle" transform="rotate(-90 30 {y+width/2})">{case.plate_width_mm:g} mm</text>
<path d="M 230 390 H 430 l -9 -5 m 9 5 l -9 5" stroke="#40c6c4" fill="none" stroke-width="2"/>
<text x="330" y="415" text-anchor="middle">Parallel water flow → · {design.flow_lpm:g} L/min total</text>
<text x="680" y="100">w {design.width_mm:g} · d {design.depth_mm:g} · web {design.web_mm:g} mm</text>
<rect x="{dx}" y="{dy}" width="{detail_width*zoom}" height="{height*zoom}" fill="#b7c7d2"/>{cavities}
<text x="680" y="335">Base {design.base_mm:g} mm · insulated cover {case.cover_mm:g} mm</text>
<text x="680" y="359">{count} channels · side margins {margin:.2f} mm</text>
<text x="680" y="383">Solid conductivity {design.conductivity_w_mk:g} W/(m·K)</text>
<text x="680" y="415">Schematic geometry · no headers or ports</text></svg>'''
