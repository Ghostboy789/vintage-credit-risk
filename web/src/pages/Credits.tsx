export function Credits() {
  return (
    <div className="mx-auto max-w-[720px] px-4 py-12 md:px-8">
      <h1 className="font-display text-4xl">Credits</h1>
      <p className="mt-4" style={{ color: "var(--ink-2)" }}>
        Where the interface ideas came from, and the data behind the numbers. Full detail in the repo's
        <code className="font-mono"> web/THIRD_PARTY.md</code>.
      </p>
      <ul className="mt-6 space-y-3 text-sm">
        <li>Path-draw technique, animated number, custom tooltip, theme toggle, nav underline, header blur, scroll progress, prose fade-in, expand-on-hover — adapted from free Skiper UI components (skiper-ui.com).</li>
        <li>Card spotlight border and the word-by-word headline reveal — rebuilt from the visible behaviour of the Skiper UI and ThreeUI card-spotlight and text-reveal effects; no source was copied.</li>
        <li>Command palette (⌘K) — rebuilt from a written spec; no Skiper Pro source was copied.</li>
        <li>The Loan Field — a Canvas2D reimplementation inspired by ThreeUI's Structure Flow "Data Field" (Community tier, MIT licence, threeui.com).</li>
        <li>Data: Freddie Mac Single-Family Loan-Level Dataset, non-commercial research use. Not affiliated with or endorsed by Freddie Mac.</li>
      </ul>
    </div>
  );
}
