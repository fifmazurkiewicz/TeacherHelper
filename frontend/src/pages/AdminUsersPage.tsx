import { useEffect, useState } from "react";
import { PasswordField } from "@/components/PasswordField";
import { api } from "@/lib/api";

type AdminUser = {
  id: string;
  email: string;
  display_name: string | null;
  role: string;
  is_approved: boolean;
  rate_limit_rpm: number | null;
  llm_monthly_cost_limit_usd: number | null;
  effective_llm_monthly_cost_limit_usd: number | null;
  uses_site_default_llm_monthly_limit: boolean;
  llm_cost_month_usd: number;
  llm_tokens_month: number;
  llm_monthly_limit_reached: boolean;
  created_at: string;
};

function formatUsd(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("pl-PL", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  }).format(value);
}

function formatTokens(value: number): string {
  return new Intl.NumberFormat("pl-PL").format(value);
}

export default function AdminUsersPage() {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [meId, setMeId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editRpm, setEditRpm] = useState("");
  const [editingCostId, setEditingCostId] = useState<string | null>(null);
  const [editCostLimit, setEditCostLimit] = useState("");
  const [resetPwId, setResetPwId] = useState<string | null>(null);
  const [newPassword, setNewPassword] = useState("");
  const [busy, setBusy] = useState(false);

  function reload() {
    setError(null);
    api<AdminUser[]>("/v1/admin/users")
      .then(setUsers)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }

  useEffect(() => {
    reload();
    api<{ id: string }>("/v1/auth/me")
      .then((me) => setMeId(me.id))
      .catch(() => setMeId(null));
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
        });
      } else {
        if (isNaN(rpm) || rpm < 1) {
          setError("Rate limit musi być liczbą >= 1 lub pusty (domyślny).");
          return;
        }
        await api(`/v1/admin/users/${userId}`, {
          method: "PATCH",
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

  async function saveCostLimit(userId: string) {
    setError(null);
    setSuccess(null);
    setBusy(true);
    try {
      const raw = editCostLimit.trim();
      if (raw === "") {
        await api(`/v1/admin/users/${userId}/llm-monthly-cost-limit`, {
          method: "DELETE",
        });
      } else {
        const limit = parseFloat(raw.replace(",", "."));
        if (isNaN(limit) || limit < 0) {
          setError("Podaj kwotę ≥ 0 (0 = brak limitu na konto) albo zostaw puste dla domyślnego z serwera.");
          return;
        }
        await api(`/v1/admin/users/${userId}`, {
          method: "PATCH",
          json: { llm_monthly_cost_limit_usd: limit },
        });
      }
      setEditingCostId(null);
      setSuccess("Limit kosztu LLM / miesiąc zapisany.");
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Błąd");
    } finally {
      setBusy(false);
    }
  }

  async function setApproval(u: AdminUser, isApproved: boolean) {
    if (!window.confirm(isApproved ? `Akceptować konto ${u.email}?` : `Cofnąć dostęp dla ${u.email}?`)) return;
    setError(null);
    setSuccess(null);
    setBusy(true);
    try {
      await api(`/v1/admin/users/${u.id}`, {
        method: "PATCH",
        json: { is_approved: isApproved },
      });
      setSuccess(isApproved ? "Konto zaakceptowane." : "Dostęp cofnięty.");
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
          Status akceptacji, role, rate limit (żądania/min), bieżące zużycie LLM (koszt i tokeny w miesiącu UTC),
          miesięczny limit kosztu w USD (wszystkie modele) i reset haseł. Panel wymaga roli administratora (JWT).
        </p>
        <button type="button" onClick={reload} className="mt-2 text-sm text-accent hover:underline">
          Odśwież
        </button>
      </div>

      {error && <p className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200">{error}</p>}
      {success && <p className="rounded-lg border border-green-200 bg-green-50 p-3 text-sm text-green-800 dark:border-green-900 dark:bg-green-950/40 dark:text-green-200">{success}</p>}

      <div className="overflow-x-auto rounded-xl border border-ink-800/15 bg-white dark:border-paper-100/10 dark:bg-ink-900">
        <table className="w-full border-collapse text-left text-sm">
          <thead>
            <tr className="border-b border-ink-800/15 dark:border-paper-100/15">
              <th className="px-3 py-3 align-middle font-medium">E-mail</th>
              <th className="hidden px-3 py-3 align-middle font-medium xl:table-cell">Nazwa</th>
              <th className="px-3 py-3 align-middle font-medium">Rola</th>
              <th className="px-3 py-3 align-middle font-medium">Status</th>
              <th className="px-3 py-3 align-middle font-medium" title="Rate limit (żądania na minutę)">
                Rate limit
              </th>
              <th className="px-3 py-3 align-middle font-medium" title="Zużycie LLM w bieżącym miesiącu UTC">
                Zużycie LLM
              </th>
              <th className="px-3 py-3 align-middle font-medium" title="Miesięczny limit kosztu LLM w USD">
                Limit LLM
              </th>
              <th className="px-3 py-3 pr-4 align-middle font-medium">Akcje</th>
            </tr>
          </thead>
          <tbody>
            {[...users]
              .sort((a, b) => Number(a.is_approved) - Number(b.is_approved) || a.email.localeCompare(b.email))
              .map((u) => (
              <tr
                key={u.id}
                className={`border-b border-ink-800/10 dark:border-paper-100/10 ${
                  u.is_approved ? "" : "bg-amber-50/70 dark:bg-amber-950/20"
                }`}
              >
                <td className="px-3 py-3.5 align-middle">
                  <span className="break-all font-mono text-xs leading-snug">{u.email}</span>
                </td>
                <td className="hidden px-3 py-3.5 align-middle text-ink-700 xl:table-cell dark:text-paper-300">
                  {u.display_name ?? <span className="text-ink-400">—</span>}
                </td>
                <td className="px-3 py-3.5 align-middle">
                  <select
                    value={u.role}
                    disabled={busy}
                    onChange={(e) => void changeRole(u, e.target.value)}
                    className="w-full max-w-[6.5rem] rounded border border-ink-800/20 bg-paper-50 px-2 py-1.5 text-xs dark:border-paper-100/20 dark:bg-ink-950"
                  >
                    <option value="teacher">teacher</option>
                    <option value="admin">admin</option>
                  </select>
                </td>
                <td className="px-3 py-3.5 align-middle">
                  <div className="flex flex-col items-start gap-1.5">
                    <span
                      className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${
                        u.is_approved
                          ? "bg-green-100 text-green-800 dark:bg-green-950/50 dark:text-green-200"
                          : "bg-amber-100 text-amber-900 dark:bg-amber-950/60 dark:text-amber-200"
                      }`}
                    >
                      {u.is_approved ? "Zaakceptowany" : "Oczekuje"}
                    </span>
                    {!u.is_approved && (
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => void setApproval(u, true)}
                        className="rounded-md bg-accent px-2 py-1 text-xs font-medium text-white hover:bg-accent/90 disabled:opacity-50"
                      >
                        Akceptuj
                      </button>
                    )}
                  </div>
                </td>
                <td className="px-3 py-3.5 align-middle text-ink-700 dark:text-paper-300">
                  {editingId === u.id ? (
                    <div className="flex flex-col gap-1.5">
                      <input
                        type="number"
                        min={1}
                        value={editRpm}
                        onChange={(e) => setEditRpm(e.target.value)}
                        placeholder="domyślny"
                        className="w-full max-w-[6rem] rounded border border-ink-800/20 px-2 py-1 text-xs dark:border-paper-100/20 dark:bg-ink-950"
                      />
                      <div className="flex flex-wrap gap-x-2 gap-y-0.5">
                        <button type="button" onClick={() => void saveRateLimit(u.id)} disabled={busy} className="text-xs text-accent hover:underline">
                          Zapisz
                        </button>
                        <button type="button" onClick={() => setEditingId(null)} className="text-xs text-ink-500 hover:underline">
                          Anuluj
                        </button>
                      </div>
                    </div>
                  ) : (
                    <span>{u.rate_limit_rpm ?? <span className="text-ink-400">domyślny</span>}</span>
                  )}
                </td>
                <td className="px-3 py-3.5 align-middle">
                  <div className="space-y-1 leading-snug">
                    <div className={u.llm_monthly_limit_reached ? "font-medium text-red-600 dark:text-red-400" : ""}>
                      {formatUsd(u.llm_cost_month_usd)}
                      {u.effective_llm_monthly_cost_limit_usd !== null && (
                        <span className="text-ink-500 dark:text-paper-400">
                          {" "}
                          / {formatUsd(u.effective_llm_monthly_cost_limit_usd)}
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-ink-500 dark:text-paper-400">
                      {formatTokens(u.llm_tokens_month)} tokenów
                    </div>
                    {u.llm_monthly_limit_reached && (
                      <div className="text-xs font-medium text-red-600 dark:text-red-400">Limit wyczerpany</div>
                    )}
                  </div>
                </td>
                <td className="px-3 py-3.5 align-middle">
                  {editingCostId === u.id ? (
                    <div className="flex flex-col gap-1.5">
                      <input
                        type="text"
                        inputMode="decimal"
                        value={editCostLimit}
                        onChange={(e) => setEditCostLimit(e.target.value)}
                        placeholder="0 lub puste"
                        title="0 = brak limitu na konto; puste + Zapisz = domyślny z serwera"
                        className="w-full max-w-[7rem] rounded border border-ink-800/20 px-2 py-1 text-xs dark:border-paper-100/20 dark:bg-ink-950"
                      />
                      <div className="flex flex-wrap gap-x-2 gap-y-0.5">
                        <button type="button" onClick={() => void saveCostLimit(u.id)} disabled={busy} className="text-xs text-accent hover:underline">
                          Zapisz
                        </button>
                        <button type="button" onClick={() => setEditingCostId(null)} className="text-xs text-ink-500 hover:underline">
                          Anuluj
                        </button>
                      </div>
                    </div>
                  ) : u.effective_llm_monthly_cost_limit_usd === null && !u.uses_site_default_llm_monthly_limit ? (
                    <span className="text-ink-600 dark:text-paper-300">Brak limitu</span>
                  ) : (
                    <span className="leading-snug">
                      <strong>{formatUsd(u.effective_llm_monthly_cost_limit_usd)}</strong>
                      {u.uses_site_default_llm_monthly_limit && (
                        <span className="mt-0.5 block text-xs text-ink-400">domyślny</span>
                      )}
                    </span>
                  )}
                </td>
                <td className="px-3 py-3.5 pr-4 align-middle">
                  <div className="flex flex-col items-start gap-1">
                    {u.is_approved && meId !== u.id && (
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => void setApproval(u, false)}
                        className="text-left text-xs text-red-600 hover:underline dark:text-red-400"
                      >
                        Cofnij dostęp
                      </button>
                    )}
                    {editingId !== u.id && (
                      <button
                        type="button"
                        onClick={() => { setEditingCostId(null); setEditingId(u.id); setEditRpm(u.rate_limit_rpm?.toString() ?? ""); }}
                        className="text-left text-xs text-accent hover:underline"
                      >
                        Zmień limit
                      </button>
                    )}
                    {editingCostId !== u.id && (
                      <button
                        type="button"
                        onClick={() => {
                          setEditingId(null);
                          setEditingCostId(u.id);
                          setEditCostLimit(
                            u.llm_monthly_cost_limit_usd === null || u.llm_monthly_cost_limit_usd === undefined
                              ? ""
                              : String(u.llm_monthly_cost_limit_usd),
                          );
                        }}
                        className="text-left text-xs text-accent hover:underline"
                      >
                        Limit kosztu
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => {
                        setResetPwId(resetPwId === u.id ? null : u.id);
                        setNewPassword("");
                      }}
                      className="text-left text-xs text-ink-600 hover:underline dark:text-paper-400"
                    >
                      Reset hasła
                    </button>
                  </div>
                  {resetPwId === u.id && (
                    <div className="mt-2 flex flex-col gap-2">
                      <PasswordField
                        key={u.id}
                        ariaLabel={`Nowe hasło dla ${u.email}`}
                        value={newPassword}
                        onChange={setNewPassword}
                        minLength={8}
                        autoComplete="new-password"
                        placeholder="Nowe hasło (min. 8 zn.)"
                        compact
                        fieldWrapperClassName="w-full"
                      />
                      <button
                        type="button"
                        onClick={() => void resetPassword(u.id)}
                        disabled={busy}
                        className="self-start text-xs text-red-600 hover:underline dark:text-red-400"
                      >
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
