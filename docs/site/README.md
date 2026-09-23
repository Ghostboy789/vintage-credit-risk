# Website

A React + Vite + Tailwind + Framer Motion static site in `web/`, built against the artefacts in
`tests/fixtures/artefacts/` (synthetic) until the real-data release points it at the real
`artefacts/` folder.

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

QA screenshots (light/dark, 1440/390, every page) are captured outside the repo during review and
are added to this folder for the README once real data replaces the fixtures.

## Known gaps against the design brief

See the handover for the full list. In short: the ExpandOnHover scorecard feature list and the
Dynamic Island mobile calculator result pill are not built; the vintage-year command-palette
index is built at runtime from the loaded artefacts rather than at build time; performance-budget
numbers (initial JS gzip) have not been measured against the brief's 120 KB target.
