// The Power BI risk pack, shown as captures from Power BI Desktop. The images follow the site
// theme: light captures in light mode, dark captures in dark mode (see .pbi-* in index.css).
import { useEffect, useRef, useState } from "react";

const PAGES = [
  { slug: "portfolio-overview", title: "Portfolio overview", question: "Active balance, delinquency and default and loss rates over time." },
  { slug: "vintages", title: "Vintages", question: "Cumulative default and loss curves by months on book." },
  { slug: "roll-rates", title: "Roll rates", question: "Month-to-month transitions between days-past-due buckets, cures and the SMA mix." },
  { slug: "scorecard-and-monitoring", title: "Scorecard and monitoring", question: "Points table, grades, out-of-time Gini and KS, score PSI." },
  { slug: "ifrs-9-ecl", title: "IFRS 9 ECL", question: "ECL by reporting date and stage, coverage ratio and the backtest by grade." },
  { slug: "capital", title: "Capital", question: "Illustrative Basel IRB capital and RWA by grade." },
];

const REPO = "https://github.com/Ghostboy789/vintage-credit-risk/tree/main/powerbi";

function Shot({ slug, title, className, ...rest }: { slug: string; title: string; className?: string } & React.ImgHTMLAttributes<HTMLImageElement>) {
  return (
    <>
      {(["dark", "light"] as const).map((t) => (
        <img
          key={t}
          src={`/img/powerbi/${slug}-${t}.png`}
          alt={`Power BI report page: ${title} (${t} theme)`}
          width={1600}
          height={896}
          className={`pbi-${t} ${className ?? ""}`}
          {...rest}
        />
      ))}
    </>
  );
}

export function PowerBi() {
  const [open, setOpen] = useState<number | null>(null);
  const dlg = useRef<HTMLDialogElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  useEffect(() => {
    const d = dlg.current;
    if (!d) return;
    if (open !== null && !d.open) d.showModal();
    if (open === null && d.open) d.close();
  }, [open]);
  const go = (d: number) => setOpen((o) => (o === null ? o : (o + d + PAGES.length) % PAGES.length));
  const cur = open === null ? null : PAGES[open];
  const btn = "rounded border px-4 text-sm";

  return (
    <div className="mx-auto max-w-[1200px] px-4 py-12 md:px-8">
      <h1 className="font-display text-4xl">Power BI risk pack</h1>
      <p className="mt-3 max-w-[720px] text-lg" style={{ color: "var(--ink-2)" }}>
        The same results as the rest of this site, laid out as a business-intelligence report a risk
        team could open and filter. Tap any page to enlarge it.
      </p>
      <p className="mt-4 max-w-[720px]" style={{ color: "var(--ink-2)" }}>
        It is a six-page Power BI report, built as a PBIP project (TMDL model and PBIR report as text
        files) on the published aggregates. It was opened and refreshed in Power BI Desktop, and each
        headline card was checked against the artefacts it reports. Open it yourself from{" "}
        <a className="underline" href={REPO}>powerbi/ on GitHub</a>.
      </p>
      <div className="mt-10 grid gap-10 md:grid-cols-2">
        {PAGES.map((p, i) => (
          <figure key={p.slug} className="m-0">
            <button
              type="button"
              onClick={(e) => {
                opener.current = e.currentTarget;
                setOpen(i);
              }}
              aria-label={`Enlarge: ${p.title}`}
              className="group block w-full cursor-zoom-in rounded-lg p-0"
            >
              <Shot slug={p.slug} title={p.title} loading="lazy" className="h-auto w-full rounded-lg border transition-transform duration-200 group-hover:scale-[1.01]" style={{ borderColor: "var(--border)" }} />
            </button>
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

      <dialog
        ref={dlg}
        aria-label={cur ? `Power BI page: ${cur.title}` : "Power BI page"}
        onClose={() => {
          setOpen(null);
          opener.current?.focus();
        }}
        onClick={(e) => e.target === e.currentTarget && setOpen(null)}
        onKeyDown={(e) => {
          if (e.key === "ArrowRight") go(1);
          if (e.key === "ArrowLeft") go(-1);
        }}
        className="m-auto h-[100dvh] max-h-none w-screen max-w-none border-0 bg-transparent p-0 md:h-auto md:max-h-[92vh] md:w-[min(96vw,1400px)] backdrop:bg-black/80"
      >
        {cur && (
          <div className="flex h-full flex-col md:max-h-[92vh] md:rounded-xl" style={{ background: "var(--surface)", color: "var(--ink)" }}>
            <div className="flex items-center justify-between gap-2 p-3">
              <div className="min-w-0">
                <div className="font-display truncate text-lg">{cur.title}</div>
                <div className="hidden truncate text-sm md:block" style={{ color: "var(--ink-2)" }}>{cur.question}</div>
              </div>
              <div className="flex shrink-0 gap-2">
                <button type="button" onClick={() => go(-1)} className={btn} style={{ borderColor: "var(--border)", minHeight: 44 }} aria-label="Previous page">‹</button>
                <button type="button" onClick={() => go(1)} className={btn} style={{ borderColor: "var(--border)", minHeight: 44 }} aria-label="Next page">›</button>
                <button type="button" onClick={() => setOpen(null)} className={btn} style={{ borderColor: "var(--border)", minHeight: 44 }}>Close</button>
              </div>
            </div>
            {/* On a phone the capture keeps a readable width and scrolls sideways (pinch-zoom also works). */}
            <div className="min-h-0 flex-1 overflow-auto p-3 pt-0">
              <Shot slug={cur.slug} title={cur.title} className="h-auto w-full min-w-[900px] rounded border md:min-w-0" style={{ borderColor: "var(--border)" }} />
            </div>
          </div>
        )}
      </dialog>
    </div>
  );
}
