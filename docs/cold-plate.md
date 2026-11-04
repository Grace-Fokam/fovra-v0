# Cold-plate geometry prototype

This experiment searches the **dimensions of a straight-channel liquid cold plate** using an unvalidated reduced-order model. The goal is to pick candidates for higher-fidelity study. It doesn't discover new channel layouts or materials, establish patent novelty, or demonstrate hardware performance.

It runs separately from the data-center cooling dashboard and its results.

## Reproduce

From the repo root, with Python 3.10+:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q
validation_dir="$(mktemp -d)"
python benchmark_cold_plate.py --output "$validation_dir/cold_plate"
```

The recorded results used **Python 3.12** and `requirements-cold-plate.txt`. The default benchmark runs four cases, six seeds, and 32 simulator calls per method. For a quick smoke test: `python benchmark_cold_plate.py --output /tmp/cold-plate-smoke --seeds 11 --budget 12`. Timings vary by machine, and package versions can change random-forest decisions. Metadata records source hashes, package versions, every candidate, and all case settings. Wall-clock times are kept out of the scientific CSVs so those can be checked exactly.

To confirm an exact match with `results/cold_plate/`, use the [pinned replay check](cold-plate-reproducibility.md) (Python 3.12.14 with the recorded packages), then run `python check_cold_plate_reproducibility.py --actual "$validation_dir/cold_plate"`. It compares the seven scientific outputs, skips `timings.csv` and `metadata.json`, shows per-file diffs, and never changes the committed results.

To evaluate one design without a search:

```python
from cold_plate import ColdPlateCase, ColdPlateDesign, evaluate_design

result = evaluate_design(
    ColdPlateCase(heat_w=100, inlet_c=25),
    ColdPlateDesign(width_mm=0.3, depth_mm=1.2, web_mm=0.4,
                    base_mm=1, flow_lpm=0.2, conductivity_w_mk=390),
)
print(result)
```

Temperatures are **modeled cold-plate base or bulk-water temperatures**, not chip junction temperatures. `feasible` means the design passes this model's operating, geometry, and correlation-range checks. It isn't a hardware certification.

## Component, design space, and loads

The coupon is 100 mm long and 50 mm wide, with parallel smooth rectangular channels cut into a conductive base and closed by an ideal insulated lid. Heat is spread evenly over the 50 cm² footprint. The model assumes 1 mm minimum side margins and a 1 mm cover, equal flow in every channel, and no designed ports or headers.

The nominal 100 W load is only **2 W/cm²**, on purpose. The higher-load case is 150 W (3 W/cm²). Neither represents a modern high-power GPU or its hotspots.

| Variable | Search values | What it affects |
| --- | --- | --- |
| Channel width `w` | 0.2, 0.3, 0.5, 0.8 mm | Flow area, hydraulic diameter, wall area |
| Channel depth `d` | 0.8, 1.2, 1.8 mm | Flow area and fin height |
| Web thickness `s` | 0.2, 0.4, 0.8 mm | Channel spacing and count, fin conduction |
| Base thickness `t` | 1, 2 mm | Conduction through the base, total height |
| Total water flow | 0.05, 0.1, 0.2, 0.4, 0.8 L/min | Heat capacity rate, velocity, pumping |
| Solid conductivity `k_s` | 167, 390 W/(m K) | Typical conductive-metal values, not certified alloy specs |

Pitch is `w+s`. Channel count is `floor((W−2e+s)/(w+s))` and occupied width is `Nw+(N−1)s`, with any leftover going to the side margins. The model requires positive finite inputs, a 0.2 mm minimum feature, at least two channels, `1 ≤ d/w ≤ 6`, and `t+d+cover ≤ 5 mm`. These are **screening rules we chose**, not machining limits. The aspect-ratio rule also keeps the thermal correlation in its supported orientation, with the insulated lid spanning the channel width.

The full grid has **660 candidates**. A fourth case holds flow at 0.2 L/min and searches **132 geometry/material combinations** to separate out the effect of flow. Conductivity and base thickness carry no cost, structural, or embodied-carbon penalty, so high conductivity and thin bases win easily.

| Case | Heat | Inlet water | Base limit | Candidates |
| --- | ---: | ---: | ---: | ---: |
| nominal | 100 W | 25°C | 45°C | 660 |
| higher_load | 150 W | 25°C | 45°C | 660 |
| warm_inlet | 100 W | 30°C | 45°C | 660 |
| fixed_flow_geometry | 100 W | 25°C | 45°C | 132, all at 0.2 L/min |

Every case caps pressure drop at 20 kPa and plate-level pump electricity at 0.5 W. These are illustrative, not customer requirements. The model assumes 40% pump efficiency, 24 hours of operation, and $0.15/kWh electricity. Water properties are fixed at approximate room-temperature values (density 997 kg/m³, viscosity 0.00089 Pa s, specific heat 4181 J/(kg K), conductivity 0.607 W/(m K)). They're configurable but not temperature-dependent.

## Thermal and hydraulic model

Everything is computed in SI units. Flow in L/min is converted to m³/s and split evenly across `N` parallel channels, which all share the same pressure drop (it is **not added in series**).

```text
Vdot = flow_lpm / 60000
u = Vdot / (N w d)
Dh = 2 w d / (w+d)
Re = rho u Dh / mu
Pr = cp mu / k_water
```

For `a=w/d` in `(0,1]`, the fully developed laminar polynomial for rectangular ducts gives the **Darcy** (not Fanning) friction factor:

```text
f_D Re = 96 (1 − 1.3553a + 1.9467a² − 1.7012a³ + 0.9564a⁴ − 0.2537a⁵)
dp_friction = f_D (L/Dh) rho u² / 2
dp_minor = K rho u² / 2
dp = dp_friction + dp_minor
P_hydraulic = dp Vdot
P_electric = P_hydraulic / eta_pump
```

`K=2` is an adjustable entrance/exit loss based on channel velocity. It isn't a fitted manifold model and doesn't fully capture developing-flow losses. Tests check the polynomial against the exact infinite-series solution for rectangular ducts, including the square-channel limit `f_D Re ≈ 56.91`.

For **three heated walls with an insulated cover**, the model uses:

```text
Nu = 8.235 (1 − 1.883a + 3.767a² − 5.814a³ + 5.361a⁴ − 2a⁵)
h = Nu k_water / Dh
m = sqrt(2h / (k_s s))
eta_fin = tanh(m d) / (m d)
A_effective = N L (w + 2 eta_fin d)
R_convection = 1 / (h A_effective)
R_base = t / (k_s W L)
```

The cover adds no heated area. Each web is treated as a straight fin with an insulated tip, and the outer side walls use the same efficiency. Pairing the ideal duct correlation with fin efficiency is a **reduced-order stand-in for conjugate heat transfer**, not an exact solution.

Peak temperature combines the outlet water temperature with the local film and base resistance:

```text
T_out = T_in + (Q_heat + P_hydraulic) / (rho Vdot cp)
T_base_peak_proxy = T_out + Q_heat (R_base + R_convection)
R_thermal_reported = (T_base_peak_proxy − T_in) / Q_heat
```

The inlet is measured at the plate, after the pump. Pressure work across the plate heats the coolant; external motor losses are outside the model. With uniform heating and constant local resistance, the outlet is the hottest point. Ignoring entrance-region heat-transfer enhancement tends to raise this estimate for the ideal duct, **but it isn't a guaranteed conservative bound for real hardware**: spreading, contact resistance, uneven flow, and hotspots can all raise real temperatures.

Energy is pump electric power × hours / 1000. `heat_removed_kwh` is the imposed component heat, not electricity used. The pump estimate covers the plate only. It leaves out pump overhead, pipes, filters, connectors, headers, the CDU, heat rejection, fans, and chillers, so these small numbers shouldn't be presented as real pump electricity or facility savings. Recirculating coolant isn't water consumption, which this experiment doesn't model.

## Model limits

Designs outside these limits stay in the CSV with a reason, but can't be returned as feasible.

- `Re ≤ 2000`, a conservative laminar cutoff. There's no transitional or turbulent model.
- Hydrodynamic entry length `0.05 Re Dh` must be at most 10% of channel length, so fully developed friction applies.
- Thermal entry length `0.1 Re Pr Dh` must be no longer than the channel, so the outlet estimate holds up for screening. These entry-length rules are heuristics, not error bounds, and flow upstream can still be thermally developing.
- Inlet water must be at least 20°C and outlet water at most 40°C. Viscosity still changes a lot over this range, so temperature-dependent properties are needed before using the numbers quantitatively.

The model also ignores uneven heat flux, heat spreading, chip/package/TIM contact resistance, heat flow through the cover, full inlet/outlet geometry, uneven channel flow, roughness, fouling, corrosion, coolant additives, erosion, boiling, leaks, plate deflection, sealing, bonding, tolerances, and reliability. A design outside the limits might still work physically, but this model can't say so, and a design inside them still needs validation.

The grid isn't a claim of innovation. It searches a familiar channel family and often picks values at the edge of the grid. Those results suggest where to extend the model or the design space; they aren't proof of a new optimum.

## Search setup and results

The objective is the **lowest plate-level pump electricity that meets the constraints**. Temperature, pressure, thermal resistance, energy, feasibility, and the temperature/pump Pareto set are reported separately.

Random search samples without replacement. Both methods start from the same eight random designs for each case and seed, and each gets exactly 32 simulator calls, counting failed evaluations and the starting designs. Seeds are 11, 22, 33, 44, 55, and 66.

The learned method fits a 64-tree random forest to its own completed results only. It predicts temperature, pressure, pump power, outlet temperature, Reynolds number, and entry-length fractions, with output scaling taken from observed samples only. It picks the predicted-feasible design with the lowest pump power, or if none look feasible, the one with the smallest total normalized constraint violation. Every fifth query after the start explores the next untested random design instead. Every pick is run through the simulator, and no prediction is ever reported as a result.

The full grid is evaluated separately and hidden from both searches, which make real simulator calls rather than reading from a lookup table. The grid best is optimal **only among these candidates and within this model**. It's used afterward to measure regret and how many evaluations each method needed to get within 5% of it.

Results from the recorded run:

| Case | Surrogate wins / ties / losses vs random | Mean random gap to grid | Mean surrogate gap to grid | Runs within 5% of grid, random / surrogate |
| --- | --- | ---: | ---: | --- |
| nominal | 5 / 1 / 0 | 117.4% | 0.0% | 1/6 / 6/6 |
| higher_load | 4 / 1 / 1 | 163.9% | 51.4% | 1/6 / 5/6 |
| warm_inlet | 4 / 1 / 1 | 163.9% | 51.4% | 1/6 / 5/6 |
| fixed_flow_geometry | 3 / 3 / 0 | 17.2% | 0.0% | 3/6 / 6/6 |

Both methods found feasible designs in all 24 case/seed pairs. Overall the surrogate won **16**, tied **6**, and lost **2**. The relative gaps are large because they divide by very small pump-power values (absolute values are in the CSVs), and one bad run moves the mean a lot. The higher-load and warm-inlet cases end up with nearly the same feasible sets and identical outcomes, so they shouldn't count as separate evidence. Six fixed seeds make this an initial benchmark, not a statistically significant or held-out result.

| Grid-best design | Nominal, variable flow | Nominal, fixed flow |
| --- | ---: | ---: |
| Width / depth / web / base | 0.8 / 1.8 / 0.2 / 1.0 mm | Same |
| Channel count | 48 | 48 |
| Conductivity | 390 W/(m K) | Same |
| Flow | 0.1 L/min | 0.2 L/min |
| Peak base proxy | 41.386°C | 34.189°C |
| Pressure drop | 56.471 Pa | 114.102 Pa |
| Plate-only pump electricity | 0.235 mW | 0.951 mW |

For comparison, an arbitrary reference design (0.3 mm width, 1.2 mm depth, 0.4 mm web, 1 mm base, 390 W/(m K)) at the same 0.2 L/min reaches 33.022°C with a 1908.324 Pa pressure drop. The grid's fixed-flow pick trades a bit more temperature for much lower pressure drop while staying under the limit. The reference isn't a commercial product or an optimized baseline.

The run used **1,536 search calls**, **2,112 grid calls**, four reference-design calls, and 20 sensitivity calls. On this machine, the full grid took about 0.05 seconds, the 24 surrogate runs about 22.31 seconds, and the random runs about 0.09 seconds, with search time including model fitting. **For a model this cheap, exhaustive search is the practical choice.** The surrogate is set up for future expensive CFD or lab evaluations; it isn't a demonstrated speedup.

The sensitivity check re-evaluates each grid winner with heat-transfer multipliers of 0.7, 1.0, and 1.3 and loss coefficients of 0, 2, and 5, one at a time. All stayed feasible in the model. These are arbitrary perturbations, not calibrated uncertainty bounds, and they don't cover the physics the model leaves out.

## Files and tests

| File | Contents |
| --- | --- |
| `cold_plate.py` | Physics model and feasibility checks |
| `cold_plate_search.py` | Equal-budget random and learned search |
| `benchmark_cold_plate.py` | Cases, grid reference, traces, timing, sensitivity, provenance |
| `tests/test_cold_plate.py` | Analytical limits, independent pressure solution, conservation, constraints, query counting, reproducibility |
| `results/cold_plate/grid.csv` | Every case and candidate, including failures and Pareto flags |
| `results/cold_plate/search_trials.csv` | Every queried design and the best feasible result after each call |
| `results/cold_plate/search_summary.csv` | Best verified results, feasibility, calls to target, gaps to grid |
| `results/cold_plate/paired_comparison.csv` | Every win/tie/loss, including failed methods |
| `results/cold_plate/timings.csv` | Wall-clock times, kept separate from the deterministic results |
| `results/cold_plate/reference_design.csv` | The arbitrary reference design under each case |
| `results/cold_plate/sensitivity.csv` | Grid-winner sensitivity to heat transfer and minor losses |
| `results/cold_plate/grid_winners.json` | Dimensions, operating conditions, and diagnostics for CFD handoff |
| `results/cold_plate/metadata.json` | Inputs, budgets, environment, and source hashes |

The tests confirm the math is implemented consistently; they don't validate the physics. All 106 tests pass, including the original 73 and 33 new cold-plate tests. The new tests also cover cases with no feasible design, geometry-failure accounting, identical starting designs, no repeated queries, and finding the best design in small exhaustive searches.

## Before any hardware claim

1. **Thermal-engineering review:** Replace the illustrative requirements with a real heat map, package stack, inlet conditions, material spec, temperature limits, pressure budget, and pump curve. Review the correlation boundary conditions and units. Have a machining or bonding partner assess the channels, wall strength, sealing, roughness, and tolerances.
2. **Conjugate CFD:** Model the base, fins, lid, real headers and ports, temperature-dependent coolant properties, and uneven heating. Check mesh independence, conservation, entrance effects, pressure losses, and flow distribution. Test a preregistered set that spans the design space and the model's limits, including weak candidates, and use the discrepancies to revise the model and define where it's valid.
3. **Bench tests:** Build a small set that includes the reference and distinct tradeoff candidates. Use calibrated temperature, flow, pressure, and heater-power measurements, and characterize insulation and heat losses. Repeat across conditions, quantify uncertainty, and measure real pump electrical input separately from hydraulic power. Report thermal-resistance and pressure curves with uncertainty, not just a best point.
4. **A fair expensive-evaluation comparison:** Fix algorithms and budgets before running CFD or hardware tests. Include random search, a conventional constrained optimizer or space-filling design, and eventually a strong Bayesian-optimization baseline. Keep calibration data separate from held-out shapes and conditions. Count failures, meshing, solver retries, parallelism, and wall time, and don't claim gains smaller than the measurement or model uncertainty.

Later designs could vary channel routing, manifolds, ribs, or branching. Those would need new heat-transfer and flow treatment or CFD, not just new shape variables in these straight-duct correlations.

## Sources

- R. K. Shah and A. L. London, *Laminar Flow Forced Convection in Ducts*, Academic Press (1978). Source of the rectangular-duct correlations. The Darcy factor used here is four times the Fanning convention. The friction relation is also given in [this University of Illinois report, §2.1.2](https://www.ideals.illinois.edu/items/11059/bitstreams/40706/data.pdf).
- D. J. G. Kuiphuis et al. (2025), [Thermal-hydrodynamic modeling and design for microchannel cold plates subjected to multiple heat sources](https://doi.org/10.1016/j.applthermaleng.2024.125220) ([author copy](https://ris.utwente.nl/ws/portalfiles/portal/480381856/1-s2.0-S1359431124028886-main.pdf)), equations 42–43 and the modeling discussion. Used to check the three-wall Nusselt polynomial and distinguish it from four-wall heating. This prototype does **not** implement that paper's full model or inherit its validation.
- P.-S. Lee and S. V. Garimella (2006), [Thermally Developing Flow and Heat Transfer in Rectangular Microchannels of Different Aspect Ratios](https://docs.lib.purdue.edu/coolingpubs/23/), DOI 10.1016/j.ijheatmasstransfer.2006.02.011. Shows why entrance effects and heating boundary conditions need explicit treatment. Its developing-flow correlations aren't implemented here.
- [NIST Chemistry WebBook, thermophysical properties of fluid systems](https://webbook.nist.gov/chemistry/fluid/), a possible source for replacing the fixed water properties with temperature-dependent ones. The rounded defaults are assumptions, not values from a specific dataset.

None of these sources validate this implementation or its selected designs.
