import { useEffect, useState } from "react";
import type { Estimate } from "../lib/types";

// Counts from the interval's ci_low up to the estimate (never from 0) once `run` is true.
// Without an interval it renders the final value and the parent fades it in. Ends on the exact value.
export function CountUp({ estimate, fmt, run, reduced }: { estimate: Estimate; fmt: (v: number) => string; run: boolean; reduced: boolean }) {
  const to = estimate.value ?? 0;
  const from = estimate.ci_low ?? to;
  const [v, setV] = useState(reduced || from === to ? to : from);
  useEffect(() => {
    if (reduced || from === to) return setV(to);
    if (!run) return;
    const t0 = performance.now();
    let raf = requestAnimationFrame(function tick(now) {
      const t = Math.min(1, (now - t0) / 800);
      setV(t < 1 ? from + (to - from) * (1 - Math.pow(1 - t, 3)) : to);
      if (t < 1) raf = requestAnimationFrame(tick);
    });
    return () => cancelAnimationFrame(raf);
  }, [run, reduced, from, to]);
  return <>{fmt(v)}</>;
}
