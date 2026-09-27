// Copies the six contract artefacts into public/artefacts/ before dev/build.
// Source per artefact: VINTAGE_ARTEFACTS_DIR, else VINTAGE_DATA_ROOT/artefacts, else the repo's own
// artefacts/ folder. An artefact not produced yet falls back to the synthetic fixture, which the
// site banners on every page that uses it. A release build refuses to ship any synthetic artefact.
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";

const ARTEFACTS = ["portfolio", "pd_models", "lgd_ead", "ecl", "capital", "monitoring"];
const repo = resolve(import.meta.dirname, "../..");

const srcDir = resolve(
  process.env.VINTAGE_ARTEFACTS_DIR ||
    (process.env.VINTAGE_DATA_ROOT ? join(process.env.VINTAGE_DATA_ROOT, "artefacts") : join(repo, "artefacts"))
);
const fixtureDir = join(repo, "tests/fixtures/artefacts");
const destDir = resolve(import.meta.dirname, "../public/artefacts");
mkdirSync(destDir, { recursive: true });

const synthetic = [];
for (const name of ARTEFACTS) {
  let src = join(srcDir, `${name}.json`);
  if (!existsSync(src)) src = join(fixtureDir, `${name}.json`);
  const doc = JSON.parse(readFileSync(src, "utf8"));
  // The site draws annual vintages only; the quarterly series is ~7 MB the browser never reads.
  if (name === "portfolio") delete doc.vintage_curves;
  writeFileSync(join(destDir, `${name}.json`), JSON.stringify(doc));
  if (doc.synthetic) synthetic.push(name);
}

const isProdBuild = process.env.VITE_BUILD_MODE === "production" || process.argv.includes("--check-release");
if (isProdBuild && synthetic.length) {
  console.error(`Refusing a release build: synthetic artefacts: ${synthetic.join(", ")}.`);
  process.exit(1);
}

console.log(`Synced ${ARTEFACTS.length} artefacts; synthetic: ${synthetic.join(", ") || "none"}`);
