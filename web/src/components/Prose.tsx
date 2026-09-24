import { m } from "framer-motion";
import type { ReactNode } from "react";

// Skiper87 "Scroll with fade": the one generic reveal, reserved for prose blocks only. Charts use
// their own data-meaningful entrances instead (Ridge/VintageCurveChart's pathLength, RollRateHeatmap's
// row fill).
export function Prose({ children }: { children: ReactNode }) {
  return (
    <m.div
      initial={{ opacity: 0, y: 8 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.3 }}
      transition={{ duration: 0.4, ease: "easeOut" }}
    >
      {children}
    </m.div>
  );
}
