import { useLocation } from "react-router-dom";
import type { Artefacts } from "../lib/artefacts";

// Design brief section 4, "Synthetic guard": undismissable, striped, pinned under the header.
// Shown on every page that draws from an artefact still on synthetic fixture data, naming which.
const ALL = ["portfolio", "pd_models", "lgd_ead", "ecl", "capital", "monitoring"] as const;
const PAGE_ARTEFACTS: Record<string, readonly (keyof Artefacts)[]> = {
  "/": ALL,
  "/vintages": ["portfolio"],
  "/roll-rates": ["portfolio"],
  "/scorecard": ["pd_models", "monitoring"],
  "/ecl": ["ecl", "lgd_ead"],
  "/capital": ["capital"],
  "/methods": ALL,
  "/credits": [],
  "/powerbi": [],
};

const NAMES: Record<string, string> = {
  portfolio: "portfolio",
  pd_models: "scorecard",
  lgd_ead: "LGD/EAD",
  ecl: "IFRS 9 ECL",
  capital: "capital",
  monitoring: "monitoring",
};

export function SyntheticBanner({ data }: { data: Artefacts }) {
  const { pathname } = useLocation();
  const used = PAGE_ARTEFACTS[pathname] ?? ALL;
  const synthetic = used.filter((n) => (data[n] as { synthetic?: boolean }).synthetic);
  if (!synthetic.length) return null;
  const all = synthetic.length === used.length;
  return (
    <div
      role="alert"
      className="sticky top-14 z-30 flex items-center justify-center px-4 py-2 text-center text-sm font-semibold md:top-16"
      style={{
        color: "#1a1200",
        background:
          "repeating-linear-gradient(45deg, var(--amber), var(--amber) 10px, color-mix(in srgb, var(--amber) 70%, black) 10px, color-mix(in srgb, var(--amber) 70%, black) 20px)",
      }}
    >
      {all
        ? "SYNTHETIC FIXTURE DATA — not real results"
        : `SYNTHETIC FIXTURE DATA in the ${synthetic.map((n) => NAMES[n]).join(", ")} figures on this page — not real results`}
    </div>
  );
}
