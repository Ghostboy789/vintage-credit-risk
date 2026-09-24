import { m } from "framer-motion";
import { ResultBadge } from "./ResultBadge";
import { RULE_NAMES, sortRules, type Rule } from "../lib/rules";
import { useReducedMotion } from "../lib/theme";

const TONE: Record<string, string> = {
  PASS: "var(--pass)",
  FAIL: "var(--fail)",
  AMBER: "var(--amber)",
};

// Compact scoreboard of pre-registered rules: plain name, rule id, result badge (icon + text, so
// colour is never the only signal). FAIL rows sort first and are never collapsed.
export function Scoreboard({ rules, showEvidence = false }: { rules: Rule[]; showEvidence?: boolean }) {
  const reduced = useReducedMotion();
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
      <ul className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {sorted.map((r, i) => (
          <m.li
            key={`${r.artefact}-${r.rule_id}`}
            initial={reduced ? false : { opacity: 0, y: 6 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.3 }}
            transition={{ duration: 0.32, delay: Math.min(i, 12) * 0.03, ease: [0.16, 1, 0.3, 1] }}
            className="flex min-h-[64px] items-start justify-between gap-3 rounded-lg border p-3"
            style={{
              borderColor: "var(--border)",
              background: "var(--surface)",
              boxShadow: `inset 3px 0 0 ${TONE[r.result] ?? "var(--neutral)"}`,
            }}
          >
            <div className="min-w-0">
              <div className="text-sm leading-snug" style={{ color: "var(--ink)" }}>
                {RULE_NAMES[r.rule_id] ?? r.rule_id}
              </div>
              <div className="font-mono mt-0.5 text-xs" style={{ color: "var(--ink-3)" }}>
                {r.rule_id}
                {showEvidence && r.evidence ? ` · ${r.evidence}` : ""}
              </div>
            </div>
            <ResultBadge result={r.result} />
          </m.li>
        ))}
      </ul>
    </div>
  );
}
