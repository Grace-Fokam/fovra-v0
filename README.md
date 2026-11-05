# Chip Cooling Design Lab

*Research prototype (v0)*

[![Tests](https://github.com/Grace-Fokam/fovra-v0/actions/workflows/tests.yml/badge.svg)](https://github.com/Grace-Fokam/fovra-v0/actions/workflows/tests.yml)
[![Cold-plate research](https://github.com/Grace-Fokam/fovra-v0/actions/workflows/cold-plate.yml/badge.svg)](https://github.com/Grace-Fokam/fovra-v0/actions/workflows/cold-plate.yml)

Fovra is exploring AI-assisted design of computer components, starting with liquid cooling. This repo holds early simulation experiments for cold-plate design and data-center cooling. The exact product and customer requirements are still being worked out.

**Status:** These are illustrative models, not validated hardware. The results don't show new cooling hardware, manufacturability, real-world efficiency gains, or a general speed advantage from machine learning.

## Research

| Track | What's built | Limits |
| --- | --- | --- |
| **Liquid cold plates** | A command-line prototype that searches straight-channel geometry, material, and flow using a reduced-order thermal/hydraulic model. Compares surrogate-assisted search with random search at equal simulator budgets. | No CFD, fabricated parts, or measurements. Manufacturability and material cost aren't modeled yet. [Details](docs/cold-plate.md) |
| **Data-center cooling** | A Streamlit dashboard comparing dry cooling and evaporative assist under the same simulated IT load and weather, plus a learned-screening vs. random-search experiment. | Synthetic equipment curves and weather. System-level configuration, not component design. [Details](docs/cooling-experiment.md) |

The dashboard covers cooling exploration. The cold-plate work runs from the command line.

## Run locally

Requires Python 3.10+.

```bash
git clone https://github.com/Grace-Fokam/fovra-v0.git
cd fovra-v0
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Open `http://localhost:8501` to adjust climate, IT load, cooler size, and evaporative-assist settings, and see the effect on electricity, water, and modeled temperature. **Run AI comparison** tests learned screening against random search on the same simulation budget.

To run the tests and benchmarks:

```bash
python -m pytest -q
python benchmark_cooling.py --output /tmp/fovra-cooling
python benchmark_cold_plate.py --output /tmp/fovra-cold-plate
```

These write to temp folders so the committed results stay untouched. The recorded cold-plate results used Python 3.12.14 and `requirements-cold-plate.txt`; see [reproducing the cold-plate results](docs/cold-plate-reproducibility.md) to check them exactly.

To deploy the dashboard, see the [Streamlit guide](docs/deploy-streamlit.md). There's no verified live URL yet.

## Findings

**Cold-plate search.** Across 24 matched synthetic comparisons, random-forest-assisted search beat random search 16 times, tied 6, and lost 2. But evaluating every candidate took about 0.05 seconds total, while the surrogate runs took about 22.31 seconds. This does **not** show ML is faster than exhaustive search. The winning designs often pick the thinnest walls and base and the most conductive material, so fabrication and material tradeoffs need a look before treating them as hardware candidates.

**Data-center cooling.** In the nine comparisons with a feasible option, AI screening and random search tied seven times, with one win and one loss for AI. The other nine had no feasible option under the modeled constraints. The dashboard flags modeled thermal failures. This does **not** show learned search is better.

Assumptions, outputs, and reproducibility details are in the [cold-plate](docs/cold-plate.md) and [cooling](docs/cooling-experiment.md) docs and in `results/`. GitHub Actions runs the tests and the pinned cold-plate replay.

## Next steps

1. Define a real component use case with engineering partners: heat loads, inlet conditions, temperature and pressure limits, and manufacturing requirements.
2. Validate preregistered cold-plate candidates with conjugate CFD, including mesh and conservation checks and uncertainty estimates.
3. Build and instrument a small reference set to measure temperature, flow, pressure loss, and pump power.
4. Compare surrogate-assisted search with conventional optimizers at matched budgets, once each evaluation is expensive enough to matter.
