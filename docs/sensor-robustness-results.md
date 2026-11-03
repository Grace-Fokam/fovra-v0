# Sensor-noise robustness benchmark

**Adaptive physics is substantially more robust than the current adaptive learned
regression under random temperature noise in these simulations. Neither adaptive
method reliably recovers the latent dynamics model under random sensor noise.
Constant bias remains an unresolved measurement problem for both.**

This is a separate experiment based on repository commit
`2c8b2d4c9ad1455cfc801cb9ba21f2680ae6811e`. It imports the existing equipment,
physical update, controllers, optimizer and training routine without modifying
them. The original adaptation benchmark, dashboard data and recorded metrics
remain unchanged.

## Reproduce

```bash
python -m pip install -r requirements-benchmark.txt
python -m pytest -q
python benchmark_sensor_robustness.py --output results/sensor_robustness
```

The numerical packages match the existing benchmark pins. Actual Python and
numerical-package versions, source SHA-256 hashes, seeds, protocol and output
hashes are in `results/sensor_robustness/metadata.json`. Tests were run using
Python 3.12 with pytest 9.2.0 and Streamlit 1.66.1. These two patch versions differ
from the old benchmark pins and do not participate in the standalone numerical
experiment. CI runs the tests and full sensor suite on Python 3.10 and 3.12 and
uploads complete results. CI results must be checked separately from local tests.

A quick CLI check, with intentionally too little follow-up to assess recovery:

```bash
python benchmark_sensor_robustness.py --output /tmp/sensor-smoke \
  --seeds 11 --sensors clean noise_0p5 --steps 24 --change-step 12
```

`--sensors` must include `clean`. Seeds must be distinct and nonnegative. The CLI
rejects output locations inside the two original result directories. Use a new
output directory to retain an existing sensor-benchmark run.

## Matched experimental design

There are 144 matched cases and 576 controller runs:
three equipment configurations × healthy/degraded × three seeds × eight sensor
conditions. Each run is one day with 288 five-minute steps. All conditions use
seeds 11, 22 and 33, the original ambient/demand trajectories and initial true
temperature of 60°C. The original positive capacity-margin check remains active.
In degraded runs, efficiency drops to 75% of its initial value at hour 10.
Controllers are not given the equipment parameters, degradation schedule,
sensor bias, noise realization or noise magnitude.

| Condition | Gaussian standard deviation (°C) | Constant bias (°C) |
|---|---:|---:|
| `clean` | 0 | 0 |
| `noise_0p1` | 0.1 | 0 |
| `noise_0p5` | 0.5 | 0 |
| `noise_1p0` | 1.0 | 0 |
| `bias_plus_1` | 0 | +1 |
| `bias_minus_1` | 0 | −1 |
| `noise_0p5_bias_plus_1` | 0.5 | +1 |
| `noise_0p5_bias_minus_1` | 0.5 | −1 |

These are illustrative stress levels, not manufacturer accuracy specifications.
Bias is present from the initial reading through the entire run, not switched on
at degradation. Gaussian noise is independent across timestamps and unbounded.
This does not test sensor drift, dropouts, quantization or temporally correlated
sensor noise.

The observation is `y[t] = x[t] + bias + sigma*z[t]`. The plant always evolves
from its true state `x[t]` using the unchanged `Equipment.delta()` equation.
Sensor corruption can change actions and thereby affect physical trajectories,
but it never enters the physical update directly. A separate PCG64 stream,
seeded with `SeedSequence([seed, 0x53454E53])`, produces `steps + 1` standard-normal
draws. These draws are independent of demand and training draws. The same error
sequence is reused across controllers, equipment and degradation conditions,
and scaled across noise levels. Controller order cannot consume or change it.

Each timestamp has exactly one sensor reading. The reading ending one transition
is reused at the start of the next. Thus both the regression input and its
temperature-change target are corrupted. Resampling either endpoint for every
training pair would create a different, unrealistic observation protocol.
The noise in a temperature-change target is `sigma*(z[t+1] - z[t])`, with variance
`2*sigma^2` and negative lag-one correlation. It is also correlated with the
noisy temperature regressor. Ordinary least squares is not corrected for this
errors-in-variables problem here.

The four controllers are the original fixed learned MPC, fixed physics MPC,
adaptive learned MPC, and adaptive physics MPC. They use the same 625 candidate
plans, 20-minute horizon, 0/3/6/9/12 kW actions, persistence forecasts, cost and
soft temperature penalties. Ambient, process demand and applied power remain
exactly observed. Each controller sees its own temperature trajectory, with the
same sensor protocol. Matched errors do not imply identical temperature values
once actions diverge.

All start from clean nominal commissioning information. This isolates corruption
during deployment and online identification, not corrupted initial training.
The fixed learned fit is equivalent to the nominal physics equation up to
floating-point error. Both adaptive methods start from nominal coefficients,
fit the latest 48 completed transitions, start fitting after six transitions,
and retain the existing ridge prior of 1e−6. The learned fit is unconstrained
affine regression. The physics fit uses nonnegative energy-balance coefficient
combinations. Feature coordinates, parameter counts and bounds differ, so equal
ridge values are not equal effective regularization. Neither method is retuned,
filtered or given a bias correction for this experiment.

At step `t`, the harness chooses an action and records forecasts and diagnostic
probe error with the current model. It then advances the true plant, obtains
`y[t+1]`, scores the forecast, and calls `observe(y[t], ..., y[t+1])`. No current
transition is fitted before its prediction is scored. Probe targets and latent
states never enter fitting or action selection.

## Metrics and output files

- **Tracking:** per-run RMSE of post-action true temperatures against 60°C.
- **Prediction:** one-step next-temperature RMSE against true `x[t+1]`, and a
  separate RMSE against the next sensor reading `y[t+1]`. Both forecasts start
  from `y[t]`. A small error against a biased sensor does not imply accurate
  absolute temperature prediction.
- **Electricity:** applied electrical power times five minutes. Degraded
  efficiency changes delivered heat, not electricity accounting.
- **Band violations:** true post-action temperatures outside inclusive 58–62°C,
  reported as five-minute sampled duration, degree-minutes and maximum excursion
  beyond the nearest limit. No noisy-state or continuous-time safety claim is made.
- **Model recovery:** pre-update MAE on a common clean 15-point probe grid,
  temperatures 58/60/62°C and powers 0/3/6/9/12 kW, always at ambient 20°C and
  demand 2 kW. Only the evaluator knows the plant for these probes. Recovery is
  the first start after degradation of 12 consecutive scores ≤0.02°C per step.
  The reported start is retrospectively confirmed one hour later. Blank times
  with `censored` status mean no qualifying full hour was observed during the
  14-hour follow-up. Healthy runs are `not_applicable`. Recovery times are not
  subtracted or averaged as if censored observations were zero.

The fixed probe ambient/demand differ from the original adaptation benchmark's
time-varying probe conditions. Clean-run physical trajectories and controls
match the original benchmark, but probe scores and recovery times need not.
The probe tests the fitted model as a latent physical model on clean inputs.
A model that has absorbed a sensor bias may predict in sensor coordinates
without recovering the true physical parameters. The recovery threshold is
an illustrative diagnostic tolerance, not a validated industrial requirement.
Post-change and final-hour probe errors are retained even when recovery is censored.

`summary.csv` holds each controller run. `paired.csv` has four within-case
contrasts: adaptive learned minus adaptive physics, each adaptive controller
minus its own fixed counterpart, and fixed learned minus fixed physics.
Differences are left minus right, so negative is better for the error,
energy and violation metrics. `noise_effects.csv` compares each controller
with its own matched clean-sensor run. `trajectories.csv.gz` contains both true
and observed states, sensor errors, applied powers, pre-update forecasts and
probe errors. It is generated deterministically and uploaded by CI rather than
committed. Its hash is recorded with the committed summary artifacts.

## Results

Values below are equal-weight means of per-run metrics over all 18 cases for
each sensor condition, including healthy and degraded equipment. They are not
pooled RMSEs. Fixed learned and fixed physics produced identical actions and
physical metrics, so their shared values occupy one row per condition.

| Sensor condition | Controller | Tracking RMSE (°C) | Electricity (kWh/day) | Violations (min/day) |
|---|---|---:|---:|---:|
| Clean | Fixed, either model | 0.170 | 148.722 | 0 |
| Clean | Adaptive learned | 0.072 | 149.278 | 0 |
| Clean | Adaptive physics | 0.074 | 149.278 | 0 |
| Noise σ=0.1°C | Fixed, either model | 0.180 | 148.792 | 0 |
| Noise σ=0.1°C | Adaptive learned | 0.132 | 149.250 | 0 |
| Noise σ=0.1°C | Adaptive physics | 0.108 | 149.278 | 0 |
| Noise σ=0.5°C | Fixed, either model | 0.377 | 148.819 | 0 |
| Noise σ=0.5°C | Adaptive learned | 0.423 | 149.569 | 0.556 |
| Noise σ=0.5°C | Adaptive physics | 0.238 | 149.375 | 0 |
| Noise σ=1.0°C | Fixed, either model | 0.573 | 148.792 | 6.111 |
| Noise σ=1.0°C | Adaptive learned | 1.743 | 149.250 | 148.889 |
| Noise σ=1.0°C | Adaptive physics | 0.378 | 149.458 | 0 |
| Bias +1°C | Fixed, either model | 1.106 | 145.292 | 0 |
| Bias +1°C | Adaptive learned | 0.999 | 145.792 | 0 |
| Bias +1°C | Adaptive physics | 1.003 | 145.778 | 0 |
| Bias −1°C | Fixed, either model | 0.882 | 152.153 | 0 |
| Bias −1°C | Adaptive learned | 1.001 | 152.708 | 0 |
| Bias −1°C | Adaptive physics | 0.996 | 152.722 | 0 |
| Noise σ=0.5°C, bias +1°C | Fixed, either model | 1.158 | 145.375 | 26.667 |
| Noise σ=0.5°C, bias +1°C | Adaptive learned | 1.347 | 145.806 | 56.389 |
| Noise σ=0.5°C, bias +1°C | Adaptive physics | 1.066 | 145.875 | 0 |
| Noise σ=0.5°C, bias −1°C | Fixed, either model | 0.921 | 152.250 | 0.556 |
| Noise σ=0.5°C, bias −1°C | Adaptive learned | 2.702 | 151.958 | 169.444 |
| Noise σ=0.5°C, bias −1°C | Adaptive physics | 1.015 | 152.903 | 0 |

Physics has lower tracking RMSE than adaptive learned MPC in all 18 matched
cases at each of the three unbiased noise levels. At σ=0.5°C its mean tracking
error is about 44% lower. The per-case learned-minus-physics difference ranges
from 0.101 to 0.335°C. At σ=1°C the difference ranges from 0.315 to 4.143°C,
and the learned controller violates the band in all 18 cases. Physics has no
sampled violations in any of the 144 cases. Adaptive learned has violations in
48 cases, including severe failures hidden by aggregate means: the worst run
has tracking RMSE 9.506°C, 405 violation minutes and a maximum excursion of
26.842°C outside the band. No failed runs were dropped or clipped.

The physics advantage is not universal across metrics or conditions. For
negative bias alone, both fixed controllers track better on average than either
adaptive controller. Bias can partially offset an existing control offset.
For combined negative bias and noise, fixed tracking remains better on average
than adaptive physics, but fixed controllers have violations in 2/18 cases.
Energy differences must be read alongside temperature and violations. Cooler
operation caused by positive sensor bias is not an efficiency improvement.

For the nine degraded cases at selected noise levels:

| Noise | Controller | Forecast RMSE vs true (°C) | Forecast RMSE vs sensor (°C) | Post-change clean-probe MAE (°C/step) | Recovered runs |
|---|---|---:|---:|---:|---:|
| Clean | Fixed, either model | 0.163 | 0.163 | 0.230 | 0/9 |
| Clean | Adaptive learned | 0.023 | 0.023 | 0.051 | 9/9 |
| Clean | Adaptive physics | 0.031 | 0.031 | 0.024 | 9/9 |
| σ=0.1°C | Fixed, either model | 0.185 | 0.215 | 0.230 | 0/9 |
| σ=0.1°C | Adaptive learned | 0.108 | 0.147 | 0.490 | 0/9 |
| σ=0.1°C | Adaptive physics | 0.098 | 0.139 | 0.188 | 0/9 |
| σ=0.5°C | Fixed, either model | 0.473 | 0.703 | 0.230 | 0/9 |
| σ=0.5°C | Adaptive learned | 0.461 | 0.666 | 0.995 | 0/9 |
| σ=0.5°C | Adaptive physics | 0.316 | 0.586 | 0.813 | 0/9 |
| σ=1.0°C | Fixed, either model | 0.936 | 1.392 | 0.230 | 0/9 |
| σ=1.0°C | Adaptive learned | 0.951 | 1.355 | 2.148 | 0/9 |
| σ=1.0°C | Adaptive physics | 0.542 | 1.134 | 1.456 | 0/9 |

With clean sensors, adaptive learned recovers in a mean 238.3 minutes and
adaptive physics in 211.7 minutes. With either constant bias alone, both meet
the chosen probe tolerance in all nine degraded cases, while true tracking
error remains about 1°C. Under any nonzero random-noise condition, including
the combined conditions, neither adaptive method meets the model-recovery
criterion in any degraded case. At larger noise levels, clean-probe errors can
be worse than the fixed nominal model even while closed-loop tracking improves.
Local feedback performance and physical model identification are distinct.

## Interpretation and limits

This establishes a reproducible failure mode of the current online regression
under imperfect observations, and a meaningful **within-suite control robustness
advantage** for its constrained physics counterpart. It does not establish
robust physical identification for either model, a machine-learning advantage,
generalization to nonlinear equipment, industrial safety, or customer energy
savings. Three seeds repeated across three related plants are not independent
field installations. Matched per-case differences and failure counts are
reported without population-level statistical significance claims.

The observation model explains why differencing noisy temperatures is a hard
identification problem, but this benchmark does not isolate the contribution
of bounds, feature count, conditioning and priors. The learned model has more
degrees of freedom and the closed-loop trajectory provides limited excitation.
A controlled estimator ablation would be needed to assign the advantage to one
mechanism. There is no filtering, state estimation, robust regression or tuned
regularization baseline here. The next useful work is to compare causal state
estimators and noise-aware identification under the same observation budget,
vary window/regularization on separate tuning seeds, test bias calibration and
drift, and validate on external systems before a live pilot.

## Validation

The complete local test suite passed: **76 tests**, including **22 new sensor
benchmark tests**. These cover seeded and prefix-stable noise, independence from
process randomness, shared sensor errors and transition endpoints, unchanged
physical dynamics under fixed actions, clean-control equivalence with the
original experiment, noisy inputs and targets reaching both estimators,
pre-update scoring, fixed-model immutability, future-observation causality,
true-state metrics, recovery censoring, exact case pairing, deterministic
compressed artifacts and protection of the original result directories.

Two complete 576-run executions produced byte-identical summaries, paired
contrasts, clean-control differences, metadata and compressed trajectories.
All recorded source hashes were verified. A repository diff also confirmed that
the original experiment code and both original result directories were untouched.
