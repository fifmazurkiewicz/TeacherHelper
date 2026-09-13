import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { PasswordField } from "@/components/PasswordField";
import { ThemeToggle } from "@/components/ThemeToggle";
import { api, setToken } from "@/lib/api";
import { isSupabaseConfigured, supabase } from "@/lib/supabase";

function GoogleGlyph() {
  return (
    <svg className="size-4" viewBox="0 0 24 24" aria-hidden>
      <path
        fill="currentColor"
        d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"
      />
      <path
        fill="currentColor"
        d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
      />
      <path
        fill="currentColor"
        d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
      />
      <path
        fill="currentColor"
        d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
      />
    </svg>
  );
}

export default function LoginPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [oauthLoading, setOauthLoading] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      if (isSupabaseConfigured && supabase) {
        const { error: authError } = await supabase.auth.signInWithPassword({ email, password });
        if (authError) throw authError;
        navigate("/assistant");
        return;
      }
      const data = await api<{ access_token: string }>("/v1/auth/login", {
        method: "POST",
        json: { email, password },
      });
      await setToken(data.access_token);
      navigate("/assistant");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Błąd logowania");
    } finally {
      setLoading(false);
    }
  }

  async function onGoogleLogin() {
    if (!supabase) return;
    setError(null);
    setOauthLoading(true);
    try {
      const { error: authError } = await supabase.auth.signInWithOAuth({ provider: "google" });
      if (authError) throw authError;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Błąd logowania Google");
      setOauthLoading(false);
    }
  }

  return (
    <div className="relative mx-auto flex min-h-screen max-w-md flex-col justify-center px-4 pb-8 pt-14">
      <div className="absolute right-4 top-4">
        <ThemeToggle />
      </div>
      <h1 className="mb-6 text-2xl font-bold text-ink-950 dark:text-paper-50">Logowanie</h1>
      <form onSubmit={onSubmit} className="flex flex-col gap-4 rounded-xl border border-ink-800/15 bg-white p-6 shadow-sm dark:border-paper-100/10 dark:bg-ink-900">
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
        <PasswordField
          label="Hasło"
          value={password}
          onChange={setPassword}
          required
          autoComplete="current-password"
        />
        {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
        <button
          type="submit"
          disabled={loading || oauthLoading}
          className="rounded-md bg-accent py-2 font-medium text-white hover:bg-accent-dim disabled:opacity-50"
        >
          {loading ? "…" : "Zaloguj"}
        </button>
        {isSupabaseConfigured && (
          <>
            <div className="relative py-1 text-center text-xs text-ink-500 dark:text-paper-400">
              <span className="bg-white px-2 dark:bg-ink-900">lub</span>
              <span className="absolute inset-x-0 top-1/2 -z-10 border-t border-ink-800/15 dark:border-paper-100/10" />
            </div>
            <button
              type="button"
              disabled={loading || oauthLoading}
              onClick={() => void onGoogleLogin()}
              className="inline-flex items-center justify-center gap-2 rounded-md border border-ink-800/20 bg-paper-50 py-2 font-medium text-ink-900 hover:bg-paper-100 disabled:opacity-50 dark:border-paper-100/20 dark:bg-ink-950 dark:text-paper-50 dark:hover:bg-ink-800"
            >
              <GoogleGlyph />
              {oauthLoading ? "Przekierowanie…" : "Kontynuuj z Google"}
            </button>
          </>
        )}
      </form>
      <p className="mt-3 text-center text-xs text-ink-500 dark:text-paper-400">
        <Link to="/privacy" className="text-accent underline">Polityka prywatności</Link>
      </p>
      <p className="mt-4 text-center text-sm text-ink-600 dark:text-paper-400">
        Nie masz konta?{" "}
        <Link to="/register" className="text-accent hover:underline">
          Rejestracja
        </Link>
      </p>
    </div>
  );
}
