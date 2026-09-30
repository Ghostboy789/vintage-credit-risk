import { lazy, Suspense, useEffect, useState } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { LazyMotion } from "framer-motion";
import { ArtefactsProvider, useArtefacts } from "./lib/artefacts";
import { ThemeProvider } from "./lib/theme";
import { Header } from "./components/Header";
import { Footer } from "./components/Footer";
import { NextPage } from "./components/NextPage";
import { SyntheticBanner } from "./components/SyntheticBanner";
import { NotReady } from "./pages/NotReady";
import { Overview } from "./pages/Overview";

// Below-the-fold pages are route chunks (perf budget: keep the initial bundle to the hero route).
const loadFeatures = () => import("./lib/motion-features").then((mod) => mod.default);

const Vintages = lazy(() => import("./pages/Vintages").then((m) => ({ default: m.Vintages })));
const RollRates = lazy(() => import("./pages/RollRates").then((m) => ({ default: m.RollRates })));
const Scorecard = lazy(() => import("./pages/Scorecard").then((m) => ({ default: m.Scorecard })));
const Ecl = lazy(() => import("./pages/Ecl").then((m) => ({ default: m.Ecl })));
const Capital = lazy(() => import("./pages/Capital").then((m) => ({ default: m.Capital })));
const Methods = lazy(() => import("./pages/Methods").then((m) => ({ default: m.Methods })));
const PowerBi = lazy(() => import("./pages/PowerBi").then((m) => ({ default: m.PowerBi })));
// The tour is its own chunk, fetched the first time someone opens it.
const StoryTour = lazy(() => import("./components/StoryTour").then((m) => ({ default: m.StoryTour })));
const Credits = lazy(() => import("./pages/Credits").then((m) => ({ default: m.Credits })));

function TourGate({ data }: { data: Parameters<typeof Overview>[0]["data"] }) {
  const [wanted, setWanted] = useState(() => window.location.hash === "#tour");
  useEffect(() => {
    if (wanted) return;
    const want = () => setWanted(true);
    const onHash = () => window.location.hash === "#tour" && want();
    window.addEventListener("vintage:tour", want);
    window.addEventListener("hashchange", onHash);
    return () => {
      window.removeEventListener("vintage:tour", want);
      window.removeEventListener("hashchange", onHash);
    };
  }, [wanted]);
  if (!wanted) return null;
  return (
    <Suspense fallback={null}>
      <StoryTour data={data} openOnMount />
    </Suspense>
  );
}

function Shell() {
  const state = useArtefacts();

  return (
    <>
      <Header />
      {state.status === "ready" && <SyntheticBanner data={state.data} />}
      <main id="main" tabIndex={-1} style={{ outline: "none" }}>
        {state.status === "loading" && (
          <div className="px-8 py-24 text-center" style={{ color: "var(--ink-2)" }}>
            Loading…
          </div>
        )}
        {state.status === "error" && <NotReady error={state.error} />}
        {state.status === "ready" && (
          <Suspense fallback={<div className="px-8 py-24 text-center" style={{ color: "var(--ink-2)" }}>Loading…</div>}>
            <Routes>
              <Route path="/" element={<Overview data={state.data} />} />
              <Route path="/vintages" element={<Vintages data={state.data} />} />
              <Route path="/roll-rates" element={<RollRates data={state.data} />} />
              <Route path="/scorecard" element={<Scorecard data={state.data} />} />
              <Route path="/ecl" element={<Ecl data={state.data} />} />
              <Route path="/capital" element={<Capital data={state.data} />} />
              <Route path="/methods" element={<Methods data={state.data} />} />
              <Route path="/powerbi" element={<PowerBi />} />
              <Route path="/credits" element={<Credits />} />
            </Routes>
          </Suspense>
        )}
      </main>
      {state.status === "ready" && <NextPage />}
      {state.status === "ready" && <TourGate data={state.data} />}
      <Footer />
    </>
  );
}

export default function App() {
  return (
    <LazyMotion features={loadFeatures} strict>
    <ThemeProvider>
      <ArtefactsProvider>
        <BrowserRouter>
          <Shell />
        </BrowserRouter>
      </ArtefactsProvider>
    </ThemeProvider>
    </LazyMotion>
  );
}
