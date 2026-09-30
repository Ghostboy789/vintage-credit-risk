import { useId, useState } from "react";
import { m } from "framer-motion";
import { ResultBadge } from "./ResultBadge";
import { RULE_NAMES, sortRules, type Rule } from "../lib/rules";
import { useReducedMotion } from "../lib/theme";

const TONE: Record<string, string> = {
  PASS: "var(--pass)",
  FAIL: "var(--fail)",
  AMBER: "var(--amber)",
};

const ARTEFACT_TAG: Record<string, string> = {
  portfolio: "Portfolio",
  pd_models: "PD model",
  lgd_ead: "LGD and EAD",
  ecl: "ECL",
  capital: "Capital",
  monitoring: "Monitoring",
};

// One rule: plain name, verdict badge, rule id (and optionally artefact) as small tags, and the raw
// evidence string behind an expand button so it never crowds the card.
export function RuleCard({ rule: r, showEvidence = false, showArtefact = false }: { rule: Rule; showEvidence?: boolean; showArtefact?: boolean }) {
  const [open, setOpen] = useState(false);
  const panel = useId();
  const tag = "font-mono rounded border px-1.5 text-[11px] leading-[18px]";
  return (
    <div
      className="rule-card rounded-lg border p-3"
      style={{
        borderColor: "var(--border)",
        background: "var(--surface)",
        boxShadow: `inset 3px 0 0 ${TONE[r.result] ?? "var(--neutral)"}`,
      }}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-sm leading-snug" style={{ color: "var(--ink)" }}>
            {RULE_NAMES[r.rule_id] ?? r.rule_id}
          </div>
          <div className="mt-1.5 flex flex-wrap gap-1.5" style={{ color: "var(--ink-3)" }}>
            <span className={tag} style={{ borderColor: "var(--border)" }}>
              {r.rule_id}
            </span>
            {showArtefact && (
              <span className={tag} style={{ borderColor: "var(--border)" }}>
                {ARTEFACT_TAG[r.artefact] ?? r.artefact}
              </span>
            )}
          </div>
        </div>
        <ResultBadge result={r.result} />
      </div>
      {showEvidence && r.evidence && (
        <>
          <button
            type="button"
            aria-expanded={open}
            aria-controls={panel}
            onClick={() => setOpen((o) => !o)}
            className="evidence-btn -mb-1 mt-1 inline-flex items-center gap-1 text-xs"
            style={{ color: "var(--accent)" }}
          >
            <span aria-hidden className="inline-block w-3 transition-transform" style={{ transform: open ? "rotate(90deg)" : "none" }}>
              ›
            </span>
            {open ? "Hide evidence" : "Show evidence"}
          </button>
          {open && (
            <p id={panel} className="font-mono mt-1 break-words text-xs leading-relaxed" style={{ color: "var(--ink-2)" }}>
              {r.evidence}
            </p>
          )}
        </>
      )}
    </div>
  );
}

// Compact scoreboard of pre-registered rules. FAIL rows sort first and are never collapsed.
// With `collapseOnPhone`, phones show only FAIL and AMBER rows until the reader asks for the rest.
export function Scoreboard({ rules, showEvidence = false, collapseOnPhone = false }: { rules: Rule[]; showEvidence?: boolean; collapseOnPhone?: boolean }) {
  const reduced = useReducedMotion();
  const [all, setAll] = useState(false);
  const sorted = sortRules(rules);
  const counts = sorted.reduce<Record<string, number>>((acc, r) => ({ ...acc, [r.result]: (acc[r.result] ?? 0) + 1 }), {});

  return (
    <div>
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm" aria-label="Results by count">
        {Object.entries(counts).map(([result, n]) => (
          <span key={result} className="inline-flex items-center gap-2">
            <ResultBadge result={result} />
            <span className="tabular font-semibold">{n}</span>
          </span>
        ))}
      </div>
      <ul className="mt-4 grid grid-cols-1 items-start gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {sorted.map((r, i) => (
          <m.li
            key={`${r.artefact}-${r.rule_id}`}
            className={collapseOnPhone && !all && r.result === "PASS" ? "hidden sm:block" : undefined}
            initial={reduced ? false : { opacity: 0, y: 6 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.3 }}
            transition={{ duration: 0.32, delay: Math.min(i, 12) * 0.03, ease: [0.16, 1, 0.3, 1] }}
          >
            <RuleCard rule={r} showEvidence={showEvidence} />
          </m.li>
        ))}
      </ul>
      {collapseOnPhone && !all && counts.PASS > 0 && (
        <button
          type="button"
          onClick={() => setAll(true)}
          className="mt-3 min-h-[44px] w-full rounded-lg border px-4 text-sm sm:hidden"
          style={{ borderColor: "var(--border)", color: "var(--ink)", background: "var(--surface)" }}
        >
          Show all {sorted.length} rules ({counts.PASS} passed)
        </button>
      )}
    </div>
  );
}
