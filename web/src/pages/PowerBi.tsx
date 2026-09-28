// The Power BI risk pack, shown as captures from Power BI Desktop. The images follow the site
// theme: light captures in light mode, dark captures in dark mode (see .pbi-* in index.css).
const PAGES = [
  { slug: "portfolio-overview", title: "Portfolio overview", question: "Active balance, delinquency and default and loss rates over time." },
  { slug: "vintages", title: "Vintages", question: "Cumulative default and loss curves by months on book." },
  { slug: "roll-rates", title: "Roll rates", question: "Month-to-month transitions between days-past-due buckets, cures and the SMA mix." },
  { slug: "scorecard-and-monitoring", title: "Scorecard and monitoring", question: "Points table, grades, out-of-time Gini and KS, score PSI." },
  { slug: "ifrs-9-ecl", title: "IFRS 9 ECL", question: "ECL by reporting date and stage, coverage ratio and the backtest by grade." },
  { slug: "capital", title: "Capital", question: "Illustrative Basel IRB capital and RWA by grade." },
];

const REPO = "https://github.com/Ghostboy789/vintage-credit-risk/tree/main/powerbi";

export function PowerBi() {
  return (
    <div className="mx-auto max-w-[1200px] px-4 py-12 md:px-8">
      <h1 className="font-display text-4xl">Power BI risk pack</h1>
      <p className="mt-4 max-w-[720px]" style={{ color: "var(--ink-2)" }}>
        The same results as a six-page Power BI report, built as a PBIP project (TMDL model and PBIR
        report as text files) on the published aggregates. It was opened and refreshed in Power BI
        Desktop, and each headline card was checked against the artefacts it reports. Open it
        yourself from <a className="underline" href={REPO}>powerbi/ on GitHub</a>.
      </p>
      <div className="mt-10 grid gap-10 md:grid-cols-2">
        {PAGES.map((p) => (
          <figure key={p.slug} className="m-0">
            <a href={`/img/powerbi/${p.slug}-dark.png`} className="pbi-dark block" target="_blank" rel="noreferrer">
              <img
                src={`/img/powerbi/${p.slug}-dark.png`}
                alt={`Power BI report page: ${p.title} (dark theme)`}
                width={1600}
                height={896}
                loading="lazy"
                className="h-auto w-full rounded-lg border"
                style={{ borderColor: "var(--border)" }}
              />
            </a>
            <a href={`/img/powerbi/${p.slug}-light.png`} className="pbi-light block" target="_blank" rel="noreferrer">
              <img
                src={`/img/powerbi/${p.slug}-light.png`}
                alt={`Power BI report page: ${p.title} (light theme)`}
                width={1600}
                height={896}
                loading="lazy"
                className="h-auto w-full rounded-lg border"
                style={{ borderColor: "var(--border)" }}
              />
            </a>
            <figcaption className="mt-3">
              <span className="font-display text-lg">{p.title}</span>
              <span className="block text-sm" style={{ color: "var(--ink-2)" }}>{p.question}</span>
            </figcaption>
          </figure>
        ))}
      </div>
      <p className="mt-10 text-sm" style={{ color: "var(--ink-3)" }}>
        Captures from Power BI Desktop. Data: Freddie Mac Single-Family Loan-Level Dataset, aggregates
        only, non-commercial research use.
      </p>
    </div>
  );
}
