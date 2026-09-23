# Data licence

Source documents (Freddie Mac's own PDFs, not committed to this repo -- see "Sources" below):

- `fre_terms_conditions_sflld.pdf` -- **Terms and Conditions for Single-Family Loan-Level
  Dataset**, the free-registration terms that apply to downloading the public sample files from
  the Freddie Mac website. This is the operative document for this project.
- `dataset_licensing_agreement.pdf` -- **Freddie Mac Single Family Loan Level Data License and
  Subscription Agreement, Fee-Based Distribution and Commercial Use**. This is a paid, signed
  agreement (blank cover page shows a $27,562.50 licence fee) for a licensee that wants to
  *resell or redistribute* the data or derived products to third parties. This project has not
  signed it, is not paying a licence fee, and is not reselling or redistributing anything, so
  this agreement does not apply here. It does confirm, in its own introduction, that internal and
  non-commercial use is covered instead by the free terms and conditions: "Use of the Contents
  and distribution of the Data for internal purposes only, and use of the Contents for
  non-commercial purposes only, are also licensed by Enterprise on a royalty free basis under
  separate terms and conditions" -- i.e. the free document above.

## What the free terms allow

Use is restricted to the **"Internal Purpose"**: "personal, or ... your company's or your
organization's internal, purposes related to analyzing or researching credit performance of the
mortgage assets described in the ... Dataset." That is exactly this project's use.

Within the Internal Purpose you may:
- retrieve and copy the dataset;
- derive data from it and create "Derived Products";
- disseminate the dataset and Derived Products "solely within your own company or organization
  for the Internal Purpose."

You may also alter/convert the data "to the extent necessary for the Internal Purpose" -- this
covers converting the raw text files to Parquet and loading them into BigQuery.

## Storing it in a private cloud project

**Allowed.** A private Google Cloud / BigQuery sandbox project that nobody else has access to is
"your own ... organization" for the Internal Purpose -- it is not redistribution to a third
party. This does not depend on the "if unclear, load anyway" fallback: the terms clearly permit
it.

## What's clearly NOT allowed

- Redistributing, licensing, reposting, or otherwise making the raw Single-Family Loan-Level
  Dataset available to any third party, in whole or in part, free or paid, without a separate
  agreement with Freddie Mac (that's what the Fee-Based agreement above is for).
- Linking or attempting to link the dataset to other information "for the purpose or with the
  result of identifying or attempting to identify any individual." Nothing in this project's plan
  does this (no PII, no external joins to identify borrowers), and none should be added.
- Modifying/altering the dataset beyond what the Internal Purpose needs (i.e. no silently
  "fixing" values to make results look better -- also barred by this project's own no-fabrication
  rule).

## Publishing aggregates, charts, or model outputs -- UNCLEAR, decide later

The terms and conditions have one clause that allows public distribution of results:

> "You may also use the ... Dataset for academic or research purposes, and make your academic or
> research results and any related Derived Products available to the public, provided that any
> such distribution is solely for noncommercial purposes and further provided that the same does
> not include and cannot be used to derive or recreate any part of the ... Dataset or to identify
> any specific individual."

Two things are clear from this clause if it applies: publication must be non-commercial, and
published material must not include or allow reconstruction of any part of the raw loan-level
dataset (so genuine aggregates and charts -- not row-level extracts, not a full re-listing of a
table -- would qualify on that count).

What's **not** clear: whether a personal credit-risk portfolio project published to demonstrate
skills for a job search counts as "academic or research purposes." The document doesn't define
that phrase, and this isn't a university/institutional research use, but it also isn't a
commercial product or service. This is a judgement call on wording Freddie Mac doesn't spell out
further.

**Decision needed from Medhansh, at the end of the project (per his own standing decision), on
whether to publish anything derived from this dataset** (README numbers, dashboard charts,
notebook outputs, etc.) publicly on GitHub / a portfolio site. Until that decision, nothing
derived from the dataset is published anywhere public -- everything stays in the private repo
and the private BigQuery sandbox project.

## Sources

Both PDFs live outside this repo, at
`vintage-cache/downloads/freddie-docs/fre_terms_conditions_sflld.pdf` and
`.../dataset_licensing_agreement.pdf` (Freddie Mac's own documents; not redistributed here per
their own terms on redistributing Contents). `fre_terms_conditions_sflld.pdf` is dated "Effective
November 2025; Date last updated 11-03-2025."
