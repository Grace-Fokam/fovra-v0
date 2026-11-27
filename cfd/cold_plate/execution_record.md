# Preparation and verification record

Date: 4 November 2026. Original model/data snapshot: `3e088831d50f8c65281bc6e84482700395a1c1a7`.

## Executed

| Check | Observed result |
| --- | --- |
| Source extraction | Seven selected nominal rows reproduced from the pinned grid, with full-precision reduced-order comparisons and source hashes |
| Input regeneration | JSON cases, selection CSV and source manifest reproduced byte-for-byte |
| Five unique CAD geometries | Generated partitioned STEP/BREP bodies with all expected volume and boundary groups |
| Geometry measures | Channel count, fluid/solid volumes, heater/inlet/outlet/interface/roof areas agreed with analytical dimensions |
| CAD units | All five STEP exports re-imported into Gmsh with metre conversion and matched expected bounds and total volume |
| Mesh units and interfaces | Smoke MSH files re-imported in metres, preserved all physical groups, and shared solid/fluid interface node IDs |
| Nominal coarse mesh | 286,080 first-order hexahedra, minimum scaled Jacobian approximately 1.0, total mesh volume approximately 1.4000×10⁻⁵ m³ |
| Other geometry smoke meshes | G1: 4,968 cells, G2: 3,528, G3: 2,952, G4: 3,528, with positive volumes and scaled Jacobians approximately 1.0 |
| Pure-water table | 41 temperature rows from 20–60°C at the assumed 101,325 Pa, all reproduced from the pinned property API |
| Property interpolation | All half-degree midpoint checks met the proposed 0.1% relative tolerance, including cp consistency with enthalpy increments |
| Handoff tests | 11 passed |
| Complete repository tests | 75 passed |

Environment: Python 3.12.14, Gmsh 4.15.0, CoolProp 7.2.0, pytest 8.4.2. General repository dependencies were installed from `requirements.txt`. The exact recorded search benchmark was not rerun or modified. The optional geometry workflow repeats the dedicated handoff checks in CI.

Commands used for the main checks:

```bash
python -m pytest -q tests/test_cfd_handoff.py
python -m pytest -q
python cfd/cold_plate/generate_geometry.py cfd/cold_plate/inputs/cases/N0_nominal.json --output build/cfd/N0_nominal --mesh coarse
```

The generated reports in the downloadable CAD package contain per-file SHA-256 values, physical-group entity maps, areas/volumes and mesh checks. M1 and F1 reuse the nominal geometry and require their own conductivity or flow settings. Their solver boundary conditions have not been executed.

## Not executed

No fluid-flow solution, conjugate thermal solution, pressure-loss calculation by CFD, solver-specific mesh conversion, medium/fine mesh study, steady-state convergence study, physical experiment, structural analysis, manufacturing review or manufacturer acceptance test has been performed in this handoff.

Numerical conservation and GCI helper tests use explicitly synthetic unit-test inputs. They are software checks, not evidence from a cold-plate simulation. Geometry reports state that solver import and mesh independence remain unverified. All CFD result fields remain null or empty.
