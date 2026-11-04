# Cooling exploration

This Fovra v0 experiment compares cooling electricity and water use for a simulated data center. Cooling remains an exploratory application with illustrative equipment and weather assumptions.

## Run it

```bash
python -m streamlit run app.py
```

The dashboard opens directly to cooling exploration. Select climate, IT load, cooler size, and evaporative-assist trigger. Results update automatically. Download the comparison or full trajectories as CSVs. **Run AI comparison** tests learned screening against random search.

```bash
python benchmark_cooling.py --output results/cooling
python -m pytest -q
```

The benchmark uses three synthetic climates, with and without a midday surge, at an 80 kW base load. Each search observes 12 simulations per case and seed. Seeds are 11, 22, and 33. The makeup-water budget is 4,000 L/day. Metadata records inputs, package versions, and source hashes.

## Two cooling options

Both options receive the same 24-hour IT load and weather. Both start at 32°C. Neither reduces the workload.

- **Dry cooler:** Rejects heat to outdoor dry-bulb temperature. No onsite cooling water is used in this model.
- **Evaporative assist:** Uses dry cooling while it can reach the target below the chosen fan trigger. Otherwise, it uses wet-bulb temperature plus an approach allowance, if that sink is cooler. Wet operation adds a spray pump and water use.

There is no backup chiller. A hot day can make either option infeasible. Simulations continue with the full workload so overheating stays visible.

## Physics and accounting

This is one bulk coolant temperature, not a chip, air-distribution, cold-plate, or separate supply/return model. Inputs are constant within each five-minute interval.

| Parameter | Illustrative assumption |
| --- | --- |
| Target / maximum bulk coolant temperature | 32°C / 35°C |
| Effective thermal capacity | 5 kWh/°C |
| Full-speed heat-exchanger conductance | 12 × cooler size kW/°C |
| Full-speed fan electricity | 4 × cooler size kW |
| Circulation pump electricity | 1.5 kW |
| Extra wet-mode pump electricity | 0.4 kW |
| Wet effective sink | Wet bulb + 3°C |
| Evaporation heat | 0.68 kWh/L |
| Cycles of concentration | 4 |

These values are not manufacturer data or ASHRAE limits. Coolant temperature is not server inlet-air or chip temperature.

For fan fraction `u` between zero and one:

```text
UA = 12 × size × u                         [kW/°C]
fan electricity = 4 × size × u³            [kW]
C × dT/dt = IT heat + pump heat − rejected heat
rejected heat = UA × max(T − sink, 0)       [thermal kW]
```

A bypass prevents reverse heat transfer. The equation is integrated analytically. Below the sink temperature, the loop first warms without rejection. Above the sink, the exponential solution applies. This avoids explicit-Euler overshoot.

A physics rule chooses the lowest fan fraction that reaches 32°C at interval end. If that is impossible, it uses full fan power. It assumes perfect measurements and immediate fan response. The cooling comparison does not use a learned controller.

All modeled pump electricity becomes loop heat. Fan heat goes outside the loop. Cooling electricity is pump plus fan power, not thermal heat removed. IT electricity is reported separately and assumed to become loop heat.

```text
evaporation = wet-mode rejected energy / 0.68     [L]
blowdown = evaporation / (4 − 1)                 [L]
makeup withdrawal = evaporation + blowdown      [L]
```

The wet model assigns all rejected heat to evaporation. It omits the sensible/latent split and detailed psychrometrics, so evaporation may be overstated. Drift, leaks, basin inventory, and treatment are excluded. Blowdown is withdrawal, not evaporative consumption. Recirculating coolant is not counted as consumed.

Cooling emissions equal cooling electricity times the grid factor. Utility cost includes cooling electricity and makeup water. Neither includes IT electricity, upstream water, embodied carbon, capital cost, or maintenance. Default prices and emissions are placeholders. These results are not full lifecycle totals, PUE, or facility WUE.

## Weather and workload

| Synthetic climate | Mean dry bulb | Mean wet bulb |
| --- | ---: | ---: |
| Cool | 15°C | 10°C |
| Hot and dry | 34°C | 19°C |
| Hot and humid | 32°C | 27°C |

Dry bulb varies by ±4°C and wet bulb by ±2°C. Wet bulb stays below dry bulb. These are prescribed profiles, not weather records or a humidity calculation.

IT load varies by ±10% around the base. A surge adds 35% from hours 10–14, increasing the daily average. All compared designs see identical profiles.

## Thermal checks

A candidate passes only if no interval endpoint exceeds 35°C and no more than 0.5 kWh of extra heat remains at day end. The latter equals 0.1°C above the initial temperature and prevents credit for leaving heat in storage.

Within each interval, temperature is monotone under the fixed inputs. Endpoint checks therefore bound the whole interval. Minutes over the limit count whole intervals conservatively. Peak temperature and stored heat remain visible even for failed designs.

The electricity/water frontier excludes thermally invalid points. It covers only tested candidates. It does not combine the environmental metrics into a single score.

## AI screening

There are 35 candidates: seven sizes (0.6, 0.8, 1.0, 1.2, 1.5, 1.8, 2.0), each with one dry setting and four wet triggers (0.35, 0.55, 0.75, 1.0).

Both methods start with the same six randomly chosen candidates. Random search continues without replacement. AI screening fits a 64-tree random forest to completed simulations. Features are type, size, and trigger. Predictions are electricity, makeup water, peak temperature, and final temperature.

The model prefers predicted feasible settings, then lower electricity. If none is predicted feasible, it sorts peak-temperature, final-temperature, and water violations in that order. It requests one simulator result, adds that observation, and refits. Final reported performance always comes from the simulator.

The best tested setting must pass the actual thermal checks and water budget. If none qualifies, the app says so. Each climate/workload case fits its own model. This does not demonstrate transfer, new hardware discovery, or an AI advantage.

The offline benchmark evaluates all 35 settings as a grid reference. It replays only requested candidate results to each search. Unqueried outcomes are hidden from the model. Grid evaluations are outside the search budgets and reported separately. This simulator is cheap, so no speedup is claimed.

In the committed run, both methods found feasible settings in 9 of 18 case/seed pairs. The other nine pairs had no feasible candidate even in the full grid. Across the nine feasible pairs, AI matched random search seven times, improved once, and was worse once. This is too small and simple to establish a learning advantage.

Larger coolers often use less operating electricity here. Their capital cost, footprint, and embodied impact are omitted. These results must not be treated as equipment-sizing recommendations.

## Outputs and next steps

- `cooling.py`: physics, accounting, and thermal checks.
- `cooling_search.py`: random and learned screening.
- `cooling_view.py`: dashboard and downloads.
- `benchmark_cooling.py`: repeatable comparison.
- `results/cooling/grid.csv`: full candidate grid for each case.
- `results/cooling/search_trials.csv`: observations available to each method.
- `results/cooling/search_summary.csv`: best verified results and gaps to the grid.
- `results/cooling/metadata.json`: inputs, package versions, and source hashes.

Next, replace assumed cooler curves with measured data and validate against a detailed simulator. Then test noise, delays, failures, degradation, and unseen conditions. A learned surrogate could eventually reduce calls to a more expensive model.

Domain references and future validation tools, not validation of the chosen parameters:

- [DOE cooling-water guidance](https://www.energy.gov/cmei/femp/cooling-water-efficiency-opportunities-federal-data-centers): water and facility accounting.
- [EnergyPlus engineering reference](https://bigladdersoftware.com/epx/docs/24-2/engineering-reference/cooling-towers-and-evaporative-fluid-coolers.html): detailed tower and fluid-cooler models.
- [LBNL modeling tools](https://datacenters.lbl.gov/facility-performance-modeling-simulation): Modelica and MOSTCOOL.
