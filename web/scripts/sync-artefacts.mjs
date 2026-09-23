// Plain fs copy plus a JSON flag check. No config framework — one env var, one purpose.
// Copies the six contract artefacts from a configurable source folder into public/artefacts/,
// so the app always builds from `VINTAGE_ARTEFACTS_DIR` (default: the repo's synthetic fixtures).
// A production build refuses to ship if any artefact is still synthetic (design brief, guardrail).
import { existsSync, mkdirSync, copyFileSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";

const ARTEFACTS = ["portfolio", "pd_models", "lgd_ead", "ecl", "capital", "monitoring"];

const srcDir = resolve(
  process.env.VINTAGE_ARTEFACTS_DIR ||
    join(import.meta.dirname, "../../../vintage-credit-risk/tests/fixtures/artefacts")
);
const destDir = resolve(import.meta.dirname, "../public/artefacts");
mkdirSync(destDir, { recursive: true });

let anySynthetic = false;
for (const name of ARTEFACTS) {
  const src = join(srcDir, `${name}.json`);
  if (!existsSync(src)) {
    console.error(`Missing artefact: ${src}`);
    process.exit(1);
  }
  copyFileSync(src, join(destDir, `${name}.json`));
  const parsed = JSON.parse(readFileSync(src, "utf8"));
  if (parsed.synthetic) anySynthetic = true;
}

const isProdBuild = process.env.VITE_BUILD_MODE === "production" || process.argv.includes("--check-release");
if (isProdBuild && anySynthetic) {
  console.error(
    "Refusing a release build: at least one artefact has synthetic: true. " +
      "Real artefacts must be wired in for the real-data release before `vite build --mode production` can ship."
  );
  process.exit(1);
}

console.log(`Synced ${ARTEFACTS.length} artefacts from ${srcDir}${anySynthetic ? " (synthetic)" : ""}`);
