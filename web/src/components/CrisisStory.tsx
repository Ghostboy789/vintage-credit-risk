import { useEffect, useMemo, useRef, useState } from "react";
import type { VintageCurveRow } from "../lib/types";
import { VintageCurveChart } from "./VintageCurveChart";
import { COMPARE_MOB, rowAt, rowsAt } from "../lib/vintage";
import { fmtPct } from "../lib/format";

// Scrollytelling through the crisis: the chart stays pinned while chapters scroll past, and each
// chapter only changes which vintages are highlighted (same axes throughout). The data never depends on scroll position.
// Pattern from The Pudding's scrollytelling write-ups (sticky graphic, one state per step).
interface Step {
  title: string;
  years: number[];
  text: string;
  annotate?: number;
  // The one figure the step is about, taken from the same rows as the text.
  stat?: { value: string; label: string };
}

const range = (a: number, b: number) => Array.from({ length: b - a + 1 }, (_, i) => a + i);

function steps(rows: VintageCurveRow[]): Step[] {
  const at = (y: number) => rowAt(rows, y)?.cum_default_rate.value ?? null;
  const pct = (y: number) => (at(y) === null ? "—" : fmtPct(at(y)!, 1));
  const span = (ys: number[]) => {
    const v = ys.map(at).filter((x): x is number => x !== null);
    return v.length ? `${fmtPct(Math.min(...v), 1)} and ${fmtPct(Math.max(...v), 1)}` : "—";
  };
  const later = rowsAt(rows).filter((r) => r.vintage_year >= 2010);
  const laterYears = later.map((r) => r.vintage_year);
  const laterMax = later.reduce<VintageCurveRow | null>(
    (m, r) => (m === null || (r.cum_default_rate.value ?? 0) > (m.cum_default_rate.value ?? 0) ? r : m),
    null
  );
  const e07 = rowAt(rows, 2007)?.cum_default_rate;
  const ratio = at(2007) !== null && at(2003) ? (at(2007)! / at(2003)!).toFixed(0) : null;
  const out: Step[] = [
    {
      title: "Before",
      years: range(1999, 2003),
      annotate: range(1999, 2003).reduce((b, y) => ((at(y) ?? -1) > (at(b) ?? -1) ? y : b), 1999),
      stat: (() => {
        const v = range(1999, 2003).map(at).filter((x): x is number => x !== null);
        return v.length ? { value: `up to ${fmtPct(Math.max(...v), 1)}`, label: `highest of the 1999–2003 vintages at month ${COMPARE_MOB}` } : undefined;
      })(),
      text: `Loans made from 1999 to 2003 had defaulted between ${span(range(1999, 2003))} of the time by month ${COMPARE_MOB}, six years on.`,
    },
    {
      title: "The build-up",
      years: [2004, 2005],
      annotate: 2005,
      stat: at(2005) === null ? undefined : { value: pct(2005), label: `of 2005 loans defaulted by month ${COMPARE_MOB}` },
      text: `The 2004 vintage reached ${pct(2004)} and 2005 reached ${pct(2005)} by the same month. The curves start to lift before the crash.`,
    },
    {
      title: "The peak",
      years: [2006, 2007],
      annotate: 2007,
      stat: at(2007) === null ? undefined : { value: pct(2007), label: `of 2007 loans defaulted by month ${COMPARE_MOB}` },
      text:
        `2006 reached ${pct(2006)} and 2007 reached ${pct(2007)}` +
        (e07 && e07.ci_low !== null && e07.ci_high !== null ? ` (95% CI ${fmtPct(e07.ci_low, 1)}–${fmtPct(e07.ci_high, 1)})` : "") +
        (ratio ? `: about ${ratio} times the 2003 vintage.` : "."),
    },
    {
      title: "The turn",
      years: [2008, 2009],
      annotate: 2008,
      stat: at(2009) === null ? undefined : { value: pct(2009), label: `of 2009 loans defaulted by month ${COMPARE_MOB}` },
      text: `2008, made as the crash began, reached ${pct(2008)}. The 2009 vintage fell back to ${pct(2009)}.`,
    },
  ];
  const [c20, c21] = [2020, 2021].map((y) => {
    const r = rows.filter((q) => q.vintage_year === y && q.fully_observed && q.cum_default_rate.value !== null).sort((a, b) => b.months_on_book - a.months_on_book)[0];
    return r ? { mob: r.months_on_book, v: r.cum_default_rate.value! } : null;
  });
  if (laterMax)
    out.push({
      title: "After",
      years: laterYears,
      annotate: laterMax.vintage_year,
      stat: { value: `at most ${fmtPct(laterMax.cum_default_rate.value ?? 0, 1)}`, label: `for any ${laterYears[0]}–${laterYears.at(-1)} vintage at month ${COMPARE_MOB}` },
      text: `No vintage from ${laterYears[0]} to ${laterYears.at(-1)} passed ${fmtPct(laterMax.cum_default_rate.value ?? 0, 1)} (the ${
        laterMax.vintage_year
      } figure) by month ${COMPARE_MOB}. Vintages after ${laterYears.at(-1)} have not been on book that long yet.`,
    });
  if (c20) {
    const ref = rows.find((q) => q.vintage_year === 2007 && q.months_on_book === c20.mob)?.cum_default_rate.value;
    out.push({
      title: "COVID",
      years: [2020, 2021],
      stat: { value: `not yet at month ${COMPARE_MOB}`, label: "neither COVID-era vintage has been observed that long" },
      text:
        `The 2020 vintage is fully observed only to month ${c20.mob}, where ${fmtPct(c20.v, 1)} of its loans had defaulted` +
        (c21 ? `; 2021 to month ${c21.mob}, at ${fmtPct(c21.v, 1)}` : "") +
        `. Neither reaches month ${COMPARE_MOB}, so they cannot be ranked against the vintages above.` +
        (ref != null ? ` For scale, 2007 stood at ${fmtPct(ref, 1)} at month ${c20.mob}.` : ""),
    });
  }
  return out;
}

const label = (s: Step) => (s.years.length > 2 ? `${s.years[0]}–${s.years.at(-1)}` : s.years.join(" and "));

export function CrisisStory({ rows }: { rows: VintageCurveRow[] }) {
  const list = useMemo(() => steps(rows), [rows]);
  const [active, setActive] = useState(0);
  const refs = useRef<(HTMLElement | null)[]>([]);

  useEffect(() => {
    // Phone: the pinned chart covers the top of the screen, so read the band just beneath it.
    const phone = window.matchMedia("(max-width: 1023px)").matches;
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) if (e.isIntersecting) setActive(Number((e.target as HTMLElement).dataset.step));
      },
      { rootMargin: phone ? "-62% 0px -28% 0px" : "-45% 0px -45% 0px" }
    );
    refs.current.forEach((el) => el && io.observe(el));
    return () => io.disconnect();
  }, [list.length]);

  const step = list[active];
  const skip = () => {
    const el = document.getElementById("every-vintage");
    el?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
    el?.focus({ preventScroll: true });
  };
  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 lg:gap-10">
      <div
        className="sticky top-0 z-10 -mx-4 border-b px-4 pb-2 pt-2 lg:top-6 lg:order-2 lg:col-span-7 lg:mx-0 lg:self-start lg:rounded-xl lg:border lg:p-4"
        style={{ background: "var(--bg)", borderColor: "var(--border)" }}
      >
        <div className="font-mono mb-1 flex items-center gap-2 text-xs" style={{ color: "var(--ink-3)" }}>
          <span className="tabular whitespace-nowrap font-semibold" style={{ color: "var(--ink)" }} aria-live="polite">
            {active + 1} / {list.length}
          </span>
          <span className="flex flex-1 gap-1" aria-hidden>
            {list.map((s, i) => (
              <span key={s.title} className="h-1 flex-1 rounded-full transition-colors duration-300 motion-reduce:transition-none" style={{ background: i <= active ? "var(--crisis)" : "var(--ink-muted)" }} />
            ))}
          </span>
          <span className="whitespace-nowrap" style={{ color: "var(--ink-2)" }}>{step.title}</span>
        </div>
        <VintageCurveChart rows={rows} highlight={step.years} annotate={step.annotate} showPresets={false} caption={false} tableToggle={false} maxMob={120} />
      </div>
      <div className="lg:order-1 lg:col-span-5">
        <a
          href="#every-vintage"
          onClick={(e) => {
            e.preventDefault();
            skip();
          }}
          className="mt-3 inline-flex min-h-[44px] items-center text-sm underline underline-offset-4"
          style={{ color: "var(--ink-2)" }}
        >
          Skip the story
        </a>
        {list.map((s, i) => (
          <article
            key={s.title}
            ref={(el) => {
              refs.current[i] = el;
            }}
            data-step={i}
            tabIndex={0}
            aria-label={`Chapter ${i + 1} of ${list.length}: ${s.title}`}
            onFocus={() => setActive(i)}
            className="flex min-h-[48vh] items-center py-6 lg:min-h-[80vh] lg:py-8"
          >
            <div
              className="w-full rounded-xl border p-5 transition-[opacity,border-color] duration-300 motion-reduce:transition-none md:p-6"
              style={{ borderColor: i === active ? "var(--crisis)" : "var(--border)", background: "var(--surface)", opacity: i === active ? 1 : 0.55 }}
            >
              <div className="font-mono text-xs uppercase" style={{ color: "var(--crisis)" }}>
                Chapter {i + 1} · {label(s)}
              </div>
              <h3 className="font-display mt-1 text-2xl md:text-3xl">{s.title}</h3>
              {s.stat && (
                <div className="mt-3">
                  <div className="tabular font-semibold leading-none" style={{ fontSize: "clamp(30px,5vw,44px)", color: "var(--crisis)" }}>
                    {s.stat.value}
                  </div>
                  <div className="mt-1 text-[13px]" style={{ color: "var(--ink-2)" }}>
                    {s.stat.label}
                  </div>
                </div>
              )}
              <p className="mt-3 text-base leading-relaxed" style={{ color: "var(--ink-2)" }}>
                {s.text}
              </p>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
