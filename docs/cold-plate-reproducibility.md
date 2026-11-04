# Cold-plate scientific replay

The compatibility matrix answers whether the experiment runs on supported Python
and dependency versions. The pinned replay job answers whether the recorded
scientific outputs still reproduce. Both checks are needed. Reproducing this
unvalidated coupon model does not validate its physical predictions.

## CI contract

`.github/workflows/cold-plate.yml` keeps its existing Python 3.10/3.12 test and
benchmark matrix using `requirements.txt`. `.github/workflows/tests.yml` checks the dashboard and other
cooling research. The additional `pinned-reproducibility` job uses Ubuntu 24.04 and the
recorded Python **3.12.14**, installs `requirements-cold-plate.txt`, runs the
cold-plate and replay-checker tests, and reruns the full benchmark with its
recorded defaults: four cases, six seeds (11, 22, 33, 44, 55, 66), and 32 queries
per method. It writes under a newly created runner temporary directory.

The scientific package pins are NumPy 2.5.4, pandas 3.1.0, SciPy 1.18.1,
scikit-learn 1.9.1, joblib 1.6.0, and threadpoolctl 3.7.0. They match the historical
`results/cold_plate/metadata.json`. The requirements file includes the broader
application dependencies, so this is a pinned scientific stack, not a complete
lock of every transitive UI dependency. The job saves the resolved package list.

`check_cold_plate_reproducibility.py` uses only the Python standard library and
requires exact byte equality for this explicit set:

| Output | Scientific evidence checked |
| --- | --- |
| `grid.csv` | Finite-grid model evaluations and Pareto flags |
| `grid_winners.json` | Case settings, winning geometry, and evaluated responses |
| `paired_comparison.csv` | Every paired win, tie, or loss |
| `reference_design.csv` | Reference geometry responses in each case |
| `search_summary.csv` | Selected designs, thermal metrics, feasibility, and query counts |
| `search_trials.csv` | Complete ordered search traces and observed responses |
| `sensitivity.csv` | Heat-transfer and minor-loss sensitivity evaluations |

`timings.csv` and `metadata.json` are excluded from equivalence checks. They
remain in the uploaded artifact for diagnosis, along with the benchmark log,
Python version, resolved packages, and comparison report. Metadata includes
source hashes and experiment settings, as well as environment information.

The checker examines every required file even if another file fails. Missing
reference or generated files fail explicitly. Changed files report their names,
sizes, SHA-256 hashes, and unified diffs (up to 80 lines per file). Diff line
endings are displayed as `\n` or `\r\n`, so serialization differences are visible.
Full generated files are retained for further comparison. The command exits 1
on any failure, including accidental comparison of a directory with itself.
GitHub's explicit Bash shell propagates a failure through `tee` via `pipefail`.

No floating-point tolerance, sorting, or aggregate-only comparison is applied.
This strict policy matches the demonstrated byte-for-byte replay. Small
roundoff or formatting differences also fail and require diagnosis. They are
not automatically evidence of changed physics, but must not silently relax the
recorded replay contract. A change to the comparison policy requires review.

## Run locally without altering history

From the repository root with Python 3.12.14 available:

```bash
python3.12 -m venv .venv/cold-plate
source .venv/cold-plate/bin/activate
python -m pip install -r requirements-cold-plate.txt
python -m pip check
export PYTHONHASHSEED=0
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
python -m pytest tests/test_cold_plate.py tests/test_cold_plate_reproducibility.py -q
validation_dir="$(mktemp -d)"
python benchmark_cold_plate.py --output "$validation_dir/generated"
python check_cold_plate_reproducibility.py --actual "$validation_dir/generated"
git diff --exit-code -- results/
```

Keep the pinned cold-plate environment separate from general testing. A smaller budget or fewer seeds is useful for smoke
testing but will correctly fail comparison with the full reference experiment.

## Determinism and dependency sensitivity

The search already has deterministic controls in `cold_plate_search.py`:

- A seeded NumPy generator creates an ordered candidate permutation. Candidate
  construction uses a fixed Cartesian-product order.
- Each forest has `random_state=seed` and `n_jobs=1`.
- Candidate IDs break exact acquisition-rank ties. Verified winners are ordered
  by pump power, temperature, then candidate ID.
- Exploration uses a fixed schedule. Measured elapsed time never enters the
  selection logic and is removed from scientific files before serialization.

The CI job additionally fixes Python hash seeding and limits numerical-library
thread counts to one. These settings reduce execution variability without
changing the historical search algorithm or its model parameters.

Scikit-learn's [RandomForestRegressor documentation](https://scikit-learn.org/1.9/modules/generated/sklearn.ensemble.RandomForestRegressor.html#notes)
explains that feature permutations and tied split improvements require a fixed
random state for deterministic fitting. Fixed seeds alone do not establish
equivalence between library releases. Changes to tree fitting, numeric
reductions, or prediction ordering can affect greedy acquisition decisions.
Once a candidate differs, subsequent training observations differ too. This is
a plausible mechanism, not proof of a specific upstream implementation change.

On November 2, 2026, the unmodified integration source at
`6cc65cda09bcc80b31d4ba953ebb2fd39bb0fa9d` was rerun locally. In the available
general Python 3.12.14 environment (NumPy 2.3.5, pandas 2.2.3, SciPy 1.17.0,
scikit-learn 1.8.0, joblib 1.5.3, threadpoolctl 3.6.0):

- Five of seven scientific files reproduced exactly. Only `search_trials.csv`
  and `search_summary.csv` differed. All random-search rows were unchanged.
- 182 of 1,536 trial rows had different candidate IDs. The first differing
  choice in file order was nominal/surrogate/seed 11/evaluation 24: recorded
  candidate 542 versus general-environment candidate 562.
- Two of 48 summary rows changed. For higher-load/surrogate/seed 22, the selected
  candidate changed from 605 to 604. Modeled peak base temperature changed from
  approximately 38.783909°C to 39.083427°C despite equal pump power.
- Every paired outcome stayed unchanged: 16 wins, six ties, and two losses.

The selected geometry and roughly 0.30°C modeled temperature difference are
scientific-result changes, not harmless print rounding. The broad environment
may legitimately execute a different version of the search, but it cannot be
treated as an exact replay of the recorded experiment. The new pinned job must
fail on these differences even when aggregate counts remain unchanged.

A controlled follow-up changed **only scikit-learn from 1.8.0 to 1.9.1** in an
isolated environment inheriting the general stack. All six reported package
versions were checked in the generated metadata. All seven scientific files
then matched the historical references byte for byte. Changing scikit-learn
alone was sufficient to remove the observed drift in this experiment. This
does not prove that other dependency changes are irrelevant in general or
identify the exact changed tree-fitting operation.

| Local run | Changed scientific dependencies from general stack | Exact matches to historical files |
| --- | --- | --- |
| General stack | None | 5/7 |
| General stack, repeated with CI hash/thread settings | None | 5/7, and 7/7 against the first general run |
| Scikit-learn-only upgrade, with CI settings | scikit-learn 1.9.1 | 7/7 |
| Full recorded stack, with CI settings | All six recorded scientific pins | 7/7 |

All runs used Python 3.12.14 on the same Linux host and had identical benchmark,
search, and simulator source hashes. The repeat rules out unfixed hash/thread
settings as the explanation for the observed general-stack variation on this
host. The single-package trial used a separate virtual environment with
`--system-site-packages` over the general stack, then
`python -m pip install --no-deps scikit-learn==1.9.1`. It reran the default full
benchmark and the same checker, without editing source or reference data.

The complete suite passed **140 tests** in both the general and fully pinned
environments. The pinned run emitted 21 existing Streamlit/pandas deprecation
warnings. `pip check` passed in the pinned environment. Twelve new checker tests
cover missing and changed scientific files, unchanged aggregate outcomes with
changed trials, multiple failures, tiny numeric drift, serialization changes,
excluded timing/metadata, self-comparison, CLI exit codes, bounded diagnostics,
and reference preservation. Local workflow parsing and `git diff --check`
passed. Python 3.10 execution and GitHub-hosted jobs are separate CI checks.

## Handling a replay failure

1. Inspect the named file's diff and the generated artifact. Separate missing
   files, serialization-only changes, small roundoff, and changed candidates,
   feasibility, or model responses.
2. Check Python and scientific package versions against the recorded pins and
   compare metadata source hashes. Rerun in a fresh pinned environment before
   attributing a mismatch to changed scientific code.
3. Investigate any remaining difference under the pinned stack. Do not replace
   committed references merely to make CI green. An intentional model or
   dependency update needs separately recorded results and scientific review,
   preserving the old evidence.

Pinning package versions does not lock wheel builds, system math libraries, or
CPU architecture. The supported CI target is Ubuntu x86-64 with the recorded
Python patch release. Other systems may expose a new portability issue. Exact
replay and physical validation remain separate requirements.
