# Combined research integration

This integration combines PRs #10 (cooling), #11 (cold-plate geometry), and #9
(sensor robustness). Passing code checks means these experiments coexist and run.
It does not validate industrial cooling equipment, establish novel hardware, or
show a general advantage from AI.

## Source snapshots and dependency order

| Source | Reviewed commit | Base |
| --- | --- | --- |
| main | `2c8b2d4c9ad1455cfc801cb9ba21f2680ae6811e` | Original tank experiments |
| #10 | `ce12821da8b12acd26e2963cbdfab2f8cd0a2e53` | main |
| #11 | `51c9628e1e94b76cca337257b7e14e84fc0180d2` | #10 |
| #9 | `e45d60398ab4b56edb8c02372fb76854604a25b3` | main |

The tested local order is main → #10 → #11 → #9. #10 and #11 fast-forward
at these snapshots. Merging #9 then produces actual content conflicts in
`.github/workflows/tests.yml` (the appended benchmark/upload blocks) and
`README.md` (the Next list). Both benchmark blocks are retained with distinct
output directories and Python-version-specific artifact names. The README keeps
all experiment sections, limitations, and findings. No experiment source code or
recorded result is changed to resolve these conflicts.

For separate upstream PR merges, merge #10 first, retarget #11 to main and
recheck its diff, then merge #11 and the reconciled #9. #9 can also precede #11
once its conflicts with #10 are resolved. Approval is required before merging
anything into main. An integration PR is an alternative review unit, not an
instruction to also merge the same changes again through every source PR.

## Reproduce without overwriting recorded evidence

Use a fresh environment with Python 3.10 or 3.12. These commands run all five
experiments, including the two original tank benchmarks:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q
validation_dir="$(mktemp -d)"
python benchmark_mpc.py --output "$validation_dir/mpc_comparison" --repeats 1
python benchmark_adaptation.py --output "$validation_dir/adaptation"
python benchmark_sensor_robustness.py --output "$validation_dir/sensor_robustness"
python benchmark_cooling.py --output "$validation_dir/cooling"
python benchmark_cold_plate.py --output "$validation_dir/cold_plate"
git diff --check
git diff --exit-code -- results/
```

Keep the generated metadata and outputs together. Source hashes and package
versions identify the execution environment. Successful execution with the broad
`requirements.txt` ranges is not a promise of byte-identical search traces across
package versions. For the recorded cold-plate environment, use a **separate
Python 3.12 environment** and install `requirements-cold-plate.txt`. The original
benchmark's recorded environment is in `requirements-benchmark.txt`. Do not
combine these two pin sets. Timings are machine-dependent and are not scientific
reproducibility targets. Historical result files remain historical evidence.

`tests.yml` runs the complete suite, Streamlit health check, original MPC,
adaptation, cooling, and sensor benchmarks on Python 3.10/3.12. The dedicated
`cold-plate.yml` runs cold-plate tests and its full benchmark on the same matrix.
Both support manual dispatch. Cold-plate code, dependency, workflow, and relevant
documentation changes trigger the dedicated workflow. A green source-PR workflow
is not evidence that this combined branch has passed remote CI.

## Dashboard and research boundaries

The dashboard retains **Original simulation**, **Adaptation experiment**, and
**Cooling exploration**. Sensor robustness and cold-plate geometry remain
separate CLI experiments. The adaptation explorer continues to read the original
noiseless results. Headless dashboard tests exercise cooling controls, simulator
agreement, downloads, AI/random comparison, stale-result invalidation, and
navigation back to both tank modes. For hosted verification, follow
[the deployment guide](deploy-streamlit.md). Local tests do not establish that a
hosted deployment has updated.

The [sensor report](sensor-robustness-results.md) retains the adverse findings:
adaptive learned versus adaptive physics RMSE is 0.423 versus 0.238°C at 0.5°C
noise, and 1.743 versus 0.378°C at 1.0°C noise. Learned adaptive has band
violations in 48/144 cases, while adaptive physics has none. Neither meets the
model-recovery criterion in degraded random-noise cases. This is synthetic
evidence, not a safety guarantee.

The [cooling report](cooling-experiment.md) retains seven ties, one win, and one
loss against random search among nine feasible pairs. The [cold-plate
report](cold-plate.md) retains its unvalidated coupon-model label, assumptions,
16 wins / 6 ties / 2 losses, and the requirement for thermal-engineering review,
conjugate CFD, and bench measurements. No GPU performance, manufacturing
feasibility, industrial energy savings, or hardware novelty is established by
integrating these branches.

## Local combined validation

Validation results and environment are recorded below after execution. Remote
CI and hosted deployment validation must be assessed separately.

On November 2, 2026, the combined branch passed 128 tests on Python 3.12.14
with NumPy 2.3.5, pandas 2.2.3, SciPy 1.17.0, scikit-learn 1.8.0,
Streamlit 1.66.1, and pytest 9.2.0. Streamlit startup returned `ok` from
`/_stcore/health`. All five full benchmark commands above exited successfully.

- Cooling: all three generated scientific CSVs match the committed tables within
  rtol 1e-9 / atol 1e-10.
- Sensor robustness: `summary.csv`, `paired.csv`, and `noise_effects.csv`
  reproduce byte for byte. The adverse RMSE and violation findings above are
  reproduced. The full compressed trajectories were generated separately.
- Cold plate in the general environment: all finite-grid, reference, sensitivity,
  and paired outcomes match. Some surrogate query sequences and selected
  equal-pump designs differ from the committed run, including selected thermal
  metrics. Aggregate outcomes remain 16 wins, 6 ties, and 2 losses. This is
  environment-sensitive numerical behavior, not an integration code change.
- Cold plate in its separate pinned environment: all seven scientific output
  files (`grid.csv`, `grid_winners.json`, `paired_comparison.csv`,
  `reference_design.csv`, `search_summary.csv`, `search_trials.csv`, and
  `sensitivity.csv`) reproduce byte for byte. Metadata records the current
  environment and timing is excluded from this comparison.
- The original tank source files, both original result directories, all three
  added experiment implementations, their reports, and their recorded result
  directories are unchanged against their respective reviewed branch snapshots.
- Workflow YAML parses, conflict markers are removed, and `git diff --check`
  passes. Python 3.10 execution and remote combined-branch CI are separate checks.

The entire combined suite also passes in the separate cold-plate pinned
environment: 128 passed (21 dependency warnings), on Python 3.12.14.
