# Preliminary conjugate CFD handoff

Revision R00, 4 November 2026. Source snapshot: [`3e088831`](https://github.com/Grace-Fokam/fovra-v0/tree/3e088831d50f8c65281bc6e84482700395a1c1a7).

This package prepares seven recorded design/operating points for independent simulation. It contains five distinct geometries, a CAD/mesh generator, boundary-condition inputs, a water-property table, and a verification protocol. **It contains no CFD solution or physical validation.** CAD and mesh preparation do not establish thermal performance, manufacturability, pressure integrity, or compliance with a manufacturer's requirements.

Start with N0. Review [the simulation specification](simulation_specification.md) before importing a mesh. Follow [the verification protocol](verification_protocol.md) before comparing results. See [execution evidence](execution_record.md) for checks actually performed.

## What is supplied

| File | Purpose |
| --- | --- |
| `inputs/cases/*.json` | SI geometry, materials, boundary inputs, recorded predictions, explicit null partner inputs |
| `inputs/comparison_set.csv` | Seven source-selected records, with candidate IDs and selection reasons |
| `inputs/source_manifest.json` | Pinned source commit and SHA-256 file hashes |
| `prepare_cases.py` | Re-extracts recorded rows and checks them against the reduced-order implementation |
| `generate_geometry.py` | Creates partitioned STEP/BREP CAD and optional conformal hexahedral MSH 4.1 meshes |
| `water_properties.py` | Recreates the pure-water sensitivity table with a pinned property package |
| `inputs/water_101325pa.csv` and `.json` | 20–60°C water properties at an assumed 101,325 Pa absolute pressure, with source/version metadata |
| `inputs/solver_results_template.csv` | Empty solver-export template, not simulation results |
| `check_solution.py` | Checks integral conservation/stationarity metrics and provides a three-grid GCI function |
| `partner_inputs.csv` | Missing engineering inputs, their impact, and when they are needed |

Generated CAD contains the fluid volumes as well as the metal. They must be assigned different regions, not treated as a single metal assembly. No physical cover, seals, ports, headers, chip, or thermal-interface layer is supplied.

## Reproduce from the repository root

Python 3.12 is the tested interpreter. Keep these optional CAD dependencies separate from the dashboard installation.

```bash
python3 -m venv .venv-cfd
source .venv-cfd/bin/activate
python -m pip install -r cfd/cold_plate/requirements.txt
python cfd/cold_plate/prepare_cases.py --output cfd/cold_plate/inputs
python cfd/cold_plate/water_properties.py --output cfd/cold_plate/inputs/water_101325pa.csv
python cfd/cold_plate/generate_geometry.py cfd/cold_plate/inputs/cases/N0_nominal.json --output build/cfd/N0_nominal --mesh coarse
```

If Linux reports `libGLU.so.1` missing, install your distribution's GLU runtime (on Ubuntu/Debian, `sudo apt-get install libglu1-mesa`). No GUI is required. On Windows use `.venv-cfd\Scripts\activate` after creating the environment.

`--mesh none` writes CAD only. `--mesh smoke` writes a very coarse mesh for topology/import testing. It is unsuitable for performance claims. `coarse`, `medium`, and `fine` double all directional cell counts at each level. They are starting grids, not proven resolutions. Generate finer meshes only after checking available memory and solver support. The nominal levels contain 286,080, 2,288,640, and 18,309,120 hex cells respectively. These are mesh counts, not solved cases.

Generate the full selection with distinct output folders:

```bash
for case_file in cfd/cold_plate/inputs/cases/*.json; do
  case_name="$(basename "$case_file" .json)"
  python cfd/cold_plate/generate_geometry.py "$case_file" --output "build/cfd/$case_name" --mesh none
done
```

M1 and F1 may reuse N0's geometry and mesh, but must retain their own material/flow boundary inputs and result identifiers. Do not rerun the original benchmark to create this selection. Its recorded files are unchanged.

## Import into the chosen solver

1. Use `mesh_si.msh` if the solver accepts Gmsh 4.1 and multiregion hexahedra. Its coordinates are **metres**. Verify the box is 0.100 × 0.050 × 0.0028 m for N0. Do not rescale it again.
2. Otherwise import `domains.step`, whose declared CAD units are **millimetres**. `domains_mm.brep` also uses mm but carries no reliable unit convention for an arbitrary importer. Verify 100 × 50 × 2.8 mm before meshing. STEP labels are not the authoritative boundary map.
3. Recover regions using `geometry_report.json`, geometry locations and the specification. Entity IDs can change on STEP import. Preserve shared topology. Merge connected solid blocks into one material region or use conservative internal continuity interfaces. Never make solid/solid partition faces insulated walls.
4. Assign the eight named groups in the specification. All 48 disconnected water channels belong to the same fluid material but each requires an inlet/outlet boundary. Confirm there are no trapped fluid volumes.
5. Set the steady laminar conjugate problem, run the smoke import check, then use the planned meshes. The package is solver-neutral. A Fluent, CFX, STAR-CCM+, OpenFOAM or other solver case must still be configured and reviewed. No solver adapter or one-command CFD solution has been tested here.
6. Export signed integrals, area/mass averages, residual history, mesh diagnostics, and field data. Complete the empty result template from those exports, then run:

```bash
python cfd/cold_plate/check_solution.py --results path/to/completed_results.csv
```

A passing report only covers its listed integral checks. It does not establish mesh independence or physical validation. Empty or incomplete inputs fail explicitly.

## Reviewable change

The repository patch adds this directory and its tests, links the package from the root README, and ignores generated build outputs. It does not alter the reduced-order model or recorded benchmark results. The downloadable handoff additionally includes generated CAD, the nominal coarse mesh, and the patch. Apply a downloaded patch to a clean checkout of the pinned snapshot with `git apply --check Fovra_CFD_Handoff_R00.patch`, then `git apply Fovra_CFD_Handoff_R00.patch`.

Do not apply the patch again if using its review branch. Scientific provenance is pinned to the original model snapshot even when the handoff is on a later branch.
