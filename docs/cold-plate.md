# Cold-plate geometry research prototype

This experiment searches the **physical dimensions of a straight-channel liquid cold plate**. It is an unvalidated reduced-order research model, intended to choose candidates for higher-fidelity investigation. It does not discover new channel topologies, invent materials, establish patent novelty, or demonstrate hardware performance.

The existing tank, adaptation, and data-center cooling experiments remain independent. This addition is a command-line experiment. It does not change their dashboard, physics, recorded results, or models. The starting point is cooling PR #10, commit `ce12821da8b12acd26e2963cbdfab2f8cd0a2e53`.

## Reproduce

From the repository root, with Python 3.10 or newer:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q
python benchmark_cold_plate.py --output results/cold_plate
```

For the recorded numerical environment, use **Python 3.12** and `python -m pip install -r requirements-cold-plate.txt`. The default benchmark has four cases, six seeds, and a budget of 32 calls per method. A shorter smoke run is `python benchmark_cold_plate.py --output /tmp/cold-plate-smoke --seeds 11 --budget 12`. Timings vary by machine. Version changes can alter random-forest decisions. Metadata records source hashes, package versions, every candidate, and all case settings. Scientific CSVs exclude wall-clock measurements so their reproducibility can be checked separately.

A single design can also be evaluated without running a search:

```python
from cold_plate import ColdPlateCase, ColdPlateDesign, evaluate_design

result = evaluate_design(
    ColdPlateCase(heat_w=100, inlet_c=25),
    ColdPlateDesign(width_mm=0.3, depth_mm=1.2, web_mm=0.4,
                    base_mm=1, flow_lpm=0.2, conductivity_w_mk=390),
)
print(result)
```

All returned temperatures are **modeled cold-plate base or bulk-water temperatures**, not semiconductor junction temperatures. `feasible` means passing this model's operating, geometry, and correlation-domain checks. It is not a hardware certification.

## Component, design space, and loading

A 100 mm long × 50 mm wide coupon contains parallel, smooth rectangular channels machined into a conductive base and closed by an ideal adiabatic lid. Heat is distributed uniformly over the entire 50 cm² footprint. Two 1 mm minimum side margins and a 1 mm cover are assumed. Ports and headers are not designed. Equal channel flow is imposed.

The nominal 100 W load is only **2 W/cm²**, intentionally modest. The higher-load case is 150 W, or 3 W/cm². These loads do not represent a current high-power GPU package or its nonuniform hotspots.

| Variable | Search values | Physical role |
| --- | --- | --- |
| Channel width `w` | 0.2, 0.3, 0.5, 0.8 mm | Flow area, hydraulic diameter, wall area |
| Channel depth `d` | 0.8, 1.2, 1.8 mm | Flow area and fin height |
| Web thickness `s` | 0.2, 0.4, 0.8 mm | Channel spacing, channel count, fin conduction |
| Base thickness `t` | 1, 2 mm | Through-thickness conduction and total height |
| Total water flow | 0.05, 0.1, 0.2, 0.4, 0.8 L/min | Heat capacity rate, velocity, pumping |
| Solid conductivity `k_s` | 167, 390 W/(m K) | Representative conductive-metal values, not certified alloy specifications |

The pitch is `w+s`. Channel count is `floor((W−2e+s)/(w+s))`, and occupied width is `Nw+(N−1)s`. Any remainder is allocated to the side margins. The model checks positive finite inputs, a 0.2 mm minimum feature, at least two channels, `1 ≤ d/w ≤ 6`, and `t+d+cover ≤ 5 mm`. These are **chosen screening rules**, not a machinist's manufacturing limits. The aspect-ratio restriction also keeps the thermal correlation in its supported orientation: the adiabatic lid spans the channel width.

The resulting full grid has **660 distinct candidates**. A fourth experiment holds flow at 0.2 L/min and searches **132 geometries/material settings**. This controls for the contribution of flow changes. Conductivity and base thickness are not assigned a purchase cost, structural penalty, or embodied-carbon score. High conductivity and thin bases can therefore be favored trivially.

| Case | Heat | Inlet water | Base limit | Candidates |
| --- | ---: | ---: | ---: | ---: |
| nominal | 100 W | 25°C | 45°C | 660 |
| higher_load | 150 W | 25°C | 45°C | 660 |
| warm_inlet | 100 W | 30°C | 45°C | 660 |
| fixed_flow_geometry | 100 W | 25°C | 45°C | 132, all at 0.2 L/min |

Every case limits pressure drop to 20 kPa and plate-attributable pump electricity to 0.5 W. These are illustrative constraints, not customer requirements. Assumed pump efficiency is 40%, operating duration 24 hours, and electricity price $0.15/kWh. Fluid properties are frozen at approximate room-temperature water values: density 997 kg/m³, viscosity 0.00089 Pa s, specific heat 4181 J/(kg K), and conductivity 0.607 W/(m K). They are configurable, and not a full water-property implementation.

## Thermal and hydraulic relationships

Calculations use SI units internally. The supplied L/min flow is converted to m³/s and divided across `N` parallel channels. All channels share the same pressure drop. Their pressure drops are **not added in series**.

```text
Vdot = flow_lpm / 60000
u = Vdot / (N w d)
Dh = 2 w d / (w+d)
Re = rho u Dh / mu
Pr = cp mu / k_water
```

For `a=w/d` in `(0,1]`, the rectangular fully developed laminar Poiseuille polynomial gives the **Darcy**, not Fanning, friction factor:

```text
f_D Re = 96 (1 − 1.3553a + 1.9467a² − 1.7012a³ + 0.9564a⁴ − 0.2537a⁵)
dp_friction = f_D (L/Dh) rho u² / 2
dp_minor = K rho u² / 2
dp = dp_friction + dp_minor
P_hydraulic = dp Vdot
P_electric = P_hydraulic / eta_pump
```

`K=2` is an exposed entrance/exit-loss assumption referenced to channel velocity. It is not a fitted manifold model and does not account rigorously for developing-flow excess loss. Tests compare the polynomial to the independent rectangular-duct infinite-series solution, including the square-channel `f_D Re ≈ 56.91` limit.

The fully developed **three heated sides with an adiabatic cover** approximation is:

```text
Nu = 8.235 (1 − 1.883a + 3.767a² − 5.814a³ + 5.361a⁴ − 2a⁵)
h = Nu k_water / Dh
m = sqrt(2h / (k_s s))
eta_fin = tanh(m d) / (m d)
A_effective = N L (w + 2 eta_fin d)
R_convection = 1 / (h A_effective)
R_base = t / (k_s W L)
```

The cover contributes no heated area. The web uses a one-dimensional straight-fin approximation with an adiabatic tip. Combining the ideal duct correlation with finite fin efficiency is a **reduced-order approximation to conjugate heat transfer**, not an exact solution of the actual wall boundary conditions. It also approximates the outer side walls using the same web efficiency.

The thermal estimate combines the outlet bulk temperature with the fully developed local film resistance and through-base conduction:

```text
T_out = T_in + (Q_heat + P_hydraulic) / (rho Vdot cp)
T_base_peak_proxy = T_out + Q_heat (R_base + R_convection)
R_thermal_reported = (T_base_peak_proxy − T_in) / Q_heat
```

The inlet is at the plate, after the external pump. Pressure-work dissipation across the plate is included in bulk coolant heating. External motor losses are outside this boundary. The imposed uniform axial heat input and constant local resistance make the outlet the hottest modeled location. Ignoring entrance heat-transfer enhancement tends to raise this temperature estimate for the ideal duct problem, **but this is not a guaranteed conservative bound for real hardware**: spreading, contacts, maldistribution, and hotspots can increase real temperatures.

The energy output is pump electric power × hours / 1000. `heat_removed_kwh` is imposed component heat, not electrical consumption. The plate-only pump estimate excludes the pump's fixed overhead, pipes, filters, connectors, headers, CDU, heat rejection, fans, and chillers. Consequently, very small pump numbers must not be presented as real pump electricity or facility energy savings. Recirculating liquid volume is not consumptive water use, which this experiment does not model.

## Correlation domain and omissions

Domain failures remain in the CSV with explicit reasons, but cannot be returned as feasible recommendations.

- `Re ≤ 2000` is a conservative laminar screening cutoff. There is no transition/turbulent interpolation.
- Estimated hydrodynamic entry length `0.05 Re Dh` must be no more than 10% of channel length, limiting use of fully developed friction.
- Estimated thermal entry length `0.1 Re Pr Dh` must be no greater than channel length, so the outlet approximation is defensible as a screening model. These entrance-length estimates and cutoff rules are heuristics, not error guarantees. Upstream flow can still be thermally developing.
- Inlet water must be at least 20°C, and predicted outlet water at most 40°C. This is a chosen approximation envelope for fixed properties, not an assertion that viscosity is constant across it. Viscosity changes substantially even within this interval. Temperature-dependent properties are needed before quantitative use.

Other omissions include nonuniform heat flux, lateral and axial spreading, chip/package/TIM contact resistance, conjugate cover conduction, full inlet/outlet geometry, unequal channel flow, roughness, fouling, corrosion, coolant additives, erosion, boiling, leakage, plate deflection, sealing, bonding, tolerances, and reliability. A design outside the envelope might work physically, but this model cannot support it. A design inside the envelope still requires validation.

The dimensional grid itself is not a claim of innovation. It searches a familiar channel family and often selects dimensions at the grid boundary. Such solutions are prompts for model review and design-space extension, not proof of a novel optimum.

## Search protocol and recorded findings

The objective is **minimum plate-attributable pump electric power under the stated constraints**. Temperature, pressure, thermal resistance, energy, feasibility, and the temperature/pump Pareto set are retained separately. The objective does not claim to minimize all metrics simultaneously.

Random search samples without replacement. Both methods receive the same initial eight randomly selected observations for each case and seed. Each gets exactly 32 simulator calls, including failed evaluations and initialization. Seeds are 11, 22, 33, 44, 55, and 66.

The learned method fits a 64-tree random forest only to its completed observations. Outputs are temperature, pressure, pump power, outlet temperature, Reynolds number, and entry-length fractions. Output scaling is estimated from observed samples only. It chooses predicted feasible candidates with the lowest pump power. If none appears feasible, it minimizes the sum of normalized constraint violations. Every fifth post-initial query instead explores the next untested random candidate. Every selected result is checked by the simulator. No surrogate prediction becomes a reported performance result.

The complete grid is evaluated separately and hidden from search. Searches make actual simulator calls and do not access a precomputed lookup table. The grid is an optimum **only within the enumerated candidates and this model**, not a global continuous-design or physical optimum. It is used afterward for regret and evaluations-to-within-5%-of-grid-best metrics.

The recorded run produced:

| Case | Surrogate wins / ties / losses vs random | Mean random gap to grid | Mean surrogate gap to grid | Runs within 5% of grid, random / surrogate |
| --- | --- | ---: | ---: | --- |
| nominal | 5 / 1 / 0 | 117.4% | 0.0% | 1/6 / 6/6 |
| higher_load | 4 / 1 / 1 | 163.9% | 51.4% | 1/6 / 5/6 |
| warm_inlet | 4 / 1 / 1 | 163.9% | 51.4% | 1/6 / 5/6 |
| fixed_flow_geometry | 3 / 3 / 0 | 17.2% | 0.0% | 3/6 / 6/6 |

Both methods found feasible designs in all 24 case/seed pairs. Overall the surrogate won **16**, tied **6**, and lost **2**. Large relative gaps divide by very small plate-only power values. Absolute values are included in the CSVs. A bad run strongly affects the mean. The higher-load and warm-inlet cases induce closely related feasible sets and the same search outcomes. They must not be treated as independent evidence of transfer or generalization. These six fixed seeds are an initial benchmark, not a statistical significance claim or a held-out evaluation of algorithm choices.

| Grid-selected design result | Nominal, variable flow | Nominal, fixed flow |
| --- | ---: | ---: |
| Width / depth / web / base | 0.8 / 1.8 / 0.2 / 1.0 mm | Same |
| Channel count | 48 | 48 |
| Conductivity | 390 W/(m K) | Same |
| Flow | 0.1 L/min | 0.2 L/min |
| Peak base proxy | 41.386°C | 34.189°C |
| Pressure drop | 56.471 Pa | 114.102 Pa |
| Plate-only pump electricity | 0.235 mW | 0.951 mW |

For context, the arbitrary reference geometry (0.3 mm width, 1.2 mm depth, 0.4 mm web, 1 mm base, 390 W/(m K)) at the same 0.2 L/min has a modeled 33.022°C peak and 1908.324 Pa pressure drop. The grid's fixed-flow choice trades a higher temperature for lower hydraulic resistance while remaining below the limit. The reference is not a commercial competitor or an optimized engineering baseline.

The run used **1,536 search calls**, **2,112 separate grid calls**, four reference-design calls, and 20 post-search sensitivity calls. On this execution environment, all full-grid evaluations together took about 0.05 seconds, while the 24 surrogate runs together took about 22.31 seconds. The random runs took about 0.09 seconds in total. Search time includes model fitting and selection. **Exhaustive search is the practical choice for this cheap model.** The surrogate is a working interface for future expensive CFD/measurement evaluations, not a demonstrated computational speedup.

Sensitivity outputs reevaluate each grid winner at heat-transfer multipliers 0.7/1.0/1.3 and at loss coefficients 0/2/5, varying one assumption at a time. All remained model-feasible in this run. These arbitrary perturbations are neither calibrated uncertainty bounds nor a robust optimization result. They exclude the major omitted physics.

## Outputs, tests, and next research gate

| File | Contents |
| --- | --- |
| `cold_plate.py` | Standalone physical model and feasibility checks |
| `cold_plate_search.py` | Equal-budget random and learned search |
| `benchmark_cold_plate.py` | Cases, oracle, traces, timing, sensitivity, provenance |
| `tests/test_cold_plate.py` | Analytical limits, independent pressure solution, conservation, constraints, query accounting, reproducibility |
| `results/cold_plate/grid.csv` | All cases and candidate outputs, including failures and Pareto flags |
| `results/cold_plate/search_trials.csv` | Every queried design and best feasible objective after each call |
| `results/cold_plate/search_summary.csv` | Best verified results, feasibility, query-to-target counts, grid gaps |
| `results/cold_plate/paired_comparison.csv` | All win/tie/loss outcomes, without dropping failed methods |
| `results/cold_plate/timings.csv` | Measured wall-clock time, separate from deterministic results |
| `results/cold_plate/reference_design.csv` | Explicit, arbitrary reference geometry under each case |
| `results/cold_plate/sensitivity.csv` | Selected-design sensitivity to assumed heat transfer and minor losses |
| `results/cold_plate/grid_winners.json` | Dimensions, operating conditions, and diagnostics for CFD handoff |
| `results/cold_plate/metadata.json` | Complete inputs, budgets, environment, and source hashes |

Tests establish mathematical implementation consistency, not physical validation. All 106 tests pass, including the original 73 and 33 new cold-plate tests. The new tests also check no-feasible-design behavior, geometric failure accounting, identical initialization, no repeated queries, and exhaustive small-space recovery.

Before any hardware-performance claim:

1. **Thermal-engineering review:** replace illustrative requirements with an actual heat map, package stack, inlet conditions, material specification, allowable temperatures, pressure budget, and pump curve. Review correlation boundary conditions and units. A machining/bonding partner must assess channels, wall strength, sealing, roughness, and tolerances.
2. **Conjugate CFD:** model the base, fins, lid, real headers and ports, temperature-dependent coolant properties, and nonuniform heating. Check mesh independence, conservation residuals, entrance development, pressure losses, and flow distribution. Evaluate a preregistered set spanning widths, depths, spacings, flow rates, and model-limit boundaries, including poor candidates. Use the resulting discrepancies to revise the model and define an actual validity region.
3. **Bench measurements:** fabricate a small set including a reference and distinct predicted tradeoff candidates. Use calibrated inlet/outlet and base-temperature measurements, flow measurement, pressure taps, heater power measurement, and insulation/loss characterization. Repeat across conditions and quantify uncertainty. Measure real pump electrical input separately from hydraulic power. Report thermal resistance and pressure curves with uncertainty, not only a best point.
4. **A meaningful expensive-evaluation comparison:** lock algorithms and budgets before running CFD or hardware tests. Include random search plus a conventional constrained optimizer or space-filling design, and eventually a stronger Bayesian-optimization baseline. Separate training/calibration from held-out shapes and conditions. Count failures, meshing, solver retries, parallelism, and wall time. Reject claimed gains smaller than physical measurement/model uncertainty.

A later geometry family could vary channel routing, manifolds, ribs, or branching. Those changes require new hydraulic/heat-transfer treatment or CFD rather than inserting shape variables into these straight-duct correlations.

## Sources and how they are used

- R. K. Shah and A. L. London, *Laminar Flow Forced Convection in Ducts*, Academic Press (1978). Source of rectangular-duct analytical correlations. The implemented Darcy factor is four times the Fanning convention. The friction relation is also reproduced in [this University of Illinois research report, §2.1.2](https://www.ideals.illinois.edu/items/11059/bitstreams/40706/data.pdf).
- D. J. G. Kuiphuis et al. (2025), [Thermal-hydrodynamic modeling and design for microchannel cold plates subjected to multiple heat sources](https://doi.org/10.1016/j.applthermaleng.2024.125220), [author-accessible paper](https://ris.utwente.nl/ws/portalfiles/portal/480381856/1-s2.0-S1359431124028886-main.pdf), equations 42–43 and thermal/hydraulic modeling discussion. Used to verify the three-side Nusselt polynomial and distinguish it from four-side heating. This prototype does **not** implement that paper's complete model or inherit its reported validation accuracy.
- P.-S. Lee and S. V. Garimella (2006), [Thermally Developing Flow and Heat Transfer in Rectangular Microchannels of Different Aspect Ratios](https://docs.lib.purdue.edu/coolingpubs/23/), DOI 10.1016/j.ijheatmasstransfer.2006.02.011. Establishes why entrance development and heating boundary conditions need explicit treatment. Its developing-flow correlations are not implemented here.
- [NIST Chemistry WebBook, thermophysical properties of fluid systems](https://webbook.nist.gov/chemistry/fluid/) is a reference route for replacing the frozen water properties with a temperature-dependent model. The rounded defaults are assumptions, not data imported from a specific measurement set.

No source cited here validates this implementation or its selected designs.
