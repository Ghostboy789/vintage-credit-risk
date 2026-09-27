# Website

A React + Vite + Tailwind + Framer Motion static site in `web/`, built against the real
`artefacts/` folder (the six contract artefacts from the Freddie Mac run).

## Run it

```
cd web
bun install
bun run dev      # dev server, artefacts synced from VINTAGE_ARTEFACTS_DIR or the fixtures
bun run build    # static build to web/dist, refuses nothing (fixtures allowed)
bun run build:release   # refuses to build if any artefact still has synthetic: true
bun run test     # node --test on the client-side scorecard calculator
```

`VINTAGE_ARTEFACTS_DIR` (env var) points `scripts/sync-artefacts.mjs` at a different artefacts
folder; it defaults to the repo's synthetic fixtures.

## Pages

Overview, Vintages, Roll rates, Scorecard (with the client-side calculator), IFRS 9 ECL, Capital,
Methods & limits, and a Credits page for third-party component attribution
(`web/THIRD_PARTY.md`).

## Screenshots

On the real portfolio, dark theme:

- Overview desktop: `overview_dark_desktop.png`, mobile: `overview_dark_mobile.png`
- Vintages desktop: `vintages_dark_desktop.png`
- Scorecard desktop: `scorecard_dark_desktop.png`
- IFRS 9 ECL desktop: `ecl_dark_desktop.png`

The full QA set (every page, light and dark, 1440 and 390, plus reduced-motion captures) is kept
outside the repo in the design review folder; this is the curated subset for the README.

## Performance

Initial JS is measured at each release: about 115 KB gzip (React, router, the hero route and the
shared motion core), under the 120 KB budget. Route chunks stay under 30 KB gzip each.

## Known gaps against the design brief

Not built: the hero series precomputed at build time into inline JSON (Overview still waits on the
artefact fetch before its first paint), the roll-rate cure panel and SMA stacked area, the
calibration sample switch and discrimination table, the Methods sticky table of contents, and an
axe or screen-reader audit.
