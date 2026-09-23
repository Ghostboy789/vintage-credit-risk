import { useArtefacts } from "../lib/artefacts";

export function Footer() {
  const state = useArtefacts();
  const suppressed = state.status === "ready" ? state.data.portfolio.suppressed_cells : "…";
  const codeVersion = state.status === "ready" ? state.data.portfolio.code_version : "…";
  const cutoff = state.status === "ready" ? state.data.portfolio.data_cutoff : "…";

  return (
    <footer
      className="mt-24 grid grid-cols-1 gap-8 border-t px-4 py-12 text-sm md:grid-cols-3 md:px-8"
      style={{ borderColor: "var(--border)", color: "var(--ink-3)" }}
    >
      <div>
        Source: Freddie Mac Single-Family Loan-Level Dataset, used for non-commercial research. Not
        affiliated with or endorsed by Freddie Mac.
      </div>
      <div>No published figure describes fewer than 10 loans. {suppressed} cells suppressed.</div>
      <div className="font-mono">
        <div>data to {cutoff}</div>
        <div>code_version: {codeVersion}</div>
        <div className="mt-1 flex gap-3">
          <a href="/credits" style={{ color: "var(--accent)" }}>
            credits
          </a>
          <a href="https://github.com/Ghostboy789/vintage-credit-risk" style={{ color: "var(--accent)" }}>
            repo
          </a>
        </div>
      </div>
    </footer>
  );
}
