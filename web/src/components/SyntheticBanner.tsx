// Design brief section 4, "Synthetic guard": undismissable, striped, pinned under the header.
export function SyntheticBanner() {
  return (
    <div
      role="alert"
      className="sticky top-14 z-30 flex items-center justify-center px-4 py-2 text-center text-sm font-semibold md:top-16"
      style={{
        color: "#1a1200",
        background:
          "repeating-linear-gradient(45deg, var(--amber), var(--amber) 10px, color-mix(in srgb, var(--amber) 70%, black) 10px, color-mix(in srgb, var(--amber) 70%, black) 20px)",
      }}
    >
      SYNTHETIC FIXTURE DATA — not real results
    </div>
  );
}
