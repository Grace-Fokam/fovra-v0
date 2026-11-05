# Chip Cooling Design Lab

*Research prototype (v0)*

[![Tests](https://github.com/Grace-Fokam/fovra-v0/actions/workflows/tests.yml/badge.svg)](https://github.com/Grace-Fokam/fovra-v0/actions/workflows/tests.yml)
[![Cold-plate research](https://github.com/Grace-Fokam/fovra-v0/actions/workflows/cold-plate.yml/badge.svg)](https://github.com/Grace-Fokam/fovra-v0/actions/workflows/cold-plate.yml)

Can AI help design better computer parts? This is my first shot at finding out, starting with liquid cooling. It's the early research behind Fovra.

**Heads up:** Everything here is simulated. None of it proves the designs can be built or would save energy in real life.

## What's here

| Project | What it does | Not there yet |
| --- | --- | --- |
| **Cold plates** | A command-line tool that tries straight-channel layouts, materials, and flow rates in a simplified heat-and-flow model, comparing ML-guided and random search. | No CFD, real parts, or measurements. Doesn't check manufacturability or cost. [More](docs/cold-plate.md) |
| **Data-center cooling** | A Streamlit dashboard comparing dry cooling and evaporative assist under the same load and weather. | Uses synthetic equipment data and weather. [More](docs/cooling-experiment.md) |

## Try it

You'll need Python 3.10+.

```bash
git clone https://github.com/Grace-Fokam/fovra-v0.git
cd fovra-v0
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Then open `http://localhost:8501`. Play with climate, IT load, and cooling settings, or hit **Run AI comparison** to race ML against random search.

Tests and benchmarks:

```bash
python -m pytest -q
python benchmark_cooling.py --output /tmp/fovra-cooling
python benchmark_cold_plate.py --output /tmp/fovra-cold-plate
```

These write to temp folders, so the saved results don't change. To match my cold-plate numbers exactly, see the [reproducibility guide](docs/cold-plate-reproducibility.md). To put the dashboard online, see the [Streamlit guide](docs/deploy-streamlit.md).

## What I found

**Cold plates:** ML-guided search beat random search in 16 of 24 matched tests, tied 6, and lost 2. But brute-forcing every design took 0.05 seconds versus 22.31 for ML, so ML wasn't faster here. The winners also lean on the thinnest walls and most conductive materials, which might be hard or pricey to build.

**Data-center cooling:** Only 9 of 18 tests had any setup that met the limits. In those, ML and random search tied 7 times and each won once. No clear win for ML yet.

Details live in the [cold-plate](docs/cold-plate.md) and [cooling](docs/cooling-experiment.md) docs and `results/`.

## What's next

1. Team up with engineers on a real use case with real heat loads, limits, and manufacturing needs.
2. Check the top cold-plate designs with full CFD, picked ahead of time so there's no cherry-picking.
3. Build a few real plates and measure temperature, flow, and pressure loss.
4. Compare against standard optimizers once each simulation is slow enough to matter.
