import { useCallback, useSyncExternalStore } from "react";

export type Audience = "new" | "pro" | "hiring" | "tour";
const KEY = "vintage.audience";
const AUDIENCE_EVENT = "vintage:audience";
const PICKER_EVENT = "vintage:picker";

const VALID: Audience[] = ["new", "pro", "hiring", "tour"];

export const AUDIENCE_LABEL: Record<Audience, string> = {
  new: "New to credit risk",
  pro: "Risk or model professional",
  hiring: "Hiring and skimming",
  tour: "Quick look on my phone",
};

function read(): Audience | null {
  try {
    const v = localStorage.getItem(KEY);
    return VALID.includes(v as Audience) ? (v as Audience) : null;
  } catch {
    return null;
  }
}

// Storage can be blocked; keep the choice for this page load either way.
let memory: Audience | null | undefined;
const current = () => (memory === undefined ? (memory = read()) : memory);

const subscribe = (cb: () => void) => {
  const on = () => {
    memory = read() ?? memory;
    cb();
  };
  window.addEventListener(AUDIENCE_EVENT, cb);
  window.addEventListener("storage", on);
  return () => {
    window.removeEventListener(AUDIENCE_EVENT, cb);
    window.removeEventListener("storage", on);
  };
};

export function useAudience(): [Audience | null, (a: Audience) => void] {
  const a = useSyncExternalStore(subscribe, current, () => null);
  const set = useCallback((next: Audience) => {
    memory = next;
    try {
      localStorage.setItem(KEY, next);
    } catch {
      /* storage blocked: the choice lasts for this visit */
    }
    window.dispatchEvent(new CustomEvent(AUDIENCE_EVENT));
  }, []);
  return [a, set];
}

// "Change" in the header asks the Overview to show the picker again. The flag survives the route
// change, so the request is not lost if the Overview mounts after it.
let pickerRequested = false;
export function setPickerRequested(v: boolean) {
  pickerRequested = v;
  window.dispatchEvent(new CustomEvent(PICKER_EVENT));
}
export function usePickerRequested() {
  return useSyncExternalStore(
    (cb) => {
      window.addEventListener(PICKER_EVENT, cb);
      return () => window.removeEventListener(PICKER_EVENT, cb);
    },
    () => pickerRequested,
    () => false,
  );
}
