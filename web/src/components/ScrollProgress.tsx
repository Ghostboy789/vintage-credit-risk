import { m, useScroll } from "framer-motion";

// Skiper89 "Scroll progress 001": a 2px accent bar under the header, kept even in reduced-motion
// (it conveys position, not motion).
export function ScrollProgress() {
  const { scrollYProgress } = useScroll();
  return (
    <m.div
      className="sticky top-14 z-30 h-0.5 origin-left md:top-16"
      style={{ scaleX: scrollYProgress, background: "var(--accent)" }}
    />
  );
}
