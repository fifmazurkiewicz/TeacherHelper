import { Link, useLocation, useNavigate } from "react-router-dom";
import { useCallback, useEffect, useState } from "react";
import { api, setToken, type MonthlyLlmUsage } from "@/lib/api";
import { ThemeToggle } from "./ThemeToggle";

const links = [
  { to: "/assistant", label: "Asystent" },
  { to: "/materials", label: "Materiały" },
  { to: "/profile", label: "Profil" },
];

const adminLinks = [
  { to: "/admin/monitoring", label: "Monitoring" },
  { to: "/admin/users", label: "Użytkownicy" },
];

const USAGE_REFRESH_MS = 60_000;

export function Nav() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const [isAdmin, setIsAdmin] = useState(false);
  const [usage, setUsage] = useState<MonthlyLlmUsage | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);

  const refreshUsage = useCallback(() => {
    api<MonthlyLlmUsage>("/v1/auth/usage").then(setUsage).catch(() => setUsage(null));
  }, []);

  useEffect(() => {
    api<{ role: string }>("/v1/auth/me")
      .then((m: { role: string }) => setIsAdmin(m.role === "admin"))
      .catch(() => setIsAdmin(false));
  }, []);

  // Usage grows while the user chats, so keep the counter fresh without a full reload.
  useEffect(() => {
    refreshUsage();
    const poll = window.setInterval(refreshUsage, USAGE_REFRESH_MS);
    window.addEventListener("focus", refreshUsage);
    return () => {
      window.clearInterval(poll);
      window.removeEventListener("focus", refreshUsage);
    };
  }, [refreshUsage]);

  useEffect(() => {
    setMenuOpen(false);
    refreshUsage();
  }, [pathname, refreshUsage]);

  function logout() {
    void setToken(null).then(() => navigate("/login"));
  }

  const allLinks = isAdmin ? [...links, ...adminLinks] : links;
  const usageLabel = usage
    ? usage.effective_llm_monthly_cost_limit_usd === null
      ? `$${usage.llm_cost_month_usd.toFixed(2)} wydano`
      : `$${usage.llm_cost_month_usd.toFixed(2)} / $${usage.effective_llm_monthly_cost_limit_usd.toFixed(2)}`
    : null;

  return (
    <header className="relative z-30 shrink-0 border-b border-ink-800/15 bg-white/90 backdrop-blur dark:border-paper-100/10 dark:bg-ink-900/90">
      <div className="flex h-12 w-full items-center gap-2 px-3 sm:h-14 sm:gap-4 sm:px-4">
        <Link to="/assistant" className="shrink-0 text-sm font-semibold text-accent sm:text-base">
          Teacher Helper
        </Link>

        <nav className="hidden min-w-0 flex-1 items-center gap-1 overflow-x-auto md:flex [&::-webkit-scrollbar]:hidden">
          {allLinks.map(({ to, label }) => (
            <Link
              key={to}
              to={to}
              aria-current={pathname === to ? "page" : undefined}
              className={`shrink-0 whitespace-nowrap rounded-md px-3 py-1.5 text-sm transition ${
                pathname === to
                  ? "bg-accent/15 font-medium text-accent"
                  : "text-ink-700 hover:bg-paper-100 dark:text-paper-300 dark:hover:bg-ink-800"
              }`}
            >
              {label}
            </Link>
          ))}
        </nav>
        <div className="flex-1 md:hidden" />

        <div className="flex shrink-0 items-center gap-1 sm:gap-2">
          {usageLabel && (
            <Link
              to="/profile"
              className={`rounded-full px-2.5 py-1 text-xs font-semibold tabular-nums ${
                usage?.llm_monthly_limit_reached
                  ? "bg-red-500/10 text-red-700 dark:text-red-400"
                  : "bg-paper-100 text-ink-800 dark:bg-ink-800 dark:text-paper-200"
              }`}
              aria-label={`Miesięczny limit AI: ${usageLabel}`}
              title="Miesięczny limit AI (UTC)"
            >
              {usageLabel}
            </Link>
          )}
          <div className="hidden items-center gap-1 md:flex">
            <ThemeToggle className="rounded-md px-2 py-1.5 text-sm text-ink-600 hover:bg-paper-100 dark:text-paper-300 dark:hover:bg-ink-800" />
            <button
              type="button"
              onClick={logout}
              className="whitespace-nowrap rounded-md px-2 py-1.5 text-sm text-ink-600 hover:bg-paper-100 dark:text-paper-300 dark:hover:bg-ink-800"
            >
              Wyloguj
            </button>
          </div>

          <div className="relative md:hidden">
            <button
              type="button"
              onClick={() => setMenuOpen((o) => !o)}
              className="inline-flex size-10 items-center justify-center rounded-md text-ink-700 hover:bg-paper-100 dark:text-paper-200 dark:hover:bg-ink-800"
              aria-expanded={menuOpen}
              aria-haspopup="menu"
              aria-label="Menu aplikacji"
            >
              <IconMenu className="size-5" />
            </button>
            {menuOpen && (
              <>
                <button
                  type="button"
                  className="fixed inset-0 z-40 cursor-default bg-transparent"
                  aria-label="Zamknij menu"
                  onClick={() => setMenuOpen(false)}
                />
                <div
                  role="menu"
                  className="absolute right-0 top-full z-50 mt-1 w-56 rounded-xl border border-ink-800/15 bg-white py-1 shadow-lg dark:border-paper-100/10 dark:bg-ink-900"
                >
                  {allLinks.map(({ to, label }) => (
                    <Link
                      key={to}
                      role="menuitem"
                      to={to}
                      aria-current={pathname === to ? "page" : undefined}
                      className={`block px-4 py-3 text-sm hover:bg-paper-100 dark:hover:bg-ink-800 ${
                        pathname === to ? "font-medium text-accent" : "text-ink-800 dark:text-paper-100"
                      }`}
                    >
                      {label}
                    </Link>
                  ))}
                  <div className="my-1 border-t border-ink-800/10 dark:border-paper-100/10" />
                  <div className="px-2">
                    <ThemeToggle alwaysShowLabel className="w-full rounded-md px-2 py-2 text-left text-sm text-ink-600 hover:bg-paper-100 dark:text-paper-300 dark:hover:bg-ink-800" />
                  </div>
                  <button
                    role="menuitem"
                    type="button"
                    onClick={logout}
                    className="block w-full px-4 py-3 text-left text-sm text-ink-600 hover:bg-paper-100 dark:text-paper-300 dark:hover:bg-ink-800"
                  >
                    Wyloguj
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}

function IconMenu({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path d="M4 6h16M4 12h16M4 18h16" strokeLinecap="round" />
    </svg>
  );
}
