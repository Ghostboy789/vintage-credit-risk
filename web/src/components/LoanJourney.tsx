import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import type { Artefacts } from "../lib/artefacts";
import type { Estimate } from "../lib/types";
import { overviewFigures } from "../lib/overview-figures";
import { fmtInt, fmtMoney, fmtMoneyCompact, fmtPct } from "../lib/format";
import { useReducedMotion } from "../lib/theme";
import { Term } from "./Term";

const ci = (e: Estimate | undefined, f: (v: number) => string) =>
  e && e.ci_low !== null && e.ci_high !== null ? `95% CI ${f(e.ci_low)} – ${f(e.ci_high)}` : "";
const pct1 = (v: number) => fmtPct(v, 1);

interface Stop {
  title: string;
  big: string;
  text: ReactNode;
  ci?: string;
  to: string;
  hot?: boolean;
}

function Op({ sym, word }: { sym: string; word: string }) {
  return (
    <>
      <span aria-hidden className="font-display self-center text-2xl" style={{ color: "var(--ink-3)" }}>
        {sym}
      </span>
      <span className="sr-only">{word}</span>
    </>
  );
}

function EqTile({ to, label, big, sub, accent }: { to: string; label: string; big: string; sub: string; accent?: boolean }) {
  return (
    <Link to={to} className="eq-tile">
      <span className="font-mono text-[11px] uppercase tracking-wide" style={{ color: "var(--ink-3)" }}>
        {label}
      </span>
      <b className="tabular text-lg" style={{ color: accent ? "var(--accent)" : "var(--ink)" }}>
        {big}
      </b>
      <span className="font-mono text-xs" style={{ color: "var(--ink-2)" }}>
        {sub}
      </span>
    </Link>
  );
}

/** Concept A: one illustrative 2006 loan walked through the pipeline, each stop quoting its real statistic. */
export function LoanJourney({ data }: { data: Artefacts }) {
  const reduced = useReducedMotion();
  const wrap = useRef<HTMLDivElement>(null);
  const runner = useRef<HTMLSpanElement>(null);
  // -2: not armed (final state), -1: armed and waiting to enter view, n: stops 0..n have been reached.
  const [reached, setReached] = useState(-2);
  const armed = reached > -2;
  const f = overviewFigures(data);
  const start = data.portfolio.vintage_curves_annual.find((r) => r.vintage_year === 2006 && r.months_on_book === 1);

  const stops: Stop[] = [];
  if (start)
    stops.push({
      title: "Made",
      big: fmtInt(start.cum_default_rate.n),
      text: "loans in the 2006 vintage, and hers is one of them.",
      to: "/vintages",
    });
  if (f.cure30?.value != null)
    stops.push({
      title: "30 days late",
      big: pct1(f.cure30.value),
      text: "of loans this late were current again a month later, in the crisis.",
      ci: ci(f.cure30, pct1),
      to: "/roll-rates",
    });
  if (f.stay90?.value != null)
    stops.push({
      title: "90+ days late",
      big: pct1(f.stay90.value),
      text: "of loans this late were still 90+ a month later, in the crisis.",
      ci: ci(f.stay90, pct1),
      to: "/roll-rates",
    });
  if (f.v2006?.cum_default_rate.value != null)
    stops.push({
      title: "Default",
      big: pct1(f.v2006.cum_default_rate.value),
      text: "of 2006 loans had defaulted by month 72.",
      ci: ci(f.v2006.cum_default_rate, pct1),
      to: "/vintages",
      hot: true,
    });
  if (f.lgd?.value != null)
    stops.push({
      title: "Loss",
      big: fmtPct(f.lgd.value),
      text: "of the balance is lost when a loan defaults.",
      ci: ci(f.lgd, fmtPct),
      to: "/ecl",
      hot: true,
    });

  const eq: { key: string; term: string; big: string; sub: string; to: string }[] = [
    { key: "pd", term: "PD", big: "Per loan", sub: "from the scorecard", to: "/scorecard" },
  ];
  if (f.lgd?.value != null) eq.push({ key: "lgd", term: "LGD", big: fmtPct(f.lgd.value), sub: ci(f.lgd, fmtPct), to: "/ecl" });
  if (f.ead?.value != null) eq.push({ key: "ead", term: "EAD", big: fmtMoney(f.ead.value), sub: `mean, ${ci(f.ead, fmtMoney)}`, to: "/ecl" });
  const count = stops.length;

  useLayoutEffect(() => {
    setReached(reduced || count < 2 ? -2 : -1);
  }, [reduced, count]);

  // Once, when the list scrolls into view: the dot hops from stop to stop and each figure pops as it lands.
  useEffect(() => {
    const list = wrap.current;
    if (!armed || !list) return;
    const timers: number[] = [];
    let anim: Animation | undefined;
    const io = new IntersectionObserver(
      ([e]) => {
        if (!e.isIntersecting) return;
        io.disconnect();
        const box = list.getBoundingClientRect();
        const pts = [...list.querySelectorAll<HTMLElement>(".journey-dot")].map((d) => {
          const r = d.getBoundingClientRect();
          return `translate(${r.left - box.left + r.width / 2 - 7}px, ${r.top - box.top + r.height / 2 - 7}px)`;
        });
        const HOP = 520;
        pts.forEach((_, i) => timers.push(window.setTimeout(() => setReached(i), i * HOP)));
        anim = runner.current?.animate(
          [
            ...pts.map((transform, i) => ({ transform, opacity: 1, offset: i / (pts.length - 1), easing: "cubic-bezier(0.65,0,0.35,1)" })),
          ],
          { duration: HOP * (pts.length - 1), fill: "both" },
        );
        timers.push(window.setTimeout(() => runner.current?.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 400, fill: "forwards" }), HOP * (pts.length - 1) + 200));
      },
      { threshold: 0.4 },
    );
    io.observe(list);
    return () => {
      io.disconnect();
      timers.forEach(clearTimeout);
      anim?.cancel();
    };
  }, [armed]);

  if (stops.length < 2) return null;

  return (
    <section aria-labelledby="journey-h" className="py-12 md:py-16">
      <div className="font-mono text-xs uppercase tracking-wide" style={{ color: "var(--accent)" }}>
        Chapter 1 · one loan, start to finish
      </div>
      <h2 id="journey-h" className="font-display mt-2 max-w-[26ch] text-3xl md:text-4xl">
        Follow one loan
      </h2>
      <p className="mt-3 max-w-[68ch]" style={{ color: "var(--ink-2)" }}>
        Meet an illustrative 2006 borrower: not a real person or a real loan. At each stop, the figure is measured on the real loans
        like hers.
      </p>

      <div ref={wrap} className={`relative mt-8${reached > -2 ? " journey-armed" : ""}`}>
      <span ref={runner} className="journey-runner" aria-hidden />
      <ol className="journey list-none p-0">
        {stops.map((s, i) => (
          <li key={s.title} className={`journey-stop${s.hot ? " hot" : ""}${reached >= i ? " arrived" : ""}`}>
            <span className="journey-dot font-mono" aria-hidden>
              {i + 1}
            </span>
            <Link to={s.to} className="journey-card">
              <span className="text-sm font-semibold" style={{ color: "var(--ink)" }}>
                {s.title}
              </span>
              <span className="journey-fig tabular text-2xl font-semibold leading-none" style={{ color: s.hot ? "var(--crisis)" : "var(--ink)" }}>
                {s.big}
              </span>
              <span className="text-sm leading-snug" style={{ color: "var(--ink-2)" }}>
                {s.text}
              </span>
              {s.ci && (
                <span className="font-mono text-xs" style={{ color: "var(--ink-3)" }}>
                  {s.ci}
                </span>
              )}
              <span className="journey-go text-sm font-medium" style={{ color: "var(--accent)" }}>
                See the evidence →
              </span>
            </Link>
          </li>
        ))}
      </ol>
      </div>

      <div className="mt-8 rounded-xl border p-4 md:p-5" style={{ borderColor: "var(--border)", background: "var(--surface)" }}>
        <div className="text-sm" style={{ color: "var(--ink-2)" }}>
          So the lender sets money aside: <Term k="ECL">expected credit loss</Term> = <Term k="PD">PD</Term> ×{" "}
          <Term k="LGD">LGD</Term> × <Term k="EAD">EAD</Term>, added up over every active loan.
        </div>
        <div className="mt-4 flex flex-wrap items-stretch gap-x-3 gap-y-3">
          {eq.map((t, i) => (
            <span key={t.key} className="contents">
              {i > 0 && <Op sym="×" word="times" />}
              <EqTile to={t.to} label={t.term} big={t.big} sub={t.sub} />
            </span>
          ))}
          {f.ecl?.value != null && (
            <span className="contents">
              <Op sym="=" word="equals" />
              <EqTile to="/ecl" label="ECL, whole book" big={fmtMoneyCompact(f.ecl.value)} sub={ci(f.ecl, fmtMoneyCompact)} accent />
            </span>
          )}
        </div>
        <p className="mt-3 text-xs" style={{ color: "var(--ink-3)" }}>
          The interval covers parameter uncertainty only, so treat it as too narrow.
        </p>
      </div>
    </section>
  );
}
