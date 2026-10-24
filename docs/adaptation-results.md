# Does online adaptation improve control?

**Result: adaptation improves prediction and target tracking in this synthetic
suite, but does not demonstrate a generalizable ML advantage over adaptive
physics.** Neither adaptive controller saves energy relative to the fixed models.
All four controllers have zero safety violations, including after degradation.

## Matched protocol

Run `python -m pip install -r requirements.txt`, then
`python benchmark_adaptation.py --output results/adaptation` and
`python -m pytest -q`. Python 3.10 and 3.12 CI also runs the experiment and uploads
its complete output. Numerical versions and source hashes are recorded in
`results/adaptation/metadata.json`. The existing `requirements-benchmark.txt`
pins the numerical packages used here. Streamlit patch versions do not affect
this standalone experiment.

There are 18 matched cases, each with four fresh controller instances:
three equipment configurations × unchanged/degraded × seeds 11, 22, 33.
Each case lasts 24 hours at five-minute intervals. Training uses only the
original nominal tank. Seeds affect nominal training samples and a shared small
demand perturbation, not equipment parameters. These are robustness replicates
of three synthetic plants, not 18 independent real installations.

| Equipment | Capacity (kWh/°C) | Loss (kW/°C) | Initial efficiency |
|---|---:|---:|---:|
| Nominal | 1.00 | 0.08 | 1.00 |
| Unseen small | 0.65 | 0.11 | 0.90 |
| Unseen large | 1.60 | 0.05 | 0.85 |

In degraded runs, efficiency unexpectedly drops to 75% of its initial value at
hour 10. Capacity and loss differ across plants but remain constant during a run.
The change time and all equipment parameters are hidden from every controller.
Ambient is 20 ± 1°C. Demand is 2 ± 0.4 kW. Even the worst degraded configuration
has >0.98 kW of heating headroom at the upper safety boundary. Zero power cools
at the upper boundary and maximum power warms at the lower boundary. Capacity
checks reject infeasible cases rather than mixing them into the results.
This is a sufficient heat-capacity check, not a guarantee of safety for every
finite-action control policy or disturbance.

All controllers reuse the existing optimizer unchanged: 625 ordered plans,
0/3/6/9/12 kW actions, four-step (20-minute) horizon, current-disturbance
persistence forecast, identical energy/tracking/slew costs, and soft penalties
outside 58–62°C. These limits are not enforced hard safety constraints.
Each observes its own current temperature, ambient, process demand, and past
applied power. Closed-loop temperatures can differ. Equal information means the
same observation protocol, not access to another controller's trajectory.

- **Fixed learned MPC:** existing nominal scikit-learn model, never updated.
- **Fixed physics MPC:** existing nominal energy balance, never updated.
- **Adaptive learned MPC:** unconstrained affine regression of temperature change
  on temperature, ambient, demand, power, and an intercept.
- **Adaptive physics MPC:** conventional bounded least squares for energy-balance
  coefficients: loss/capacity, (1−efficiency)/capacity, efficiency/capacity.
  Nonnegative bounds preserve nonnegative loss and efficiency between zero and
  one. It estimates combinations of parameters. Individual parameters need
  adequate excitation to be identified.

Both adaptive models start from the same nominal dynamics and fit the latest
48 completed transitions (four hours), starting after six samples. Both use
ridge strength 1e−6 toward their nominal coefficients. The learned prior is the
analytical nominal linear model, equivalent to the original nominal training
fit up to floating-point error. Prediction and action selection occur **before**
observing the next temperature and updating. No oracle reset, change detector,
future observations, or extra identification actions are provided. Different
feature coordinates and physical bounds are intentional inductive biases, so
equal ridge values do not imply identical effective priors.

## Measurements

Prediction MAE is scored before each update on the controller's actual next
transition. A second metric uses an identical 15-point grid of temperatures
58/60/62°C and powers 0/3/6/9/12 kW at the current ambient and demand. Only the
evaluator uses true plant dynamics for these probes. Probe targets never enter
training. This grid reduces the chance of mistaking good predictions on one
visited operating point for an accurate dynamics model.

The following are means over all nine **degraded** cases. Post-change MAE covers
hours 10–24. Energy, target RMSE, and violations cover the full day.

| Controller | Post-change on-policy MAE (°C/step) | Post-change probe MAE (°C/step) | Energy (kWh/day) | Target RMSE (°C) | Violations (min/day) |
|---|---:|---:|---:|---:|---:|
| Fixed learned | 0.195642 | 0.230176 | 161.611 | 0.221665 | 0 |
| Fixed physics | 0.195642 | 0.230176 | 161.611 | 0.221665 | 0 |
| Adaptive learned | 0.009812 | 0.048354 | 162.500 | 0.069011 | 0 |
| Adaptive physics | 0.016483 | 0.023726 | 162.500 | 0.072722 | 0 |

Both adaptive methods track 60°C more closely, using 0.889 kWh/day more than
fixed learned MPC on average (about 0.55%). Lower error does not imply lower
electricity use. The learned adaptive model has lower on-policy error, while
the physical adaptive model has lower common-probe error. Neither is uniformly
better. Their actions differ on 326 of 5,184 decisions across the full suite,
despite identical average energy. Fixed learned and fixed physics decisions
match on every step.

Recovery has two separately reported definitions:

- **Safety recovery:** first start of 12 consecutive in-band observations after
  the change. Every degraded run scores zero minutes because no controller
  leaves the safety band. This is not evidence of a recovery advantage.
- **Model recovery:** first start of 12 consecutive common-probe MAEs ≤0.02°C
  per step after the change. Adaptive learned averages 238.9 minutes (range
  230–240). Adaptive physics averages 212.8 minutes (range 175–240). Both recover
  in all nine cases. Neither fixed model recovers within the observation period.
  Missing CSV values mean censored/no recovery, not zero. The threshold is an
  explicit diagnostic choice, not a claimed industrial tolerance.

Without degradation, both adaptive models use 136.056 kWh/day on average,
versus 135.833 for fixed models. Target RMSE is 0.075450°C for either adaptive
method versus 0.118563°C fixed. All remain safe. Post-hour-10 common-probe errors
for both adaptive methods are below 4e−8°C/step. The nominal unchanged case is
included to expose the cost of adapting when nothing changes.

## Reproducibility and limits

`summary.csv` contains every case/controller result. `paired.csv` contains
case-matched differences from fixed learned MPC. `adaptive_learned_minus_physics.csv`
contains the direct adaptive comparison. Full `trajectories.csv` is generated
by the CLI and included in CI artifacts rather than committed. Its SHA-256 is
recorded in metadata. Metrics are deterministic in the recorded numerical
environment, with no wall-clock performance claims.

The simulator remains linear, noiseless, and deliberately well matched to both
model classes. Ordinary online physical identification already explains most of
the gain from updating a stale model. This does not establish cross-system
representation learning, nonlinear generalization, robustness to faulty sensors,
safe online learning on real equipment, or customer energy savings. No
statistical superiority claim is justified by three synthetic configurations.
The window, regularization, and recovery threshold are fixed experiment choices,
not a tuned best result. Future work should vary these, add sensor noise and
nonlinear drift, and validate on external datasets or real equipment.

Investor-safe description: **“Fovra now demonstrates causal online model updates
on unseen simulated thermal systems. Adaptation improves predictions and target
tracking, while a conventional adaptive physical model remains competitive.
Energy savings and an ML-specific generalization advantage remain unproven.”**


## Interactive dashboard

Run `python -m streamlit run app.py` and select **Adaptation experiment** in
**Dashboard view**. This mode reads the committed 72-record `summary.csv` only.
Equipment, change condition, seeds, and controllers filter matched cases.
Tables and the metric chart show equal-weight per-controller means, with raw
selected records and a CSV download available below. Hours 10–24 prediction
metrics are distinct from full-day tracking, electricity, and violations.
The same time window is used for unchanged cases.

The **Original simulation** mode retains its fixed-model controls and cached
on-demand simulations. Adaptation browsing does not execute simulations.
Generate trajectories offline with the benchmark CLI or retrieve CI artifacts.
No trajectory simulation is launched from the dashboard.
