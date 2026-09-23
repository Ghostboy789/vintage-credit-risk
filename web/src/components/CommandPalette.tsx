import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { useArtefacts } from "../lib/artefacts";

// Rebuild of Skiper92 "Vercel Command Search" (Pro tier — rebuilt from the brief's spec, no
// copied source). Plain case-insensitive substring match over a small in-memory index; no fuzzy
// search library. Index built once on load from the loaded artefacts, not a separate
// build step — equivalent result at this data size, simpler pipeline.
interface Item {
  group: "Pages" | "Vintages" | "Rules" | "Grades";
  label: string;
  meta?: string;
  to: string;
}

const PAGES: Item[] = [
  { group: "Pages", label: "Overview", to: "/" },
  { group: "Pages", label: "Vintages", to: "/vintages" },
  { group: "Pages", label: "Roll rates", to: "/roll-rates" },
  { group: "Pages", label: "Scorecard", to: "/scorecard" },
  { group: "Pages", label: "IFRS 9 ECL", to: "/ecl" },
  { group: "Pages", label: "Capital", to: "/capital" },
  { group: "Pages", label: "Methods & limits", to: "/methods" },
];

export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [query, setQuery] = useState("");
  const [highlight, setHighlight] = useState(0);
  const navigate = useNavigate();
  const state = useArtefacts();

  const items = useMemo<Item[]>(() => {
    const out = [...PAGES];
    if (state.status === "ready") {
      const years = new Set(state.data.portfolio.vintage_curves_annual.map((r) => r.vintage_year));
      for (const y of years) out.push({ group: "Vintages", label: String(y), meta: `${y}Q1–Q4`, to: `/vintages?year=${y}` });
      for (const g of state.data.pd_models.grades) out.push({ group: "Grades", label: `Grade ${g.grade}`, to: `/scorecard#grade-${g.grade}` });
      const allRules = [
        ...(state.data.portfolio.pass_rules ?? []),
        ...(state.data.pd_models.pass_rules ?? []),
      ] as { rule_id?: string; id?: string; result: string }[];
      for (const r of allRules) {
        const id = r.rule_id ?? r.id;
        if (id) out.push({ group: "Rules", label: id, meta: r.result, to: `/methods#${id}` });
      }
    }
    return out;
  }, [state]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return items.slice(0, 20);
    return items.filter((i) => i.label.toLowerCase().includes(q) || i.meta?.toLowerCase().includes(q)).slice(0, 30);
  }, [items, query]);

  useEffect(() => {
    setHighlight(0);
  }, [query]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setHighlight((h) => Math.min(filtered.length - 1, h + 1));
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setHighlight((h) => Math.max(0, h - 1));
      }
      if (e.key === "Enter" && filtered[highlight]) {
        navigate(filtered[highlight].to);
        onClose();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, filtered, highlight, navigate, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-50 flex justify-center" style={{ paddingTop: "18vh" }}>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0"
            style={{ background: "rgba(0,0,0,.5)" }}
            onClick={onClose}
          />
          <motion.div
            role="dialog"
            aria-label="Search"
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.98 }}
            transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
            className="relative z-10 h-fit w-full rounded-xl border"
            style={{ maxWidth: 640, margin: "0 16px", background: "var(--surface-2)", borderColor: "var(--border)" }}
          >
            <div className="flex h-[52px] items-center gap-2 border-b px-4" style={{ borderColor: "var(--border)" }}>
              <span aria-hidden>⌕</span>
              <input
                autoFocus
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search pages, vintage years, rule IDs, grades…"
                className="h-full flex-1 bg-transparent outline-none"
                style={{ color: "var(--ink)" }}
              />
              <kbd className="font-mono rounded border px-1.5 py-0.5 text-xs" style={{ borderColor: "var(--border)", color: "var(--ink-3)" }}>
                Esc
              </kbd>
            </div>
            <div className="max-h-[360px] overflow-y-auto p-2">
              {(["Pages", "Vintages", "Rules", "Grades"] as const).map((group) => {
                const rows = filtered.filter((i) => i.group === group);
                if (!rows.length) return null;
                return (
                  <div key={group} className="mb-2">
                    <div className="px-2 py-1 text-[11px] uppercase" style={{ color: "var(--ink-3)" }}>
                      {group}
                    </div>
                    {rows.map((item) => {
                      const idx = filtered.indexOf(item);
                      return (
                        <button
                          key={`${item.group}-${item.label}`}
                          onClick={() => {
                            navigate(item.to);
                            onClose();
                          }}
                          className="relative flex h-10 w-full items-center justify-between rounded px-2 text-left"
                          style={{
                            background: idx === highlight ? "color-mix(in srgb, var(--accent) 12%, transparent)" : "transparent",
                            borderLeft: idx === highlight ? "2px solid var(--accent)" : "2px solid transparent",
                          }}
                        >
                          <span>{item.label}</span>
                          {item.meta && (
                            <span className="font-mono text-xs" style={{ color: "var(--ink-3)" }}>
                              {item.meta}
                            </span>
                          )}
                        </button>
                      );
                    })}
                  </div>
                );
              })}
              {filtered.length === 0 && (
                <div className="p-4 text-sm" style={{ color: "var(--ink-3)" }}>
                  No matches.
                </div>
              )}
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
