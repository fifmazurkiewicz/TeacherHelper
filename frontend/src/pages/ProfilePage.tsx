import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Me = { id: string; email: string; display_name: string | null; role: string };

export default function ProfilePage() {
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Me>("/v1/auth/me")
      .then(setMe)
      .catch((e) => setError(e instanceof Error ? e.message : "Błąd"));
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
            <dt className="text-xs uppercase text-ink-500">ID</dt>
            <dd className="break-all font-mono text-xs">{me.id}</dd>
          </div>
        </dl>
      )}
      <p className="max-w-xl text-sm text-ink-600 dark:text-paper-400">
        Administrator może zmieniać role innych użytkowników w zakładce{" "}
        <span className="font-medium">Użytkownicy</span>. Endpointy{" "}
        <code className="rounded bg-paper-100 px-1 dark:bg-ink-800">/v1/admin/*</code> wymagają roli admin oraz — gdy backend ma{" "}
        <code className="rounded bg-paper-100 px-1 dark:bg-ink-800">ADMIN_API_KEY</code> — tego samego klucza we frontendzie jako{" "}
        <code className="rounded bg-paper-100 px-1 dark:bg-ink-800">VITE_ADMIN_API_KEY</code> (nagłówek{" "}
        <code className="rounded bg-paper-100 px-1 dark:bg-ink-800">X-Admin-Key</code>).
      </p>
    </div>
  );
}
