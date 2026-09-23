# Vintage

A credit portfolio risk pack built on 20+ years of real US mortgage loan-level data (Freddie Mac
Single-Family Loan-Level Dataset, sample files): loan-month panel, vintage curves, roll rates, a
WoE/IV application scorecard, LGD/EAD, IFRS 9 / Ind AS 109 staging and ECL, and (stretch) Basel IRB
capital.

Status: work in progress. The validation plan (`VALIDATION_PLAN.md`) and the data contracts
(`CONTRACTS.md`) were committed before any model result. This README becomes the full write-up
once the results are in.

## Layout
- `extract/` -- turns the raw Freddie Mac text files into typed Parquet
- `dbt/` -- staging -> intermediate -> marts on BigQuery (star schema) and the metrics layer
- `models/` -- PD scorecard / challenger, LGD, EAD, lifetime PD, ECL, capital
- `analysis/` -- vintage curves, roll rates, monitoring
- `artefacts/` -- published JSON artefacts (contracts fixed in `CONTRACTS.md`)
- `excel/` -- the reconciled ECL workbook
- `app/` -- the FastAPI website
- `powerbi/` -- the Power BI risk pack (PBIP)
- `docs/` -- data licence, data profile, validation plan and other write-ups
- `scripts/` -- one-off and operational scripts (BigQuery load, fixture generation, exports)
- `tests/` -- pytest suite; `tests/fixtures/` holds synthetic fixtures only

## Data
Raw files, Parquet and model outputs live under `data/`, `marts_out/` and `models_out/`, all
gitignored and never published -- see `docs/DATA_LICENCE.md` for why. Every script reads them by
absolute path through `VINTAGE_DATA_ROOT` (see `config.py`), not a relative path.

## Data source and terms
Source: Freddie Mac Single-Family Loan-Level Dataset (sample files, 1999–2025 vintages), used
under Freddie Mac's terms for non-commercial research. The raw data is not redistributed here;
to reproduce the results, register with Freddie Mac and download the sample files yourself.
Only aggregates are published, with no cell describing fewer than 10 loans. Details in
`docs/DATA_LICENCE.md`.
