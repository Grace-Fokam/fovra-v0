# Fovra v0

[![Tests](https://github.com/Grace-Fokam/fovra-v0/actions/workflows/tests.yml/badge.svg)](https://github.com/Grace-Fokam/fovra-v0/actions/workflows/tests.yml)
[![Cold-plate research](https://github.com/Grace-Fokam/fovra-v0/actions/workflows/cold-plate.yml/badge.svg)](https://github.com/Grace-Fokam/fovra-v0/actions/workflows/cold-plate.yml)

Fovra is exploring AI-assisted design of computer components, with liquid cooling as an active research direction. This repository contains early component-design and data-center cooling simulation experiments. The precise product and customer requirements remain under investigation.

**Research status:** The models are illustrative, not validated hardware or field deployments. The results do not demonstrate new cooling hardware, manufacturing feasibility, real-world efficiency gains, or a general computational advantage from machine learning.

## Research

| Track | Implemented work | Evidence boundary |
| --- | --- | --- |
| **Computer-component design: liquid cold plates** | A command-line prototype evaluates straight-channel geometry, material conductivity, and flow using a reduced-order thermal/hydraulic model. It compares surrogate-assisted and random search with equal simulator-call budgets. | No CFD, fabricated samples, or measured package performance. Manufacturability and material cost are not yet modeled. [Methods and limitations](docs/cold-plate.md). |
| **Data-center cooling exploration** | An interactive Streamlit dashboard compares dry cooling and evaporative assistance under matched simulated IT loads and weather. A second experiment compares learned screening and random search. | Synthetic equipment curves and weather. This is system-level configuration research, not a validated component design. [Methods and limitations](docs/cooling-experiment.md). |

The Streamlit app opens directly into **Cooling exploration**. Cold-plate geometry research runs separately from the command line.

## Run locally

Python 3.10 or newer is required for the general research environment.

```bash
git clone https://github.com/Grace-Fokam/fovra-v0.git
cd fovra-v0
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Open `http://localhost:8501`. Adjust climate, IT load, cooler size, and evaporative-assist settings. Explore cooling electricity, water, and modeled temperature limits. The optional **Run AI comparison** action evaluates learned screening against random search using the same simulation budget.

To run the tests and independent experiments:

```bash
python -m pytest -q
python benchmark_cooling.py --output /tmp/fovra-cooling
python benchmark_cold_plate.py --output /tmp/fovra-cold-plate
```

These commands write to temporary directories rather than overwriting committed results. The recorded cold-plate numerical environment uses Python 3.12.14 and `requirements-cold-plate.txt`. Follow the [scientific replay instructions](docs/cold-plate-reproducibility.md) to check all seven scientific outputs against their references.

To deploy the dashboard, use the [Streamlit Community Cloud guide](docs/deploy-streamlit.md). No live URL has been verified in this repository.

## Findings and limitations

**Cold-plate search.** Across 24 matched synthetic comparisons, random-forest-assisted search beat random search in 16, tied six, and lost two. However, exhaustive evaluation of the finite candidate grids took about 0.05 seconds, whereas the recorded surrogate runs collectively took about 22.31 seconds. This benchmark does **not** show that ML is faster than exhaustive search. Reference winners often select minimum web/base thickness and maximum available material conductivity, so fabrication and material tradeoffs need to be evaluated before treating these as hardware candidates.

**System-level cooling.** Among nine feasible case-and-seed comparisons, AI screening and random search tied seven times, with one AI win and one AI loss. Nine other comparisons have no feasible grid candidate under the modeled constraints. The dashboard labels modeled thermal failures explicitly. The experiment does **not** establish that learned search is superior.

See the [cold-plate report](docs/cold-plate.md), [cooling experiment report](docs/cooling-experiment.md), and committed `results/cold_plate/` and `results/cooling/` for assumptions, outputs, and reproducibility information. The `.github/workflows/` checks exercise the remaining code and the pinned cold-plate replay.

## Next research steps

1. Specify a component use case and constraints with prospective engineering collaborators, including heat loads, inlet conditions, temperature and pressure limits, and manufacturing requirements.
2. Validate preregistered cold-plate candidates using conjugate CFD, mesh/conservation checks, and uncertainty estimates.
3. Fabricate and instrument a small reference set to measure temperatures, flow, pressure loss, and pump power.
4. Compare surrogate-assisted search against conventional optimization methods under matched budgets when each evaluation is materially more expensive.

These are proposed research gates, not evidence of commercial readiness.
