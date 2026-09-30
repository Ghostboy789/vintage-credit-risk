import { useEffect, useRef, useState, type ReactNode } from "react";
import { m } from "framer-motion";
import { useReducedMotion } from "../lib/theme";
import { spotlightMove } from "./spotlight";
import { setPickerRequested, useAudience, usePickerRequested, type Audience } from "../lib/audience";

const CHOICES: { key: Audience; title: string; line: string }[] = [
  { key: "new", title: "New to credit risk", line: "Plain words first: follow one loan from start to loss." },
  { key: "pro", title: "Risk or model professional", line: "Straight to the crisis vintages, the validation and the methods." },
  { key: "hiring", title: "Hiring and skimming", line: "One screen of headline numbers, each linking to its evidence." },
  { key: "tour", title: "Quick look on my phone (60-second tour)", line: "Six cards, one idea each." },
];

// Tiny looping previews, one per view (CSS only, see .pv in index.css). Their resting state is the finished picture.
const PREVIEW: Record<Audience, ReactNode> = {
  new: (
    <>
      <path d="M6 32h52" stroke="var(--border)" strokeWidth="2" strokeLinecap="round" />
      {[6, 19, 32, 45, 58].map((x) => (
        <circle key={x} cx={x} cy="32" r="2.5" fill="var(--ink-3)" />
      ))}
      <circle className="pv-walker" cx="58" cy="32" r="5" fill="var(--accent)" />
    </>
  ),
  pro: (
    <>
      <path d="M4 52h56" stroke="var(--border)" strokeWidth="1.5" />
      <path className="pv-draw" pathLength="1" d="M4 50C14 50 18 46 26 40S38 12 44 12 52 36 60 44" fill="none" stroke="var(--accent)" strokeWidth="2.5" strokeLinecap="round" />
      <circle className="pv-peak" cx="44" cy="12" r="4" fill="var(--crisis)" />
    </>
  ),
  hiring: (
    <>
      {[
        [4, 6, 34, 22],
        [42, 6, 18, 22],
        [4, 32, 18, 26],
        [26, 32, 34, 26],
      ].map(([x, y, w, h], i) => (
        <rect key={i} className="pv-tile" style={{ ["--i" as string]: i }} x={x} y={y} width={w} height={h} rx="3" fill={i === 1 ? "var(--crisis)" : "var(--ink-3)"} fillOpacity={i === 1 ? 0.9 : 0.35} />
      ))}
    </>
  ),
  tour: (
    <>
      {[-14, 0, 14].map((deg, i) => (
        <rect key={deg} className="pv-card" style={{ ["--r" as string]: `${deg}deg`, ["--i" as string]: i }} x="22" y="8" width="20" height="46" rx="3" fill="var(--surface-2)" stroke={i === 1 ? "var(--accent)" : "var(--ink-3)"} strokeWidth="1.5" />
      ))}
    </>
  ),
};

/** "Who's reading?" strip under the hero headline. Shown until a choice is stored, and again on request. */
export function AudiencePicker() {
  const [audience, setAudience] = useAudience();
  const requested = usePickerRequested();
  const root = useRef<HTMLElement>(null);
  const visible = audience === null || requested;
  const reduced = useReducedMotion();
  // The card being chosen lends its outline to the header chip (shared layoutId), for the very first choice only.
  const [chosen, setChosen] = useState<Audience | null>(null);

  // Touch has no hover: play each preview once, gently, when the picker first scrolls into view.
  useEffect(() => {
    const el = root.current;
    if (!el || !visible || !window.matchMedia("(hover: none)").matches) return;
    const io = new IntersectionObserver(([e]) => {
      if (!e.isIntersecting) return;
      el.setAttribute("data-play", "");
      io.disconnect();
    }, { threshold: 0.5 });
    io.observe(el);
    return () => io.disconnect();
  }, [visible]);

  useEffect(() => {
    if (!requested) return;
    root.current?.scrollIntoView({ block: "center" });
    root.current?.querySelector<HTMLElement>("button")?.focus({ preventScroll: true });
  }, [requested]);

  if (!visible) return null;

  const choose = (a: Audience) => {
    // Only when the header chip is on screen (xl and up), and only the first time: give the shell a frame to render.
    if (audience === null && !reduced && a !== "tour" && window.matchMedia("(min-width: 1280px)").matches) {
      setChosen(a);
      requestAnimationFrame(() => requestAnimationFrame(() => commit(a)));
    } else commit(a);
  };
  const commit = (a: Audience) => {
    setAudience(a);
    setPickerRequested(false);
    if (a === "tour") window.dispatchEvent(new CustomEvent("vintage:tour"));
    // The picker unmounts on choice: move focus (and the reader) to the reordered content.
    else requestAnimationFrame(() => {
      const el = document.getElementById("overview-content");
      el?.focus({ preventScroll: true });
      el?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  };

  return (
    <section id="audience-picker" ref={root} aria-labelledby="audience-h" className="audience-picker mt-6 scroll-mt-24 md:mt-8 lg:mb-28">
      <h2 id="audience-h" className="font-mono text-xs uppercase tracking-wide" style={{ color: "var(--accent)" }}>
        Who's reading?
      </h2>
      <p className="mt-1 text-sm" style={{ color: "var(--ink-2)" }}>
        Pick one and the page reorders to suit. Everything stays one click away either way.
      </p>
      <ul className="mt-3 grid list-none grid-cols-1 gap-3 p-0 sm:grid-cols-2 lg:grid-cols-4">
        {CHOICES.map((c) => (
          <li key={c.key}>
            <button
              type="button"
              onClick={() => choose(c.key)}
              onPointerMove={spotlightMove}
              aria-pressed={audience === c.key}
              className="audience-choice spot relative flex h-full min-h-[88px] w-full flex-col gap-1 rounded-xl p-4 text-left"
              data-on={audience === c.key ? "" : undefined}
            >
              {chosen === c.key ? (
                <m.span layoutId="audience-shell" className="pv-shell" style={{ borderRadius: 12, borderColor: "var(--accent)" }} />
              ) : (
                <span className="pv-shell" />
              )}
              <svg className="pv" viewBox="0 0 64 64" width="56" height="56" aria-hidden>
                {PREVIEW[c.key]}
              </svg>
              <span className="text-base font-semibold leading-tight" style={{ color: "var(--ink)" }}>
                {c.title}
              </span>
              <span className="text-sm leading-snug" style={{ color: "var(--ink-2)" }}>
                {c.line}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
