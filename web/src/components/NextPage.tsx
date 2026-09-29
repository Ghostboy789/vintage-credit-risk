import { Link, useLocation } from "react-router-dom";

// The reading order of the site; each page ends with a card to the next one.
const ORDER = [
  { to: "/", label: "Overview", blurb: "The whole story in one page." },
  { to: "/vintages", label: "Vintages", blurb: "How each year's loans went bad over time." },
  { to: "/roll-rates", label: "Roll rates", blurb: "How late loans get later, or recover." },
  { to: "/scorecard", label: "Scorecard", blurb: "Score a loan yourself and see its risk grade." },
  { to: "/ecl", label: "IFRS 9 ECL", blurb: "How much money to set aside for expected losses." },
  { to: "/capital", label: "Capital", blurb: "How much capital a bank would hold against these loans." },
  { to: "/powerbi", label: "Power BI", blurb: "The same results as a six-page report." },
  { to: "/methods", label: "Methods & limits", blurb: "Every rule, its evidence, and what isn't proven." },
];

export function NextPage() {
  const { pathname } = useLocation();
  const i = ORDER.findIndex((p) => p.to === pathname);
  if (i < 0 || i === ORDER.length - 1) return null;
  const next = ORDER[i + 1];
  return (
    <div className="mx-auto max-w-[1200px] px-4 pb-16 md:px-8">
      <Link
        to={next.to}
        className="next-card group flex items-center justify-between gap-4 rounded-xl border p-6 md:p-8"
        style={{ borderColor: "var(--border)", background: "var(--surface)" }}
      >
        <span>
          <span className="font-mono block text-xs uppercase tracking-wider" style={{ color: "var(--ink-3)" }}>
            Next · {i + 2} of {ORDER.length}
          </span>
          <span className="font-display mt-1 block text-2xl md:text-3xl" style={{ color: "var(--ink)" }}>{next.label}</span>
          <span className="mt-1 block text-sm" style={{ color: "var(--ink-2)" }}>{next.blurb}</span>
        </span>
        <span aria-hidden className="next-arrow text-2xl" style={{ color: "var(--accent)" }}>→</span>
      </Link>
    </div>
  );
}
