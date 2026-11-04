# Reproducing the cold-plate results

There are two separate checks. The compatibility matrix confirms the experiment runs on supported Python and package versions. The pinned replay confirms the recorded scientific outputs still come out exactly the same. Reproducing this unvalidated model doesn't validate its physics.

## What CI checks

`.github/workflows/cold-plate.yml` runs the tests and benchmark on Python 3.10 and 3.12 with `requirements.txt`. `.github/workflows/tests.yml` covers the dashboard and the rest of the cooling work.

The `pinned-reproducibility` job uses Ubuntu 24.04 and the recorded Python **3.12.14**, installs `requirements-cold-plate.txt`, runs the cold-plate and replay-checker tests, and reruns the full benchmark with its recorded defaults: four cases, six seeds (11, 22, 33, 44, 55, 66), and 32 queries per method. It writes to a fresh temporary directory.

The scientific packages are pinned to NumPy 2.5.4, pandas 3.1.0, SciPy 1.18.1, scikit-learn 1.9.1, joblib 1.6.0, and threadpoolctl 3.7.0, matching `results/cold_plate/metadata.json`. The other app dependencies aren't pinned, so this locks the scientific stack, not every UI package. The job saves the full resolved package list.

`check_cold_plate_reproducibility.py` uses only the standard library and requires an exact byte match for these files:

| Output | What it covers |
| --- | --- |
| `grid.csv` | Every grid evaluation and Pareto flag |
| `grid_winners.json` | Case settings, winning geometry, and results |
| `paired_comparison.csv` | Every paired win, tie, or loss |
| `reference_design.csv` | The reference design under each case |
| `search_summary.csv` | Selected designs, thermal results, feasibility, and query counts |
| `search_trials.csv` | Full ordered search traces and results |
| `sensitivity.csv` | Heat-transfer and minor-loss sensitivity runs |

`timings.csv` and `metadata.json` aren't compared. They're still uploaded with the benchmark log, Python version, package list, and comparison report for debugging. Metadata includes source hashes, experiment settings, and environment details.

The checker looks at every file even after one fails. Missing files fail explicitly. Changed files show their names, sizes, SHA-256 hashes, and a unified diff (up to 80 lines each), with line endings shown as `\n` or `\r\n` so formatting differences are visible. Full generated files are kept for further comparison. The command exits 1 on any failure, including comparing a directory with itself. In CI, Bash's `pipefail` makes sure a failure isn't hidden by `tee`.

There's no floating-point tolerance, sorting, or summary-only comparison. This matches the byte-for-byte replay we've shown. Small rounding or formatting changes will also fail. They don't necessarily mean the physics changed, but they shouldn't quietly loosen the check either. Any change to the comparison rules needs review.

## Run it locally

From the repo root, with Python 3.12.14:

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

Keep this pinned environment separate from your general one. A smaller budget or fewer seeds works for a quick smoke test, but it will (correctly) fail the comparison against the full recorded run.

## Determinism

`cold_plate_search.py` already controls randomness:

- A seeded NumPy generator sets the candidate order, and candidates are built in a fixed order.
- Each forest uses `random_state=seed` and `n_jobs=1`.
- Exact ties are broken by candidate ID. Verified winners are sorted by pump power, then temperature, then candidate ID.
- Exploration follows a fixed schedule. Elapsed time never affects selection and is removed from the scientific files.

CI also fixes Python's hash seed and limits math libraries to one thread. This reduces variation without changing the search algorithm or its settings.

As [scikit-learn's RandomForestRegressor docs](https://scikit-learn.org/1.9/modules/generated/sklearn.ensemble.RandomForestRegressor.html#notes) explain, a fixed random state is needed for deterministic fits because of feature permutations and tied splits. But fixed seeds don't guarantee identical results across library versions. Changes in tree fitting, numeric reductions, or prediction order can change which candidate the search picks, and once one pick differs, every later training set differs too. That's a plausible explanation, not proof of a specific upstream change.

### What we found

On November 2, 2026, we reran the unmodified source at `6cc65cda09bcc80b31d4ba953ebb2fd39bb0fa9d` locally in a general Python 3.12.14 environment (NumPy 2.3.5, pandas 2.2.3, SciPy 1.17.0, scikit-learn 1.8.0, joblib 1.5.3, threadpoolctl 3.6.0):

- Five of seven scientific files matched exactly. Only `search_trials.csv` and `search_summary.csv` differed, and every random-search row was unchanged.
- 182 of 1,536 trial rows picked different candidates. The first difference was nominal/surrogate/seed 11/evaluation 24: candidate 542 in the recorded run vs. 562 in the general environment.
- Two of 48 summary rows changed. For higher-load/surrogate/seed 22, the selected candidate went from 605 to 604, and the modeled peak base temperature went from about 38.783909°C to 39.083427°C at the same pump power.
- Every paired outcome stayed the same: 16 wins, six ties, and two losses.

A different selected design and a roughly 0.30°C temperature change are real result changes, not rounding. The general environment may be running a legitimately different version of the search, but it isn't an exact replay, and the pinned job has to fail on these differences even when the overall counts match.

A follow-up changed **only scikit-learn, from 1.8.0 to 1.9.1**, in an isolated environment built on the general stack. With all six package versions confirmed in the generated metadata, all seven files matched the recorded results byte for byte. In this experiment, the scikit-learn change alone explained the drift. That doesn't prove other dependency changes never matter, or pinpoint the exact tree-fitting change.

| Local run | Packages changed from the general stack | Exact matches with recorded files |
| --- | --- | --- |
| General stack | None | 5/7 |
| General stack, rerun with CI hash/thread settings | None | 5/7, and 7/7 against the first general run |
| scikit-learn upgrade only, with CI settings | scikit-learn 1.9.1 | 7/7 |
| Full recorded stack, with CI settings | All six recorded pins | 7/7 |

Every run used Python 3.12.14 on the same Linux machine with identical benchmark, search, and simulator source hashes. The repeat run rules out hash and thread settings as the cause on this machine. The single-package test used a separate virtual environment with `--system-site-packages` on top of the general stack, then `python -m pip install --no-deps scikit-learn==1.9.1`, and reran the full default benchmark and checker without changing any source or reference data.

All **140 tests** passed in both the general and fully pinned environments. The pinned run showed 21 existing Streamlit/pandas deprecation warnings, and `pip check` passed. Twelve new checker tests cover missing and changed files, unchanged totals with changed trials, multiple failures, tiny numeric drift, formatting changes, excluded timing/metadata, self-comparison, exit codes, diff limits, and leaving the references untouched. Workflow parsing and `git diff --check` passed locally. Python 3.10 and the GitHub-hosted jobs are checked separately in CI.

## If the replay fails

1. Look at the diff and generated artifact for the failing file. Sort out whether it's a missing file, a formatting-only change, small rounding, or a change in selected candidates, feasibility, or results.
2. Compare Python and package versions with the recorded pins, and compare source hashes in the metadata. Rerun in a fresh pinned environment before blaming the scientific code.
3. If a difference remains under the pinned stack, investigate it. Don't replace the committed references just to make CI pass. An intentional model or dependency change needs separately recorded results and scientific review, with the old results kept.

Pinning packages doesn't lock wheel builds, system math libraries, or CPU architecture. The supported target is Ubuntu x86-64 on the recorded Python patch release, and other systems may surface new portability issues. Exact replay and physical validation are separate requirements.
