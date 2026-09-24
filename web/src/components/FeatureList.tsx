import { useState, useMemo, useId } from "react";
import { AnimatePresence, m } from "framer-motion";
import type { PointsBin, Estimate } from "../lib/types";
import { fmtPct, fmtInt } from "../lib/format";
import { useReducedMotion } from "../lib/theme";

export function FeatureList({
  features,
  bins,
}: {
  features: { feature: string; iv: Estimate; selected: boolean; drop_reason: string | null }[];
  bins: PointsBin[];
}) {
  const reduced = useReducedMotion();
  const [openFeature, setOpenFeature] = useState<string | null>(null);
  const hoverSupported = useMemo(
    () => typeof window !== "undefined" && window.matchMedia("(hover: hover)").matches,
    []
  );

  const selectedFeatures = useMemo(
    () =>
      features
        .filter((f) => f.selected)
        .sort((a, b) => (b.iv.value ?? 0) - (a.iv.value ?? 0)),
    [features]
  );

  const maxIv = useMemo(
    () => Math.max(0.001, ...selectedFeatures.map((f) => f.iv.value ?? 0)),
    [selectedFeatures]
  );

  const featureBins = useMemo(() => {
    const map = new Map<string, PointsBin[]>();
    for (const b of bins) {
      if (!map.has(b.feature)) map.set(b.feature, []);
      map.get(b.feature)!.push(b);
    }
    return map;
  }, [bins]);

  const panelId = useId();

  return (
    <div className="space-y-2">
      {selectedFeatures.map((f) => {
        const isOpen = openFeature === f.feature;
        const thisPanelId = `${panelId}-${f.feature}`;
        const thisBins = featureBins.get(f.feature) ?? [];
        const maxWoe = Math.max(
          0.001,
          ...thisBins.map((b) => Math.abs(b.woe))
        );

        return (
          <div
            key={f.feature}
            onMouseEnter={hoverSupported ? () => setOpenFeature(f.feature) : undefined}
            onMouseLeave={hoverSupported ? () => setOpenFeature(null) : undefined}
          >
            <button
              id={`${thisPanelId}-label`}
              type="button"
              aria-expanded={isOpen}
              aria-controls={thisPanelId}
              onClick={() => setOpenFeature((prev) => (prev === f.feature ? null : f.feature))}
              className="w-full min-h-[48px] rounded-lg border px-4 py-3 text-left transition-colors"
              style={{
                borderColor: "var(--border)",
                background: "var(--surface)",
              }}
            >
              <div className="flex items-center gap-3">
                <span className="font-mono">{f.feature}</span>
                <div className="flex-1 max-w-[120px] h-2 rounded overflow-hidden" style={{ background: "var(--ink-muted)" }}>
                  <div
                    className="h-full"
                    style={{
                      width: `${((f.iv.value ?? 0) / maxIv) * 100}%`,
                      background: "var(--accent)",
                    }}
                  />
                </div>
                <span className="font-mono text-xs" style={{ color: "var(--ink-2)" }}>
                  IV {f.iv.value === null ? "—" : f.iv.value.toFixed(2)} {f.iv.ci_low !== null && f.iv.ci_high !== null ? `[${f.iv.ci_low.toFixed(2)}–${f.iv.ci_high.toFixed(2)}]` : ""}
                </span>
              </div>
            </button>

            <AnimatePresence initial={false}>
              {isOpen && (
                <m.div
                  id={thisPanelId}
                  role="region"
                  aria-labelledby={`${thisPanelId}-label`}
                  initial={reduced ? false : { height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={reduced ? undefined : { height: 0, opacity: 0 }}
                  transition={{ duration: 0.32, ease: [0.16, 1, 0.3, 1] }}
                  style={{ overflow: "hidden" }}
                >
                  <div className="mt-3 grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 240px), 1fr))" }}>
                    {thisBins.map((bin) => (
                      <div key={bin.bin} className="space-y-2 p-3 rounded border" style={{ borderColor: "var(--border)", background: "var(--surface)" }}>
                        <div className="flex items-center gap-2">
                          <span className="font-mono">{bin.is_missing_bin ? "Unknown" : bin.bin}</span>
                        </div>
                        <div className="flex items-center gap-2">
                        <div className="relative h-3 flex-1" style={{ background: "var(--surface-2)", borderRadius: 4 }}>
                          <div
                            className="absolute top-0 bottom-0 w-px"
                            style={{ left: "50%", background: "var(--ink-3)" }}
                          />
                          <div
                            className="absolute top-0 bottom-0"
                            style={{
                              left: bin.woe >= 0 ? "50%" : `calc(50% - ${(Math.abs(bin.woe) / maxWoe) * 50}%)`,
                              width: bin.woe >= 0 ? `${(Math.abs(bin.woe) / maxWoe) * 50}%` : `${(Math.abs(bin.woe) / maxWoe) * 50}%`,
                              background: bin.woe >= 0 ? "var(--pass)" : "var(--fail)",
                              borderRadius: bin.woe >= 0 ? "0 4px 4px 0" : "4px 0 0 4px",
                            }}
                          />
                        </div>
                          <span className="font-mono w-16 text-right text-xs" style={{ color: "var(--ink-2)" }}>
                            WoE {bin.woe.toFixed(2)}
                          </span>
                        </div>
                        <div className="font-mono tabular">{bin.points} pts</div>
                        <div className="text-xs" style={{ color: "var(--ink-3)" }}>
                          {bin.default_rate_dev_train.value === null
                            ? "—"
                            : `Default rate ${fmtPct(bin.default_rate_dev_train.value)} [${bin.default_rate_dev_train.ci_low === null ? "—" : fmtPct(bin.default_rate_dev_train.ci_low)}–${bin.default_rate_dev_train.ci_high === null ? "—" : fmtPct(bin.default_rate_dev_train.ci_high)}]`}
                          {" · "}n = {fmtInt(bin.default_rate_dev_train.n)}
                        </div>
                      </div>
                    ))}
                  </div>
                </m.div>
              )}
            </AnimatePresence>
          </div>
        );
      })}

      {selectedFeatures.length > 0 && (
        <p className="mt-4 text-xs font-mono" style={{ color: "var(--ink-3)" }}>
          IV and default rates on the development-train sample · {selectedFeatures[0].iv.ci_method}
        </p>
      )}
    </div>
  );
}