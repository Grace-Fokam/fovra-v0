# Fovra v0 🔥💧

[![tests](https://github.com/Grace-Fokam/fovra-v0/actions/workflows/tests.yml/badge.svg)](https://github.com/Grace-Fokam/fovra-v0/actions/workflows/tests.yml)

**Can a little ML model learn how a physical system behaves, and then use that to make decisions?**

That's the question this repo starts poking at. It's the very first prototype of [Fovra](#whats-next): a tiny virtual hot-water tank, a model that learns how it heats up and cools down, and a controller that uses that model to plan ahead. There's a Streamlit dashboard so you can mess with the conditions and watch it work against classic controllers.

Everything runs on your laptop. No hardware, no GPU, no real factory required.

> ⚠️ **Quick honesty check:** this is a simplified *simulation*. It's not a digital twin of real equipment, not proof of energy savings, and not a safe controller for anything real. It's a starting point.

---

## What's going on in here

The loop is pretty simple:

1. **Observe**: read the tank temperature, room temperature, and how much heat production is pulling out
2. **Predict**: a scikit-learn model guesses what the temperature will be 5 minutes from now for different heater settings
3. **Plan**: try every combination of heater settings over the next 20 minutes (625 plans), score each on electricity + staying near 60°C + not leaving the 58–62°C band + not flip-flopping the heater
4. **Act**: apply only the first step of the best plan, see what actually happened, and plan again

That's called *model predictive control* (MPC). Fovra's version uses a *learned* model instead of hand-written physics.

It goes head-to-head against two conventional controllers on the exact same simulated day:

- **Thermostat**: heater on full below 59°C, off above 61°C
- **PI controller**: the classic industrial feedback controller

## Run it

You'll need Python 3.10+.

```bash
git clone https://github.com/Grace-Fokam/fovra-v0.git
cd fovra-v0

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt

python -m streamlit run app.py
```

Your browser should open to `http://localhost:8501`. Hit **Ctrl+C** in the terminal to stop it.

In the sidebar you can:

- slide the **surrounding temperature** (10–35°C)
- slide the **production heat demand** (1–6 kW)
- pick a **scenario**: Normal, Production surge, or Heater degradation
- pick which **baseline** Fovra goes up against

Then smash **Run simulation**. Every chart and number gets recomputed from the actual simulation, so nothing's hardcoded.

### Don't want the browser?

```bash
python run_example.py
```

This dumps the default comparisons into `examples/` as CSVs.

### Tests

```bash
python -m pytest -q
```

- `tests/test_core.py` covers the physics, scenarios, model, and controller comparisons
- `tests/test_app.py` drives the dashboard headlessly with Streamlit's `AppTest` (moves sliders, picks scenarios, clicks Run, checks the numbers on screen match the simulator)

These also run automatically on every push via GitHub Actions.

## The three scenarios

| Scenario | What happens | What it's testing |
|---|---|---|
| **Normal** | Room temp and production demand drift a little over the day | Can Fovra hold temperature without wasting energy? |
| **Production surge** | Hours 10–14: production suddenly pulls an extra 2.5 kW | Can it react to a surprise? (No one gets advance warning.) |
| **Heater degradation** | From hour 10: only 65% of the heater's power actually reaches the water, but it still draws full electricity | What happens when the model's picture of the world goes stale? |

The degradation one is meant to show a weakness, not a strength: the model is never told about it or retrained.

## Results so far

Default settings (20°C room, 3 kW demand, 24 hours, vs. thermostat):

| Scenario | Fovra (kWh) | Thermostat (kWh) | Time outside 58–62°C |
|---|---|---|---|
| Normal | 148.75 | 149.00 | 0 min / 0 min |
| Production surge | 158.75 | 158.00 | 0 min / 0 min |
| Heater degradation | 194.00 | 196.00 | 0 min / 0 min |

Translation: **basically a tie.** And that's expected! The tank has a fixed-efficiency heater with fixed requirements, so there just isn't much energy to save. What this proves is that the whole learn → predict → plan → act pipeline works end to end. Not that AI wins.

A few things get more interesting at the edges:

- **Cold room + high demand + surge:** Fovra stays in band while the thermostat drops below 58°C for 50 minutes. But Fovra changes the heater setting 151 times vs. 25, which real equipment might not love.
- **Cold room + high demand + degradation:** both controllers sink to ~42°C. The weakened heater physically can't keep up, so no controller could.

### Why is the prediction error basically zero?

Because the simulator is a linear equation and the model is linear regression, so it's just rediscovering the formula I wrote. That's a sanity check that the wiring is right, not a breakthrough. Making the physics messier is next on the list.

## Repo tour

| File | What it does |
|---|---|
| `simulator.py` | The virtual tank: energy balance every 5 minutes, plus the three scenarios |
| `train_model.py` | Generates 6,000 synthetic examples and trains the linear regression model |
| `controllers.py` | Thermostat, PI controller, and Fovra's learned MPC |
| `evaluation.py` | Runs fair matched experiments and computes the metrics |
| `app.py` | The Streamlit dashboard |
| `run_example.py` | Same experiments, no browser |
| `examples/` | Saved CSVs from the default runs |
| `tests/` | Core + dashboard tests |

<details>
<summary><b>How the metrics are calculated</b></summary>

- **Electricity (kWh):** sum of heater electrical input over 288 five-minute steps. A degraded heater still bills you for full power.
- **Time outside 58–62°C:** number of 5-minute checkpoints outside the band × 5 minutes. An approximation, not continuous time.
- **Worst deviation from 60°C:** biggest gap between any checkpoint and the 60°C target.
- **Heater power adjustments:** how many times the heater command changed by more than 0.01 kW.
- **One-step prediction MAE:** average gap between what the model predicted and what the simulator actually did.

</details>

<details>
<summary><b>The physics, in one line</b></summary>

```
next temp = temp + (heater × efficiency − 0.08 × (temp − room temp) − production demand) × (5/60 h) ÷ 1 kWh/°C
```

All parameters are made-up-but-reasonable illustration values, not measurements from real equipment.

</details>

## What's next

Fovra is aiming at **generalizable AI for physical systems**, starting with industrial energy. This repo is v0. Roughly what comes after:

- [ ] Messier physics: nonlinear heater efficiency, sensor noise, delays, equipment wear
- [ ] Fairer baselines: a well-tuned PID and a classic physics-based MPC
- [ ] **Adaptation:** let the model notice it's wrong (hi, degradation scenario) and update itself
- [ ] A second system (a pump between tanks) to see whether the architecture carries over
- [ ] Test on outside benchmarks like [BOPTEST](https://ibpsa.github.io/project1-boptest/) so I'm not grading my own homework

## License

MIT. See [LICENSE](LICENSE). No external datasets are used; everything is generated locally.
