import { AnimatePresence, m } from "framer-motion";
import type { Estimate } from "../lib/types";
import { fmtInt } from "../lib/format";

// Skiper101 "custom tooltip" adapted: the single tooltip used by every chart, fixed content order.
export function ChartTooltip({
  x,
  y,
  label,
  estimate,
  fmt,
  visible,
}: {
  x: number;
  y: number;
  label: string;
  estimate: Estimate;
  fmt: (v: number) => string;
  visible: boolean;
}) {
  return (
    <AnimatePresence>
      {visible && (
        <m.div
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.16 }}
          className="pointer-events-none absolute z-10 max-w-[240px] rounded-md border p-2 text-xs"
          style={{
            left: x,
            top: y,
            background: "var(--surface-2)",
            borderColor: "var(--border)",
            color: "var(--ink)",
            transform: "translate(-50%, -110%)",
          }}
          role="status"
        >
          <div style={{ color: "var(--ink-2)" }}>{label}</div>
          <div className="tabular font-semibold">{estimate.value === null ? "—" : fmt(estimate.value)}</div>
          {estimate.ci_low !== null && estimate.ci_high !== null && (
            <div className="tabular" style={{ color: "var(--ink-2)" }}>
              [{fmt(estimate.ci_low)} – {fmt(estimate.ci_high)}]
            </div>
          )}
          <div className="font-mono" style={{ color: "var(--ink-3)" }}>
            n = {fmtInt(estimate.n)} · {estimate.ci_method}
          </div>
        </m.div>
      )}
    </AnimatePresence>
  );
}
