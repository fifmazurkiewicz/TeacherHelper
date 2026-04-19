import { Link, useLocation } from "react-router-dom";
import { useAssistantActivity } from "@/context/AssistantActivityContext";

/**
 * Gdy użytkownik opuści widok asystenta w trakcie POST /v1/chat, lokalny stan ładowania znika.
 * Kontekst trzyma „oczekiwanie” do zakończenia żądania — ten pasek pokazuje, że backend nadal pracuje.
 */
export function AssistantBackgroundChatBanner() {
  const { pathname } = useLocation();
  const { pending, abortAssistantRequest } = useAssistantActivity();

  if (pathname === "/assistant" || !pending) return null;

  return (
    <div
      className="border-b border-accent/30 bg-accent/10 px-4 py-2 text-center text-sm text-ink-800 dark:border-accent/25 dark:bg-accent/15 dark:text-paper-100"
      role="status"
      aria-live="polite"
    >
      <span className="inline-flex items-center gap-2">
        <span
          className="inline-block size-3.5 shrink-0 animate-spin rounded-full border-2 border-accent/35 border-t-accent"
          aria-hidden
        />
        <span>
          <strong className="font-semibold text-accent dark:text-accent-muted">Asystent</strong>
          {" — "}
          {pending.label}
        </span>
        <Link to="/assistant" className="whitespace-nowrap font-medium text-accent underline underline-offset-2">
          Wróć do czatu
        </Link>
        <button
          type="button"
          onClick={() => abortAssistantRequest()}
          className="whitespace-nowrap rounded-md border border-ink-800/25 bg-white/80 px-2 py-0.5 text-xs font-medium text-ink-800 hover:bg-paper-50 dark:border-paper-100/20 dark:bg-ink-900/80 dark:text-paper-100 dark:hover:bg-ink-800"
        >
          Przerwij
        </button>
      </span>
      <span className="mt-0.5 block text-xs text-ink-600 dark:text-paper-400">
        Odpowiedź pojawi się w rozmowie po zakończeniu (czasem kilka minut przy generowaniu materiałów).
      </span>
    </div>
  );
}
