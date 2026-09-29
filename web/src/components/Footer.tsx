import { Link } from "react-router-dom";
import { useArtefacts } from "../lib/artefacts";

const EXPLORE = [
  { to: "/vintages", label: "Vintages" },
  { to: "/roll-rates", label: "Roll rates" },
  { to: "/scorecard", label: "Scorecard" },
  { to: "/ecl", label: "IFRS 9 ECL" },
  { to: "/capital", label: "Capital" },
  { to: "/powerbi", label: "Power BI" },
  { to: "/methods", label: "Methods & limits" },
];

function Heading({ children }: { children: string }) {
  return (
    <h2 className="font-mono text-xs uppercase tracking-wide" style={{ color: "var(--ink-2)" }}>
      {children}
    </h2>
  );
}

export function Footer() {
  const state = useArtefacts();
  const suppressed = state.status === "ready" ? state.data.portfolio.suppressed_cells : "…";
  const codeVersion = state.status === "ready" ? state.data.portfolio.code_version : "…";
  const cutoff = state.status === "ready" ? state.data.portfolio.data_cutoff : "…";
  const link = "footer-link inline-flex min-h-[44px] items-center lg:min-h-[28px]";

  return (
    <footer className="mt-24 border-t" style={{ borderColor: "var(--border)", color: "var(--ink-3)" }}>
      <div className="mx-auto grid max-w-[1200px] grid-cols-1 gap-10 px-4 py-12 text-sm md:grid-cols-2 md:px-8 lg:grid-cols-4">
        <div>
          <div className="font-display text-xl" style={{ color: "var(--ink)" }}>
            Vintage
          </div>
          <p className="mt-2 max-w-[34ch]" style={{ color: "var(--ink-2)" }}>
            A credit-risk study of US mortgages, from default definitions to IFRS 9 expected loss.
          </p>
        </div>
        <nav aria-label="Pages">
          <Heading>Explore</Heading>
          <ul className="mt-2">
            {EXPLORE.map((n) => (
              <li key={n.to}>
                <Link to={n.to} className={link} style={{ color: "var(--ink-2)" }}>
                  {n.label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
        <div>
          <Heading>Data and privacy</Heading>
          <p className="mt-2">
            Source: Freddie Mac Single-Family Loan-Level Dataset, used for non-commercial research. Not affiliated with or endorsed
            by Freddie Mac.
          </p>
          <p className="mt-2">No published figure describes fewer than 10 loans. {suppressed} cells suppressed.</p>
        </div>
        <div>
          <Heading>Project</Heading>
          <ul className="mt-2">
            <li>
              <a href="https://github.com/Ghostboy789/vintage-credit-risk" className={link} style={{ color: "var(--accent)" }}>
                Repository
              </a>
            </li>
            <li>
              <Link to="/credits" className={link} style={{ color: "var(--accent)" }}>
                Credits
              </Link>
            </li>
          </ul>
          <div className="font-mono mt-3 text-xs">
            <div>data to {cutoff}</div>
            <div>code_version: {codeVersion}</div>
          </div>
        </div>
      </div>
    </footer>
  );
}
