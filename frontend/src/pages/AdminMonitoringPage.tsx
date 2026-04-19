import { useEffect, useState } from "react";
import { adminStats, api, getAdminKeyHeaders, type AdminStats } from "@/lib/api";

type Monitoring = {
  application: { users: number; files: number; ai_read_audits: number };
  alerts: {
    operational: { code: string; severity: string; message: string }[];
    tokens_today_utc: number;
    soft_limit: number | null;
    hard_limit: number | null;
    webhook_configured: boolean;
    hint: string;
  };
  recent_incidents: {
    id: string;
    event_type: string;
    severity: string;
    title: string;
    detail_json: string | null;
    created_at: string | null;
  }[];
  llm_usage: {
    total_calls: number;
    total_prompt_tokens: number;
    total_completion_tokens: number;
    total_tokens_recorded: number;
    by_model: {
      model: string;
      provider: string;
      calls: number;
      prompt_tokens: number;
      completion_tokens: number;
      total_tokens: number;
    }[];
    by_call_kind_and_module: {
      call_kind: string;
      module_name: string | null;
      calls: number;
      prompt_tokens: number;
      completion_tokens: number;
      total_tokens: number;
    }[];
    description: string;
  };
  langfuse: { enabled: boolean; host: string; dashboard_url: string; hint: string };
  langgraph: { role: string };
  per_user_llm_tokens?: {
    user_id: string;
    email: string;
    tokens_today_utc: number;
    tokens_month_utc: number;
    tokens_all_time: number;
    llm_daily_token_limit: number | null;
    effective_llm_daily_token_limit: number | null;
    uses_site_default_llm_daily_limit: boolean;
  }[];
  per_user_llm_tokens_hint?: string;
};

export default function AdminMonitoringPage() {
  const [data, setData] = useState<Monitoring | null>(null);
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [webhookMsg, setWebhookMsg] = useState<string | null>(null);

  function reload() {
    setError(null);
    const h = getAdminKeyHeaders();
    Promise.all([
      api<Monitoring>("/v1/admin/monitoring", { headers: h }),
      adminStats(),
    ])
      .then(([m, s]) => {
        setData(m);
        setStats(s);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }

  useEffect(() => {
    reload();
  }, []);

  async function testWebhook() {
    setWebhookMsg(null);
    try {
      const r = await api<{ sent: boolean }>("/v1/admin/alerts/test-webhook", {
        method: "POST",
        headers: getAdminKeyHeaders(),
      });
      setWebhookMsg(r.sent ? "Testowy webhook wysłany." : "Webhook zwrócił błąd (sprawdź logi serwera).");
    } catch (e) {
      setWebhookMsg(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold">Monitoring (admin)</h1>
        <p className="mt-1 text-sm text-ink-600 dark:text-paper-400">
          Alerty limitów, incydenty (błędy LLM, blokady), zużycie tokenów oraz opcjonalny webhook.
        </p>
        <button type="button" onClick={() => reload()} className="mt-2 text-sm text-accent hover:underline">
          Odśwież dane
        </button>
      </div>

      {error && (
        <p className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200">
          {error}
          {error.includes("403") && (
            <span className="mt-2 block">
              Wymagana rola administratora (i ewentualnie poprawny nagłówek X-Admin-Key).
            </span>
          )}
        </p>
      )}

      {data && (
        <>
          <section className="rounded-xl border border-ink-800/15 bg-white p-4 dark:border-paper-100/10 dark:bg-ink-900">
            <h2 className="mb-3 font-semibold">Aplikacja</h2>
            <ul className="grid gap-2 text-sm sm:grid-cols-3">
              <li>Użytkownicy: <strong>{data.application.users}</strong></li>
              <li>Pliki: <strong>{data.application.files}</strong></li>
              <li>Audyty odczytu AI: <strong>{data.application.ai_read_audits}</strong></li>
            </ul>
            {stats && (
              <div className="mt-4 border-t border-ink-800/10 pt-3 dark:border-paper-100/10">
                <h3 className="mb-2 text-sm font-medium text-ink-700 dark:text-paper-300">
                  Endpoint <code className="rounded bg-paper-100 px-1 text-xs dark:bg-ink-800">GET /v1/admin/stats</code>
                </h3>
                <ul className="grid gap-2 text-sm sm:grid-cols-3">
                  <li>Użytkownicy: <strong>{stats.users}</strong></li>
                  <li>Pliki: <strong>{stats.files}</strong></li>
                  <li>Audyty odczytu AI: <strong>{stats.ai_read_audits}</strong></li>
                </ul>
              </div>
            )}
          </section>

          {data.per_user_llm_tokens && (
          <section className="rounded-xl border border-ink-800/15 bg-white p-4 dark:border-paper-100/10 dark:bg-ink-900">
            <h2 className="mb-2 font-semibold">Tokeny LLM wg użytkownika</h2>
            <p className="mb-3 text-xs text-ink-500">
              {data.per_user_llm_tokens_hint ??
                "Suma tokenów (bez dry-run): dzisiaj i bieżący miesiąc w UTC, oraz od początku. Kolumna „Limit/dzień” to indywidualny limit z panelu Użytkownicy (POST /v1/chat)."}
            </p>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] border-collapse text-left text-sm">
                <thead>
                  <tr className="border-b border-ink-800/15 dark:border-paper-100/15">
                    <th className="py-2 pr-4 font-medium">E-mail</th>
                    <th className="py-2 pr-4 font-medium">Dziś (UTC)</th>
                    <th className="py-2 pr-4 font-medium">Miesiąc (UTC)</th>
                    <th className="py-2 pr-4 font-medium">Łącznie</th>
                    <th className="py-2 font-medium">Limit / dzień</th>
                  </tr>
                </thead>
                <tbody>
                  {data.per_user_llm_tokens.map((row) => (
                    <tr key={row.user_id} className="border-b border-ink-800/10 dark:border-paper-100/10">
                      <td className="py-2 pr-4 font-mono text-xs">{row.email}</td>
                      <td className="py-2 pr-4">{row.tokens_today_utc.toLocaleString("pl-PL")}</td>
                      <td className="py-2 pr-4">{row.tokens_month_utc.toLocaleString("pl-PL")}</td>
                      <td className="py-2 pr-4">{row.tokens_all_time.toLocaleString("pl-PL")}</td>
                      <td className="py-2">
                        {row.effective_llm_daily_token_limit === null && !row.uses_site_default_llm_daily_limit ? (
                          <span className="text-ink-500">Brak (konto)</span>
                        ) : (
                          <>
                            <span>{(row.effective_llm_daily_token_limit ?? 0).toLocaleString("pl-PL")}</span>
                            {row.uses_site_default_llm_daily_limit && (
                              <span className="ml-1 text-xs text-ink-400">(domyślny)</span>
                            )}
                          </>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {data.per_user_llm_tokens.length === 0 && (
                <p className="text-sm text-ink-500">Brak użytkowników.</p>
              )}
            </div>
          </section>
          )}

          <section className="rounded-xl border border-ink-800/15 bg-white p-4 dark:border-paper-100/10 dark:bg-ink-900">
            <h2 className="mb-2 font-semibold">Alerty operacyjne</h2>
            <p className="mb-2 text-xs text-ink-500">{data.alerts.hint}</p>
            <ul className="mb-3 text-sm">
              <li>Tokeny dziś (UTC): <strong>{data.alerts.tokens_today_utc}</strong></li>
              <li>Limit miękki: {data.alerts.soft_limit ?? "—"}</li>
              <li>Limit twardy: {data.alerts.hard_limit ?? "—"}</li>
              <li>Webhook: {data.alerts.webhook_configured ? "skonfigurowany" : "brak ALERT_WEBHOOK_URL"}</li>
            </ul>
            {data.alerts.operational.length === 0 ? (
              <p className="text-sm text-ink-500">Brak aktywnych alertów limitów.</p>
            ) : (
              <ul className="space-y-2">
                {data.alerts.operational.map((a) => (
                  <li
                    key={a.code}
                    className={`rounded-md border px-3 py-2 text-sm ${
                      a.severity === "critical"
                        ? "border-red-300 bg-red-50 text-red-900 dark:border-red-900 dark:bg-red-950/30 dark:text-red-100"
                        : "border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-100"
                    }`}
                  >
                    <strong>{a.code}</strong> ({a.severity}) — {a.message}
                  </li>
                ))}
              </ul>
            )}
            <button
              type="button"
              onClick={() => void testWebhook()}
              className="mt-3 rounded-md border border-ink-800/20 px-3 py-1.5 text-sm dark:border-paper-100/20"
            >
              Wyślij test webhooka
            </button>
            {webhookMsg && <p className="mt-2 text-xs text-ink-600 dark:text-paper-400">{webhookMsg}</p>}
          </section>

          <section className="rounded-xl border border-ink-800/15 bg-white p-4 dark:border-paper-100/10 dark:bg-ink-900">
            <h2 className="mb-2 font-semibold">Ostatnie incydenty</h2>
            <ul className="max-h-64 space-y-2 overflow-y-auto text-xs">
              {data.recent_incidents.map((i) => (
                <li key={i.id} className="border-b border-ink-800/10 pb-2 dark:border-paper-100/10">
                  <span className="font-mono text-ink-500">{i.created_at}</span>{" "}
                  <strong>{i.event_type}</strong> [{i.severity}] {i.title}
                </li>
              ))}
            </ul>
            {data.recent_incidents.length === 0 && <p className="text-sm text-ink-500">Brak wpisów.</p>}
          </section>

          <section className="rounded-xl border border-ink-800/15 bg-white p-4 dark:border-paper-100/10 dark:bg-ink-900">
            <h2 className="mb-1 font-semibold">LLM — sumy</h2>
            <p className="mb-3 text-xs text-ink-500">{data.llm_usage.description}</p>
            <ul className="grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-4">
              <li>Wywołania: <strong>{data.llm_usage.total_calls}</strong></li>
              <li>Tokeny wejścia: <strong>{data.llm_usage.total_prompt_tokens}</strong></li>
              <li>Tokeny wyjścia: <strong>{data.llm_usage.total_completion_tokens}</strong></li>
              <li>Tokeny (suma): <strong>{data.llm_usage.total_tokens_recorded}</strong></li>
            </ul>
          </section>

          <section className="rounded-xl border border-ink-800/15 bg-white p-4 dark:border-paper-100/10 dark:bg-ink-900">
            <h2 className="mb-3 font-semibold">Wg modelu i dostawcy</h2>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px] border-collapse text-left text-sm">
                <thead>
                  <tr className="border-b border-ink-800/15 dark:border-paper-100/15">
                    <th className="py-2 pr-4 font-medium">Model</th>
                    <th className="py-2 pr-4 font-medium">Dostawca</th>
                    <th className="py-2 pr-4 font-medium">Zapytania</th>
                    <th className="py-2 pr-4 font-medium">Prompt</th>
                    <th className="py-2 pr-4 font-medium">Completion</th>
                    <th className="py-2 font-medium">Razem</th>
                  </tr>
                </thead>
                <tbody>
                  {data.llm_usage.by_model.map((row) => (
                    <tr key={`${row.provider}:${row.model}`} className="border-b border-ink-800/10 dark:border-paper-100/10">
                      <td className="py-2 pr-4 font-mono text-xs">{row.model}</td>
                      <td className="py-2 pr-4">{row.provider}</td>
                      <td className="py-2 pr-4">{row.calls}</td>
                      <td className="py-2 pr-4">{row.prompt_tokens}</td>
                      <td className="py-2 pr-4">{row.completion_tokens}</td>
                      <td className="py-2">{row.total_tokens}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {data.llm_usage.by_model.length === 0 && (
                <p className="text-sm text-ink-500">Brak zapisów — wykonaj czat lub inną operację korzystającą z modelu.</p>
              )}
            </div>
          </section>

          <section className="rounded-xl border border-ink-800/15 bg-white p-4 dark:border-paper-100/10 dark:bg-ink-900">
            <h2 className="mb-3 font-semibold">Wg typu wywołania</h2>
            <p className="mb-2 text-xs text-ink-500">
              orchestrator — plan z czatu; module — generacja materiału; intent_analyze — endpoint diagnostyczny.
            </p>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[560px] border-collapse text-left text-sm">
                <thead>
                  <tr className="border-b border-ink-800/15 dark:border-paper-100/15">
                    <th className="py-2 pr-4 font-medium">Typ</th>
                    <th className="py-2 pr-4 font-medium">Moduł</th>
                    <th className="py-2 pr-4 font-medium">Zapytania</th>
                    <th className="py-2 pr-4 font-medium">Prompt</th>
                    <th className="py-2 pr-4 font-medium">Completion</th>
                    <th className="py-2 font-medium">Razem</th>
                  </tr>
                </thead>
                <tbody>
                  {data.llm_usage.by_call_kind_and_module.map((row, i) => (
                    <tr key={`${row.call_kind}-${row.module_name ?? "x"}-${i}`} className="border-b border-ink-800/10 dark:border-paper-100/10">
                      <td className="py-2 pr-4">{row.call_kind}</td>
                      <td className="py-2 pr-4">{row.module_name ?? "—"}</td>
                      <td className="py-2 pr-4">{row.calls}</td>
                      <td className="py-2 pr-4">{row.prompt_tokens}</td>
                      <td className="py-2 pr-4">{row.completion_tokens}</td>
                      <td className="py-2">{row.total_tokens}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="rounded-xl border border-ink-800/15 bg-white p-4 dark:border-paper-100/10 dark:bg-ink-900">
            <h2 className="mb-2 font-semibold">Langfuse</h2>
            <p className="text-sm">
              Status: <strong>{data.langfuse.enabled ? "włączony (klucze w .env)" : "wyłączony"}</strong>
            </p>
            <p className="mt-2 text-sm text-ink-600 dark:text-paper-400">{data.langfuse.hint}</p>
            {data.langfuse.enabled && (
              <a
                href={data.langfuse.dashboard_url}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-3 inline-block text-sm text-accent hover:underline"
              >
                Otwórz dashboard Langfuse
              </a>
            )}
          </section>

          <section className="rounded-xl border border-ink-800/10 bg-paper-100/80 p-4 dark:border-paper-100/10 dark:bg-ink-800/50">
            <h2 className="mb-2 text-sm font-semibold text-ink-700 dark:text-paper-300">LangGraph</h2>
            <p className="text-sm text-ink-700 dark:text-paper-300">{data.langgraph.role}</p>
          </section>
        </>
      )}

      {!data && !error && <p className="text-ink-500">Ładowanie…</p>}
    </div>
  );
}
