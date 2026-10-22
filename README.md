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

It goes head-to-head against three conventional controllers on the exact same simulated day:

- **Thermostat**: heater on full below 59°C, off above 61°C
- **PI controller**: the classic industrial feedback controller
- **Physics MPC**: the same planner as Fovra, using the nominal heat-balance equation

**Current finding:** the learned and physics MPCs produce identical actions in the
27 matched cases below. The learned model adds no measured control benefit under
these assumptions. This comparison tests the value of learning separately from
the value of planning ahead.

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

For the matched physics-MPC experiment, including all four controllers:

```bash
python benchmark_mpc.py --output results/mpc_comparison
# Shorter rerun (same cases, one timing repetition):
python benchmark_mpc.py --output /tmp/fovra-mpc --repeats 1
```

Use `--seeds 20261020 20261021 20261022` to specify training seeds explicitly.
The committed results used Python 3.12.14 and the versions in
`requirements-benchmark.txt`. Install that file in a separate Python 3.12
environment to match the numerical environment. Normal installs and CI use
`requirements.txt`, which supports Python 3.10+. Timings will vary by machine.

### Tests

```bash
python -m pytest -q
```

- `tests/test_core.py` covers the physics, scenarios, model, and controller comparisons
- `tests/test_app.py` drives the dashboard headlessly with Streamlit's `AppTest` (moves sliders, picks scenarios, clicks Run, checks the numbers on screen match the simulator)
- `tests/test_mpc.py` checks both planners against an independent scalar cost calculation, shared observations, hidden degradation, persistence forecasts, metrics, and preservation of the original learned-controller results
- `tests/test_benchmark.py` checks fresh-state repeatability and exported experiment records

These run on every push and pull request with Python 3.10 and 3.12. CI also runs
the benchmark with one timing repetition and uploads the records as artifacts.

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

## Learned versus physics-based MPC

### Comparison protocol

The new `PhysicsMPC` uses the nominal energy balance directly. It assumes heat
capacity 1 kWh/°C, heat loss 0.08 kW/°C, and heater efficiency 1.0. These are the
same nominal parameters that generated the learned model's training data. It
does **not** receive the plant's actual efficiency after degradation. Neither
controller adapts or retrains during evaluation.

Both inherit one optimizer in `controllers.py`. Only the dynamics prediction
differs, preventing accidental differences in tuning or search from being
credited to machine learning.

| Choice | Shared by both MPCs |
|---|---|
| Observations | Current water temperature, ambient temperature and production demand |
| Hidden information | No scenario name, clock, future disturbance schedule or actual heater efficiency |
| Forecast | Hold current ambient and demand constant for the entire horizon |
| Actuation | 0, 3, 6, 9 or 12 kW, with a hard 0–12 kW actuator limit |
| Horizon and search | Four 5-minute steps, all 625 ordered plans, apply the first action |
| Starting state | Tank at 60°C, previous command 0 kW, fresh controller for every trial |
| Objective per step | Electrical kWh + 9 × target error² + 500 × band violation² + 0.006 × command change² |
| Temperature limits | 58–62°C **soft penalties**, not guaranteed hard constraints |
| Tie handling | First minimum in the same ordered plan grid via `numpy.argmin` |

The benchmark uses all three scenarios at `(ambient °C, demand kW)` profiles
`(20, 3)`, `(10, 6)` and `(35, 1)`, and training seeds 20261020, 20261021 and
20261022. That is **27 distinct matched MPC cases**. Three timing repetitions
and four controllers produce **324 simulated controller-days**. Five warmup
decisions use disposable controllers. Execution order rotates, native numerical
libraries use one thread, and evaluation always starts from fresh state.

Seeds resample noiseless synthetic training data. Repetitions rerun deterministic
days for timing. Neither represents independent real plants, and neither supports
statistical claims about industrial generalization.

### Measured control results

At default conditions, both MPCs produced the following results. Each common
metric applies to **each** controller, not an average between them.

| Scenario | Learned / physics energy (kWh) | RMSE from 60°C, both (°C) | Outside band, both (min) | Power adjustments, both | Total power variation, both (kW) |
|---|---:|---:|---:|---:|---:|
| Normal | 148.75 / 148.75 | 0.0652 | 0 | 62 | 186 |
| Production surge | 158.75 / 158.75 | 0.0649 | 0 | 68 | 204 |
| Heater degradation | 194.00 / 194.00 | 0.2586 | 0 | 79 | 237 |

All 27 matched cases had **zero action mismatches and zero temperature-trajectory
gap**. Energy, temperature RMSE and standard deviation, constraint-violation
duration and severity, adjustment counts and total actuator movement were
identical. There was no measured control benefit from the learned model.

The harsher cases show the limits of both controllers:

| Cold/high-demand case (10°C, 6 kW) | Energy, each (kWh) | Target RMSE, each (°C) | Outside band, each (min) | Minimum temperature, each (°C) |
|---|---:|---:|---:|---:|
| Production surge | 249.75 | 0.4517 | 0 | 58.56 |
| Heater degradation | 268.75 | 9.1938 | 795 | 42.08 |

The degraded heater cannot sustain the required band at this high load. Its
maximum delivered heat is only 7.8 kW. Low energy use during a violation is not
a performance win. The exact equality of the MPC trajectories also means they
finish with the same stored thermal energy, avoiding an endpoint-energy bias in
this particular comparison.

### Computation time

The values below summarize this environment, **not a platform-independent speed
guarantee**. Each row is the median across 81 controller-days of that day's mean,
95th percentile, or total decision time, respectively. Training, diagnostic
predictions, simulation updates and UI rendering are excluded from decision
timing. Training and validation time is recorded separately in `metadata.json`.

| Controller | Median daily mean (ms/decision) | Median daily p95 (ms/decision) | Median daily total (ms) |
|---|---:|---:|---:|
| Fovra | 0.206676 | 0.312409 | 59.523 |
| Physics MPC | 0.096876 | 0.133417 | 27.900 |
| Thermostat | 0.000133 | 0.000171 | 0.038 |
| PI controller | 0.004964 | 0.005044 | 1.430 |

The learned path incurs scikit-learn prediction and input-processing overhead.
This is a comparison of the current implementations, not proof that a learned
linear equation intrinsically requires more computation. The dashboard caches
results, including their original timing. Use the benchmark for fresh timings.

### What the result means

With noiseless linear training data and a linear simulator, regression recovers
the same transition equation available to the physics controller. The shared
optimizer then assigns essentially the same cost to each plan and chooses the
same actions in these runs. Both use a nominal model when efficiency drops, so
both make the same prediction errors and react through feedback. Small numerical
differences can still affect discrete decisions near an exact cost tie outside
these tested cases.

**The current evidence supports a working learned-control pipeline, not a useful
ML advantage, demonstrated generalization, or industrial validation.** Better
performance than the illustrative thermostat or untuned PI controller cannot by
itself establish that learning helped. Physics MPC now isolates that question.

### Experiments that would test generalization

1. **Held-out plants and operating regimes.** Split by thermal capacity, heat
   loss, efficiency, starting temperatures and complete trajectories, not random
   rows from the same plant. Report zero-shot performance separately from
   recalibration. Give both methods the same commissioning data and compare to
   an identified physics model as well as fixed nominal physics.
2. **Unmodeled nonlinear dynamics.** Introduce temperature-dependent efficiency,
   multi-node thermal inertia, delays or saturation. Compare nonlinear learned
   and hybrid residual models against appropriate nonlinear/grey-box MPC, with
   the same action grid, objective, forecasts and data budget. A deliberately
   misspecified physics baseline alone would be weak evidence.
3. **Causal adaptation to drift.** Adapt from past measurements only, without
   revealing the change time or true efficiency. Compare learned adaptation with
   online parameter estimation and adaptive physics MPC. Measure recovery time,
   cumulative violations and energy, including the cost of data collection.
4. **Noise and uncertainty.** Add held-out sensor noise, biases and disturbance
   patterns. Share observations and forecasting information. Measure multi-step
   rollout error, constraint violations and uncertainty calibration over paired
   disturbance seeds, with uncertainty intervals and equal tuning budgets.
5. **Independent systems or data.** Evaluate on an external simulator or measured
   trajectories with held-out equipment. Predeclare success metrics combining
   comfort/process constraints, energy, actuator movement and compute. Check
   final stored energy and physical feasibility before claiming savings.

### Reproducible records

- [Per-controller measurements](results/mpc_comparison/measurements.csv): all
  324 runs, including thermostat and PI, every requested metric, repeat and order.
- [Paired differences](results/mpc_comparison/paired_differences.csv): learned
  minus physics metrics and action/trajectory gaps for all 27 distinct pairs.
- [Run metadata](results/mpc_comparison/metadata.json): seeds, profiles, package
  versions, platform, timing protocol, training cost and source-file SHA-256s.
- `results/mpc_comparison/{normal,production_surge,heater_degradation}.csv`:
  step records for default conditions and the first seed/repetition, including
  both predictions and per-decision timings. All other trajectories regenerate
  deterministically through `run_controller`.

Non-timing outcomes are reproducible. Wall-clock times, metadata timestamps and
floating-point roundoff may differ. The original `examples/` records and
`run_example.py` thermostat comparison remain available.

## Repo tour

| File | What it does |
|---|---|
| `simulator.py` | The virtual tank: energy balance every 5 minutes, plus the three scenarios |
| `train_model.py` | Generates 6,000 synthetic examples and trains the linear regression model |
| `controllers.py` | Thermostat, PI controller, learned MPC and physics MPC with a shared planner |
| `evaluation.py` | Runs fair matched experiments and computes the metrics |
| `app.py` | The Streamlit dashboard |
| `run_example.py` | Same experiments, no browser |
| `benchmark_mpc.py` | Matched physics-versus-learned MPC trials and repeatable timing protocol |
| `results/mpc_comparison/` | Recorded benchmark measurements, paired differences and provenance |
| `examples/` | Saved CSVs from the default runs |
| `tests/` | Core + dashboard tests |

<details>
<summary><b>How the metrics are calculated</b></summary>

- **Electricity (kWh):** sum of heater electrical input over 288 five-minute steps. A degraded heater still bills you for full power.
- **Time outside 58–62°C:** number of 5-minute checkpoints outside the band × 5 minutes. An approximation, not continuous time.
- **Worst deviation from 60°C:** biggest gap between any checkpoint and the 60°C target.
- **Target RMSE:** square root of mean squared error from 60°C at end-of-step checkpoints. Temperature standard deviation is population standard deviation about the observed mean, so it does not measure target bias.
- **Violation severity:** maximum distance outside 58–62°C, plus the sum of outside-band distances × 5 minutes in °C·min.
- **Heater power adjustments:** how many successive commands changed by more than 0.01 kW. The initial off-to-first-command transition is excluded, preserving the original metric. This measures command changes, not mechanical relay cycles.
- **Total heater variation:** sum of absolute changes between successive commands, in kW, also excluding the initial transition.
- **Decision computation:** elapsed wall time around `choose` only, reported as mean, 95th percentile and total milliseconds.
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
- [x] Matched nominal physics-based MPC and reproducible comparisons
- [ ] Well-tuned PID and identified/adaptive physics MPC for harder experiments
- [ ] **Adaptation:** let the model notice it's wrong (hi, degradation scenario) and update itself
- [ ] A second system (a pump between tanks) to see whether the architecture carries over
- [ ] Test on outside benchmarks like [BOPTEST](https://ibpsa.github.io/project1-boptest/) so I'm not grading my own homework

## License

MIT. See [LICENSE](LICENSE). No external datasets are used; everything is generated locally.
