import { useEffect, useState } from "react";
import { api, getAdminKeyHeaders } from "@/lib/api";

type AdminUser = {
  id: string;
  email: string;
  display_name: string | null;
  role: string;
  rate_limit_rpm: number | null;
  llm_daily_token_limit: number | null;
  effective_llm_daily_token_limit: number | null;
  uses_site_default_llm_daily_limit: boolean;
  created_at: string;
};

export default function AdminUsersPage() {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editRpm, setEditRpm] = useState("");
  const [editingTokenId, setEditingTokenId] = useState<string | null>(null);
  const [editTokenLimit, setEditTokenLimit] = useState("");
  const [resetPwId, setResetPwId] = useState<string | null>(null);
  const [newPassword, setNewPassword] = useState("");
  const [busy, setBusy] = useState(false);

  function reload() {
    setError(null);
    api<AdminUser[]>("/v1/admin/users", { headers: getAdminKeyHeaders() })
      .then(setUsers)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }

  useEffect(() => {
    reload();
  }, []);

  async function saveRateLimit(userId: string) {
    setError(null);
    setSuccess(null);
    setBusy(true);
    try {
      const rpm = editRpm.trim() === "" ? null : parseInt(editRpm, 10);
      if (rpm === null) {
        await api(`/v1/admin/users/${userId}/rate-limit`, {
          method: "DELETE",
          headers: getAdminKeyHeaders(),
        });
      } else {
        if (isNaN(rpm) || rpm < 1) {
          setError("Rate limit musi być liczbą >= 1 lub pusty (domyślny).");
          return;
        }
        await api(`/v1/admin/users/${userId}`, {
          method: "PATCH",
          headers: getAdminKeyHeaders(),
          json: { rate_limit_rpm: rpm },
        });
      }
      setEditingId(null);
      setSuccess("Rate limit zapisany.");
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Błąd");
    } finally {
      setBusy(false);
    }
  }

  async function saveTokenLimit(userId: string) {
    setError(null);
    setSuccess(null);
    setBusy(true);
    try {
      const raw = editTokenLimit.trim();
      if (raw === "") {
        await api(`/v1/admin/users/${userId}/llm-daily-token-limit`, {
          method: "DELETE",
          headers: getAdminKeyHeaders(),
        });
      } else {
        const limit = parseInt(raw, 10);
        if (isNaN(limit) || limit < 0) {
          setError("Podaj liczbę całkowitą ≥ 0 (0 = brak limitu na konto) albo zostaw puste dla domyślnego z konfiguracji.");
          return;
        }
        await api(`/v1/admin/users/${userId}`, {
          method: "PATCH",
          headers: getAdminKeyHeaders(),
          json: { llm_daily_token_limit: limit },
        });
      }
      setEditingTokenId(null);
      setSuccess("Limit tokenów / dobę zapisany.");
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Błąd");
    } finally {
      setBusy(false);
    }
  }

  async function changeRole(u: AdminUser, newRole: string) {
    if (newRole === u.role) return;
    if (!window.confirm(`Ustawić rolę użytkownika ${u.email} na „${newRole}”?`)) return;
    setError(null);
    setSuccess(null);
    setBusy(true);
    try {
      await api(`/v1/admin/users/${u.id}`, {
        method: "PATCH",
        headers: getAdminKeyHeaders(),
        json: { role: newRole },
      });
      setSuccess("Rola zaktualizowana.");
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Błąd");
    } finally {
      setBusy(false);
    }
  }

  async function resetPassword(userId: string) {
    if (!newPassword || newPassword.length < 8) {
      setError("Hasło musi mieć min. 8 znaków.");
      return;
    }
    setError(null);
    setSuccess(null);
    setBusy(true);
    try {
      await api(`/v1/admin/users/${userId}/reset-password`, {
        method: "POST",
        headers: getAdminKeyHeaders(),
        json: { new_password: newPassword },
      });
      setResetPwId(null);
      setNewPassword("");
      setSuccess("Hasło zresetowane.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Błąd");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Użytkownicy</h1>
        <p className="mt-1 text-sm text-ink-600 dark:text-paper-400">
          Role, rate limit (żądania/min), dzienny limit tokenów LLM (UTC, dotyczy czatu) i reset haseł. Przy włączonym{" "}
          <code className="rounded bg-paper-100 px-1 dark:bg-ink-800">ADMIN_API_KEY</code> ustaw też{" "}
          <code className="rounded bg-paper-100 px-1 dark:bg-ink-800">VITE_ADMIN_API_KEY</code> we frontendzie.
        </p>
        <button type="button" onClick={reload} className="mt-2 text-sm text-accent hover:underline">
          Odśwież
        </button>
      </div>

      {error && <p className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200">{error}</p>}
      {success && <p className="rounded-lg border border-green-200 bg-green-50 p-3 text-sm text-green-800 dark:border-green-900 dark:bg-green-950/40 dark:text-green-200">{success}</p>}

      <div className="overflow-x-auto rounded-xl border border-ink-800/15 bg-white dark:border-paper-100/10 dark:bg-ink-900">
        <table className="w-full min-w-[960px] border-collapse text-left text-sm">
          <thead>
            <tr className="border-b border-ink-800/15 dark:border-paper-100/15">
              <th className="px-4 py-3 font-medium">E-mail</th>
              <th className="px-4 py-3 font-medium">Nazwa</th>
              <th className="px-4 py-3 font-medium">Rola</th>
              <th className="px-4 py-3 font-medium">Rate limit (req/min)</th>
              <th className="px-4 py-3 font-medium">Limit tokenów / dobę (UTC)</th>
              <th className="px-4 py-3 font-medium">Akcje</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id} className="border-b border-ink-800/10 dark:border-paper-100/10">
                <td className="px-4 py-3 font-mono text-xs">{u.email}</td>
                <td className="px-4 py-3">{u.display_name ?? "—"}</td>
                <td className="px-4 py-3">
                  <select
                    value={u.role}
                    disabled={busy}
                    onChange={(e) => void changeRole(u, e.target.value)}
                    className="rounded border border-ink-800/20 bg-paper-50 px-2 py-1 text-xs dark:border-paper-100/20 dark:bg-ink-950"
                  >
                    <option value="teacher">teacher</option>
                    <option value="admin">admin</option>
                  </select>
                </td>
                <td className="px-4 py-3">
                  {editingId === u.id ? (
                    <div className="flex items-center gap-2">
                      <input
                        type="number"
                        min={1}
                        value={editRpm}
                        onChange={(e) => setEditRpm(e.target.value)}
                        placeholder="domyślny"
                        className="w-24 rounded border border-ink-800/20 px-2 py-1 text-xs dark:border-paper-100/20 dark:bg-ink-950"
                      />
                      <button type="button" onClick={() => void saveRateLimit(u.id)} disabled={busy} className="text-xs text-accent hover:underline">
                        Zapisz
                      </button>
                      <button type="button" onClick={() => setEditingId(null)} className="text-xs text-ink-500 hover:underline">
                        Anuluj
                      </button>
                    </div>
                  ) : (
                    <span>
                      {u.rate_limit_rpm ?? <span className="text-ink-400">domyślny</span>}
                    </span>
                  )}
                </td>
                <td className="px-4 py-3">
                  {editingTokenId === u.id ? (
                    <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                      <input
                        type="number"
                        min={0}
                        value={editTokenLimit}
                        onChange={(e) => setEditTokenLimit(e.target.value)}
                        placeholder="0 lub puste"
                        title="0 = brak limitu na konto; puste + Zapisz = domyślny z serwera"
                        className="w-36 rounded border border-ink-800/20 px-2 py-1 text-xs dark:border-paper-100/20 dark:bg-ink-950"
                      />
                      <button type="button" onClick={() => void saveTokenLimit(u.id)} disabled={busy} className="text-xs text-accent hover:underline">
                        Zapisz
                      </button>
                      <button type="button" onClick={() => setEditingTokenId(null)} className="text-xs text-ink-500 hover:underline">
                        Anuluj
                      </button>
                    </div>
                  ) : u.effective_llm_daily_token_limit === null && !u.uses_site_default_llm_daily_limit ? (
                    <span className="text-ink-600 dark:text-paper-300">Brak limitu (konto)</span>
                  ) : (
                    <span>
                      <strong>{(u.effective_llm_daily_token_limit ?? 0).toLocaleString("pl-PL")}</strong>
                      {u.uses_site_default_llm_daily_limit && (
                        <span className="ml-1 text-ink-400">(domyślny)</span>
                      )}
                    </span>
                  )}
                </td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-2">
                    {editingId !== u.id && (
                      <button
                        type="button"
                        onClick={() => { setEditingTokenId(null); setEditingId(u.id); setEditRpm(u.rate_limit_rpm?.toString() ?? ""); }}
                        className="text-xs text-accent hover:underline"
                      >
                        Zmień limit
                      </button>
                    )}
                    {editingTokenId !== u.id && (
                      <button
                        type="button"
                        onClick={() => {
                          setEditingId(null);
                          setEditingTokenId(u.id);
                          setEditTokenLimit(
                            u.llm_daily_token_limit === null || u.llm_daily_token_limit === undefined
                              ? ""
                              : String(u.llm_daily_token_limit),
                          );
                        }}
                        className="text-xs text-accent hover:underline"
                      >
                        Limit tokenów
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => { setResetPwId(resetPwId === u.id ? null : u.id); setNewPassword(""); }}
                      className="text-xs text-ink-600 hover:underline dark:text-paper-400"
                    >
                      Reset hasła
                    </button>
                  </div>
                  {resetPwId === u.id && (
                    <div className="mt-2 flex items-center gap-2">
                      <input
                        type="password"
                        value={newPassword}
                        onChange={(e) => setNewPassword(e.target.value)}
                        placeholder="Nowe hasło (min. 8 zn.)"
                        className="w-48 rounded border border-ink-800/20 px-2 py-1 text-xs dark:border-paper-100/20 dark:bg-ink-950"
                      />
                      <button type="button" onClick={() => void resetPassword(u.id)} disabled={busy} className="text-xs text-red-600 hover:underline dark:text-red-400">
                        Resetuj
                      </button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {users.length === 0 && <p className="p-4 text-sm text-ink-500">Brak użytkowników.</p>}
      </div>
    </div>
  );
}
