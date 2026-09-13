import { useEffect, useState } from "react";
import {
  api,
  deleteAllConversations,
  deleteAllMaterials,
  deleteMyAccount,
  downloadMyData,
  setToken,
  type AuthMe,
} from "@/lib/api";
import { useNavigate } from "react-router-dom";

export default function ProfilePage() {
  const navigate = useNavigate();
  const [me, setMe] = useState<AuthMe | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [privacyBusy, setPrivacyBusy] = useState<"export" | "conversations" | "materials" | "delete" | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [confirmation, setConfirmation] = useState("");

  async function exportData() {
    setError(null);
    setPrivacyBusy("export");
    try {
      const { blob, filename } = await downloadMyData();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Nie udało się wyeksportować danych");
    } finally {
      setPrivacyBusy(null);
    }
  }

  async function deleteAccount() {
    setError(null);
    setPrivacyBusy("delete");
    try {
      await deleteMyAccount(confirmation);
      await setToken(null);
      navigate("/login", { replace: true });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Nie udało się usunąć konta");
      setPrivacyBusy(null);
    }
  }

  async function clearData(kind: "conversations" | "materials") {
    const label = kind === "conversations" ? "wszystkie rozmowy" : "wszystkie przesłane i wygenerowane materiały";
    if (!window.confirm(`Czy na pewno usunąć ${label}? Tej operacji nie można cofnąć.`)) return;
    setError(null);
    setPrivacyBusy(kind);
    try {
      if (kind === "conversations") await deleteAllConversations();
      else await deleteAllMaterials();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Nie udało się usunąć danych");
    } finally {
      setPrivacyBusy(null);
    }
  }

  useEffect(() => {
    api<AuthMe>("/v1/auth/me")
      .then(setMe)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Błąd"));
  }, []);

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Profil</h1>
      {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
      {!me && !error && <p className="text-ink-500">Ładowanie…</p>}
      {me && (
        <dl className="max-w-md space-y-2 rounded-xl border border-ink-800/15 bg-white p-6 dark:border-paper-100/10 dark:bg-ink-900">
          <div>
            <dt className="text-xs uppercase text-ink-500">E-mail</dt>
            <dd className="font-medium">{me.email}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-ink-500">Nazwa</dt>
            <dd>{me.display_name ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-ink-500">Rola</dt>
            <dd>{me.role}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-ink-500">Status</dt>
            <dd>{me.is_approved ? "Zaakceptowany" : "Oczekuje na akceptację"}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-ink-500">ID</dt>
            <dd className="break-all font-mono text-xs">{me.id}</dd>
          </div>
        </dl>
      )}
      <p className="max-w-xl text-sm text-ink-600 dark:text-paper-400">
        Administrator może zmieniać role innych użytkowników w zakładce{" "}
        <span className="font-medium">Użytkownicy</span>. Endpointy{" "}
        <code className="rounded bg-paper-100 px-1 dark:bg-ink-800">/v1/admin/*</code> wymagają roli administratora
        (JWT). Opcjonalny <code className="rounded bg-paper-100 px-1 dark:bg-ink-800">ADMIN_API_KEY</code> jest tylko
        dla skryptów maszynowych — nie umieszczaj go w SPA.
      </p>
      <section className="max-w-xl space-y-2 rounded-xl border border-ink-800/15 bg-white p-4 text-sm text-ink-600 dark:border-paper-100/10 dark:bg-ink-900 dark:text-paper-400">
        <h2 className="font-semibold text-ink-900 dark:text-paper-100">Dane i monitoring AI</h2>
        <p>
          Treść rozmów w asystencie jest przechowywana w aplikacji, żebyś mógł wrócić do historii i generować
          materiały. Wywołania modelów (prompty techniczne, odpowiedzi, koszt) są logowane do limitów miesięcznych
          i rozwiązywania problemów.
        </p>
        <p>
          Opcjonalnie administrator może włączyć <strong className="font-medium text-ink-800 dark:text-paper-200">Langfuse</strong> —
          wtedy wywołania z danej rozmowy są grupowane w jednej sesji (ID rozmowy) w zewnętrznym panelu
          observability. Nie sprzedajemy Twoich danych do reklam.
        </p>
      </section>
      <section className="max-w-xl space-y-4 rounded-xl border border-ink-800/15 bg-white p-4 dark:border-paper-100/10 dark:bg-ink-900">
        <div>
          <h2 className="font-semibold text-ink-900 dark:text-paper-100">Twoje dane</h2>
          <p className="mt-1 text-sm text-ink-600 dark:text-paper-400">
            Możesz pobrać archiwum konta wraz z rozmowami i plikami albo trwale usunąć konto. Szczegóły znajdziesz w{" "}
            <a className="text-accent underline" href="/privacy">Polityce prywatności</a>.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={privacyBusy !== null}
            onClick={() => void exportData()}
            className="rounded-md bg-accent px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {privacyBusy === "export" ? "Przygotowywanie…" : "Eksportuj moje dane"}
          </button>
          <button type="button" disabled={privacyBusy !== null} onClick={() => void clearData("conversations")} className="rounded-md border border-ink-800/20 px-3 py-2 text-sm disabled:opacity-50 dark:border-paper-100/20">
            {privacyBusy === "conversations" ? "Usuwanie…" : "Usuń wszystkie rozmowy"}
          </button>
          <button type="button" disabled={privacyBusy !== null} onClick={() => void clearData("materials")} className="rounded-md border border-ink-800/20 px-3 py-2 text-sm disabled:opacity-50 dark:border-paper-100/20">
            {privacyBusy === "materials" ? "Usuwanie…" : "Usuń wszystkie materiały"}
          </button>
          <button
            type="button"
            disabled={privacyBusy !== null}
            onClick={() => setDeleteOpen(true)}
            className="rounded-md border border-red-600/40 px-3 py-2 text-sm font-medium text-red-700 hover:bg-red-500/10 disabled:opacity-50 dark:text-red-400"
          >
            Usuń moje konto
          </button>
        </div>
      </section>

      {deleteOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink-950/60 p-4" role="dialog" aria-modal="true" aria-labelledby="delete-account-title">
          <div className="w-full max-w-md space-y-4 rounded-xl bg-white p-5 dark:bg-ink-900">
            <div>
              <h2 id="delete-account-title" className="text-lg font-semibold">Trwale usunąć konto?</h2>
              <p className="mt-2 text-sm text-ink-600 dark:text-paper-400">
                Usuniemy konto, rozmowy, projekty, przesłane pliki, wygenerowane materiały i indeks wyszukiwania. Operacji nie można cofnąć. Chronione kopie zapasowe wygasają zgodnie z polityką dostawcy.
              </p>
            </div>
            <label className="block text-sm">
              Wpisz <strong>USUŃ MOJE KONTO</strong>
              <input
                value={confirmation}
                onChange={(e) => setConfirmation(e.target.value)}
                className="mt-1 w-full rounded-md border border-ink-800/20 bg-paper-50 px-3 py-2 dark:border-paper-100/20 dark:bg-ink-950"
              />
            </label>
            <div className="flex justify-end gap-2">
              <button type="button" disabled={privacyBusy !== null} onClick={() => setDeleteOpen(false)} className="rounded-md px-3 py-2 text-sm">Anuluj</button>
              <button
                type="button"
                disabled={confirmation !== "USUŃ MOJE KONTO" || privacyBusy !== null}
                onClick={() => void deleteAccount()}
                className="rounded-md bg-red-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-40"
              >
                {privacyBusy === "delete" ? "Usuwanie…" : "Usuń konto bezpowrotnie"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
