import { useState } from "react";
import { analyzeIntent, type IntentAnalyzeResponse } from "@/lib/api";

export default function IntentAnalyzePage() {
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<IntentAnalyzeResponse | null>(null);

  async function run(e: React.FormEvent) {
    e.preventDefault();
    const t = message.trim();
    if (!t) return;
    setError(null);
    setResult(null);
    setBusy(true);
    try {
      const r = await analyzeIntent(t);
      setResult(r);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Błąd analizy");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Analiza intencji</h1>
        <p className="mt-1 text-sm text-ink-600 dark:text-paper-400">
          Diagnostyka: ten sam kontrakt JSON co orchestrator czatu, bez zapisu plików i bez uruchamiania modułów. Wywołuje{" "}
          <code className="rounded bg-paper-100 px-1 text-xs dark:bg-ink-800">POST /v1/intent/analyze</code>.
        </p>
      </div>

      {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}

      <form onSubmit={run} className="space-y-3 rounded-xl border border-ink-800/15 bg-white p-4 dark:border-paper-100/10 dark:bg-ink-900">
        <label className="block text-sm font-medium">Tekst użytkownika</label>
        <textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          rows={4}
          className="w-full rounded-md border border-ink-800/20 bg-paper-50 px-3 py-2 text-sm dark:border-paper-100/20 dark:bg-ink-950"
          placeholder="Np. Przygotuj scenariusz lekcji o fotosyntezie dla klasy 7…"
        />
        <button
          type="submit"
          disabled={busy || !message.trim()}
          className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-dim disabled:opacity-50"
        >
          {busy ? "Analizuję…" : "Analizuj"}
        </button>
      </form>

      {result && (
        <div className="space-y-4 rounded-xl border border-ink-800/15 bg-white p-4 dark:border-paper-100/10 dark:bg-ink-900">
          <div>
            <h2 className="text-sm font-semibold text-ink-700 dark:text-paper-300">Podsumowanie (odpowiedź asystenta w planie)</h2>
            <p className="mt-1 whitespace-pre-wrap text-sm text-ink-800 dark:text-paper-200">{result.summary}</p>
          </div>
          <div>
            <h2 className="text-sm font-semibold text-ink-700 dark:text-paper-300">Sugerowane moduły</h2>
            <p className="mt-1 text-sm text-ink-800 dark:text-paper-200">
              {result.suggested_modules.length ? result.suggested_modules.join(", ") : "—"}
            </p>
          </div>
          <div>
            <h2 className="text-sm font-semibold text-ink-700 dark:text-paper-300">Wymaga doprecyzowania</h2>
            <p className="mt-1 text-sm text-ink-800 dark:text-paper-200">{result.needs_clarification ? "tak" : "nie"}</p>
          </div>
          <details className="text-sm">
            <summary className="cursor-pointer font-medium text-accent">Surowy JSON planu</summary>
            <pre className="mt-2 max-h-64 overflow-auto rounded-md bg-paper-100 p-3 text-xs dark:bg-ink-950">{result.raw_json}</pre>
          </details>
        </div>
      )}
    </div>
  );
}
