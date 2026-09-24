import { lazy, Suspense, useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import { ThemeToggle } from "./ThemeToggle";
// The palette loads on first open, keeping it out of the initial bundle.
const CommandPalette = lazy(() => import("./CommandPalette").then((mod) => ({ default: mod.CommandPalette })));

const NAV = [
  { to: "/", label: "Overview" },
  { to: "/vintages", label: "Vintages" },
  { to: "/roll-rates", label: "Roll rates" },
  { to: "/scorecard", label: "Scorecard" },
  { to: "/ecl", label: "IFRS 9 ECL" },
  { to: "/capital", label: "Capital" },
  { to: "/methods", label: "Methods" },
];

// Text-roll navigation adapted from skiper-ui.com (skiper58): on hover or keyboard focus each letter
// rolls up to reveal its copy, 12 ms apart. CSS only; touch screens and reduced motion get a plain
// colour change (see .roll in index.css).
function NavItem({ to, label }: { to: string; label: string }) {
  return (
    <NavLink
      to={to}
      end={to === "/"}
      className="nav-roll relative py-1 text-sm"
      style={({ isActive }: { isActive: boolean }) => ({
        color: isActive ? "var(--ink)" : "var(--ink-2)",
        borderBottom: isActive ? "2px solid var(--accent)" : "2px solid transparent",
      })}
    >
      <span className="sr-only">{label}</span>
      <span className="roll" aria-hidden>
        {[...label].map((ch, i) => {
          const c = ch === " " ? " " : ch;
          return (
            <span key={i} className="roll-ch" data-ch={c} style={{ transitionDelay: `${i * 12}ms` }}>
              {c}
            </span>
          );
        })}
      </span>
    </NavLink>
  );
}

export function Header() {
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [paletteLoaded, setPaletteLoaded] = useState(false);
  useEffect(() => {
    if (paletteOpen) setPaletteLoaded(true);
  }, [paletteOpen]);

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
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
        </button>
        <a
          href="https://github.com/Ghostboy789"
          target="_blank"
          rel="noreferrer"
          aria-label="GitHub"
          className="hidden h-10 w-10 items-center justify-center rounded-md border md:flex"
          style={{ borderColor: "var(--border)" }}
        >
          <svg width="18" height="18" viewBox="0 0 16 16" fill="currentColor" aria-hidden><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8z" /></svg>
        </a>
        <a
          href="https://linkedin.com/in/medhansh-shekhawat"
          target="_blank"
          rel="noreferrer"
          aria-label="LinkedIn"
          className="hidden h-10 w-10 items-center justify-center rounded-md border md:flex"
          style={{ borderColor: "var(--border)" }}
        >
          <svg width="18" height="18" viewBox="0 0 16 16" fill="currentColor" aria-hidden><circle cx="3.2" cy="3.2" r="1.7" /><rect x="1.7" y="6" width="3" height="8.5" /><path d="M6.6 6h2.9v1.2c.4-.8 1.4-1.4 2.7-1.4 2.4 0 2.9 1.6 2.9 3.6v5.1h-3V10c0-1 0-2-1.2-2s-1.4.9-1.4 1.9v4.6H6.6z" /></svg>
        </a>
        <ThemeToggle />
        <button
          type="button"
          onClick={() => setMenuOpen(true)}
          aria-label="Menu"
          className="flex h-10 w-10 items-center justify-center rounded-md border lg:hidden"
          style={{ borderColor: "var(--border)" }}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden><path d="M4 7h16M4 12h16M4 17h16" /></svg>
        </button>
      </div>

      {paletteLoaded && (
        <Suspense fallback={null}>
          <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
        </Suspense>
      )}

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
