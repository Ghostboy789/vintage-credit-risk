import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import { ThemeToggle } from "./ThemeToggle";
import { CommandPalette } from "./CommandPalette";

const NAV = [
  { to: "/", label: "Overview" },
  { to: "/vintages", label: "Vintages" },
  { to: "/roll-rates", label: "Roll rates" },
  { to: "/scorecard", label: "Scorecard" },
  { to: "/ecl", label: "IFRS 9 ECL" },
  { to: "/capital", label: "Capital" },
  { to: "/methods", label: "Methods" },
];

// Text-roll nav (skiper58) simplified to a colour/underline change (also the reduced-motion and
// touch fallback the brief specifies) — CSS-only, no letter-stagger JS, one less dependency path.
function NavItem({ to, label }: { to: string; label: string }) {
  return (
    <NavLink
      to={to}
      className="relative py-1 text-sm transition-colors hover:opacity-100"
      style={({ isActive }: { isActive: boolean }) => ({
        color: isActive ? "var(--ink)" : "var(--ink-2)",
        borderBottom: isActive ? "2px solid var(--accent)" : "2px solid transparent",
      })}
    >
      {label}
    </NavLink>
  );
}

export function Header() {
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <header
      className="sticky top-0 z-40 flex h-14 items-center justify-between px-4 md:h-16 md:px-8"
      style={{
        borderBottom: "1px solid var(--border)",
        background: "color-mix(in srgb, var(--bg) 92%, transparent)",
        backdropFilter: "blur(12px)",
      }}
    >
      <a href="/" className="leading-tight">
        <div className="font-display text-lg md:text-[22px]" style={{ color: "var(--ink)" }}>
          Vintage
        </div>
        <div className="text-[11px] md:text-[12px]" style={{ color: "var(--ink-3)" }}>
          Medhansh Shekhawat
        </div>
      </a>

      <nav className="hidden items-center gap-6 lg:flex">
        {NAV.map((n) => (
          <NavItem key={n.to} {...n} />
        ))}
      </nav>

      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => setPaletteOpen(true)}
          className="hidden h-10 items-center gap-2 rounded-md border px-3 text-sm md:flex"
          style={{ borderColor: "var(--border)", color: "var(--ink-2)" }}
        >
          Search <kbd className="font-mono text-xs">⌘K</kbd>
        </button>
        <button
          type="button"
          onClick={() => setPaletteOpen(true)}
          aria-label="Search"
          className="flex h-10 w-10 items-center justify-center rounded-md border md:hidden"
          style={{ borderColor: "var(--border)" }}
        >
          ⌕
        </button>
        <a
          href="https://github.com/Ghostboy789"
          target="_blank"
          rel="noreferrer"
          aria-label="GitHub"
          className="hidden h-10 w-10 items-center justify-center rounded-md border md:flex"
          style={{ borderColor: "var(--border)" }}
        >
          GH
        </a>
        <a
          href="https://linkedin.com/in/medhansh-shekhawat"
          target="_blank"
          rel="noreferrer"
          aria-label="LinkedIn"
          className="hidden h-10 w-10 items-center justify-center rounded-md border md:flex"
          style={{ borderColor: "var(--border)" }}
        >
          in
        </a>
        <ThemeToggle />
        <button
          type="button"
          onClick={() => setMenuOpen(true)}
          aria-label="Menu"
          className="flex h-10 w-10 items-center justify-center rounded-md border lg:hidden"
          style={{ borderColor: "var(--border)" }}
        >
          ☰
        </button>
      </div>

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />

      {menuOpen && (
        <div
          className="fixed inset-0 z-50 flex flex-col p-6"
          style={{ background: "var(--bg)" }}
          role="dialog"
          aria-label="Menu"
        >
          <button aria-label="Close menu" className="self-end p-2" onClick={() => setMenuOpen(false)}>
            ✕
          </button>
          <nav className="mt-8 flex flex-col gap-1">
            {NAV.map((n) => (
              <a
                key={n.to}
                href={n.to}
                onClick={() => setMenuOpen(false)}
                className="min-h-[44px] border-b py-3 text-lg"
                style={{ borderColor: "var(--border)" }}
              >
                {n.label}
              </a>
            ))}
          </nav>
        </div>
      )}
    </header>
  );
}
