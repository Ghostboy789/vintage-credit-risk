import type { PointerEvent } from "react";

// Cursor-follow spotlight border, rebuilt from the effect seen in Skiper UI / ThreeUI "card spotlight":
// the pointer position is written to CSS variables and the .spot rule in index.css draws the glow.
export function spotlightMove(e: PointerEvent<HTMLElement>) {
  const el = e.currentTarget;
  const r = el.getBoundingClientRect();
  el.style.setProperty("--mx", `${e.clientX - r.left}px`);
  el.style.setProperty("--my", `${e.clientY - r.top}px`);
}
