import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, setToken } from "@/lib/api";

export default function RegisterPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const data = await api<{ access_token: string }>("/v1/auth/register", {
        method: "POST",
        json: { email, password, display_name: displayName || undefined },
      });
      setToken(data.access_token);
      navigate("/assistant");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Błąd rejestracji");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-4">
      <h1 className="mb-6 text-2xl font-bold">Rejestracja</h1>
      <form onSubmit={onSubmit} className="flex flex-col gap-4 rounded-xl border border-ink-800/15 bg-white p-6 shadow-sm dark:border-paper-100/10 dark:bg-ink-900">
        <label className="flex flex-col gap-1 text-sm">
          Wyświetlana nazwa (opcjonalnie)
          <input
            type="text"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            className="rounded-md border border-ink-800/20 bg-paper-50 px-3 py-2 dark:border-paper-100/20 dark:bg-ink-950"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          E-mail
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="rounded-md border border-ink-800/20 bg-paper-50 px-3 py-2 dark:border-paper-100/20 dark:bg-ink-950"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Hasło
          <input
            type="password"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="rounded-md border border-ink-800/20 bg-paper-50 px-3 py-2 dark:border-paper-100/20 dark:bg-ink-950"
          />
        </label>
        {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
        <button
          type="submit"
          disabled={loading}
          className="rounded-md bg-accent py-2 font-medium text-white hover:bg-accent-dim disabled:opacity-50"
        >
          {loading ? "…" : "Utwórz konto"}
        </button>
      </form>
      <p className="mt-4 text-center text-sm text-ink-600 dark:text-paper-400">
        Masz konto?{" "}
        <Link to="/login" className="text-accent hover:underline">
          Zaloguj się
        </Link>
      </p>
    </div>
  );
}
