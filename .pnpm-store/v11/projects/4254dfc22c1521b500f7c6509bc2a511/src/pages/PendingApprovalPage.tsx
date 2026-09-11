import { useNavigate } from "react-router-dom";
import { setToken } from "@/lib/api";
import { ThemeToggle } from "@/components/ThemeToggle";

type Props = {
  checking?: boolean;
  onCheckStatus: () => void;
};

export default function PendingApprovalPage({ checking = false, onCheckStatus }: Props) {
  const navigate = useNavigate();

  function logout() {
    void setToken(null).then(() => navigate("/login"));
  }

  return (
    <div className="flex min-h-screen flex-col bg-paper-50 dark:bg-ink-950">
      <div className="flex justify-end px-3 py-2">
        <ThemeToggle />
      </div>
      <main className="flex flex-1 items-center justify-center px-4 pb-16">
        <div className="w-full max-w-md space-y-4 rounded-xl border border-ink-800/15 bg-white p-6 dark:border-paper-100/10 dark:bg-ink-900">
          <h1 className="text-xl font-semibold text-ink-900 dark:text-paper-100">
            Konto oczekuje na akceptację
          </h1>
          <p className="text-sm leading-relaxed text-ink-600 dark:text-paper-400">
            Administrator musi zaakceptować to konto, zanim będzie można korzystać z asystenta.
          </p>
          <div className="flex flex-col gap-2 sm:flex-row">
            <button
              type="button"
              onClick={onCheckStatus}
              disabled={checking}
              className="rounded-md bg-accent px-3 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-60"
            >
              {checking ? "Sprawdzanie…" : "Sprawdź status"}
            </button>
            <button
              type="button"
              onClick={logout}
              className="rounded-md px-3 py-2 text-sm text-ink-700 hover:bg-paper-100 dark:text-paper-300 dark:hover:bg-ink-800"
            >
              Wyloguj
            </button>
          </div>
        </div>
      </main>
    </div>
  );
}
