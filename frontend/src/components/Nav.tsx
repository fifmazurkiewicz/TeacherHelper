import { Link, useLocation, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { api, setToken } from "@/lib/api";
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

  useEffect(() => {
    api<{ role: string }>("/v1/auth/me")
      .then((m: { role: string }) => setIsAdmin(m.role === "admin"))
      .catch(() => setIsAdmin(false));
  }, []);

  function logout() {
    setToken(null);
    navigate("/login");
  }

  const isAdminSection = pathname.startsWith("/admin");

  return (
    <header className="border-b border-ink-800/20 bg-white/80 backdrop-blur dark:bg-ink-900/80 dark:border-paper-100/10">
      <div className="mx-auto flex max-w-5xl items-center justify-between gap-2 px-3 py-2.5 sm:gap-4 sm:px-4 sm:py-3">
        <span className="shrink-0 text-sm font-semibold text-accent sm:text-base">Teacher Helper</span>
        <nav className="flex min-w-0 flex-1 flex-wrap items-center justify-end gap-0.5 sm:gap-1">
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
      </div>
    </header>
  );
}
