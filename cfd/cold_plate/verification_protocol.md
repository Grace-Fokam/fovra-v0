# Verification and comparison protocol

This is a proposed study protocol. No entries in it imply that a CFD run, convergence study, or physical test has occurred. Thresholds are provisional research acceptance criteria chosen for this handoff, not partner specifications.

## 1. Freeze the inputs and import audit

Archive the commit, input JSON, source hashes, generator/dependency versions, solver/version, commands, property functions, mesh settings, precision, machine and solver settings. Keep each physics variant and mesh in its own directory. Retain unsuccessful runs and their failure causes.

Check the CAD/mesh envelope, positive cell volumes, no overlaps or gaps, channel count, and named groups after solver import. For N0, require 48 channel inlets/outlets, inlet area 6.912×10⁻⁵ m², heater area 0.005 m², fluid volume 6.912×10⁻⁶ m³ and metal volume 7.088×10⁻⁶ m³. Require area/volume agreement within 0.01% after import. Check minimum web and base thickness in the mesh. No feature suppression or automatic small-face removal may erase the 0.2 mm webs.

Verify continuous conduction across internal solid partitions and paired temperature/flux coupling at all solid/fluid interfaces. Confirm shared mesh nodes or conservative nonconformal coupling after conversion. Inspect orthogonality, skewness, aspect ratio, minimum Jacobian and disconnected components. The supplied mesh is orthogonal but deliberately anisotropic along the long channel. A positive Jacobian is necessary, not sufficient for a reliable solution.

Before thermal runs, solve an isothermal duct case with the same fluid properties/flow. Check the downstream pressure gradient against the rectangular-duct fully developed analytical relation. This is a solver/import verification check, not a manufactured-part test.

## 2. Iterative convergence and conservation

For every mesh, use double precision and converged steady laminar momentum, energy and solid conduction. Begin with conservative relaxation if needed, then use the same reported spatial order across the mesh sequence. Monitor continuity, all velocity components, fluid/solid energy residuals, underside maximum and mean temperature, outlet bulk temperature, pressure drop, integrated heat and mass rates.

Provisional normalized residual goals are 10⁻⁶ for continuity/momentum and 10⁻⁸ for energy, where meaningful for that solver's residual scaling. Document actual definitions. Residual thresholds alone do not demonstrate convergence. Over the final 200 iterations require temperature drift ≤0.01 K and relative Δp drift ≤0.1%. Restart with tighter tolerances or twice the iterations and require changes smaller than one tenth of the intended mesh-error allowance. If the steady state will not settle, investigate numerics and physics before switching to a transient average.

Use positive inlet and outlet mass-rate magnitudes from signed face integrals:

`mass imbalance = abs(mdot_out − mdot_in) / mdot_in`.

Require ≤0.1% globally and check every channel individually. Also require each channel's imposed inlet flow to equal total/N within 0.1%. Equal flow is imposed here, so it is not evidence that a real manifold distributes flow evenly.

For the B0 sensible-energy equation with viscous heating off:

`Qheater = Σout integral(rho un cp T dA) − Σin integral(rho |un| cp T dA) + Qother,outward`.

Use a consistent reference temperature to reduce cancellation. Measure any axial conduction through inlet/outlet planes and include it in `Qother,outward`, along with other exterior heat leakage if enabled. It may be small but must not be silently discarded. Integrate actual fluxes. Do not replace measured CFD outlet energy by the imposed heat load merely to make conservation pass.

Require `abs(Qheater + Qdiss − enthalpy_gain − Qother,outward)/(Qheater + Qdiss) ≤0.5%`, with Qdiss=0 for B0. Check integrated heater power against the requested value within 0.1%. Independently require the solid-side interface heat leaving the solid and fluid-side heat entering the fluid to agree within 0.1% of Qheater. The checker uses both as positive solid-to-fluid magnitudes. Inspect the local paired interface fluxes and temperature jumps as well, rather than relying only on a globally cancelling imbalance.

For variable properties, integrate mass-flux-weighted sensible enthalpy at each face, using a consistent thermodynamic implementation. For a fixed-pressure thermal-enthalpy convention, use h(T,pref)−h(Tref,pref). If the solver solves total energy or includes pressure work, use its own full control-volume energy balance, including kinetic-energy and stress-work terms where relevant. Do not add Δp×Vdot again if the solver already includes that work. Adapt the template to the chosen energy convention and record it explicitly.

The recorded nominal hydraulic power is only 9.41186×10⁻⁵ W. Its contribution to the model's coolant temperature is about 1.35×10⁻⁵ K. B0 intentionally omits it. Compare B0's outlet to the heat-only analytical value, approximately 39.393815°C, and keep the recorded model outlet, 39.393829°C, separately. Do not interpret that tiny difference as solver error or add a fictitious pump heat source. For a viscous-heating sensitivity use the resolved dissipation consistent with the modeled channel only.

## 3. Mesh independence

Run at least three systematically refined meshes for N0 with unchanged geometry, boundary conditions, properties and discretization. The supplied coarse/medium/fine family doubles cells in x, channel width, channel depth, webs, base and margins. Its characteristic spacing ratio is 2 and its total cell count increases by 8 each level. It uses uniform spacing within each block. These are initial settings and may require additional refinement at entrances, the heated underside, walls and thermal gradients.

| Level | Axial | Across each channel | Through channel depth | Across each web | Through base | Across each margin |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Smoke, import only | 8 | 2 | 2 | 1 | 1 | 2 |
| Coarse | 80 | 4 | 8 | 2 | 4 | 6 |
| Medium | 160 | 8 | 16 | 4 | 8 | 12 |
| Fine | 320 | 16 | 32 | 8 | 16 | 24 |

The uniform coarse axial spacing is 1.25 mm, so the nominal model's hydrodynamic entry estimate of about 1.66 mm spans only about 1.3 coarse cells. This mesh must not be assumed adequate for end-to-end pressure loss. Conduct an additional axial-only refinement or develop an entrance-graded family. If grading is introduced, preserve its distribution through all three levels and document the new family. The thermal entry estimate is about 20.3 mm and is likewise only an approximate model diagnostic.

Report each mesh's cells by region, wall-normal resolution, first-cell distance, maximum aspect ratio, quality, iteration count, conservation errors and observables. Laminar flow still requires wall-normal resolution, but turbulent y+ wall-function targets are not the acceptance measure.

Use base maximum temperature rise above inlet, base mean rise, outlet bulk rise, thermal resistance, channel-end Δp and fully developed pressure gradient as mesh observables. Compare temperature changes in kelvin, not percentages of a Celsius temperature. Require medium-to-fine changes ≤0.1 K in base maximum and outlet bulk temperature, ≤1% in thermal resistance and channel pressure metrics, and all conservation criteria on both meshes.

Estimate observed order and a fine-grid uncertainty band using Richardson extrapolation and the grid convergence index approach in [NASA's spatial convergence guidance](https://www.grc.nasa.gov/www/wind/valid/tutorial/spatconv.html). For an equal-ratio monotonic sequence C,M,F:

`p = ln(abs((C−M)/(M−F))) / ln(r)`

`phi_ext = F + (F−M)/(r^p−1)`

`GCI_abs,fine = 1.25 × abs(F−M)/(r^p−1)`.

`check_solution.grid_convergence` implements these equations and rejects nonfinite, flat, oscillating or divergent sequences. Use positive temperature rise or thermal resistance rather than raw Celsius for normalized GCI. Require estimated fine-grid uncertainty ≤0.1 K for thermal observables and ≤1% for pressure/resistance before general comparisons. A three-value fit is not independent proof of the asymptotic regime. Use a fourth mesh or directional refinements if the observed order is implausibly high, nonmonotonic, sensitive to the mesh family, or inconsistent with the expected scheme order. Do not force an observed order to obtain a favorable error band.

Repeat the full study for G1, which has narrower channels, and G2, which has shallower channels. At minimum check medium/fine stability for every other case. Expand to three levels wherever these fail, field gradients differ, or ranking differences approach estimated uncertainty. A common mesh name does not mean identical numerical error across geometries.

For a claimed design advantage, require the difference to exceed the combined conservative uncertainty bounds of the two runs, including iterative and grid errors. For the small G4 thermal difference, aim for <0.02 K uncertainty in each run or report the ordering as unresolved. No conclusion may depend on a rounded last digit.

## 4. Pressure-drop definitions

Store static pressure in **Pa**. If a solver exports kinematic pressure in m²/s², convert with the density consistent with that formulation. Variable-density pressure fields need solver-specific treatment. Record area averages for Δp and mass-flow averages for total-pressure diagnostics. Do not mix the two definitions.

| Metric | Measurement | Corresponding model comparison |
| --- | --- | --- |
| Channel-end static Δp | Area-averaged p at x=0 minus x=L across fluid openings | Contains the resolved developing-flow effect of the chosen inlet, but no physical port/header loss |
| Fully developed friction estimate | Fit area-averaged p versus x at 0.60L, 0.675L, 0.75L, 0.825L, 0.90L, separately per channel, then report −slope×L | Compare to `friction_pressure_pa`, 55.8914817 Pa for N0 B0 |
| Recorded aggregate model Δp | `friction_pressure_pa + minor_pressure_pa` | 56.4711575 Pa for N0, includes empirical K=2 allowance of 0.5796758 Pa |
| Device pressure loss | Defined partner port-to-port planes and averaging convention | Cannot be obtained from this geometry |

Check the downstream pressure fit's linearity and repeat over a shifted interval such as 0.50L–0.80L. Report slope spread, fit residuals and channel-to-channel spread. If no developed interval exists, do not extrapolate it as a fully developed friction result. Under variable viscosity, a nonlinear axial pressure distribution is physically possible, so compare that variant separately rather than forcing a constant gradient.

The channel pressure drops are parallel and must not be summed over 48 channels. A modeled channel hydraulic-power estimate is Δp×total Vdot only under the matching incompressible convention. Include kinetic-energy correction when inlet and outlet profiles differ materially. Total-pressure loss and static-pressure drop are not interchangeable for developing flow. Neither estimate is measured electrical pump power or loop pressure loss.

Do not add K=2 to CFD and then claim agreement with the same K=2 model as independent validation. Show friction, developing-flow effects, and the empirical allowance separately. Small pressure drops require sufficient solver precision and reference-pressure handling.

## 5. Temperature-dependent property checks

Recreate `water_101325pa.csv` with the pinned dependency and verify rho, viscosity, cp and conductivity at 25, 35 and 40°C against the direct property API. At every 0.5 K midpoint compare linear interpolation against direct evaluation. Provisional maximum relative interpolation error is 0.1% for each property. Require finite positive values, liquid phase, complete coverage and no extrapolation. Check h derivatives against cp if both are imported.

Run B0 and B1 on the accepted mesh at the same inlet volumetric flow and heat load. Separate the change due to mu/k from the change due to density/enthalpy. Report ΔTbase, ΔTout, Δp, maximum/minimum properties and local Re. Repeat mesh/stationarity checks if the variable-property solution changes boundary-layer resolution or convergence. The table does not establish actual coolant composition or operating pressure. Replace its pressure/composition only from explicit partner data or a separately labeled sensitivity scenario.

## 6. Reduced-order comparison and deliverable review

Report the actual maximum temperature on the **heated underside** as `base_max_k`, its area-weighted mean as `base_mean_k`, and a separate maximum over the entire metal. Record the location of maxima. The model's `peak_base_c` is a proxy, so CFD/model agreement is not required by construction and it is not chip junction temperature.

Compute outlet bulk temperature by mass-flux weighting for constant cp. With variable cp, average enthalpy by mass flow and invert to an equivalent bulk temperature at a stated pressure. Never substitute a simple area average for the energy comparison. Also report channel-specific outlet bulk temperatures and heat shares, since side margins can cause thermal nonuniformity even with imposed equal flow.

Compare `R = (Tbase,max−Tin)/Qheater` using the same inlet, area and heat definition. For N0, the recorded peak proxy is 41.3861757°C and R is 0.1638617568 K/W. Report absolute temperature discrepancies in K and pressure/resistance discrepancies in both absolute units and percent of the recorded reference. B0 versus the recorded outlet must account for the small omitted hydraulic heating described above.

The reduced-order thermal model assumes fully developed three-wall heat transfer and an approximate fin efficiency. Finite-length CHT resolves axial conduction, thermal entry and side-wall differences. Discrepancies should therefore be diagnosed before revising any coefficient. Suggested investigation triggers, **not pass/fail physics validation criteria**, are >1 K in base temperature or >10% in matched B0 friction pressure. Smaller discrepancies still need uncertainty assessment.

Keep the original recorded predictions unchanged. Deliver meshes, all solver input decks, numerical settings, property files, run logs, complete comparison tables with uncertainty, conservation integrals, pressure/temperature profiles and figures with labels for each physics variant. Have the thermal engineer review boundary choices and the parameter register before advancing to partner geometry. Physical validation still requires manufactured parts, calibrated measurements and experimental uncertainty.

## Result-template conventions

`physics_variant` identifies B0/B1/etc, plus any finer distinctions. `cell_count` counts fluid and solid 3D cells, not boundary elements. `solver_version` must identify the actual solver build. `mass_in_kg_s` and `mass_out_kg_s` are positive magnitudes. `enthalpy_gain_w` is the net outlet-minus-inlet energy flux. `other_outward_heat_w` includes all uncounted conductive/exterior heat crossing the control volume. `dissipation_w` is zero when disabled. Interface columns are separately exported positive solid-to-fluid magnitudes. `pressure_gradient_pa_m` is the signed fitted dp/dx, normally negative. Temperatures are K. Last-window pressure drift is divided by the measured Δp, not by absolute pressure.

The supplied checker does not parse a solver's native fields or residuals. It checks a completed export. Cross-check the input power, requested flow, per-channel balances, property range, mesh study and field definitions in the review record before accepting a case.
