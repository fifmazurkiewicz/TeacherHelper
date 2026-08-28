import { useApiPulse } from "./ApiPulseProvider";

export function ApiPulseBanner() {
  const { isHealthy, isWaking, checkNow } = useApiPulse();

  if (isHealthy && !isWaking) return null;

  return (
    <div
      className="border-b border-amber-500/35 bg-amber-50 px-4 py-2 text-center text-sm text-amber-950 dark:border-amber-400/25 dark:bg-amber-950/40 dark:text-amber-100"
      role="status"
      aria-live="polite"
    >
      <span className="inline-flex flex-wrap items-center justify-center gap-2">
        <span
          className="inline-block size-3.5 shrink-0 animate-spin rounded-full border-2 border-amber-500/35 border-t-amber-600 dark:border-amber-300/35 dark:border-t-amber-200"
          aria-hidden
        />
        <span>Budzenie API… serwer mógł przejść w uśpienie (ok. 30–60 s).</span>
        <button
          type="button"
          onClick={() => void checkNow()}
          className="rounded-md border border-amber-600/30 bg-white/90 px-2 py-0.5 text-xs font-medium text-amber-950 hover:bg-amber-100 dark:border-amber-300/25 dark:bg-ink-900/80 dark:text-amber-100 dark:hover:bg-ink-800"
        >
          Spróbuj ponownie
        </button>
      </span>
    </div>
  );
}
