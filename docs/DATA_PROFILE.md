# Data profile

Every number below is computed straight from `data/parquet/` with DuckDB by
`scripts/profile_data.py` -- nothing here is estimated. Re-run that script to regenerate them.
Aggregates only, per `docs/DATA_LICENCE.md` (no loan ids, no individual rows).

Scope: the 27-year, 1999-2025 sample dataset (50,000 loans per origination vintage, ~1.35M loans
total, ~74.9M performance loan-months total), Freddie Mac Single-Family Loan-Level Dataset,
Release 47 (July 2026 layout). Every origination file has exactly 50,000 distinct loan ids, no
duplicates anywhere. The 2025 performance file is the one exception on the other side: only
49,995 distinct loan ids appear in it at all, versus 50,000 in `orig_2025`. The 5 missing loans
all carry a `Q4` loan id (originated in the last quarter of 2025) and simply have no performance
record yet -- the most recent partial vintage, cut off before their first reporting period.

## Loans and loan-months per origination vintage

Every vintage has exactly 50,000 origination rows (it's a fixed-size sample). Loan-months per
vintage range from ~0.4M (2025, barely a year old) up to 4.5M (2012, the longest-observed
mid-cycle vintage):

| Vintage | Loans | Loan-months |
|---|---|---|
| 1999 | 50,000 | 2,503,335 |
| 2000 | 50,000 | 1,442,994 |
| 2001 | 50,000 | 1,977,237 |
| 2002 | 50,000 | 2,496,389 |
| 2003 | 50,000 | 4,078,243 |
| 2004 | 50,000 | 3,985,245 |
| 2005 | 50,000 | 3,877,176 |
| 2006 | 50,000 | 3,203,499 |
| 2007 | 50,000 | 3,012,061 |
| 2008 | 50,000 | 2,456,504 |
| 2009 | 50,000 | 3,160,160 |
| 2010 | 50,000 | 3,446,018 |
| 2011 | 50,000 | 3,631,696 |
| 2012 | 50,000 | 4,510,559 |
| 2013 | 50,000 | 4,197,674 |
| 2014 | 50,000 | 3,394,276 |
| 2015 | 50,000 | 3,467,166 |
| 2016 | 50,000 | 3,379,650 |
| 2017 | 50,000 | 2,800,219 |
| 2018 | 50,000 | 2,059,564 |
| 2019 | 50,000 | 1,934,614 |
| 2020 | 50,000 | 2,517,857 |
| 2021 | 50,000 | 2,537,054 |
| 2022 | 50,000 | 2,034,798 |
| 2023 | 50,000 | 1,458,169 |
| 2024 | 50,000 | 952,865 |
| 2025 | 50,000 | 404,946 |

Totals: 1,350,000 loans, 74,919,968 loan-months.

## How loans end, by vintage

Per loan, its "terminal" Zero Balance Code is the code on its last record where the field is
populated (Freddie Mac only sets it once, in the period the loan leaves the dataset). A loan
with no Zero Balance Code in any record is still active/reporting as of the sample's cutoff.

"Default-type" here means Zero Balance Codes 02 (Third Party Sale), 03 (Short Sale or Charge
Off), 09 (REO Disposition), 15 (Whole Loan sales) -- Freddie Mac's own General User Guide
defines Actual Loss as calculated only for these four codes.

| Vintage | Active | Prepaid/matured | Default-type | Other removal |
|---|---|---|---|---|
| 1999 | 0.3% | 98.2% | 0.9% | 0.5% |
| 2000 | 0.2% | 97.9% | 1.3% | 0.6% |
| 2001 | 0.4% | 98.0% | 1.2% | 0.5% |
| 2002 | 0.6% | 97.6% | 1.3% | 0.5% |
| 2003 | 1.4% | 96.6% | 1.5% | 0.5% |
| 2004 | 2.0% | 94.0% | 3.1% | 0.9% |
| 2005 | 2.4% | 90.3% | 5.7% | 1.6% |
| 2006 | 2.2% | 87.3% | 8.1% | 2.4% |
| 2007 | 2.6% | 85.1% | 9.0% | 3.3% |
| 2008 | 2.2% | 91.4% | 4.3% | 2.1% |
| 2009 | 4.6% | 93.7% | 1.1% | 0.6% |
| 2010 | 6.3% | 92.1% | 1.0% | 0.6% |
| 2011 | 9.5% | 89.1% | 0.8% | 0.7% |
| 2012 | 19.1% | 79.5% | 0.8% | 0.6% |
| 2013 | 21.0% | 77.8% | 0.6% | 0.5% |
| 2014 | 17.5% | 81.6% | 0.4% | 0.5% |
| 2015 | 23.0% | 76.4% | 0.3% | 0.3% |
| 2016 | 28.1% | 71.5% | 0.2% | 0.3% |
| 2017 | 24.7% | 74.6% | 0.2% | 0.4% |
| 2018 | 19.8% | 79.7% | 0.1% | 0.4% |
| 2019 | 28.5% | 71.1% | 0.1% | 0.3% |
| 2020 | 60.9% | 38.8% | 0.0% | 0.3% |
| 2021 | 80.5% | 19.2% | 0.0% | 0.2% |
| 2022 | 80.0% | 19.3% | 0.1% | 0.5% |
| 2023 | 73.5% | 26.0% | 0.1% | 0.4% |
| 2024 | 81.2% | 18.4% | 0.0% | 0.4% |
| 2025 | 92.5% | 7.4% | 0.0% | 0.1% |

The 2005-2008 vintages carry the visible credit-crisis signature: default-type shares 3-9x
higher than the vintages just before or after them. Peak is 2007 at 9.0%. This is exactly the
window the project plan calls out for the PD/LGD build.

Zero Balance Code distribution across all vintages (terminal record per loan; every code that
appears is in Freddie Mac's documented set -- none outside it):

| Code | Loans | Meaning |
|---|---|---|
| 01 | 976,210 | Prepaid or Matured (Voluntary Payoff) |
| 09 | 11,885 | REO Disposition |
| 16 | 5,925 | Reperforming loan securitizations |
| 03 | 4,590 | Short Sale or Charge Off |
| 96 | 4,117 | Confirmed Underwriting Defect or Major Servicing Defect prior to credit event |
| 02 | 3,390 | Third Party Sale |
| 15 | 1,291 | Whole Loan sales |

## Delinquency status distribution (all 74.9M loan-months)

| Bucket | Loan-months | Share |
|---|---|---|
| Current (00) | 72,754,909 | 97.11% |
| 30-59 days (01) | 902,551 | 1.20% |
| 60-89 days (02) | 270,331 | 0.36% |
| 90+ days (numeric >= 03) | 877,814 | 1.17% |
| REO acquisition (RA) | 100,736 | 0.13% |
| Not available (XX) | 13,627 | 0.02% |

No codes outside `00`-`99`, `RA`, `XX` appear anywhere in the 74.9M rows.

## Loss-field coverage

The eight fields that only populate on a default-type disposition (mi_recoveries,
non_mi_recoveries, total_expenses, legal_costs, maintenance_and_preservation_costs,
taxes_and_insurance, miscellaneous_expenses, delinquent_accrued_interest) are filled on
19,544-19,639 of the 74,919,968 loan-months (0.026%) -- consistent with only ~21,156 loans
(the sum of Zero Balance Codes 02/03/09/15 above) ever reaching that terminal record.
`actual_loss` matches at 19,639.

`zero_balance_removal_upb` (1,007,408 rows, 1.345%) and `bankruptcy_cramdown_costs` (2,104,152
rows, 2.809%) are filled far more often -- both populate on *any* terminal record, not just
default-type ones (removal UPB is set whenever a loan leaves the dataset for any reason;
cramdown costs are their own, separate bankruptcy-driven event).

**Surprise**: `cumulative_modification_costs` shows 100.000% filled (74,919,968 / 74,919,968),
unlike every other loss field. That's not loss data being unusually complete -- 73,527,027 of
those rows (98.1%) are exactly `0`; only 1,392,941 (1.86%) carry a non-zero cost. Freddie Mac's
glossary explains why: this field is "disclosed in every monthly reporting period" rather than
only at termination, with 0 meaning "no modification cost this month." Coverage alone would be
misleading here without that context.

**Net Sales Proceeds** (the field typed as VARCHAR instead of the sibling loss fields' numeric
type, per the file layout's own "Alpha-Numeric" spec -- see `extract/build_parquet.py`): filled
on 19,638 of 74,919,968 rows (0.026%). Across the full 27-year sample, every filled value is
purely numeric (no letter codes) -- 19,328 negative (recoveries/gains, as the glossary's sign
convention specifies), 238 zero, 72 positive (expenses/losses). This confirms the earlier
release-47-sample finding at full scale: the VARCHAR typing is a defensive choice for a field
that, in this dataset, has never actually needed it.

## Original UPB / Current Non-Interest Bearing UPB: do they carry cents?

- `original_upb`: **never**. All 1,350,000 origination rows are whole dollars, and every one is
  an exact multiple of $1,000 (range $9,000-$2,300,000). This matches Freddie Mac's own glossary
  note verbatim: "The Original UPB is rounded to the nearest $1,000." The earlier DOUBLE typing
  (deviating from the layout's plain "Numeric" spec) is safe but, on this evidence, stricter than
  necessary -- a BIGINT would have held every value without loss.
- `current_non_interest_bearing_upb`: **yes**, in 573,886 of 74,919,968 non-null loan-months.
  This one does need DOUBLE, as the module's own deviation note already says.

## Forbearance / disaster / assistance flag coverage

| Flag | 2020-2021 | All 27 years |
|---|---|---|
| `payment_deferral_flag` | 105,061 / 7,026,772 (1.495%) | 489,428 / 74,919,968 (0.653%) |
| `delinquency_due_to_disaster` | 176,497 / 7,026,772 (2.512%) | 229,459 / 74,919,968 (0.306%) |
| `borrower_assistance_plan` | 186,105 / 7,026,772 (2.649%) | 289,683 / 74,919,968 (0.387%) |

All three flags are markedly more common in 2020-2021 than across the full history (2.4-4x for
`delinquency_due_to_disaster` and `borrower_assistance_plan`), consistent with COVID-era
forbearance activity. `borrower_assistance_plan` in 2020-2021 breaks down as F (Forbearance)
177,045, T (Trial Period) 7,144, R (Repayment) 1,916 -- forbearance dominates the window, as
expected.

## Missing credit scores, DTI, LTV/CLTV at origination

Sentinel "Not Available" codes per Freddie Mac's own glossary (FICO/VantageScore 4.0: 9999;
DTI/LTV/CLTV: 999). None of these five fields carry a true NULL anywhere in the 1,350,000
origination rows -- "missing" is always the sentinel code, never a blank:

| Field | Missing (sentinel) | Share |
|---|---|---|
| `classic_fico` (9999) | 2,113 | 0.157% |
| `vantage_score_4_0` (9999) | 1,350,000 | **100.000%** |
| `dti` (999) | 95,502 | 7.074% |
| `ltv` (999) | 43 | 0.003% |
| `cltv` (999) | 46 | 0.003% |

**Surprise**: `vantage_score_4_0` is Not Available for every single loan in the 27-year sample --
0 loans have a real VantageScore 4.0 value. This dataset cannot support any model or analysis
built on VantageScore; `classic_fico` (99.84% populated) is the credit score to use throughout
this project. `dti` at 7.1% missing is also notably higher than LTV/CLTV (both under 0.01%
missing) -- DTI disclosure has real gaps that LTV/CLTV mostly don't.

## Anything that contradicts the file layout

- No contradictions found beyond the two typing deviations `extract/build_parquet.py` already
  documents (Original UPB / Current Non-Interest Bearing UPB as DOUBLE; Net Sales Proceeds as
  VARCHAR) -- both confirmed above, at full 27-year scale, not just the small release-47 sample.
- Every Zero Balance Code and every Current Loan Delinquency Status value observed falls inside
  Freddie Mac's own documented enumeration (Zero Balance Codes 01/02/03/09/15/16/96; delinquency
  status 00-99, RA, XX). No undocumented codes appeared anywhere in the 74.9M loan-months.
- `original_upb`'s "rounded to the nearest $1,000" rule holds exactly, with zero exceptions.
