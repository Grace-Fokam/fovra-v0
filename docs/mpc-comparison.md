# Fovra vs. Physics MPC

This compares two planners that are the same in every way but one. Fovra predicts the tank with a learned model. Physics MPC predicts it with the tank's equation. If Fovra does better, the learning helped. If they tie, only the planning did.

## How the test is set up

Physics MPC uses the same equation that generated Fovra's training data: heat capacity 1 kWh/°C, heat loss 0.08 kW/°C, and a heater that's 100% efficient. It isn't told when the heater degrades. Neither planner retrains or adapts during a run.

Both planners share the same code in `controllers.py`. Only the prediction step is different, so any difference in results comes from the model, not from tuning.

| | Both planners |
|---|---|
| What they see | Water temperature, room temperature, and production demand right now |
| What they don't see | The scenario, the clock, future changes, or the heater's real efficiency |
| Forecast | Room temperature and demand stay the same for the next 20 minutes |
| Heater settings | 0, 3, 6, 9, or 12 kW |
| Search | All 625 plans over four 5-minute steps, then apply the first step |
| Start | Water at 60°C, heater off, a fresh controller every run |
| Score per step | kWh + 9 × (miss from 60°C)² + 500 × (distance out of range)² + 0.006 × (change in heater power)² |
| The 58–62°C range | A penalty, not a hard guarantee |
| Ties | The first best plan in the list (`numpy.argmin`) |

I ran all three scenarios at three settings (20°C room / 3 kW demand, 10°C / 6 kW, and 35°C / 1 kW), with three training seeds (20261020, 20261021, 20261022). That's 27 matched cases. Each was repeated three times for timing, across all four controllers, for 324 simulated days in total.

The seeds only change which simulated examples the model trains on. They aren't different tanks, so these runs don't say anything about how Fovra would do on other equipment.

## Results

At the default setting (20°C room, 3 kW demand), each number below is the same for both planners.

| Scenario | Energy (kWh) | Typical miss from 60°C (°C) | Time out of range | Heater changes | Total heater movement (kW) |
|---|---:|---:|---:|---:|---:|
| Normal | 148.75 | 0.0652 | 0 min | 62 | 186 |
| Production surge | 158.75 | 0.0649 | 0 min | 68 | 204 |
| Heater degradation | 194.00 | 0.2586 | 0 min | 79 | 237 |

In all 27 cases, the two planners made exactly the same choice at every step and produced the same temperatures.

The cold, high-demand setting (10°C room, 6 kW demand) shows where both planners hit their limits:

| Scenario | Energy (kWh) | Typical miss from 60°C (°C) | Time out of range | Lowest temperature |
|---|---:|---:|---:|---:|
| Production surge | 249.75 | 0.4517 | 0 min | 58.56°C |
| Heater degradation | 268.75 | 9.1938 | 795 min | 42.08°C |

Once the heater degrades, it can only deliver 7.8 kW, which isn't enough at this load. No controller could keep the water in range.

## Speed

These timings are from one machine and only count the time spent choosing a heater setting. Each row is the median over 81 simulated days.

| Controller | Average (ms per decision) | Slow decisions, 95th percentile (ms) | Total per day (ms) |
|---|---:|---:|---:|
| Fovra | 0.207 | 0.312 | 59.5 |
| Physics MPC | 0.097 | 0.133 | 27.9 |
| Thermostat | 0.0001 | 0.0002 | 0.04 |
| PI controller | 0.005 | 0.005 | 1.4 |

Fovra is slower because each prediction goes through scikit-learn. That's a detail of this code, not something a learned model has to cost. Training time is recorded in `metadata.json`.

## What it means

With clean training data from a simple linear tank, the model learns the same equation Physics MPC already has. Both planners then score every plan the same way and make the same choices. When the heater degrades, both make the same wrong predictions and recover only by reacting to the temperature.

So v0 shows a working learn, predict, and plan pipeline. It doesn't show that the learning helps, that Fovra works on other equipment, or that it works on real equipment. Beating the thermostat or the PI controller doesn't prove the learning helped either. That's why Physics MPC is here.

## Tests that would show whether learning helps

1. **New tanks.** Train on some tanks and test on others with a different size, heat loss, or heater efficiency. Give Fovra and a physics model the same setup data.
2. **Behavior an equation can't capture.** Add efficiency that changes with temperature, uneven heating, or delays. Compare against a physics model built to handle them, with the same plans, score, and data.
3. **Drift.** Let both learn from past measurements only, without being told when or how the heater changed. Measure how fast each recovers, how long it's out of range, and how much energy it uses.
4. **Noise.** Add noisy or biased sensors. Measure prediction errors over longer horizons and how often each planner leaves the range.
5. **Outside data.** Test on a simulator I didn't build, or on real measurements. Decide what counts as success before running the test.

## Saved results

- [measurements.csv](../results/mpc_comparison/measurements.csv): all 324 runs, for every controller
- [paired_differences.csv](../results/mpc_comparison/paired_differences.csv): Fovra minus Physics MPC for all 27 cases
- [metadata.json](../results/mpc_comparison/metadata.json): seeds, settings, package versions, machine, and file hashes
- `normal.csv`, `production_surge.csv`, `heater_degradation.csv` in the same folder: step-by-step records for the default setting

Everything except timing reruns to the same result. Timings, timestamps, and tiny rounding differences will vary. The committed results used Python 3.12.14 with the versions in `requirements-benchmark.txt`.

## How each number is measured

- **Energy:** total heater electricity over the 288 five-minute steps. A degraded heater still uses its full power.
- **Time out of range:** the number of 5-minute checkpoints outside 58–62°C, times 5.
- **Typical miss from 60°C:** the RMSE from 60°C across checkpoints.
- **Biggest miss from 60°C:** the largest gap from 60°C at any checkpoint.
- **Heater changes:** how many times the heater setting changed by more than 0.01 kW, not counting the first switch on.
- **Total heater movement:** the sum of every change in heater setting, in kW.
- **Prediction error:** the average gap between the predicted and actual temperature 5 minutes later.
