import { useEffect, useRef } from "react";
import { setPickerRequested, useAudience, usePickerRequested, type Audience } from "../lib/audience";

const CHOICES: { key: Audience; title: string; line: string }[] = [
  { key: "new", title: "New to credit risk", line: "Plain words first: follow one loan from start to loss." },
  { key: "pro", title: "Risk or model professional", line: "Straight to the crisis vintages, the validation and the methods." },
  { key: "hiring", title: "Hiring and skimming", line: "One screen of headline numbers, each linking to its evidence." },
  { key: "tour", title: "Quick look on my phone (60-second tour)", line: "Six cards, one idea each." },
];

/** "Who's reading?" strip under the hero headline. Shown until a choice is stored, and again on request. */
export function AudiencePicker() {
  const [audience, setAudience] = useAudience();
  const requested = usePickerRequested();
  const root = useRef<HTMLElement>(null);
  const visible = audience === null || requested;

  useEffect(() => {
    if (!requested) return;
    root.current?.scrollIntoView({ block: "center" });
    root.current?.querySelector<HTMLElement>("button")?.focus({ preventScroll: true });
  }, [requested]);

  if (!visible) return null;

  const choose = (a: Audience) => {
    setAudience(a);
    setPickerRequested(false);
    if (a === "tour") window.dispatchEvent(new CustomEvent("vintage:tour"));
  };

  return (
    <section id="audience-picker" ref={root} aria-labelledby="audience-h" className="audience-picker mt-6 scroll-mt-24 md:mt-8">
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
              aria-pressed={audience === c.key}
              className="audience-choice flex h-full min-h-[88px] w-full flex-col gap-1 rounded-xl border p-4 text-left"
              style={{ borderColor: audience === c.key ? "var(--accent)" : "var(--border)", background: "var(--surface)" }}
            >
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
