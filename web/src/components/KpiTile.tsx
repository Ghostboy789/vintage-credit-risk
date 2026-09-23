import { useEffect, useRef, useState } from "react";
import { motion, useReducedMotion as useFramerReducedMotion } from "framer-motion";
import type { Estimate } from "../lib/types";
import { fmtInt, fmtPct } from "../lib/format";

// Skiper37 "animated number" adapted: counts from ci_low to value (never from 0), so the estimate
// visibly settles inside its own interval. Interval text/bar/n are static and visible from frame 0.
export function KpiTile({
  label,
  estimate,
  isPct = true,
  unit = "",
}: {
  label: string;
  estimate: Estimate;
  isPct?: boolean;
  unit?: string;
}) {
  const reduced = useFramerReducedMotion();
  const [display, setDisplay] = useState(estimate.value ?? 0);
  const ref = useRef<HTMLDivElement>(null);
  const fmt = (v: number) => (isPct ? fmtPct(v) : `${fmtInt(v)}${unit}`);

  useEffect(() => {
    if (estimate.value === null) return;
    const from = estimate.ci_low ?? estimate.value;
    const to = estimate.value;
    if (reduced || from === to) {
      setDisplay(to);
      return;
    }
    const start = performance.now();
    const duration = 700;
    let raf = 0;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      setDisplay(from + (to - from) * eased);
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [estimate.value, estimate.ci_low, reduced]);

  const noEstimate = estimate.ci_method.startsWith("none:");
  const track = estimate.value !== null && estimate.ci_low !== null && estimate.ci_high !== null;
  const pct01 = (v: number) => {
    if (!track) return 0;
    const lo = estimate.ci_low as number;
    const hi = estimate.ci_high as number;
    if (hi === lo) return 0.5;
    return Math.min(1, Math.max(0, (v - lo) / (hi - lo)));
  };

  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, y: 8 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.4 }}
      transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
      className="rounded-lg border p-4"
      style={{ borderColor: "var(--border)", background: "var(--surface)" }}
    >
      <div className="text-[13px]" style={{ color: "var(--ink-2)" }}>
        {label}
      </div>
      <div className="tabular font-semibold" style={{ fontSize: "clamp(28px,4vw,48px)", color: "var(--ink)" }}>
        {estimate.value === null ? "—" : fmt(display)}
      </div>
      {noEstimate ? (
        <div className="mt-1 text-sm" style={{ color: "var(--ink-2)" }}>
          {estimate.ci_method.replace("none: ", "")}
        </div>
      ) : (
        <>
          <div className="mt-1 text-sm" style={{ color: "var(--ink-2)" }}>
            95% CI {fmt(estimate.ci_low ?? 0)} – {fmt(estimate.ci_high ?? 0)}
          </div>
          <div className="relative mt-2 h-1.5 w-[120px] rounded-full" style={{ background: "var(--ink-muted)" }}>
            <div
              className="absolute inset-y-0 rounded-full"
              style={{
                left: `${pct01(estimate.ci_low ?? 0) * 100}%`,
                right: `${(1 - pct01(estimate.ci_high ?? 1)) * 100}%`,
                background: "var(--ink-2)",
              }}
            />
            <div
              className="absolute top-1/2 h-3 w-0.5 -translate-y-1/2"
              style={{ left: `${pct01(estimate.value ?? 0) * 100}%`, background: "var(--ink)" }}
            />
          </div>
        </>
      )}
      <div className="font-mono mt-2 text-xs" style={{ color: "var(--ink-3)" }}>
        n = {fmtInt(estimate.n)} loans{noEstimate ? "" : ` · ${estimate.ci_method}`}
      </div>
    </motion.div>
  );
}
