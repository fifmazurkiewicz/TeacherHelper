const STORAGE_KEY = "th_theme";

export type ThemeChoice = "light" | "dark";

function prefersDark(): boolean {
  if (typeof window === "undefined") return false;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
}

export function getStoredTheme(): ThemeChoice {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (v === "light" || v === "dark") return v;
  } catch {
    /* private mode / blocked */
  }
  return prefersDark() ? "dark" : "light";
}

export function setStoredTheme(choice: ThemeChoice): void {
  try {
    localStorage.setItem(STORAGE_KEY, choice);
  } catch {
    /* ignore */
  }
}

export function applyTheme(choice: ThemeChoice): void {
  if (typeof document === "undefined") return;
  document.documentElement.classList.toggle("dark", choice === "dark");
}

export function initThemeFromStorage(): void {
  applyTheme(getStoredTheme());
}
