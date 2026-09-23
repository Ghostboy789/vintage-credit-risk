# Third-party component credit

Techniques adapted for this site, kept small and inline (this project does not install any of
these libraries as packages — each is a short, hand-written re-implementation of the described
technique, credited here).

## Skiper UI (skiper-ui.com) — free-tier components, adapted

Skiper UI does not publish a licence page; its free components are marketed as copy-paste. Each
technique below was re-implemented from the component's public description, not copied output.

- **Path-draw technique** (skiper19, "Svg follow scroll") — used for the Ridge
  (`src/components/Ridge.tsx`) and the vintage curve chart (`src/components/VintageCurveChart.tsx`).
  Only the `pathLength` draw technique was taken; it is not scroll-scrubbed here.
- **Animated number** (skiper37) — `src/components/KpiTile.tsx`, adapted to count from `ci_low`
  to `value` rather than from 0.
- **Custom tooltip** (skiper101) — `src/components/ChartTooltip.tsx`.
- **Theme toggle** (skiper4, the simple icon-swap variant) — `src/components/ThemeToggle.tsx`.
- **Text roll navigation** (skiper58) — simplified in `src/components/Header.tsx` to a colour/
  underline change, which is also the component's own reduced-motion and touch fallback.
- **Progressive Blur** (skiper41) — the sticky header backdrop in `src/components/Header.tsx`
  (`backdrop-filter: blur(12px)` over a 64px band, never over a chart or number).
- **Scroll progress** (skiper89) — `src/components/ScrollProgress.tsx`, on the Methods page.
- **Scroll with fade** (skiper87) — `src/components/Prose.tsx`, used for the Methods "what these
  results do not establish" section.
- **ExpandOnHover** (skiper53) — not built; open item, see the handover.
- **Dynamic Island** (skiper2) — not built as the calculator's mobile result pill; open item, see
  the handover.

## Rebuilt from a written spec (Pro-tier reference only, no source copied)

- **Command palette** (⌘K) — `src/components/CommandPalette.tsx`. Skiper's "Vercel Command
  Search" (skiper92) is a paid component; nothing from it was inspected or copied. This is a
  from-scratch implementation of the design brief's own spec: a modal dialog, grouped results,
  arrow-key navigation and plain substring matching.

## ThreeUI (threeui.com) — Community tier, MIT licence

- **The Loan Field** — `src/components/LoanField.tsx`. Inspired by ThreeUI's Structure Flow
  "Data Field" (Community, MIT), reimplemented from scratch in Canvas2D. No three.js or WebGL is
  used anywhere on this site, and no ThreeUI source was copied.

## Data

Freddie Mac Single-Family Loan-Level Dataset, used for non-commercial research. This site is not
affiliated with or endorsed by Freddie Mac.
