# Fovra v0

[![tests](https://github.com/Grace-Fokam/fovra-v0/actions/workflows/tests.yml/badge.svg)](https://github.com/Grace-Fokam/fovra-v0/actions/workflows/tests.yml)

Fovra v0 is a first experiment. Can a small machine learning model learn how a physical system behaves, and then use that to control it?

The test system is a simulated hot water tank. A heater has to keep the water between 58 and 62°C while production pulls heat out. Fovra learns how the tank responds, looks 20 minutes ahead, and picks heater settings that stay in range without wasting energy.

It's all a simulation with made-up but reasonable numbers. It isn't real equipment, and it doesn't prove energy savings.

![How Fovra works](docs/fovra_loop.png)

## What I compare it against

Each controller gets the exact same simulated day.

- **Thermostat.** Heater on below 59°C, off above 61°C.
- **PI controller.** A standard feedback controller used in industry.
- **Physics MPC.** Plans exactly like Fovra, but uses the tank's equation instead of a learned model. This one answers whether the learning helps, or only the planning.

## Run it

You'll need Python 3.10 or newer.

```bash
git clone https://github.com/Grace-Fokam/fovra-v0.git
cd fovra-v0
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

The dashboard opens at `http://localhost:8501`. Pick a room temperature, a production demand, a scenario, and a controller to compare against, then click Run.

Other things you can run:

- `python run_example.py` saves the thermostat comparisons as CSVs in `examples/`
- `python benchmark_mpc.py --output results/mpc_comparison` reruns the full Fovra vs. Physics MPC comparison
- `python -m pytest -q` runs the tests

## Scenarios

- **Normal.** Demand and room temperature drift a little through the day.
- **Production surge.** From hour 10 to 14, production needs 2.5 kW more, with no warning.
- **Heater degradation.** From hour 10, the heater only delivers 65% of its power. No controller is told.

## What I found

**Planning ahead helps.** In a cold room with high demand and a surge, Fovra stayed in range. The thermostat dropped below 58°C for 50 minutes. Fovra changed the heater setting far more often, though (151 times vs. 25).

![Fovra during a production surge](docs/fovra_stress_test.png)

**The learning doesn't help yet.** Fovra and Physics MPC made exactly the same choices in all 27 cases I tested. That makes sense: the simulator is a simple equation, so the model just learns that equation. To show that learning adds something, the tank needs behavior a simple equation can't capture.

**Neither model notices when the heater changes.** After the heater degrades, both make the same wrong predictions and never correct them. Fixing that is the next step.

![Prediction error after the heater degrades](docs/fovra_model_goes_stale.png)

Energy use was about the same for every controller at normal settings (148.75 kWh for Fovra vs. 149.00 for the thermostat). A tank this simple doesn't leave much energy to save.

The full comparison, with every number and how it was measured, is in [docs/mpc-comparison.md](docs/mpc-comparison.md).

## Files

- `simulator.py`: the tank and the scenarios
- `train_model.py`: trains the model
- `controllers.py`: the thermostat, the PI controller, Physics MPC, and Fovra
- `evaluation.py`: runs the comparisons and computes the results
- `app.py`: the dashboard
- `run_example.py`: the thermostat comparisons, without the browser
- `benchmark_mpc.py`: the Fovra vs. Physics MPC comparison
- `results/mpc_comparison/`: saved results from that comparison
- `tests/`: tests for the simulation, the planners, the benchmark, and the dashboard

## Next

- Messier physics: sensor noise, delays, wear, and uneven heating
- Stronger baselines: a well-tuned PID, and a physics model that updates itself
- A model that notices when it's wrong and adapts
- A second system, like a pump
- Testing on an outside benchmark like [BOPTEST](https://ibpsa.github.io/project1-boptest/)

## License

MIT

## Adaptive control experiment

A separate [adaptation experiment](docs/adaptation-results.md) compares rolling
learned dynamics with conventional online physical-parameter identification and
both fixed MPC baselines on unseen equipment and feasible efficiency changes.
Run `python benchmark_adaptation.py` to reproduce all trajectories and metrics.
This experiment leaves the original benchmark and dashboard unchanged.
