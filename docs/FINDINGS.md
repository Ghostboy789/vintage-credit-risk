# Portfolio findings

`analysis/portfolio.py` builds `artefacts/portfolio.json` from the real dbt marts
(`marts_out/`, 1999-2024 vintages; 2025 is excluded everywhere in this file, window incomplete,
D6). Every number below is read back from that artefact; none is computed separately for this
page. Development years are 1999-2015 (`n` = 50,000 loans per vintage year unless stated).

**Right-censoring.** Recent vintages have not had as long on book as old ones.
`comparable_months_on_book` in the artefact is the largest months on book that *every* vintage
in the artefact has fully observed; because the newest included vintage (2024) has barely had a
month, that portfolio-wide scalar is now 1. The specific comparisons below instead use each
compared vintage's own `fully_observed = true` flag at the stated months-on-book point, which is
the plan's actual rule ("compare vintages only at months on book that all of them have
reached") applied to the specific vintages being compared, not to the whole 26-year artefact at
once. Every vintage-curve chart built from this artefact must carry the same caveat.

**Pre-registration.** No outcome analysis of 2016+ vintages happened before
`models_out/oot_scoring_log.jsonl` recorded the scorecard's out-of-time scoring (P3); that file
now exists (`scorecard-5abfae854ca0`, scored 2026-09-24), so this run covers the full 1999-2024
population. Reconciliation (R1-R4) does not depend on that gate: it is counts, loan-month
counts, balances and loss sums, never a default rate by vintage.

## 1. The 2005-2008 crisis vintages defaulted 6-8x more than the vintages around them

At 72 months on book (6 years; all three vintages `fully_observed = true` there), the 2007
vintage's cumulative primary default rate is **14.41% (95% CI 14.11-14.72%, n=50,000)**, against
**1.83% (1.71-1.95%, n=50,000)** for 2003 and **2.57% (2.43-2.71%, n=50,000)** for 1999. Its
cumulative loss rate is **2.65% (2.54-2.77%) of original UPB**, against 0.05% and 0.05% for those
two benign years -- roughly 50x, not just 6-8x, because loss severity also rose in the crisis
(the LGD-by-LTV finding below). *Caveat:* this is the whole cohort's realised outcome, not a
model; it says what happened to 2007 originations, not what a similar loan would do today.

## 2. The COVID forbearance exemption (D3) changes a vintage's measured 12-month default rate by
   ~11x, with no change in the underlying loans

For the 2019 vintage, `default_definition_effect` shows a 12-month primary (D1, COVID-exempt)
default rate of **0.208% (n=50,000)** against a naive (D2, no exemption) rate of
**2.324% (n=50,000)** -- both counted on exactly the same 50,000 loans. Every other pre-2018
vintage checked (1999-2008) has primary and naive rates equal to 3 decimal places, because the
forbearance and disaster flags Freddie Mac reports do not exist before 2014 (VALIDATION_PLAN
D3), so the exemption cannot have fired retroactively. This is the single largest reason two
credible analysts could publish different "2019 default rate" numbers from the same data, and it
is a measurement artefact of forbearance reporting, not a change in borrower behaviour.

## 3. Severely delinquent loans cured *faster* under COVID-era forbearance than they did in 2008

`roll_cure_rates` (dpd_90p -> current, the month-to-month roll-rate cure, not D4): **4.04%
(n=268,745)** during the 2008 crisis window, but **8.64% (n=139,122)** during COVID -- higher
even than the 7.36% (n=35,692) seen before the crisis. Conversely the *escalation* rate from 60
to 90+ days past due was higher in the 2008 crisis (**40.21%, n=77,571**) than pre-crisis
(**31.20%, n=22,905**); COVID-era escalation (`dpd_60`->`dpd_90p`, not shown here in full) sits
between the two. Read together, these say the crisis and the pandemic were different kinds of
shock to the same population: 2008 pushed more loans further into delinquency and cured fewer of
them, while COVID-era forbearance and modification programmes moved severely delinquent loans
back to current at a rate the housing crash never matched. *Caveat:* roll rates here are pooled
across every vintage and forbearance status in the period; they are not one vintage's experience.

## 4. Loan-to-value at origination is the strongest loss driver measured here

`loss_drivers` (dimension `ltv_band`, whole 1999-2024 population): default rate rises from
**2.14% (n=321,605)** for LTV <= 60 to **8.52% (8.26-8.78%, n=45,712)** for LTV > 95, and loss
rate (of original UPB) rises from **0.11% (0.10-0.12%)** to **1.05% (0.98-1.12%)** over the same
bands -- about a 4x rise in default incidence and a 9-10x rise in loss rate, since higher-LTV
defaults also lose more per dollar of exposure. *Caveat:* LTV band alone; this is not a
multivariate loss model, and MI coverage (excluded here) tracks LTV and mitigates part of the
gap for the highest bands.

## 5. Prepayment speeds trace the real refinancing cycles, which is itself a check on the pipeline

`prepayment` (CPR, from `fct_loan_month.exit_type` and `at_risk_at_start`, monthly, n in the
hundreds of thousands per month): CPR reaches **21-23%** through the 2010-2012 refinancing wave,
**16-18%** in 2002-2004, and peaks at **30.6% in September 2020** during the pandemic refinancing
boom, against **5-10%** in slow years either side. These numbers were not fit to anything --
they fall out of the raw exit flags -- and they land exactly where the historical mortgage
market record says they should, which is independent evidence the panel and its exit-type
handling are correct (see the "did not hold up" section for the one place they weren't).

## 6. Reconciliation (R1-R8) passes, with one exact, already-explained exception

R2 (loan-months), R3 (balances, off by $0.35 on a $12.6 trillion sum), R4 (loss sums, off by
$2.4e-7 on $1.39 billion), R7 (metrics-layer arithmetic, 1,635 checks, largest relative
difference 4.9e-15) and R8 (this artefact's own counts against their marts) all **PASS**. R1
(loan count) **FAILs** by exactly 5 loans out of 1,349,995 mart loans against 1,350,000 raw
loans -- the same 5 loans `docs/RECONCILIATION.md` already documents and root-causes (2025Q4
originations with no performance records yet at the data cut-off, dropped when `dim_loan`
inner-joins its resolution table). Reported as a FAIL, not tuned away, because it is one.

## What did not hold up

- **The pre-registration sizing overstated crisis-vintage 12-month defaults by roughly 2x.**
  VALIDATION_PLAN.md Appendix A, computed before the dbt build existed, used Freddie Mac's own
  `loan_age` field as a stand-in clock and reported 1,214 twelve-month primary defaults for the
  2007 vintage (2.43%). The dbt-built mart's actual D0 (`months_on_book`) count is 556 (1.11%,
  matches `fct_scorecard_base.default_12m` exactly). The plan's own caveat ("final counts may
  differ slightly") undersold how much they differ; a factor of ~2 for the crisis vintages is
  the kind of gap a validator should be told about explicitly, not left to a footnote.
- **`fct_roll_rates.to_state` does not carry exit types on the real build.** Of 1,349,995
  loans, 1,348,739 month-to-month transitions that should show `prepaid`, `matured`,
  `credit_event` or `other_exit` are instead recorded as `to_state = "missing"` --
  `dim_loan.exit_type` and `fct_loan_month.exit_type` are both correct (970,705 prepaid, 5,505
  matured, 21,156 credit_event, 10,042 other_exit), so this is a defect isolated to the roll-rate
  mart's own derivation, not the underlying data. `prepayment` in this artefact was computed
  directly from `fct_loan_month` to route around it (finding 5 above). `roll_rates` and
  `roll_cure_rates` in this artefact are unaffected for their published `to_state` values
  (`current`, `dpd_30`, `dpd_60`, `dpd_90p`, `reo`), but any reading of `fct_roll_rates.to_state
  = "missing"` elsewhere in this project should not be taken as "no next-month record" until the
  mart is fixed; flagged separately for a dbt fix, not patched here (outside this file's
  ownership).

## What this does not establish

- These are vintage-level and portfolio-level descriptive statistics, not a model: they say what
  happened, not what will happen to a new loan (that is the scorecard and the hazard model).
- The bootstrap interval on `cum_loss_rate` and on the loss-driver `loss_rate` treats each
  vintage's or segment's own loans as a sample from a hypothetical superpopulation -- the same
  framing the Wilson interval on `cum_default_rate` already uses -- not a claim that a different
  draw of loans was possible.
- US conforming mortgages only (VALIDATION_PLAN.md section 11): no reject inference, not Indian
  loans, and every relationship here is an association, not a causal effect.
