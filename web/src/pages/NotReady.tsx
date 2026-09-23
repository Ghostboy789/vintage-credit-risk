export function NotReady({ error }: { error: string }) {
  return (
    <div className="mx-auto max-w-xl px-4 py-24 text-center">
      <h1 className="font-display text-3xl">Not ready</h1>
      <p className="mt-4" style={{ color: "var(--ink-2)" }}>
        The artefacts this site reads could not be loaded, so there is nothing honest to show yet.
      </p>
      <p className="font-mono mt-4 text-xs" style={{ color: "var(--ink-3)" }}>
        {error}
      </p>
    </div>
  );
}
