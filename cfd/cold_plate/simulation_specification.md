# Geometry and simulation specification

All parameters described as recorded below come from the repository snapshot in `inputs/source_manifest.json`. They are established inputs to the research model, not confirmed physical specifications. Proposed solver choices are explicitly identified as idealizations.

## Nominal geometry and coordinates

Use x along flow, y across plate width, and z from the heated underside upward. Coordinates here are in metres unless stated otherwise.

| Item | Value | Evidence/status |
| --- | ---: | --- |
| Length L and width W | 0.100 and 0.050 m | Recorded |
| Channel width w and depth d | 0.0008 and 0.0018 m | Recorded |
| Web s and base t | 0.0002 and 0.0010 m | Recorded |
| Number N | 48 | Recorded and independently recomputed from packing rule |
| Occupied channel/web width | 0.0478 m | Nw + (N−1)s |
| Side margin e | 0.0011 m on each side | (W−occupied width)/2 |
| Modeled solid/fluid envelope height | 0.0028 m | t+d, excludes the unmodeled cover |
| Cover allowance in original height screening | 0.0010 m | Recorded screening input, not a lid assembly design |
| Conductivity | 390 W/(m K), constant isotropic | Recorded material proxy, no certified alloy |
| Total flow | 1.6666666667×10⁻⁶ m³/s | Recorded 0.1 L/min, total across all channels |
| Inlet speed | 0.02411265432 m/s | Total flow divided by Nwd |
| Total mass flow with baseline density | 0.001661666667 kg/s | 997 kg/m³ × total volume flow |
| Heat and inlet temperature | 100 W and 298.15 K | Recorded illustrative condition |
| Underside heat flux | 20,000 W/m² | 100 W / 0.005 m² = 2 W/cm² |

Channel i, with i=0…47, occupies x=[0,L], y=[e+i(w+s), e+i(w+s)+w], z=[t,t+d]. The solid is the bounding block [0,L]×[0,W]×[0,t+d] minus the channel volumes. Nominal fluid volume is 6.912×10⁻⁶ m³, solid volume is 7.088×10⁻⁶ m³, and total inlet area is 6.912×10⁻⁵ m².

The metal is partitioned into conformal cuboids to support an orthogonal hex mesh. These partitions have no material discontinuity. The nominal CAD has 194 blocks: 48 fluid blocks and 146 solid blocks. The physical solid remains connected through the base. Internal solid boundaries must conduct without contact resistance.

The fluid roof at z=t+d is a zero-thickness no-slip, adiabatic wall. Exposed web/side tops are also adiabatic. This reproduces the model's insulated-cover assumption without assigning an invented lid material, bond or contact conductance. Adding a real conductive cover changes the model and requires additional inputs.

## Region and boundary map

The physical IDs below are preserved in MSH 4.1. The adjacent regions identify the two sides of the coupled interface. CAD entity tags are supplied for the current export only.

| Group / ID | Location | Baseline treatment |
| --- | --- | --- |
| `solid` / volume 1 | Base, webs, side margins | Steady Fourier conduction with recorded k |
| `fluid` / volume 2 | All N channel interiors | Water, steady laminar momentum and energy |
| `inlet` / surface 11 | Fluid faces at x=0 | Axial uniform velocity U, transverse velocities zero, uniform recorded inlet temperature |
| `outlet` / surface 12 | Fluid faces at x=L | Static pressure 0 Pa gauge, natural/zero-gradient thermal outflow, backflow temperature set to inlet only as a numerical safeguard |
| `heater` / surface 13 | Entire solid underside z=0 | Uniform inward heat flux Q/(LW) |
| `solid_fluid` / surface 14 | Channel floors and two sidewalls | No slip, temperature continuity and conservative heat-flux continuity, zero contact resistance |
| `adiabatic_roof` / surface 15 | Fluid faces at z=t+d | No-slip, zero thermal flux |
| `adiabatic_solid` / surface 16 | Remaining exterior solid faces | Zero thermal flux, including end faces |

There is **no prescribed convection coefficient at solid/fluid interfaces**. CFD resolves heat transfer directly. Do not apply the reduced-order Nusselt number, film resistance or fin efficiency as CFD boundary conditions. A heat-flux sign depends on the solver's outward-normal convention. Check that the integrated heater adds +100 W to the combined domain.

Uniform inlet velocity imposes equal channel flow and allows hydrodynamic development inside the finite channel. It does not predict distribution from a common header. All outlets share the same gauge reference. Nonzero backflow in this simple geometry requires investigation rather than hiding it with the backflow setting.

## Physics sequence

**B0, constant-property baseline:** steady, laminar, incompressible water with density 997 kg/m³, dynamic viscosity 0.00089 Pa s, cp 4181 J/(kg K), and thermal conductivity 0.607 W/(m K). Enable energy and conjugate conduction. Begin with viscous heating, gravity, radiation and external heat leakage off. No turbulent wall functions are appropriate for the nominal reduced-order Re≈29.92. Use bounded second-order spatial schemes for reported solutions. Document pressure/velocity coupling and convergence controls.

Solid density and cp are intentionally unspecified. They do not enter steady conduction. If software requires numerical defaults for those fields, document that they are inactive in the steady formulation. They must not become unstated physical inputs to a transient study.

**B1, property sensitivity:** retain geometry, heat and inlet volumetric flow, then use temperature-dependent pure-water properties. First replace only viscosity and fluid conductivity, keeping density and cp at B0 values to isolate their effects. Then enable consistent density/enthalpy/cp variation if supported by the solver. Set mass inflow to rho(Tin,pref)×Vdot when using a mass-flow boundary. Do not hold the B0 mass flow and claim the inlet volumetric flow is unchanged.

The supplied table uses 101,325 Pa **absolute** solely as an analyst assumption. The outlet's zero gauge value does not imply a vacuum. Record the absolute pressure separately and replace it when an operating pressure is supplied. Use local absolute pressure if pressure variation materially affects the selected property model. Use enthalpy and cp consistently, avoid independent interpolants that violate their thermodynamic relationship, and stop if temperatures leave the table range. CoolProp's water backend references IAPWS formulations [3–4]. No glycol or inhibitor concentration has been specified.

**B2, inlet/model-form checks:** compare the plug inlet with a fully developed rectangular-duct velocity profile or a separately converged fluid-only precursor. Keep the profile mean equal to the recorded U. The precursor has no added heated metal and defines the profile at x=0 of the same 100 mm heated plate. Preserve the main channel pressure planes. This separates imposed inlet-profile effects from geometry effects.

**B3, omitted-physics checks:** quantify the significance of viscous dissipation, outlet treatment, solid axial conduction, buoyancy/orientation and a physical cover when sufficient inputs exist. Never add the model's K=2 loss as a momentum sink or heating source inside the straight-channel CFD domain. There are no physical headers in this model.

## Comparison set from existing records

All seven entries below are rows of `results/cold_plate/grid.csv`, recorded case `nominal`. They share 100 W, 25°C inlet and a 100×50 mm footprint. IDs are specific to that case's candidate list. The fixed-flow case uses a different candidate numbering scheme. Values below are **reduced-order predictions**, not CFD outputs.

| ID | Nominal candidate | Change from N0 | N | Peak proxy °C | Total model Δp Pa |
| --- | ---: | --- | ---: | ---: | ---: |
| N0 | 603 | 0.8/1.8/0.2/1 mm width/depth/web/base, k=390, 0.1 L/min | 48 | 41.3862 | 56.4712 |
| G1 | 423 | Width 0.5 mm | 68 | 40.3653 | 141.7864 |
| G2 | 543 | Depth 1.2 mm | 48 | 42.0467 | 104.0984 |
| G3 | 623 | Web 0.4 mm | 40 | 41.7126 | 67.9045 |
| G4 | 613 | Base 2 mm | 48 | 41.4375 | 56.4712 |
| M1 | 602 | k=167 W/(m K) | 48 | 41.5859 | 56.4712 |
| F1 | 605 | Flow 0.2 L/min | 48 | 34.1893 | 114.1017 |

N0 versus G1 tests a temperature/pressure tradeoff. G2 tests wetted area and flow area. G3 tests conductive webs versus channel count. G4 tests whether the model's very small base-thickness effect survives conjugate conduction. M1 isolates material conductivity. F1 isolates flow and entry effects. Geometry changes necessarily change channel count or velocity under the recorded packing rule. These are not comparisons at fixed per-channel velocity or fixed pumping power.

Keep the whole selection even if CFD reverses the ranking. At 0.1 L/min, the ~0.051 K reduced-order G4 effect is smaller than the provisional 0.1 K general mesh tolerance. A ranking claim for G4 therefore needs substantially tighter numerical uncertainty or must be reported as unresolved. All selected rows are feasible in the original model, so this set does not characterize its failure boundary.

After the initial comparison, the recorded `higher_load` and `warm_inlet` winners can be added as operating-condition checks. They share the N0 geometry at 0.2 L/min and are not independent geometry evidence. They are not included in the first seven-run set.

## What can be learned now, and what cannot

| Question | Idealized study possible now? | Required additions for a hardware conclusion |
| --- | --- | --- |
| Does the straight-channel friction implementation agree with a resolved duct solution? | Yes, at matched properties and flow | Roughness, tolerances and actual fluid for hardware pressure loss |
| Are the fin/base approximations adequate for uniform heating? | Yes, within the idealized insulated-cover problem | Actual alloy, lid/bond and contact assembly |
| How do geometry and flow alter this model's temperature and channel Δp? | Yes | Partner constraints and uncertainty before selecting a manufactured part |
| Do headers distribute flow evenly? | No | Header and port geometry, common inlet/outlet connections and flow conditions |
| What is chip junction temperature or hotspot performance? | No | Heat map, die/package stack, contact footprint, TIM and contact resistance |
| Will it seal, survive pressure, or be machinable? | No | Structural load case, seals, bonding process, tolerances and fabrication review |
| What pumping electricity or facility savings result? | No | Complete loop, fittings, pump curve/efficiency and system operating data |

`partner_inputs.csv` is the open-input register. Null values must remain null until supplied or explicitly defined as sensitivity assumptions.

## Primary references

1. [Pinned Fovra model documentation](https://github.com/Grace-Fokam/fovra-v0/blob/3e088831d50f8c65281bc6e84482700395a1c1a7/docs/cold-plate.md) and [recorded winners](https://github.com/Grace-Fokam/fovra-v0/blob/3e088831d50f8c65281bc6e84482700395a1c1a7/results/cold_plate/grid_winners.json).
2. [Gmsh reference manual](https://gmsh.info/doc/texinfo/gmsh.html), physical groups, OpenCASCADE fragments, transfinite meshes and file formats. Runtime pinned to 4.15.0, not the moving documentation version.
3. [CoolProp water model references](https://coolprop.org/fluid_properties/fluids/Water.html) and [property API](https://coolprop.org/coolprop/HighLevelAPI.html). Runtime pinned to 7.2.0.
4. [IAPWS water releases](https://iapws.org/documents/release) and [liquid water near 0.1 MPa](https://iapws.org/technical-guidance/release/LiquidWater).
5. [NASA/NPARC spatial convergence guidance](https://www.grc.nasa.gov/www/wind/valid/tutorial/spatconv.html). The numerical acceptance thresholds in this package are proposed study criteria, not manufacturer specifications or NASA mandates.
