import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode, type PointerEvent as RPointerEvent } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import type { Artefacts } from "../lib/artefacts";
import type { Estimate } from "../lib/types";
import { collectRules } from "../lib/rules";
import { eclDates, stageTotals, type EclRow } from "../lib/ecl";
import { fmtDate, fmtInt, fmtMoneyCompact, fmtPct } from "../lib/format";
import { COMPARE_MOB, rowAt } from "../lib/vintage";

const CARD_MS = 8000;
const STAGE_VAR = ["var(--stage-1)", "var(--stage-2)", "var(--stage-3)"];
const ci = (e: Estimate, f: (v: number) => string) =>
  e.ci_low !== null && e.ci_high !== null ? `95% CI ${f(e.ci_low)} – ${f(e.ci_high)}` : null;

interface Card {
  label: string;
  title: string;
  body?: ReactNode;
  stat?: string;
  extra?: ReactNode;
}

function buildCards(data: Artefacts): Card[] {
  const { portfolio, pd_models } = data;
  const cards: Card[] = [];
  const years = portfolio.vintage_curves_annual.map((r) => r.vintage_year);
  const y0 = Math.min(...years);
  const y1 = Math.max(...years);
  const nLoans = portfolio.summary.n_loans.value ?? 0;
  cards.push({
    label: "What this is",
    title: `${(nLoans / 1e6).toFixed(1)} million Freddie Mac mortgages, ${y0}–${y1}`,
    body: `Every loan is followed month by month until ${fmtDate(portfolio.data_cutoff)}. The question: how did each year's loans go bad, and could a lender have seen it coming?`,
  });

  const a = rowAt(portfolio.vintage_curves_annual, 2003);
  const b = rowAt(portfolio.vintage_curves_annual, 2007);
  if (a && b && a.cum_default_rate.value && b.cum_default_rate.value !== null) {
    const bi = ci(b.cum_default_rate, (v) => fmtPct(v, 1));
    cards.push({
      label: "The crisis",
      title: `2007 loans defaulted ${(b.cum_default_rate.value / a.cum_default_rate.value).toFixed(1)}× as often as 2003's`,
      stat: `${fmtPct(b.cum_default_rate.value, 1)} vs ${fmtPct(a.cum_default_rate.value, 1)}`,
      body: `Share of each year's loans that had defaulted by month ${COMPARE_MOB}.${bi ? ` 2007: ${bi}.` : ""}`,
    });
  }

  const ecl = data.ecl as unknown as { by_date: EclRow[]; scenario_totals?: { reporting_date: string; scenario: string; ecl: Estimate }[] };
  const dates = eclDates(ecl.by_date);
  const date = dates[dates.length - 1];
  const tot = (ecl.scenario_totals ?? []).find((t) => t.reporting_date === date && t.scenario === "final")?.ecl;
  if (tot && tot.value !== null) {
    const st = stageTotals(ecl.by_date, date);
    const n = st.reduce((s, t) => s + t.n, 0) || 1;
    const ciText = ci(tot, fmtMoneyCompact);
    cards.push({
      label: "The money",
      title: `A lender would set aside ${fmtMoneyCompact(tot.value)}`,
      body: `Expected credit loss on ${fmtInt(n)} active loans at ${fmtDate(date)}, under IFRS 9.${ciText ? ` ${ciText}, parameter uncertainty only, so too narrow.` : ""}`,
      extra: (
        <div>
          <div className="tour-stagebar" role="img" aria-label={st.map((t) => `Stage ${t.stage} ${fmtPct(t.n / n, 1)} of loans`).join(", ")}>
            {st.map((t, i) => (
              <i key={t.stage} style={{ flexGrow: t.n, background: STAGE_VAR[i], minWidth: t.n > 0 ? 4 : 0 }} />
            ))}
          </div>
          <p className="tour-small">
            Loans by stage: {st.map((t, i) => `${["performing", "risk risen", "defaulted"][i]} ${fmtPct(t.n / n, 1)}`).join(" · ")}
          </p>
        </div>
      ),
    });
  }

  const disc = (pd_models.discrimination ?? []) as { sample: string; definition: string; model: string; gini: Estimate }[];
  const oot = disc.find((d) => d.sample === "oot" && d.definition === "primary" && d.model === "champion")?.gini;
  const rules = collectRules(data);
  const s4b = rules.find((r) => r.rule_id === "S4b");
  if (oot && oot.value !== null) {
    const ciText = ci(oot, (v) => v.toFixed(2));
    cards.push({
      label: "The model",
      title: `The risk score ranks borrowers well: Gini ${oot.value.toFixed(2)}`,
      stat: ciText ?? undefined,
      body:
        "Tested on later loans it had never seen (0 is a coin flip, 1 is perfect)." +
        (s4b?.result === "FAIL" ? " But it ranks well without being calibrated out of time: the default rates it predicts are off." : ""),
    });
  }

  const count = (r: string) => rules.filter((x) => x.result === r).length;
  cards.push({
    label: "Honesty",
    title: `${rules.length} tests written down before the results. ${count("FAIL")} failed.`,
    body: "None was re-tuned to pass. The failures are shown, first, on the Methods page.",
    extra: (
      <div className="tour-pills">
        <span className="tour-pill" style={{ color: "var(--fail)" }}>{count("FAIL")} FAIL</span>
        <span className="tour-pill" style={{ color: "var(--amber)" }}>{count("AMBER")} AMBER</span>
        <span className="tour-pill" style={{ color: "var(--pass)" }}>{count("PASS")} PASS</span>
      </div>
    ),
  });

  cards.push({ label: "Go deeper", title: "Explore the full analysis" });
  return cards;
}

const LINKS = [
  { to: "/vintages", label: "Vintages" },
  { to: "/scorecard", label: "Scorecard" },
  { to: "/ecl", label: "IFRS 9 ECL" },
  { to: "/methods", label: "Methods" },
];

export function StoryTour({ data, openOnMount = false }: { data: Artefacts; openOnMount?: boolean }) {
  const [open, setOpen] = useState(false);
  const [idx, setIdx] = useState(0);
  const [held, setHeld] = useState(false);
  const [hidden, setHidden] = useState(false);
  const [reduced, setReduced] = useState(false);
  const navigate = useNavigate();
  const cards = useMemo(() => buildCards(data), [data]);
  const last = cards.length - 1;
  const fill = useRef<HTMLElement | null>(null);
  const elapsed = useRef(0);
  const dialog = useRef<HTMLDivElement>(null);
  const opener = useRef<Element | null>(null);
  const down = useRef<{ x: number; y: number; t: number } | null>(null);

  const close = useCallback(() => {
    setOpen(false);
    if (window.location.hash === "#tour") history.replaceState(null, "", window.location.pathname + window.location.search);
  }, []);
  const go = useCallback(
    (i: number) => {
      elapsed.current = 0;
      setIdx(Math.max(0, Math.min(last, i)));
    },
    [last]
  );

  // Open triggers: custom event and #tour.
  useEffect(() => {
    const show = () => {
      opener.current = document.activeElement;
      elapsed.current = 0;
      setIdx(0);
      setOpen(true);
    };
    const onHash = () => window.location.hash === "#tour" && show();
    if (openOnMount) show();
    else onHash();
    window.addEventListener("vintage:tour", show);
    window.addEventListener("hashchange", onHash);
    return () => {
      window.removeEventListener("vintage:tour", show);
      window.removeEventListener("hashchange", onHash);
    };
  }, [openOnMount]);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const sync = () => setReduced(mq.matches);
    const vis = () => setHidden(document.hidden);
    sync();
    mq.addEventListener("change", sync);
    document.addEventListener("visibilitychange", vis);
    return () => {
      mq.removeEventListener("change", sync);
      document.removeEventListener("visibilitychange", vis);
    };
  }, []);

  // Modal behaviour: scroll lock, inert page, focus in and back, Esc / arrows / Tab trap.
  useEffect(() => {
    if (!open) return;
    const root = document.getElementById("root");
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    root?.setAttribute("inert", "");
    dialog.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") return close();
      if (e.key === "ArrowRight") return go(idx + 1);
      if (e.key === "ArrowLeft") return go(idx - 1);
      if (e.key !== "Tab" || !dialog.current) return;
      const f = [...dialog.current.querySelectorAll<HTMLElement>("button:not([disabled])")];
      if (!f.length) return;
      const first = f[0];
      const lastEl = f[f.length - 1];
      const cur = document.activeElement;
      if (e.shiftKey && (cur === first || cur === dialog.current)) {
        e.preventDefault();
        lastEl.focus();
      } else if (!e.shiftKey && cur === lastEl) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
      root?.removeAttribute("inert");
      (opener.current as HTMLElement | null)?.focus?.();
    };
  }, [open, idx, close, go]);

  // Auto-advance: fills the current segment over CARD_MS; paused on hold / hidden tab; none for reduced motion or the last card.
  const running = open && !held && !hidden && !reduced && idx < last;
  useEffect(() => {
    if (fill.current) fill.current.style.transform = `scaleX(${Math.min(1, elapsed.current / CARD_MS)})`;
    if (!running) return;
    let prev = performance.now();
    let raf = requestAnimationFrame(function tick(now) {
      elapsed.current += now - prev;
      prev = now;
      if (elapsed.current >= CARD_MS) return go(idx + 1);
      if (fill.current) fill.current.style.transform = `scaleX(${elapsed.current / CARD_MS})`;
      raf = requestAnimationFrame(tick);
    });
    return () => cancelAnimationFrame(raf);
  }, [running, idx, go]);

  if (!open) return null;

  const onDown = (e: RPointerEvent<HTMLDivElement>) => {
    down.current = { x: e.clientX, y: e.clientY, t: Date.now() };
    setHeld(true);
  };
  const onUp = (e: RPointerEvent<HTMLDivElement>) => {
    setHeld(false);
    const d = down.current;
    down.current = null;
    if (!d || (e.target as HTMLElement).closest("button")) return;
    const dy = e.clientY - d.y;
    if (dy > 80 && dy > Math.abs(e.clientX - d.x)) return close();
    if (Date.now() - d.t > 300 || Math.abs(e.clientX - d.x) > 12 || Math.abs(dy) > 12) return;
    const r = e.currentTarget.getBoundingClientRect();
    go((e.clientX - r.left) / r.width < 1 / 3 ? idx - 1 : idx + 1);
  };

  const c = cards[idx];
  return createPortal(
    <div className="tour-backdrop" onClick={(e) => e.target === e.currentTarget && close()}>
      <div ref={dialog} className="tour-card" role="dialog" aria-modal="true" aria-labelledby="tour-title" tabIndex={-1}>
        <div className="tour-prog" aria-hidden>
          {cards.map((_, i) => (
            <span key={i} className="tour-seg">
              <i
                ref={i === idx ? (el) => void (fill.current = el) : undefined}
                style={{ transform: i < idx || (reduced && i === idx) ? "scaleX(1)" : "scaleX(0)" }}
              />
            </span>
          ))}
        </div>
        <div className="tour-top">
          <span className="font-mono tour-label">
            {idx + 1} of {cards.length} · {c.label}
          </span>
          <button type="button" className="tour-x" onClick={close} aria-label="Close tour">
            <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden>
              <path d="M3 3l12 12M15 3L3 15" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
          </button>
        </div>
        <div
          className="tour-stage"
          onPointerDown={onDown}
          onPointerUp={onUp}
          onPointerCancel={() => {
            setHeld(false);
            down.current = null;
          }}
        >
          <div key={idx} className="tour-body" aria-live="polite">
            <h2 id="tour-title" className="font-display tour-title">{c.title}</h2>
            {c.stat && <p className="tabular tour-stat">{c.stat}</p>}
            {c.body && <p className="tour-text">{c.body}</p>}
            {c.extra}
            {idx === last && (
              <div className="tour-links">
                {LINKS.map((l) => (
                  <button
                    key={l.to}
                    type="button"
                    className="tour-link"
                    onClick={() => {
                      close();
                      navigate(l.to);
                    }}
                  >
                    {l.label} <span aria-hidden>→</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
        <div className="tour-foot">
          <button type="button" className="tour-nav" onClick={() => go(idx - 1)} disabled={idx === 0}>‹ Back</button>
          <span className="tour-small">{idx === last ? "" : "Hold to pause"}</span>
          <button type="button" className="tour-nav" onClick={() => go(idx + 1)} disabled={idx === last}>Next ›</button>
        </div>
      </div>
    </div>,
    document.body
  );
}
