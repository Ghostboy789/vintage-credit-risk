import { lazy, Suspense, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Link, NavLink, useLocation } from "react-router-dom";
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
  { to: "/powerbi", label: "Power BI" },
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
      className="nav-roll relative -mx-2 rounded-md px-2 py-1.5 text-sm"
      style={({ isActive }: { isActive: boolean }) => ({
        color: isActive ? "var(--ink)" : "var(--ink-2)",
        background: isActive ? "color-mix(in srgb, var(--accent) 12%, transparent)" : "transparent",
        boxShadow: isActive ? "inset 0 -2px 0 var(--accent)" : "none",
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
  const { pathname } = useLocation();
  useEffect(() => setMenuOpen(false), [pathname]);
  // Give the page's <main> an id so the skip link has a target.
  useEffect(() => {
    const main = document.querySelector("main");
    if (main) {
      main.id = "main";
      main.tabIndex = -1;
      main.style.outline = "none";
    }
  }, []);

  // Lock page scroll and close on Escape while the mobile menu is open.
  useEffect(() => {
    if (!menuOpen) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setMenuOpen(false);
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener("keydown", onKey);
    };
  }, [menuOpen]);
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
    <>
    <a href="#main" className="skip-link">
      Skip to content
    </a>
    <header
      className="sticky top-0 z-40 flex h-14 items-center justify-between px-4 md:h-16 md:px-8"
      style={{
        borderBottom: "1px solid var(--border)",
        background: "color-mix(in srgb, var(--bg) 92%, transparent)",
        backdropFilter: "blur(12px)",
      }}
    >
      <Link to="/" className="leading-tight">
        <div className="font-display text-lg md:text-[22px]" style={{ color: "var(--ink)" }}>
          Vintage
        </div>
        <div className="text-[11px] md:text-[12px]" style={{ color: "var(--ink-3)" }}>
          Medhansh Shekhawat
        </div>
      </Link>

      <nav aria-label="Main" className="hidden items-center gap-7 lg:flex">
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

      {/* Portalled to <body>: the header's backdrop-filter would otherwise trap this fixed overlay
          inside the 56px header bar. */}
      {menuOpen &&
        createPortal(
          <div
            className="menu-sheet fixed inset-0 z-50 flex flex-col overflow-y-auto px-4 pb-8"
            style={{ background: "var(--bg)", paddingTop: "env(safe-area-inset-top)" }}
            role="dialog"
            aria-modal="true"
            aria-label="Menu"
          >
            <div className="flex h-14 shrink-0 items-center justify-between">
              <span className="font-display text-lg" style={{ color: "var(--ink)" }}>Vintage</span>
              <button
                type="button"
                aria-label="Close menu"
                autoFocus
                className="flex h-10 w-10 items-center justify-center rounded-md border"
                style={{ borderColor: "var(--border)" }}
                onClick={() => setMenuOpen(false)}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden><path d="M6 6l12 12M18 6 6 18" /></svg>
              </button>
            </div>
            <nav className="mt-4 flex flex-col">
              {NAV.map((n, i) => (
                <NavLink
                  key={n.to}
                  to={n.to}
                  end={n.to === "/"}
                  onClick={() => setMenuOpen(false)}
                  className="menu-item flex min-h-[52px] items-center justify-between border-b text-lg"
                  style={({ isActive }: { isActive: boolean }) => ({
                    borderColor: "var(--border)",
                    color: isActive ? "var(--accent)" : "var(--ink)",
                    animationDelay: `${i * 30}ms`,
                  })}
                >
                  {n.label}
                  <span aria-hidden style={{ color: "var(--ink-3)" }}>→</span>
                </NavLink>
              ))}
            </nav>
            <div className="mt-8 flex gap-3 text-sm" style={{ color: "var(--ink-2)" }}>
              <a href="https://github.com/Ghostboy789" target="_blank" rel="noreferrer" className="underline">GitHub</a>
              <a href="https://linkedin.com/in/medhansh-shekhawat" target="_blank" rel="noreferrer" className="underline">LinkedIn</a>
            </div>
          </div>,
          document.body,
        )}
    </header>
    </>
  );
}
