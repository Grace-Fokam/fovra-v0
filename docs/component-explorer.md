# Component design explorer

Run `python -m streamlit run app.py` after installing `requirements.txt`. The app opens **Component design**. The sidebar also provides the existing **Data-center cooling** dashboard.

## A short walkthrough

1. Start with the **Nominal** operating case in **Design studio**. The initial grid-selected design has 48 channels and evaluates to a 41.386°C base-temperature proxy, 56.471 Pa pressure drop and 0.235 mW plate-only pump electricity.
2. **Pin current design**, then raise total water flow from 0.1 to 0.2 L/min. Inspect the change in outlet/base temperature and pressure. The drawing shows exact channel count, dimensions and side margins. Its colors identify solid and water, not temperature.
3. Select **Reference** to load the arbitrary research baseline. Compare it with the grid winner. Neither is a commercial product. Grid best optimizes feasible pump electricity, not minimum temperature.
4. Change the operating case. Every compared design is evaluated again at that case. The **fixed-flow** case locks flow to 0.2 L/min for the current design, reference, winner and pins.
5. Open **Recorded search**, choose a seed and move the replay budget. The first eight simulator queries are identical between methods. The slider displays a prefix of a saved 32-query run, not a new optimization. It counts failed and initial evaluations. The geometry sliders do not alter this historical experiment.
6. Inspect all six seeds, including losses and ties, then read the timing comparison. It compares complete recorded runs across all cases. The exhaustive grid was faster than learned search on this cheap model.
7. Open **Model & evidence** for assumptions and provenance. Export current-design JSON or comparison CSV from the studio, or the displayed search-trial prefix from the experiment view.

Pins last only for the current session, with up to three distinct definitions. Their results always reflect the currently selected operating case. The comparison CSV includes case parameters, geometry, full diagnostics and raw feasibility flags. The JSON contains the current case, design and simulator result, with the unvalidated status stated explicitly.

## Scientific boundaries

All live calculations call `cold_plate.evaluate_design`. The UI does not add physics, retrain a model or modify any recorded files. The 100/150 W uniformly heated coupon is illustrative and does not represent a high-power GPU or its hotspots. The reported temperature is a base proxy, not a chip junction temperature. Pump electricity includes only modeled plate losses and the assumed pump efficiency.

Invalid geometry gets no physical outputs or valid-geometry drawing. A valid geometry outside the correlation envelope retains diagnostic numbers with an explicit warning. Feasibility requires geometry, domain and operating checks, not just falling below the temperature and pressure lines on the chart. The recorded CSV's Pareto flag is for temperature/pump power and is deliberately not presented as a temperature/pressure frontier.

No CFD or experimental hardware validation is shown. Manufacturing, material cost and structural penalties are absent. Higher-load and warm-inlet results are nearly redundant, and six seeds do not establish a held-out statistical advantage.

## Review checks

- Default design matches the nominal recorded grid winner.
- Changing width, depth, web, base, conductivity or flow updates the simulator outputs and geometry.
- Width 0.2 mm with depth 1.8 mm fails the aspect-ratio rule and shows unavailable outputs.
- The nominal grid geometry at 0.8 L/min displays correlation-domain warnings.
- Pins retain their design definitions and recalculate when the case changes. Fixed-flow comparisons all use 0.2 L/min.
- Recorded case, seed and budget changes update the trace, comparison table and tradeoff markers. At eight calls both methods tie for every recorded case/seed.
- CSV/JSON downloads contain the displayed selection and units, and the original cooling dashboard still runs.

Run `python -m pytest -q` for the UI and model tests. Follow [the pinned replay instructions](cold-plate-reproducibility.md) for exact scientific reproducibility. The simulator, search algorithm, benchmark, original scientific outputs and replay workflow are unchanged by the explorer.
