// One badge for PASS/FAIL/AMBER/INSUFFICIENT/NOT_RUN/pending everywhere (design brief section 4).
// Colour is never the only signal: each state also has its own icon glyph and text.
const CONFIG: Record<string, { color: string; icon: string }> = {
  PASS: { color: "var(--pass)", icon: "✓" },
  FAIL: { color: "var(--fail)", icon: "✕" },
  AMBER: { color: "var(--amber)", icon: "▲" },
  INSUFFICIENT: { color: "var(--neutral)", icon: "?" },
  NOT_RUN: { color: "var(--neutral)", icon: "○" },
  pending: { color: "var(--neutral)", icon: "◔" },
  green: { color: "var(--pass)", icon: "✓" },
  amber: { color: "var(--amber)", icon: "▲" },
  red: { color: "var(--fail)", icon: "✕" },
};

export function ResultBadge({ result }: { result: string }) {
  const cfg = CONFIG[result] ?? CONFIG.NOT_RUN;
  return (
    <span
      className="font-mono inline-flex h-[22px] items-center gap-1 rounded px-2 text-[12px] uppercase"
      style={{ color: cfg.color, background: `color-mix(in srgb, ${cfg.color} 14%, transparent)` }}
    >
      <span aria-hidden>{cfg.icon}</span>
      {result}
    </span>
  );
}
