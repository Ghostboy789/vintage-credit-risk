import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

type ThemeChoice = "system" | "light" | "dark";
const ThemeContext = createContext<{ choice: ThemeChoice; setChoice: (c: ThemeChoice) => void }>({
  choice: "system",
  setChoice: () => {},
});

function readStored(): ThemeChoice {
  try {
    const v = localStorage.getItem("vintage-theme");
    if (v === "light" || v === "dark" || v === "system") return v;
  } catch {
    /* ignore: private mode / blocked storage */
  }
  return "system";
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [choice, setChoiceState] = useState<ThemeChoice>(readStored);

  useEffect(() => {
    const root = document.documentElement;
    if (choice === "system") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", choice);
  }, [choice]);

  const setChoice = (c: ThemeChoice) => {
    setChoiceState(c);
    try {
      localStorage.setItem("vintage-theme", c);
    } catch {
      /* ignore */
    }
  };

  return <ThemeContext.Provider value={{ choice, setChoice }}>{children}</ThemeContext.Provider>;
}

export const useTheme = () => useContext(ThemeContext);

export function useReducedMotion() {
  const [reduced, setReduced] = useState(
    () => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const onChange = () => setReduced(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return reduced;
}
