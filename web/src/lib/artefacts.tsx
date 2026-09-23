import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import type {
  PortfolioArtefact,
  PdModelsArtefact,
  LgdEadArtefact,
  EclArtefact,
  CapitalArtefact,
  MonitoringArtefact,
} from "./types";

export interface Artefacts {
  portfolio: PortfolioArtefact;
  pd_models: PdModelsArtefact;
  lgd_ead: LgdEadArtefact;
  ecl: EclArtefact;
  capital: CapitalArtefact;
  monitoring: MonitoringArtefact;
}

type State =
  | { status: "loading" }
  | { status: "error"; error: string }
  | { status: "ready"; data: Artefacts; anySynthetic: boolean };

const ArtefactsContext = createContext<State>({ status: "loading" });

const NAMES = ["portfolio", "pd_models", "lgd_ead", "ecl", "capital", "monitoring"] as const;

export function ArtefactsProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    Promise.all(NAMES.map((n) => fetch(`/artefacts/${n}.json`).then((r) => {
      if (!r.ok) throw new Error(`${n}.json: ${r.status}`);
      return r.json();
    })))
      .then(([portfolio, pd_models, lgd_ead, ecl, capital, monitoring]) => {
        if (cancelled) return;
        const data = { portfolio, pd_models, lgd_ead, ecl, capital, monitoring } as Artefacts;
        const anySynthetic = NAMES.some((n) => (data[n] as { synthetic?: boolean }).synthetic);
        setState({ status: "ready", data, anySynthetic });
      })
      .catch((err) => {
        if (!cancelled) setState({ status: "error", error: String(err) });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return <ArtefactsContext.Provider value={state}>{children}</ArtefactsContext.Provider>;
}

export function useArtefacts() {
  return useContext(ArtefactsContext);
}
