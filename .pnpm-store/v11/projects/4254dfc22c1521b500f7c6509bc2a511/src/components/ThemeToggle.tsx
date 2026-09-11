import { useCallback, useState } from "react";
import { applyTheme, getStoredTheme, setStoredTheme, type ThemeChoice } from "@/lib/theme";

type Props = { className?: string };

export function ThemeToggle({ className }: Props) {
  const [choice, setChoice] = useState<ThemeChoice>(() => getStoredTheme());

  const toggle = useCallback(() => {
    const next: ThemeChoice = choice === "dark" ? "light" : "dark";
    setChoice(next);
    applyTheme(next);
    setStoredTheme(next);
  }, [choice]);

  const isDark = choice === "dark";

  return (
    <button
      type="button"
      onClick={toggle}
      className={
        className ??
        "rounded-md px-2 py-1.5 text-sm text-ink-600 hover:bg-paper-100 dark:text-paper-300 dark:hover:bg-ink-800"
      }
      aria-pressed={isDark}
      title={isDark ? "Przełącz na tryb jasny" : "Przełącz na tryb ciemny (nocny)"}
    >
      <span className="sr-only">{isDark ? "Tryb jasny" : "Tryb ciemny"}</span>
      {isDark ? (
        <span className="inline-flex items-center gap-1.5" aria-hidden>
          <IconSun className="size-4 shrink-0" />
          <span className="hidden sm:inline">Jasny</span>
        </span>
      ) : (
        <span className="inline-flex items-center gap-1.5" aria-hidden>
          <IconMoon className="size-4 shrink-0" />
          <span className="hidden sm:inline">Ciemny</span>
        </span>
      )}
    </button>
  );
}

function IconMoon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function IconSun({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" strokeLinecap="round" />
    </svg>
  );
}
