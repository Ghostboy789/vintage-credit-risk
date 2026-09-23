# Vintage · Power BI risk pack

A six-page Power BI report over the portfolio, scorecard, loss and ECL results, built as PBIP
(TMDL model + PBIR report) so every table, measure and visual is a readable text file that diffs
in git. **Built and validated on the project's synthetic fixtures** (see "Synthetic data" below);
It is pointed at the real Freddie Mac marts once the scorecard, loss/ECL and portfolio results exist.

## Open it

1. Install [Power BI Desktop](https://www.microsoft.com/power-bi/desktop) (Windows, free).
2. Clone the repository and open **`powerbi/Vintage.pbip`**.
3. Click **Refresh**. The data loads from this repository's `powerbi/data` folder on GitHub. The
   first time, Power BI asks how to connect to the web source: choose **Anonymous**, then
   **Connect**.

To work offline, set the `DataFolder` parameter (Transform data -> Edit parameters) to your local
`powerbi\data\` path.

**Dark mode:** View -> Themes -> Browse for themes -> `powerbi/themes/Vintage-Dark.json`. All
report colours come from the theme.

## Pages

| Page | Question it answers |
|---|---|
| **Portfolio Overview** | Active balance, delinquency and default/loss rate over time |
| **Vintages** | Cumulative default and loss curves by months on book, per origination quarter |
| **Roll Rates** | Month-to-month transitions between DPD buckets, cure rates, SMA balance mix |
| **Scorecard and Monitoring** | Points table, grades, Gini/KS out-of-time, score PSI |
| **IFRS 9 ECL** | ECL by reporting date and stage, coverage ratio, the backtest by grade |
| **Capital** *(stretch)* | Basel IRB capital and RWA by grade, illustrative only |

Slicers for vintage year and grade sit on the pages where the underlying tables carry that
column; see "Known simplifications" for why they are not global.

## Model

The report reads only already-aggregated tables: the dbt marts `dim_date` and `metrics_monthly`,
and every list field of the six published artefacts (`portfolio.json`, `pd_models.json`,
`monitoring.json`, `lgd_ead.json`, `ecl.json`, `capital.json`), flattened one metric object
(`value`/`ci_low`/`ci_high`/`n`/`ci_method`) into five columns each. `scripts/export_powerbi.py`
builds `powerbi/data/*.csv` from them; nothing in the model re-derives a number.

- **`Key Measures`**: DAX measures in display folders, one per page.
- **`Dim Vintage Year`, `Dim Grade`**: small calculated dimensions the fact tables relate to.
- **No loan-level table.** `fct_loan_month`, `fct_scorecard_base` and `fct_stage_inputs` are
  loan-level and never leave the warehouse (CONTRACTS.md publication rule); this report is
  aggregates only, same as every other published artefact.

## Synthetic data

Every row in `powerbi/data/` right now comes from `tests/fixtures/`, which
`scripts/make_fixtures.py` invents with a fixed seed — none of it is a real Freddie Mac loan.
Every table carries a `Synthetic` column, and the `Key Measures[Synthetic Data Warning]` measure
shows a banner on every page while it is `true`. `scripts/export_powerbi.py --source real` reads
the real marts and artefacts instead, once the scorecard, LGD/ECL/capital and portfolio analytics
results exist; the real export is then re-run, every KPI re-checked against the
marts with DAX, and turns this banner off.

## How it was checked

- `pbir validate Vintage.Report` and `powerbi-report-author validate Vintage.pbip`: **0 errors**
  (a handful of Best-Practice-Analyzer sizing warnings on the smaller KPI cards remain; noted in
  the build notes, not blocking).
- `tests/test_powerbi.py`: the export never carries a `loan_id` column, every fixture row is
  flagged synthetic, and a spot-checked metric value matches the source artefact exactly.
- Not yet rendered in Power BI Desktop: the Desktop automation bridge did not start on the build
  machine, so the pages have been validated as files only. Rendering, DAX checks against the
  marts and screenshots (`docs/powerbi/`) come with the real-data export.

## Known simplifications (to revisit with the real-data export)

- **No global state slicer.** The published aggregates carry `property_state` only inside two
  segment tables (`lgd_segments`, `loss_drivers`), not as a column on every fact, so a
  report-wide state slicer would filter almost nothing. State appears as a category axis on the
  tables that have it instead. Revisit once G's portfolio analytics gives a wider state
  breakdown.
- **No global vintage/grade slicer sync group.** `pbir`'s local PBIR editor doesn't have a
  supported way to author the Desktop "Sync Slicers" pane groups from the CLI in this
  environment; the per-page slicers on `Dim Vintage Year` and `Dim Grade` filter their own page
  correctly, but a selection doesn't carry across pages. Wire it in Desktop's Sync Slicers pane
  (View -> Sync slicers) if that matters more than the time it takes.
