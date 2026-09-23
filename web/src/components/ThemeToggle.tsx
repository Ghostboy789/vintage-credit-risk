import { useTheme } from "../lib/theme";

// Skiper4 (simple icon swap, not skiper26's full-screen wipe): three states, system/light/dark.
const ICONS: Record<string, string> = { system: "◐", light: "☀", dark: "☾" };
const NEXT: Record<string, "system" | "light" | "dark"> = { system: "light", light: "dark", dark: "system" };

export function ThemeToggle() {
  const { choice, setChoice } = useTheme();
  return (
    <button
      type="button"
      aria-label={`Theme: ${choice}. Click to change.`}
      onClick={() => setChoice(NEXT[choice])}
      className="flex h-10 w-10 items-center justify-center rounded-md border text-lg transition-transform duration-200 hover:scale-105"
      style={{ borderColor: "var(--border)", color: "var(--ink)" }}
    >
      <span aria-hidden>{ICONS[choice]}</span>
    </button>
  );
}
