import { useEffect, useRef } from "react";
import { animate, m, useMotionValue } from "framer-motion";
import { useReducedMotion } from "../lib/theme";

// Grade A (lowest risk) to the last grade (highest): green, through amber, to red.
// The letter is always shown, so colour is never the only signal.
export function gradeColor(i: number, n: number) {
  const t = n <= 1 ? 0 : i / (n - 1);
  return t < 0.5
    ? `color-mix(in srgb, var(--amber) ${t * 200}%, var(--pass))`
    : `color-mix(in srgb, var(--fail) ${(t - 0.5) * 200}%, var(--amber))`;
}

// A number that settles with a spring instead of jumping. Reduced motion: shows the value at once.
// Behaviour rebuilt from the visible effect of an animated-number result reveal.
export function SpringNumber({ value, className, style }: { value: number; className?: string; style?: React.CSSProperties }) {
  const reduced = useReducedMotion();
  const mv = useMotionValue(value);
  const el = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const write = (v: number) => {
      if (el.current) el.current.textContent = String(Math.round(v));
    };
    if (reduced) {
      mv.set(value);
      write(value);
      return;
    }
    const c = animate(mv, value, { type: "spring", stiffness: 140, damping: 16, mass: 0.9, onUpdate: write });
    return () => c.stop();
  }, [value, reduced, mv]);
  return (
    <span ref={el} className={className} style={style}>
      {Math.round(value)}
    </span>
  );
}

// The grade letter in a coloured chip; it pops in with a spring whenever the grade changes.
export function GradeChip({ grade, index, count, size = 44 }: { grade: string; index: number; count: number; size?: number }) {
  const reduced = useReducedMotion();
  const c = gradeColor(index, count);
  return (
    <m.span
      key={grade}
      className="font-display inline-flex items-center justify-center rounded-lg font-semibold leading-none"
      style={{
        width: size,
        height: size,
        fontSize: size * 0.6,
        color: "var(--ink)",
        background: `color-mix(in srgb, ${c} 26%, var(--surface))`,
        border: `2px solid ${c}`,
      }}
      initial={reduced ? false : { scale: 0.55, rotate: -8, opacity: 0.4 }}
      animate={{ scale: 1, rotate: 0, opacity: 1 }}
      transition={reduced ? { duration: 0 } : { type: "spring", stiffness: 520, damping: 16 }}
    >
      {grade}
    </m.span>
  );
}
