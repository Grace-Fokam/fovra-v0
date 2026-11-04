# Cooling exploration

This experiment compares cooling electricity and water use for a simulated data center. It's exploratory, and the equipment and weather are illustrative.

## Run it

```bash
python -m streamlit run app.py
```

Pick a climate, IT load, cooler size, and evaporative-assist trigger, and the results update automatically. You can download the comparison or the full time series as CSVs. **Run AI comparison** tests learned screening against random search.

```bash
validation_dir="$(mktemp -d)"
python benchmark_cooling.py --output "$validation_dir/cooling"
python -m pytest -q
```

The benchmark writes to a fresh temporary directory so the committed results stay unchanged.

The benchmark uses three synthetic climates, each with and without a midday surge, at an 80 kW base load. Each search gets 12 simulations per case and seed, with seeds 11, 22, and 33 and a makeup-water budget of 4,000 L/day. Metadata records inputs, package versions, and source hashes.

## The two cooling options

Both options get the same 24-hour IT load and weather, start at 32°C, and never reduce the workload.

- **Dry cooler:** Rejects heat to the outdoor dry-bulb temperature. No onsite water in this model.
- **Evaporative assist:** Uses dry cooling when it can hit the target below the chosen fan trigger. Otherwise it switches to wet-bulb temperature plus an approach margin, if that's cooler, which adds a spray pump and water use.

There's no backup chiller, so a hot day can make either option fail. The simulation keeps running at full load so overheating stays visible.

## Physics and accounting

The model tracks one bulk coolant temperature. It has no chip, airflow, cold-plate, or separate supply/return model. Inputs are held constant within each five-minute step.

| Parameter | Illustrative value |
| --- | --- |
| Target / maximum bulk coolant temperature | 32°C / 35°C |
| Effective thermal capacity | 5 kWh/°C |
| Full-speed heat-exchanger conductance | 12 × cooler size kW/°C |
| Full-speed fan electricity | 4 × cooler size kW |
| Circulation pump electricity | 1.5 kW |
| Extra wet-mode pump electricity | 0.4 kW |
| Wet heat sink | Wet bulb + 3°C |
| Evaporation heat | 0.68 kWh/L |
| Cycles of concentration | 4 |

These aren't manufacturer data or ASHRAE limits, and coolant temperature isn't server inlet-air or chip temperature.

For fan fraction `u` between 0 and 1:

```text
UA = 12 × size × u                         [kW/°C]
fan electricity = 4 × size × u³            [kW]
C × dT/dt = IT heat + pump heat − rejected heat
rejected heat = UA × max(T − sink, 0)       [thermal kW]
```

A bypass prevents heat from flowing backward. The equation is solved exactly: below the sink temperature the loop just warms up, and above it the exponential solution applies. This avoids the overshoot a simple time-stepping method would cause.

Each step, a physics rule picks the lowest fan speed that reaches 32°C by the end of the step, or full speed if that's not possible. It assumes perfect sensing and instant fan response. The cooling comparison doesn't use a learned controller.

All pump electricity becomes heat in the loop, while fan heat goes outside. Cooling electricity is pump plus fan power, not heat removed. IT electricity is reported separately and assumed to become loop heat.

```text
evaporation = wet-mode rejected energy / 0.68     [L]
blowdown = evaporation / (4 − 1)                 [L]
makeup withdrawal = evaporation + blowdown      [L]
```

The wet model treats all rejected heat as evaporation, skipping the sensible/latent split and detailed psychrometrics, so it may overstate water use. Drift, leaks, basin volume, and water treatment are left out. Blowdown counts as withdrawal, not consumption, and recirculating coolant isn't counted as used.

Cooling emissions are cooling electricity times the grid factor. Utility cost covers cooling electricity and makeup water. Neither includes IT electricity, upstream water, embodied carbon, capital cost, or maintenance, and the default prices and emissions are placeholders. These aren't full lifecycle totals, PUE, or facility WUE.

## Weather and workload

| Synthetic climate | Mean dry bulb | Mean wet bulb |
| --- | ---: | ---: |
| Cool | 15°C | 10°C |
| Hot and dry | 34°C | 19°C |
| Hot and humid | 32°C | 27°C |

Dry bulb swings ±4°C and wet bulb ±2°C over the day, with wet bulb always below dry bulb. These are made-up profiles, not weather records.

IT load varies ±10% around the base. The surge adds 35% from hours 10 to 14, which raises the daily average. Every design sees the same profiles.

## Thermal checks

A design passes only if no step ends above 35°C and no more than 0.5 kWh of extra heat is left at the end of the day. That's 0.1°C above the starting temperature, and it keeps a design from getting credit for storing heat instead of rejecting it.

Within a step, temperature moves in one direction, so checking step endpoints covers the whole step. Time over the limit is counted in whole steps, conservatively. Peak temperature and leftover heat are still shown for failed designs.

The electricity/water frontier leaves out thermally invalid designs, covers only tested designs, and doesn't merge the metrics into one score.

## AI screening

There are 35 candidates: seven sizes (0.6, 0.8, 1.0, 1.2, 1.5, 1.8, 2.0), each with one dry setting and four wet triggers (0.35, 0.55, 0.75, 1.0).

Both methods start with the same six random candidates. Random search continues without replacement. AI screening fits a 64-tree random forest to its completed simulations, using type, size, and trigger to predict electricity, makeup water, peak temperature, and final temperature.

The model prefers settings predicted to be feasible, then lower electricity. If none look feasible, it ranks by peak-temperature, final-temperature, and water violations, in that order. It runs one simulation, adds the result, and refits. Reported results always come from the simulator.

The best tested setting has to pass the real thermal checks and water budget, and the app says so if none does. Each climate/workload case gets its own model. This doesn't show transfer, new hardware, or an AI advantage.

The offline benchmark evaluates all 35 settings as a reference grid but only gives each search the results it asks for, so unqueried results stay hidden. Grid evaluations don't count toward search budgets. The simulator is cheap, so no speedup is claimed.

In the committed run, both methods found feasible settings in 9 of 18 case/seed pairs; the other nine had no feasible setting even in the full grid. In the nine feasible pairs, AI matched random search seven times, did better once, and did worse once. That's too small and too simple to show a learning advantage.

Larger coolers often use less electricity here, but their capital cost, footprint, and embodied impact aren't modeled, so these results aren't equipment-sizing recommendations.

## Files and next steps

- `cooling.py`: physics, accounting, and thermal checks
- `cooling_search.py`: random and learned screening
- `cooling_view.py`: dashboard and downloads
- `benchmark_cooling.py`: repeatable comparison
- `results/cooling/grid.csv`: full candidate grid for each case
- `results/cooling/search_trials.csv`: what each method saw
- `results/cooling/search_summary.csv`: best verified results and gaps to the grid
- `results/cooling/metadata.json`: inputs, package versions, and source hashes

Next, replace the assumed cooler curves with measured data and validate against a detailed simulator. Then test noise, delays, failures, degradation, and unseen conditions. Eventually, a learned surrogate could cut down calls to a more expensive model.

Useful references and future validation tools (these don't validate the chosen parameters):

- [DOE cooling-water guidance](https://www.energy.gov/cmei/femp/cooling-water-efficiency-opportunities-federal-data-centers): water and facility accounting
- [EnergyPlus engineering reference](https://bigladdersoftware.com/epx/docs/24-2/engineering-reference/cooling-towers-and-evaporative-fluid-coolers.html): detailed cooling tower and fluid cooler models
- [LBNL modeling tools](https://datacenters.lbl.gov/facility-performance-modeling-simulation): Modelica and MOSTCOOL
