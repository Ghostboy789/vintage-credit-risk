import { useEffect, useId, useRef, useState } from "react";
import { m } from "framer-motion";
import type { CalcResult } from "../lib/calculator";
import { fmtPct } from "../lib/format";
import { useReducedMotion } from "../lib/theme";

// Calculator result pill for phones and tablets, sticky at the bottom (the "Dynamic Island"
// pattern from skiper-ui.com, skiper2). One element morphs between the collapsed pill and the
// full result card with a spring; reduced motion swaps the content with no morph.
export function ResultIsland({ result }: { result: CalcResult }) {
  const reduced = useReducedMotion();
  const [open, setOpen] = useState(false);
  const id = useId();
  const pill = useRef<HTMLButtonElement>(null);
  const close = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    close.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const shut = () => {
    setOpen(false);
    requestAnimationFrame(() => pill.current?.focus());
  };

  return (
    <div className="fixed inset-x-0 bottom-4 z-40 flex justify-center px-4 lg:hidden">
      <m.div
        layout={!reduced}
        transition={{ type: "spring", stiffness: 420, damping: 32 }}
        style={{
          borderRadius: open ? 20 : 999,
          background: "var(--ink)",
          color: "var(--bg)",
          width: open ? "min(420px, 100%)" : "auto",
          maxWidth: "100%",
        }}
      >
        {open ? (
          <div id={id} role="region" aria-label="Calculator result" className="relative p-5">
            <button
              ref={close}
              type="button"
              aria-label="Close result"
              onClick={shut}
              className="absolute right-2 top-2 flex h-11 w-11 items-center justify-center rounded-full"
              style={{ color: "var(--bg)" }}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
                <path d="M6 6l12 12M18 6L6 18" />
              </svg>
            </button>
            <div className="flex items-end gap-5">
              <div>
                <div className="text-xs opacity-70">Score</div>
                <div className="tabular text-4xl font-semibold leading-none">{result.score}</div>
              </div>
              <div>
                <div className="text-xs opacity-70">Grade</div>
                <div className="font-display text-3xl leading-none">{result.grade}</div>
              </div>
              <div>
                <div className="text-xs opacity-70">12-month PD</div>
                <div className="tabular text-2xl font-semibold leading-none">{fmtPct(result.pd12m)}</div>
              </div>
            </div>
            <p className="mt-2 text-xs opacity-70">{result.pdLabel}</p>
            <ol className="mt-3 space-y-1 text-sm">
              {result.reasonCodes.length === 0 && <li>No shortfall: every feature is in its best bin.</li>}
              {result.reasonCodes.map((c, i) => (
                <li key={c.feature}>
                  {i + 1}. {c.feature} <span className="font-mono text-xs">{c.bin.is_missing_bin ? "Unknown" : c.bin.bin}</span>: −{c.shortfall} points vs
                  best bin
                </li>
              ))}
            </ol>
          </div>
        ) : (
          <button
            ref={pill}
            type="button"
            aria-expanded={false}
            aria-controls={id}
            onClick={() => setOpen(true)}
            className="tabular h-12 whitespace-nowrap px-5 text-sm font-semibold"
          >
            Score {result.score} · Grade {result.grade} · PD {fmtPct(result.pd12m)}
          </button>
        )}
      </m.div>
    </div>
  );
}
