import { create } from "zustand";

/**
 * "Acting as" operator name. There is no login yet, so every lifecycle action
 * (review, re-grade, resolve, notes, acknowledge) is attributed to this name
 * in the audit trail. Remembered per browser; storage may be unavailable.
 */
const KEY = "varuna.operator";

function load(): string {
  try {
    return localStorage.getItem(KEY) ?? "";
  } catch {
    return "";
  }
}

interface OperatorState {
  name: string;
  setName: (name: string) => void;
}

export const useOperator = create<OperatorState>((set) => ({
  name: load(),
  setName: (name) => {
    try {
      localStorage.setItem(KEY, name);
    } catch {
      /* storage blocked: keep it for this session only */
    }
    set({ name });
  },
}));

/** Name used in the audit trail when none has been set. */
export function operatorOrDefault(name: string): string {
  return name.trim() || "Control room operator";
}
