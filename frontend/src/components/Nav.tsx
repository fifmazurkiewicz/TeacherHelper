import { Link, useLocation, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { api, setToken, type MonthlyLlmUsage } from "@/lib/api";
import { ThemeToggle } from "./ThemeToggle";

const links = [
  { to: "/assistant", label: "Asystent" },
  { to: "/materials", label: "Moje materiały" },
  { to: "/profile", label: "Profil" },
];

const adminLinks = [
  { to: "/admin/monitoring", label: "Monitoring" },
  { to: "/admin/users", label: "Użytkownicy" },
];

export function Nav() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const [isAdmin, setIsAdmin] = useState(false);
  const [usage, setUsage] = useState<MonthlyLlmUsage | null>(null);

  useEffect(() => {
    api<{ role: string }>("/v1/auth/me")
      .then((m: { role: string }) => setIsAdmin(m.role === "admin"))
      .catch(() => setIsAdmin(false));
    api<MonthlyLlmUsage>("/v1/auth/usage").then(setUsage).catch(() => setUsage(null));
  }, []);

  function logout() {
    void setToken(null).then(() => navigate("/login"));
  }

  const isAdminSection = pathname.startsWith("/admin");
  const usageLabel = usage
    ? usage.effective_llm_monthly_cost_limit_usd === null
      ? `$${usage.llm_cost_month_usd.toFixed(2)} wydano`
      : `$${usage.llm_cost_month_usd.toFixed(2)} / $${usage.effective_llm_monthly_cost_limit_usd.toFixed(2)}`
    : null;

  return (
    <header className="border-b border-ink-800/20 bg-white/80 backdrop-blur dark:bg-ink-900/80 dark:border-paper-100/10">
      <div
        className={`mx-auto flex w-full items-center gap-2 px-3 py-2.5 sm:gap-4 sm:px-4 sm:py-3 ${
          isAdminSection ? "max-w-7xl" : "max-w-5xl"
        }`}
      >
        <span className="shrink-0 text-sm font-semibold text-accent sm:text-base">Teacher Helper</span>
        <nav className="flex min-w-0 flex-1 flex-wrap items-center gap-0.5 sm:gap-1">
          {links.map(({ to, label }) => (
            <Link
              key={to}
              to={to}
              className={`rounded-md px-2 py-1 text-xs transition sm:px-3 sm:py-1.5 sm:text-sm ${
                pathname === to
                  ? "bg-accent text-white"
                  : "text-ink-800 hover:bg-paper-100 dark:text-paper-200 dark:hover:bg-ink-800"
              }`}
            >
              {label}
            </Link>
          ))}
          {isAdmin &&
            adminLinks.map(({ to, label }) => (
              <Link
                key={to}
                to={to}
                className={`rounded-md px-2 py-1 text-xs transition sm:px-3 sm:py-1.5 sm:text-sm ${
                  pathname === to
                    ? "bg-ink-800 text-white dark:bg-paper-200 dark:text-ink-950"
                    : isAdminSection
                      ? "text-ink-700 hover:bg-paper-100 dark:text-paper-300 dark:hover:bg-ink-800"
                      : "text-ink-800 hover:bg-paper-100 dark:text-paper-200 dark:hover:bg-ink-800"
                }`}
              >
                {label}
              </Link>
            ))}
          <ThemeToggle className="ml-0.5 rounded-md px-2 py-1 text-xs text-ink-600 hover:bg-paper-100 sm:ml-1 sm:px-3 sm:py-1.5 sm:text-sm dark:text-paper-300 dark:hover:bg-ink-800" />
          <button
            type="button"
            onClick={logout}
            className="ml-1 rounded-md px-2 py-1 text-xs text-ink-600 hover:bg-paper-100 sm:ml-2 sm:px-3 sm:py-1.5 sm:text-sm dark:text-paper-300 dark:hover:bg-ink-800"
          >
            Wyloguj
          </button>
        </nav>
        {usageLabel && (
          <span
            className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold tabular-nums ${
              usage?.llm_monthly_limit_reached
                ? "bg-red-500/10 text-red-700 dark:text-red-400"
                : "bg-paper-100 text-ink-800 dark:bg-ink-800 dark:text-paper-200"
            }`}
            aria-label={`Miesięczny limit AI: ${usageLabel}`}
            title="Miesięczny limit AI (UTC)"
          >
            {usageLabel}
          </span>
        )}
      </div>
    </header>
  );
}
