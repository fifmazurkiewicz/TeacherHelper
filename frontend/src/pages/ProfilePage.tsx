import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Me = { id: string; email: string; display_name: string | null; role: string };

export default function ProfilePage() {
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Me>("/v1/auth/me")
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
    </div>
  );
}
