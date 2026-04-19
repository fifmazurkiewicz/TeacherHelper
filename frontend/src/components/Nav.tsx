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
      .then((m) => setIsAdmin(m.role === "admin"))
      .catch(() => setIsAdmin(false));
  }, []);

  function logout() {
    setToken(null);
    navigate("/login");
  }

  const isAdminSection = pathname.startsWith("/admin");

  return (
    <header className="border-b border-ink-800/20 bg-white/80 backdrop-blur dark:bg-ink-900/80 dark:border-paper-100/10">
      <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-4 py-3">
        <span className="font-semibold text-accent">Teacher Helper</span>
        <nav className="flex flex-wrap items-center gap-1">
          {links.map(({ to, label }) => (
            <Link
              key={to}
              to={to}
              className={`rounded-md px-3 py-1.5 text-sm transition ${
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
                className={`rounded-md px-3 py-1.5 text-sm transition ${
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
          <ThemeToggle className="ml-1 rounded-md px-3 py-1.5 text-sm text-ink-600 hover:bg-paper-100 dark:text-paper-300 dark:hover:bg-ink-800" />
          <button
            type="button"
            onClick={logout}
            className="ml-2 rounded-md px-3 py-1.5 text-sm text-ink-600 hover:bg-paper-100 dark:text-paper-300 dark:hover:bg-ink-800"
          >
            Wyloguj
          </button>
        </nav>
      </div>
    </header>
  );
}
