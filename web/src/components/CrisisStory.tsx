import { useEffect, useRef, useState } from "react";
import type { VintageCurveRow } from "../lib/types";
import { VintageCurveChart } from "./VintageCurveChart";
import { COMPARE_MOB, rowAt, rowsAt } from "../lib/vintage";
import { fmtPct } from "../lib/format";

// A stepped walk through the crisis: the chart stays pinned while the text scrolls past, and each
// step only changes which vintages are highlighted. The data never depends on scroll position.
// Pattern from The Pudding's scrollytelling write-ups (sticky graphic, one state per step).
interface Step {
  title: string;
  years: number[];
  text: string;
  annotate?: number;
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
      text: `Loans made from 1999 to 2003 had defaulted between ${span(range(1999, 2003))} of the time by month ${COMPARE_MOB}, six years on.`,
    },
    {
      title: "The build-up",
      years: [2004, 2005],
      text: `The 2004 vintage reached ${pct(2004)} and 2005 reached ${pct(2005)} by the same month. The curves start to lift before the crash.`,
    },
    {
      title: "The peak",
      years: [2006, 2007],
      annotate: 2007,
      text:
        `2006 reached ${pct(2006)} and 2007 reached ${pct(2007)}` +
        (e07 && e07.ci_low !== null && e07.ci_high !== null ? ` (95% CI ${fmtPct(e07.ci_low, 1)}–${fmtPct(e07.ci_high, 1)})` : "") +
        (ratio ? `: about ${ratio} times the 2003 vintage.` : "."),
    },
    {
      title: "The turn",
      years: [2008, 2009],
      text: `2008, made as the crash began, reached ${pct(2008)}. The 2009 vintage fell back to ${pct(2009)}.`,
    },
  ];
  if (laterMax)
    out.push({
      title: "After",
      years: laterYears,
      text: `No vintage from ${laterYears[0]} to ${laterYears.at(-1)} passed ${fmtPct(laterMax.cum_default_rate.value ?? 0, 1)} (the ${
        laterMax.vintage_year
      } figure) by month ${COMPARE_MOB}. Vintages after ${laterYears.at(-1)} have not been on book that long yet.`,
    });
  return out;
}

export function CrisisStory({ rows }: { rows: VintageCurveRow[] }) {
  const list = steps(rows);
  const [active, setActive] = useState(0);
  const refs = useRef<(HTMLDivElement | null)[]>([]);

  useEffect(() => {
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) if (e.isIntersecting) setActive(Number((e.target as HTMLElement).dataset.step));
      },
      { rootMargin: "-45% 0px -45% 0px" }
    );
    refs.current.forEach((el) => el && io.observe(el));
    return () => io.disconnect();
  }, [list.length]);

  const step = list[active];
  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 lg:gap-10">
      <div
        className="sticky top-14 z-10 -mx-4 px-4 pb-2 pt-3 md:top-16 lg:top-[96px] lg:col-span-7 lg:mx-0 lg:self-start lg:px-0"
        style={{ background: "var(--bg)" }}
      >
        <div className="font-mono mb-1 flex items-center gap-2 text-xs" style={{ color: "var(--ink-3)" }} aria-hidden>
          {list.map((s, i) => (
            <span
              key={s.title}
              className="h-1 flex-1 rounded-full transition-colors duration-300"
              style={{ background: i <= active ? "var(--crisis)" : "var(--ink-muted)" }}
            />
          ))}
          <span className="ml-1 tabular">
            {active + 1}/{list.length}
          </span>
        </div>
        <VintageCurveChart rows={rows} highlight={step.years} annotate={step.annotate} showPresets={false} caption={false} maxMob={120} />
      </div>
      <div className="lg:col-span-5">
        {list.map((s, i) => (
          <div
            key={s.title}
            ref={(el) => {
              refs.current[i] = el;
            }}
            data-step={i}
            className="flex min-h-[55vh] items-center py-8 lg:min-h-[80vh]"
          >
            <div
              className="rounded-xl border p-5 transition-opacity duration-300"
              style={{ borderColor: i === active ? "var(--crisis)" : "var(--border)", background: "var(--surface)", opacity: i === active ? 1 : 0.55 }}
            >
              <div className="font-mono text-xs uppercase" style={{ color: "var(--crisis)" }}>
                {s.title} · {s.years.length > 2 ? `${s.years[0]}–${s.years.at(-1)}` : s.years.join(" and ")}
              </div>
              <p className="mt-2 text-lg leading-snug">{s.text}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
