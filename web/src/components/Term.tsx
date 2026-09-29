import { useId, useState } from "react";
import { GLOSSARY } from "../lib/glossary";

// A glossary word: dotted underline, definition on hover, focus or tap (Skiper101 tooltip styling).
export function Term({ k, children }: { k: string; children?: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const def = GLOSSARY[k];
  if (!def) return <>{children ?? k}</>;
  return (
    <span className="relative inline-block">
      <button
        type="button"
        aria-describedby={open ? id : undefined}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={() => setOpen((o) => !o)}
        className="term cursor-help"
      >
        {children ?? k}
      </button>
      {open && (
        <span
          id={id}
          role="tooltip"
          className="term-tip absolute bottom-full left-1/2 z-30 mb-2 w-[240px] -translate-x-1/2 rounded-md border p-2 text-left text-xs leading-snug"
          style={{ background: "var(--surface-2)", borderColor: "var(--border)", color: "var(--ink)" }}
        >
          {def}
        </span>
      )}
    </span>
  );
}
